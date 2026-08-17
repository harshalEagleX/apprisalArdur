"""
extraction.vision.provider (vpr-1.0.0) — the VLM behind UAD 3.6 transcription.

An interface, not a hardcoded vendor. Two reasons that is worth the indirection
here specifically:

  1. The model is a **runtime setting, not a code constant.** Provider, model,
     DPI and the per-order dollar cap are all config today and belong in the
     frontend tomorrow — "no config setting in the python side" is the standing
     requirement, and an interface is what makes swapping the backend a settings
     change rather than an edit.
  2. Nobody has yet measured either model's field-level precision on a 4-column
     3.6 sales grid. That is THE open question in this design, and it is settled
     by running both against the same pages — which requires them to be
     interchangeable.

Together stays the judge regardless of what is configured here (see
app/llm/client.py). This provider transcribes pixels; it never judges.
"""

from __future__ import annotations

import itertools
import json
import logging
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.extraction.vision.render import RenderedPage

__version__ = "vpr-1.0.0"

logger = logging.getLogger(__name__)

# Transient HTTP statuses worth retrying: rate limit, server errors, gateway.
_RETRY_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
_MAX_HTTP_ATTEMPTS = 3
_BACKOFF_BASE_S = 1.5

# A read timeout is NOT the same kind of failure as a 5xx and must not be
# retried like one. A 5xx means the request was rejected and nothing is running;
# a read timeout means it was ACCEPTED and the model is already generating, so
# re-posting starts a second generation from scratch AND re-uploads every page
# image. Run 14 spent 546 seconds — the single longest item in the whole order —
# discovering that on one comparable: three consecutive 180s timeouts, ~1.5 MB
# re-uploaded each time, nothing returned.
#
# ONE attempt, not two. The second is pure loss and the log above says why: the
# model is still generating, so re-posting abandons that work, re-uploads every
# image, and starts over against the same clock. It therefore costs a failing
# call EXACTLY DOUBLE its read timeout — reconstructed across run 25/26, five of
# five unclamped give-ups landed at 2x their timeout plus 4-8s of reconnect.
#
# Giving up after one attempt also feeds the split path sooner, and splitting is
# what actually recovers the fields; the retry never did.
_MAX_TIMEOUT_ATTEMPTS = 1

# Output decode rate, MEASURED AT RUNTIME rather than assumed.
#
# The "25 tok/s floor" was never a property of the model or of Together — it was
# self-inflicted. A key serves roughly 101 tok/s in total, so N calls in flight
# on one key each see ~101/N. At 23 calls over 4 keys that is 101/5.75 ≈ 17-25
# tok/s, which is exactly the floor that got baked in as if it were physics.
#
# Freezing it as a constant then poisoned the timeout: 25 tok/s x 180s implies a
# 4,500-token hard ceiling, so every section legitimately needing 5,600-6,500
# tokens timed out WHILE GENERATING CORRECTLY. Measuring instead means the
# timeout tracks the concurrency actually in effect.
_RATE_PER_KEY_TPS = 101.0
# Until enough calls have completed to measure, assume the rate implied by the
# configured concurrency rather than a pessimistic constant.
_MIN_SAMPLES_FOR_RATE = 3
_REQUEST_OVERHEAD_S = 20.0
# Sized so a call that is generating correctly is never cut off: the ceiling is
# the most it can emit, and 1.5x covers queueing and a slow start.
_TIMEOUT_SAFETY = 1.5

# `json_object` + the schema restated in the prompt is the DEFAULT, and strict
# `json_schema` is opt-in. That is the opposite of what it looks like it should
# be, so the measurement is recorded here.
#
# The history matters. gemma-4-31B-it used to reject `json_schema` with a hard
# 400, so every call posted twice — once to be refused, once to succeed — which
# doubled this order's image payload from 4.0 MB to 8.0 MB. Together has since
# STARTED accepting it, and that silently turned a fast failure into a slow
# success: measured back-to-back on the real 24-field `assignment` schema with
# the same page image,
#
#     json_object + schema in prompt   39.8s   2,866 output tokens   24/24 fields
#     json_schema (strict)            107.7s   3,813 output tokens   24/24 fields
#
# 2.7x the wall clock and 33% more output tokens for an identical result —
# constrained decoding against a 12,472-character grammar is expensive. On a
# 23-call order that is the difference between finishing and timing out; it took
# a full run to 4 fields.
#
# The guarantee `json_schema` buys is shape, and shape is already checked when
# the response is parsed. Latency is the binding constraint here, so it loses.
_FORMAT_JSON_OBJECT = "json_object"
_FORMAT_JSON_SCHEMA = "json_schema"

# Per-model memory of a REFUSED format, so a model that rejects the configured
# one falls back once per process rather than once per call. A race between two
# threads costs one extra probe and then settles; a lock would serialise every
# call to guard a boolean write CPython already performs atomically.
_FORMAT_REFUSED: Dict[str, bool] = {}

# max_tokens values already warned about, so an incoherent ceiling is reported
# once rather than once per call.
_CEILING_WARNED: set = set()


# The transcription contract. Every rule here was earned from a specific observed
# failure in the 2026-08-03 audit of this document — they are not general advice.
# DELIBERATELY SHORT.
#
# The first version of this prompt was eight numbered paragraphs of rules. On a
# REASONING model that was actively harmful: the model spent its entire token
# budget deliberating about the rules inside its `reasoning` field, hit
# max_tokens, and returned an EMPTY `content` — a 105-second average latency and
# a 100% failure rate, with no error to explain it. The same model, given a
# short prompt, read the page correctly in 3.3 seconds.
#
# So the rules are compressed to the ones that change behaviour, phrased as
# instructions rather than as a rationale to think about. Length here is not
# free; it is paid for in reasoning tokens on every call.
SYSTEM_PROMPT = """You transcribe appraisal report pages into JSON. Transcribe only; never judge.

Rules:
1. Copy values exactly as printed. Do not normalize, correct, or complete them.
2. Not visible on this image? Emit null. Never guess. A null is correct; a guess is a defect.
3. Match each value to its own printed label. Never take a value from a neighbouring field, header, or footer.
4. Checkboxes: name the option actually marked, else null.
5. In tables, identify rows by their row LABEL, not by band headers.
6. Keep accounting parentheses on negatives: $(12,000) stays $(12,000).

Answer with the JSON object only."""


def _strip_code_fence(text: str) -> str:
    """Unwrap ```json ... ``` fencing. Needed on the json_object fallback path,
    where the model is asked for JSON in prose rather than schema-constrained —
    several models wrap it in markdown and a bare json.loads then fails on a
    response that was otherwise perfectly correct."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    s = s.split("\n", 1)[-1] if "\n" in s else s
    if s.rstrip().endswith("```"):
        s = s.rstrip()[:-3]
    return s.strip()


@dataclass
class VisionResponse:
    """One transcription call's result."""

    data: Dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    # Wall-clock window of the HTTP call, for the run's timeline. Measured in
    # the provider so it covers retries and backoff too — the caller only sees
    # one call, but the clock may have paid for three.
    started_at: float = 0.0
    ended_at: float = 0.0
    truncated: bool = False
    refused: bool = False
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.refused


class VisionProvider(ABC):
    """Transcribe images against a JSON schema."""

    name: str = "abstract"

    @abstractmethod
    def transcribe(self, images: List[RenderedPage], instruction: str,
                   schema: Dict[str, Any], *, max_tokens: int = 4000,
                   effort: str = "low") -> VisionResponse:
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        ...


# ── JSON-schema sanitising ────────────────────────────────────────────────────

# Structured outputs reject these; they are silently dropped rather than passed
# through, so a schema authored in YAML (eventually: authored in the FRONTEND by
# someone who has never read the API docs) cannot 400 an entire order. Numeric
# and length constraints belong in verify.py anyway, where a violation produces
# a re-extract instead of a hard failure.
_UNSUPPORTED_KEYWORDS = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "minItems", "maxItems", "uniqueItems",
    "minProperties", "maxProperties", "pattern", "default", "examples",
)


def sanitize_schema(node: Any) -> Any:
    """Make a hand/UI-authored JSON schema acceptable to structured outputs.

    Enforces the two hard requirements — every object carries
    `additionalProperties: false`, and every declared property is listed in
    `required` — and strips the keywords the API rejects. Nullability is how
    optionality is expressed instead: a field the model may not find is typed
    `["string", "null"]`, which is also what makes rule 2 (abstention) a legal
    answer rather than a schema violation.
    """
    if isinstance(node, list):
        return [sanitize_schema(x) for x in node]  # noqa: RET504
    if not isinstance(node, dict):
        return node

    out: Dict[str, Any] = {
        k: sanitize_schema(v) for k, v in node.items()
        if k not in _UNSUPPORTED_KEYWORDS
    }
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
        props = out.get("properties") or {}
        out["required"] = list(props.keys())
    return out


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicVisionProvider(VisionProvider):
    """Claude vision. Default `claude-sonnet-5`.

    Three parameter choices worth stating, because each is a place where a
    reasonable-looking alternative returns a 400 or silently costs money:

      * **No `temperature`.** Sonnet 5 rejects non-default sampling parameters
        outright. Determinism comes from the JSON schema constraining the output
        shape, a literal prompt, and `effort` — not from temperature=0, which
        never guaranteed identical output on any model anyway.
      * **Adaptive thinking, low effort.** Thinking is ON BY DEFAULT on Sonnet 5
        (a change from 4.6, where omitting the field meant no thinking).
        Transcription is not a reasoning task, so effort is held low; but
        thinking is left adaptive rather than disabled because disabling it is
        the documented cause of malformed-output failure modes.
      * **`max_tokens` sized with headroom.** It caps thinking PLUS response
        together. A budget tuned to the JSON alone truncates mid-grid, and a
        truncated JSON is a parse failure, not a partial read.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-5",
                 timeout_s: float = 180.0):
        self._model = model
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "the `anthropic` package is required for UAD 3.6 vision "
                "extraction — pip install anthropic") from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)

    @property
    def model(self) -> str:
        return self._model

    def transcribe(self, images: List[RenderedPage], instruction: str,
                   schema: Dict[str, Any], *, max_tokens: int = 4000,
                   effort: str = "low") -> VisionResponse:
        content: List[Dict[str, Any]] = [
            {"type": "image",
             "source": {"type": "base64", "media_type": img.media_type, "data": img.b64}}
            for img in images
        ]
        content.append({"type": "text", "text": instruction})

        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=[{
                    "type": "text", "text": SYSTEM_PROMPT,
                    # Below Sonnet 5's 1024-token minimum this is a no-op rather
                    # than an error, and images dominate input regardless — so
                    # the realistic saving is modest. Marked anyway because the
                    # prompt is byte-stable across every call in a run.
                    "cache_control": {"type": "ephemeral"},
                }],
                thinking={"type": "adaptive"},
                output_config={
                    "format": {"type": "json_schema", "schema": sanitize_schema(schema)},
                    "effort": effort,
                },
                messages=[{"role": "user", "content": content}],
            )
        except self._anthropic.RateLimitError as exc:
            return VisionResponse(data={}, error=f"rate_limited: {exc}")
        except self._anthropic.APIStatusError as exc:
            return VisionResponse(data={}, error=f"api_error_{exc.status_code}: {exc}")
        except self._anthropic.APIConnectionError as exc:
            return VisionResponse(data={}, error=f"connection: {exc}")
        except Exception as exc:  # pragma: no cover - defensive
            return VisionResponse(data={}, error=f"unexpected: {exc}")

        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0

        # Safety classifiers can decline; that arrives as a 200 with
        # stop_reason="refusal" and possibly EMPTY content. Reading content[0]
        # without checking is the documented way this crashes.
        if getattr(resp, "stop_reason", None) == "refusal":
            return VisionResponse(data={}, input_tokens=in_tok, output_tokens=out_tok,
                                  model=self._model, refused=True,
                                  error="model declined to transcribe this page")

        truncated = getattr(resp, "stop_reason", None) == "max_tokens"
        text = "".join(b.text for b in (resp.content or [])
                       if getattr(b, "type", None) == "text")
        if not text.strip():
            return VisionResponse(data={}, input_tokens=in_tok, output_tokens=out_tok,
                                  model=self._model, truncated=truncated,
                                  error="empty response" + (" (truncated)" if truncated else ""))
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return VisionResponse(
                data={}, input_tokens=in_tok, output_tokens=out_tok, model=self._model,
                truncated=truncated,
                error=(f"unparseable JSON{' — response was truncated, raise max_tokens' if truncated else ''}: {exc}"))

        return VisionResponse(data=data, input_tokens=in_tok, output_tokens=out_tok,
                              model=self._model, truncated=truncated)


# ── Together (alternate backend) ──────────────────────────────────────────────

class TogetherVisionProvider(VisionProvider):
    """Serverless multimodal models over Together's OpenAI-compatible endpoint.

    **Serverless only, deliberately.** Together's Qwen3-VL line (8B, 32B, 235B)
    is the obvious-looking choice and is DEDICATED-ONLY: running one means
    provisioning a GPU endpoint billed per hour whether or not any order is
    processed. That is the wrong economics until volume is sustained and high,
    so this backend is restricted to models that are callable per-token. The
    dedicated VL endpoint stays available as a growth lever; it is not a default.

    Watch two traps in the catalogue: several priced (= serverless) Qwen models
    are TEXT-ONLY (Qwen3.7 Max, Qwen2.5 7B Turbo) and the "Qwen Image" family
    GENERATES images from text — the opposite direction from what this does.
    Only text+image-INPUT models belong in the tier map below.

    Structural caveat vs the Anthropic backend: Together's image handling caps
    near a 2x2 tile grid (~1120px), so a full-page 4-column sales grid arrives
    at roughly 280px per column. Whether that is legible is UNMEASURED. The
    mitigation is already built — render.label_and_column_clips() crops one
    comparable at a time — and this backend should always use it for the grid.
    """

    name = "together"

    # Tiered routing: cheap model for label/value sections, stronger multimodal
    # for the dense grid, and a DIFFERENT-FAMILY model for the checksum-failure
    # retry so an escalation is an uncorrelated second opinion rather than the
    # same model failing the same way twice.
    # Default: one model for every tier — `google/gemma-4-31B-it`, the chosen
    # backend. Uniform rather than tiered on purpose: it is the model whose
    # serverless availability, Text+Image input and JSON Mode were confirmed
    # against the account's own catalogue, and mixing in models whose image
    # support has NOT been confirmed would trade a verified path for an
    # unverified one to save fractions of a cent on an order that is already an
    # order of magnitude under budget.
    #
    # Checksum-failure escalation therefore runs on DPI (150 -> 200) and a
    # re-prompt carrying the arithmetic error, both of which are mechanisms
    # rather than model bets. Cross-family escalation stays available — set
    # VISION_MODEL_ESCALATE to a different family for an uncorrelated second
    # opinion — but is not the default until that model is verified.
    DEFAULT_TIERS = {
        "section": "google/gemma-4-31B-it",
        "grid": "google/gemma-4-31B-it",
        "escalate": "google/gemma-4-31B-it",
    }

    def __init__(self, api_keys, model: Optional[str] = None,
                 tiers: Optional[Dict[str, str]] = None, timeout_s: float = 180.0,
                 call_budget_s: float = 300.0,
                 response_format: str = _FORMAT_JSON_OBJECT,
                 max_in_flight: int = 0):
        # See the _FORMAT_* note above: json_object is the default because strict
        # schema decoding measured 2.7x slower on the same schema and image, for
        # an identical result.
        self._response_format = response_format
        self._tiers = {**self.DEFAULT_TIERS, **(tiers or {})}
        self._model = model or self._tiers["grid"]
        # Round-robin across every configured key. Together's limits are PER KEY,
        # so N keys is N times the throughput with no added 429 risk — unlike
        # raising in-flight requests on ONE key, which just contends for the same
        # budget and produces the retry storms that make a run slower AND lossier.
        # This is what lets vision concurrency go wide enough to overlap ~19 calls.
        keys = [api_keys] if isinstance(api_keys, str) else [k for k in (api_keys or []) if k]
        self._keys = keys or [""]
        self._key_turn = itertools.count()
        self._timeout = timeout_s
        # Rolling record of (output_tokens, seconds) for completed calls, used to
        # size the next call's timeout from what this account is ACTUALLY
        # delivering under the concurrency in force right now.
        self._rate_samples: List[float] = []
        self._rate_lock = threading.Lock()
        self._in_flight = 0
        # Hard wall-clock ceiling for ONE logical call including every retry and
        # backoff. Without it the retry policy is unbounded in time: three
        # 180s timeouts plus backoff is 546s spent on a single comparable, which
        # is what set run 14's entire 555s wall clock. The run finishes when its
        # slowest call finishes, so this bound IS the latency control.
        self._call_budget = call_budget_s
        # GLOBAL admission control. The caller's `concurrency` is handed to the
        # section pool AND the grid pool, which run at the same time, so the
        # configured limit was silently applied twice: run 19 asked for 2
        # calls/key and measured `peak_in_flight: 16` across 4 keys — 4 per key.
        # Past ~2 per key a key's fixed throughput is split so thin that calls
        # stop completing and start timing out; nine of that run's twelve grid
        # calls died that way.
        #
        # A pool-side limit cannot express this, because neither pool can see the
        # other. The provider is the only object both share, so the invariant
        # lives here. Zero disables the gate.
        self._admission = threading.BoundedSemaphore(max_in_flight) if max_in_flight else None

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def _next_key(self) -> str:
        return self._keys[next(self._key_turn) % len(self._keys)]

    def _current_rate(self) -> float:
        """Output tokens/sec a single call can expect right now.

        Measured once enough calls have finished; until then, predicted from the
        concurrency in force — a key serves ~101 tok/s in total, shared by the
        calls on it, so N calls per key each see roughly 101/N. Predicting beats
        assuming a worst case: a pessimistic constant produces timeouts short
        enough to kill healthy calls, which is the failure this replaces.
        """
        with self._rate_lock:
            samples = list(self._rate_samples)
            in_flight = max(self._in_flight, 1)
        if len(samples) >= _MIN_SAMPLES_FOR_RATE:
            # Median, not mean: one stalled call should not drag every
            # subsequent timeout upward.
            samples.sort()
            return max(samples[len(samples) // 2], 5.0)
        per_key = in_flight / max(len(self._keys), 1)
        return max(_RATE_PER_KEY_TPS / max(per_key, 1.0), 5.0)

    def _record_rate(self, output_tokens: int, seconds: float) -> None:
        if output_tokens <= 0 or seconds <= 0.5:
            return
        with self._rate_lock:
            self._rate_samples.append(output_tokens / seconds)
            # Keep it recent: concurrency changes between passes, and a rate
            # measured during the wide grid pass should not size timeouts during
            # a narrow one.
            if len(self._rate_samples) > 24:
                self._rate_samples.pop(0)

    @property
    def model(self) -> str:
        return self._model

    def for_tier(self, tier: str) -> str:
        """Model string for 'section' | 'grid' | 'escalate'."""
        return self._tiers.get(tier, self._model)

    def transcribe(self, images: List[RenderedPage], instruction: str,
                   schema: Dict[str, Any], *, max_tokens: int = 4000,
                   effort: str = "low", tier: Optional[str] = None,
                   budget_s: Optional[float] = None) -> VisionResponse:
        """Queue behind the global admission gate, then transcribe.

        Waiting here is not lost time. A call admitted past the point where each
        key is serving more than ~2 requests does not run slower and still
        finish — it runs slower and TIMES OUT, returning nothing for the full
        wait. Queuing converts that into a completion that arrives later.
        """
        if self._admission is None:
            return self._transcribe(images, instruction, schema,
                                    max_tokens=max_tokens, effort=effort, tier=tier,
                                    budget_s=budget_s)
        with self._admission:
            return self._transcribe(images, instruction, schema,
                                    max_tokens=max_tokens, effort=effort, tier=tier,
                                    budget_s=budget_s)

    def _transcribe(self, images: List[RenderedPage], instruction: str,
                    schema: Dict[str, Any], *, max_tokens: int = 4000,
                    effort: str = "low", tier: Optional[str] = None,
                    budget_s: Optional[float] = None) -> VisionResponse:
        import requests

        model = self.for_tier(tier) if tier else self._model

        content: List[Dict[str, Any]] = [
            {"type": "image_url",
             "image_url": {"url": f"data:{img.media_type};base64,{img.b64}"}}
            for img in images
        ]
        content.append({"type": "text", "text": instruction})
        clean = sanitize_schema(schema)

        # Size the read timeout from the ceiling AND the rate this account is
        # actually delivering right now. A timeout below what `max_tokens` can
        # generate is not a safety net — it is a guaranteed failure that costs
        # the full wait and returns nothing, and it fires on exactly the calls
        # doing the most work. Run 18 lost its two longest sections that way.
        rate = self._current_rate()
        attempt_timeout = max(
            30.0, _REQUEST_OVERHEAD_S + (max_tokens / rate) * _TIMEOUT_SAFETY)
        if attempt_timeout > self._timeout and max_tokens not in _CEILING_WARNED:
            _CEILING_WARNED.add(max_tokens)
            logger.info(
                "vision(together): %d-token ceiling at the measured %.0f tok/s "
                "needs ~%.0fs; allowing it rather than cutting off a call that is "
                "generating correctly", max_tokens, rate, attempt_timeout)

        def _post(response_format: Dict[str, Any], extra_text: str = "") -> Any:
            """POST with backoff on transient failures, under a wall-clock budget.

            **Retrying 5xx and 429 is not optional here.** Measured on a real
            run: 5 of 13 calls came back 500/503 from the serverless endpoint,
            and with no retry each one permanently lost an entire section or
            comparable — a third of the order gone to a fault that clears in a
            second. Concurrency makes these MORE likely, not less, so the two
            changes belong together.

            **A read timeout is retried differently, and the whole thing is
            bounded in time.** See `_MAX_TIMEOUT_ATTEMPTS` and `_call_budget`:
            an unbounded retry policy turned one slow comparable into 546s of
            wall clock, which is worse than the failure it was insuring against.
            """
            msgs = [{"role": "system", "content": SYSTEM_PROMPT + extra_text},
                    {"role": "user", "content": content}]
            body = {"model": model, "max_tokens": max_tokens,
                    # Together accepts sampling params (unlike Sonnet 5, where a
                    # non-default temperature is a hard 400). Zero is the right
                    # setting for transcription.
                    "temperature": 0,
                    "response_format": response_format, "messages": msgs}
            # The CALLER's remaining time wins when it is tighter. Without this
            # the two budgets do not know about each other: a section deadline
            # gates ENTRY to a call, but the call then runs the provider's own
            # 300s allowance, so a call admitted one second before a 240s section
            # deadline still ran to 539s. Run 22 measured exactly that — slowest
            # call 301.2s inside a 240s deadline, total 530.4s.
            budget = min(self._call_budget, budget_s) if budget_s else self._call_budget
            deadline = time.monotonic() + budget
            last = None
            resp = None
            timeouts = 0
            for attempt in range(_MAX_HTTP_ATTEMPTS):
                remaining = deadline - time.monotonic()
                # NEVER dispatch a call whose timeout would be shorter than the
                # work needs. `timeout=min(attempt_timeout, remaining)` looks
                # prudent and is a doom loop: as a section's budget runs down,
                # remaining shrinks, so each call gets a TIGHTER deadline exactly
                # when the model is slowest, times out, is counted as truncation,
                # splits, and hands its halves even less. Run 27 issued its last
                # five calls with 43s timeouts — the shortest in the run — and
                # all five failed, ending at 170 fields against 291.
                #
                # A call that cannot be given the time it needs is not "worth
                # trying anyway": it burns a slot, re-uploads the images, and
                # returns nothing. Abandoning it honestly leaves the budget for
                # calls that can still finish.
                if remaining < min(attempt_timeout, 30.0):
                    logger.info("vision(together): %s — %.0fs left but this call "
                                "needs ~%.0fs; abandoning rather than dispatching "
                                "it pre-doomed", model, max(remaining, 0.0),
                                attempt_timeout)
                    break
                try:
                    resp = requests.post(
                        "https://api.together.xyz/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self._next_key()}"},
                        json=body, timeout=min(attempt_timeout, remaining))
                except requests.Timeout as exc:
                    last, resp = exc, None
                    timeouts += 1
                    if timeouts >= _MAX_TIMEOUT_ATTEMPTS:
                        logger.info("vision(together): %s — %d read timeout(s); the "
                                    "model is generating but slower than the %.0fs "
                                    "timeout, so re-posting only re-uploads the "
                                    "images. Giving up on this call.",
                                    model, timeouts, attempt_timeout)
                        break
                except requests.RequestException as exc:
                    last, resp = exc, None
                if resp is not None and resp.status_code not in _RETRY_STATUS:
                    return resp
                if attempt < _MAX_HTTP_ATTEMPTS - 1:
                    # Jittered backoff: a synchronised retry from every worker
                    # in the pool would recreate the overload that caused the
                    # 5xx in the first place.
                    delay = _BACKOFF_BASE_S * (2 ** attempt) * (0.6 + random.random() * 0.8)
                    if time.monotonic() + delay >= deadline:
                        break
                    status = resp.status_code if resp is not None else "conn"
                    logger.info("vision(together): %s on %s — retry %d/%d in %.1fs",
                                status, model, attempt + 1, _MAX_HTTP_ATTEMPTS - 1, delay)
                    time.sleep(delay)
            if resp is not None:
                return resp
            raise last if last else RuntimeError("request failed")

        # ONE request in the normal case: the configured format is sent directly,
        # with no capability probe. A probe re-uploads every page image just to
        # learn something fixed about the model, which is how the payload used to
        # double.
        schema_in_prompt = ("\n\nReturn ONLY a JSON object matching this schema "
                            "exactly, with every key present:\n" + json.dumps(clean))
        want_schema = (self._response_format == _FORMAT_JSON_SCHEMA
                       and not _FORMAT_REFUSED.get(model))
        started = time.monotonic()
        with self._rate_lock:
            self._in_flight += 1
        try:
            if want_schema:
                r = _post({"type": "json_schema", "schema": clean})
                if r.status_code == 400:
                    _FORMAT_REFUSED[model] = True
                    logger.info("vision(together): %s rejected json_schema — falling "
                                "back to json_object + in-prompt schema (remembered, "
                                "so later calls skip the probe and its upload)", model)
                    r = _post({"type": "json_object"}, schema_in_prompt)
            else:
                r = _post({"type": "json_object"}, schema_in_prompt)
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            return VisionResponse(data={}, model=model, started_at=started,
                                  ended_at=time.monotonic(),
                                  error=f"together: {exc}")
        finally:
            with self._rate_lock:
                self._in_flight = max(self._in_flight - 1, 0)
        ended = time.monotonic()

        usage = body.get("usage") or {}
        in_tok = usage.get("prompt_tokens", 0) or 0
        out_tok = usage.get("completion_tokens", 0) or 0
        # Feed the observed throughput back so the NEXT call's timeout reflects
        # what this account is delivering under the concurrency in force.
        self._record_rate(out_tok, ended - started)
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        truncated = choice.get("finish_reason") == "length"

        if not text.strip():
            # A REASONING model spends tokens in `reasoning` before writing
            # `content`. Truncated mid-reasoning means content is empty and the
            # whole call is wasted — the single most expensive failure mode
            # here, because it costs full latency and full output tokens for
            # nothing. Say so explicitly: "empty response" alone sent an earlier
            # debugging pass looking at the image pipeline instead of at
            # max_tokens, which is where the fault actually was.
            reasoning = str(message.get("reasoning") or "")
            hint = ""
            if truncated and reasoning:
                hint = (f" — the model exhausted max_tokens inside its reasoning "
                        f"field ({len(reasoning)} chars) and never emitted content; "
                        f"raise max_tokens or shorten the prompt/schema")
            elif truncated:
                hint = " — truncated; raise max_tokens"
            return VisionResponse(data={}, model=model, input_tokens=in_tok,
                                  output_tokens=out_tok, truncated=truncated,
                                  started_at=started, ended_at=ended,
                                  error="empty response" + hint)
        try:
            data = json.loads(_strip_code_fence(text))
        except json.JSONDecodeError as exc:
            return VisionResponse(
                data={}, model=model, input_tokens=in_tok, output_tokens=out_tok,
                truncated=truncated, started_at=started, ended_at=ended,
                error=(f"unparseable JSON{' — response was truncated, raise max_tokens' if truncated else ''}: {exc}"))
        return VisionResponse(data=data, model=model, input_tokens=in_tok,
                              output_tokens=out_tok, truncated=truncated,
                              started_at=started, ended_at=ended)


def get_vision_provider() -> Optional[VisionProvider]:
    """Build the configured provider, or None when vision is not configured.

    Model/provider come from runtime_config (what the frontend writes), falling
    back to the environment. CREDENTIALS never do — an API key is read from the
    environment only, so nothing that can be set from a browser can redirect
    this service's traffic or exfiltrate a key.

    None is a legitimate return, not an error: it makes the 3.6 path degrade
    loudly (a recorded gap plus REVIEW cards) instead of returning an empty
    field set that is indistinguishable from a clean extraction.
    """
    from app import runtime_config as rc
    from app.config import settings

    provider = rc.get("vision_provider", settings.vision_provider)

    if provider == "anthropic" and not settings.anthropic_api_key:
        logger.warning("vision: provider 'anthropic' selected but ANTHROPIC_API_KEY "
                       "is unset — UAD 3.6 extraction will degrade to REVIEW cards")
        return None
    # EVERY key, vision's own first. Limits are per key, so the pool is the
    # throughput lever — with the dedicated TOGETHER_API_GEMMA key leading so it
    # takes the first (and, at low call counts, most) of the traffic rather than
    # contending with the judge.
    together_keys = [k for k in
                     ([settings.together_vision_api_key] + list(settings.together_keys)) if k]
    # De-duplicate while preserving order: the same key twice would double its
    # share of the round-robin and silently halve the intended spread.
    seen = set()
    together_keys = [k for k in together_keys if not (k in seen or seen.add(k))]
    if provider == "together" and not together_keys:
        logger.warning("vision: provider 'together' selected but neither "
                       "TOGETHER_API_GEMMA nor TOGETHER_API_KEY_1..8 is set "
                       "— UAD 3.6 extraction will degrade to REVIEW cards")
        return None

    try:
        if provider == "anthropic":
            return AnthropicVisionProvider(
                settings.anthropic_api_key, rc.get("vision_model", settings.vision_model))
        if provider == "together":
            return TogetherVisionProvider(
                together_keys,
                rc.get("vision_model", settings.vision_model),
                tiers={
                    "section": rc.get("vision_model_section", settings.vision_model_section),
                    "grid": rc.get("vision_model_grid", settings.vision_model_grid),
                    "escalate": rc.get("vision_model_escalate", settings.vision_model_escalate),
                },
                # Derived from the key pool, exactly like the caller's pool size —
                # but enforced ONCE, globally, so the section and grid pools
                # cannot each spend the whole allowance (run 19: asked for 8,
                # measured 16 in flight, nine grid calls lost to timeouts).
                # min() with the absolute cap, or the cap is unreachable: the
                # per-key figure alone put 16-23 calls in flight on a 12-key pool
                # and MEASURED THROUGHPUT FELL — 301 tok/s at 8 in flight, 193 at
                # 16, 157 at 23, with 10-13 connection errors per run. This
                # account is throttled globally, not per key, so the pool is not
                # a linear throughput lever and the absolute cap has to bind.
                max_in_flight=max(1, min(
                    len(together_keys) * int(rc.get(
                        "vision_calls_per_key", settings.vision_calls_per_key)),
                    int(rc.get("vision_concurrency", settings.vision_concurrency)))),
            )
    except Exception as exc:
        logger.warning("vision: provider init failed: %s", exc)
        return None

    logger.warning("vision: unknown provider '%s'", provider)
    return None
