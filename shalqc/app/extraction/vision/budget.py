"""
extraction.vision.budget (bgt-1.0.0) — a hard per-order spend ceiling.

Vision extraction is the first component in this service whose cost scales with
the SIZE OF THE INPUT DOCUMENT rather than the number of checklist items. A
40-page report costs five times a 1004, a 120-page one with addenda costs
fifteen — and nothing upstream stops a pathological file from being fed in. So
the ceiling is enforced here, per order, in dollars.

Two properties make it trustworthy rather than decorative:

  1. **It refuses BEFORE spending.** `check()` prices the next call from the
     image dimensions (which are known before rendering) and raises if it would
     breach. A governor that notices the overrun afterwards has not governed
     anything.
  2. **Breaching degrades, it does not crash.** The caller catches
     BudgetExceeded, stops extracting, and the affected regions become REVIEW
     cards with a stated reason. A partially-extracted order is a reviewer's
     problem; a silently-truncated one is a false-negative machine.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__version__ = "bgt-1.0.0"

logger = logging.getLogger(__name__)


# USD per million tokens, (input, output). Sonnet 5 carries introductory pricing
# through 2026-08-31 ($2/$10); the STANDARD rate is used here deliberately so a
# budget set today does not quietly breach the day the intro period ends.
_PRICING: Dict[str, tuple] = {
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),

    # Together SERVERLESS multimodal models (per-token, no endpoint to provision).
    #
    # The Qwen3-**VL** line (8B / 32B / 235B) is deliberately absent: every one of
    # them is DEDICATED-ONLY on Together, so "using" one means standing up a GPU
    # endpoint billed per hour (~$6.49/hr for an H100, ~$4.7k/month running 24/7)
    # whether or not a single order is processed. At this service's volume that is
    # an order of magnitude worse than serverless AND adds cold-start latency, so
    # the VL models are a growth lever at sustained high volume, never a default.
    # Pricing confirmed from the account's own model catalogue.
    # Qwen3.5-9B and Qwen3.7-Plus were candidates and are RETIRED — both were
    # tested against this document and rejected, so they are not priced here and
    # must not be reintroduced as options.
    "Qwen/Qwen3.6-Plus": (0.50, 3.00),
    "google/gemma-4-31B-it": (0.39, 0.97),
}
_DEFAULT_PRICING = (3.00, 15.00)


class BudgetExceeded(RuntimeError):
    """The next call would breach the order's ceiling. Caught by the runner,
    which stops extracting and records a degradation."""


@dataclass
class CallCost:
    label: str
    input_tokens: int
    output_tokens: int
    usd: float
    # Wall-clock window, relative to the governor's creation. Recorded so the
    # WAVE STRUCTURE is visible: whether calls actually overlapped, or queued.
    # Without it a slow order is indistinguishable from a serialized one, and
    # those need opposite fixes.
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def elapsed(self) -> float:
        return max(self.ended_at - self.started_at, 0.0)


@dataclass
class BudgetGovernor:
    """Tracks and caps one order's vision spend."""

    cap_usd: float
    model: str = "claude-sonnet-5"
    calls: List[CallCost] = field(default_factory=list)
    # Set when the cap actually bound, for the run's degradation list.
    breached_on: Optional[str] = None
    # Calls are recorded from worker threads, so the list needs a lock: list
    # .append is atomic under CPython but spent/remaining read the whole list
    # while another thread may be appending, and a torn read here silently
    # mis-prices the budget check that decides whether to keep spending.
    _lock: Any = field(default_factory=threading.Lock, repr=False, compare=False)

    @property
    def spent_usd(self) -> float:
        return sum(c.usd for c in self.calls)

    @property
    def remaining_usd(self) -> float:
        return max(self.cap_usd - self.spent_usd, 0.0)

    def price(self, input_tokens: int, output_tokens: int) -> float:
        pin, pout = _PRICING.get(self.model, _DEFAULT_PRICING)
        return (input_tokens * pin + output_tokens * pout) / 1_000_000

    def check(self, label: str, est_input: int, est_output: int) -> None:
        """Raise BudgetExceeded if this call would breach the cap.

        Estimated, not actual — the point is to decide before the money is
        spent. Output is an estimate because it cannot be known in advance;
        the estimate is deliberately generous so the governor errs toward
        refusing a marginal call rather than allowing an overrun.
        """
        projected = self.spent_usd + self.price(est_input, est_output)
        if projected > self.cap_usd:
            self.breached_on = label
            raise BudgetExceeded(
                f"vision budget ${self.cap_usd:.2f}/order would be exceeded by "
                f"'{label}' (spent ${self.spent_usd:.4f}, this call "
                f"~${self.price(est_input, est_output):.4f}, projected "
                f"${projected:.4f}) — stopping extraction; unread regions become "
                f"REVIEW cards")

    def record(self, label: str, input_tokens: int, output_tokens: int,
               started_at: float = 0.0, ended_at: float = 0.0) -> CallCost:
        """Book actual usage from the API response."""
        cost = CallCost(label=label, input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        usd=self.price(input_tokens, output_tokens),
                        started_at=started_at, ended_at=ended_at)
        with self._lock:
            self.calls.append(cost)
        return cost

    def timeline(self) -> Dict[str, Any]:
        """Wave structure: did the calls actually overlap, or queue?

        `wall` is what the user waits; `serial` is the sum of every call. Their
        RATIO is the parallelism actually achieved — 1.0 means fully serialized
        no matter how large the thread pool is, and that distinction decides
        whether to fix the pool or the calls.
        """
        timed = [c for c in self.calls if c.ended_at > 0]
        if not timed:
            return {}
        t0 = min(c.started_at for c in timed)
        t1 = max(c.ended_at for c in timed)
        wall = t1 - t0
        serial = sum(c.elapsed for c in timed)
        # Peak overlap: the most calls in flight at any instant.
        events = sorted([(c.started_at, 1) for c in timed] +
                        [(c.ended_at, -1) for c in timed])
        cur = peak = 0
        for _t, delta in events:
            cur += delta
            peak = max(peak, cur)
        slowest = max(timed, key=lambda c: c.elapsed)
        return {
            "wall_s": round(wall, 1),
            "serial_s": round(serial, 1),
            "parallelism": round(serial / wall, 2) if wall else 0,
            "peak_in_flight": peak,
            "calls": len(timed),
            "slowest": {"label": slowest.label, "s": round(slowest.elapsed, 1)},
            "p50_s": round(sorted(c.elapsed for c in timed)[len(timed) // 2], 1),
            "max_s": round(slowest.elapsed, 1),
            "per_call": sorted(
                [{"label": c.label, "start": round(c.started_at - t0, 1),
                  "end": round(c.ended_at - t0, 1), "s": round(c.elapsed, 1)}
                 for c in timed], key=lambda x: x["start"]),
        }

    def summary(self) -> Dict[str, object]:
        return {
            "model": self.model,
            "cap_usd": round(self.cap_usd, 4),
            "spent_usd": round(self.spent_usd, 4),
            "remaining_usd": round(self.remaining_usd, 4),
            "calls": len(self.calls),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "breached_on": self.breached_on,
            "by_call": [{"label": c.label, "in": c.input_tokens,
                         "out": c.output_tokens, "usd": round(c.usd, 5)}
                        for c in self.calls],
        }


def project_order_cost(page_count: int, extractable_pages: int, comp_count: int = 6,
                       model: str = "claude-sonnet-5",
                       dpi_section: int = 130, dpi_grid: int = 150,
                       page_pt: tuple = (612.0, 792.0)) -> Dict[str, object]:
    """What this order WILL cost, computed from the page map before any call.

    Logged up front so the spend on a given document is a decision rather than a
    surprise, and so an unusually expensive file (a 200-page addendum dump) is
    visible before it is paid for.
    """
    from app.extraction.vision.render import image_tokens, page_pixels

    w_s, h_s = page_pixels(page_pt[0], page_pt[1], dpi_section)
    w_g, h_g = page_pixels(page_pt[0], page_pt[1], dpi_grid)
    sec_img = image_tokens(w_s, h_s, model)
    grid_img = image_tokens(w_g, h_g, model)

    # Triage: every extractable page as a low-DPI thumbnail, one call.
    w_t, h_t = page_pixels(page_pt[0], page_pt[1], 72)
    triage_in = extractable_pages * image_tokens(w_t, h_t, model) + 800
    triage_out = 60 * max(extractable_pages, 1)

    # Sections: roughly one call per extractable non-grid page.
    section_calls = max(extractable_pages - 4, 1)
    sec_in = section_calls * (sec_img + 1_200)
    sec_out = section_calls * 500

    # Grid: one call per comparable, label strip + column strip.
    grid_in = comp_count * (2 * grid_img + 1_500)
    grid_out = comp_count * 700

    total_in = triage_in + sec_in + grid_in
    total_out = triage_out + sec_out + grid_out
    pin, pout = _PRICING.get(model, _DEFAULT_PRICING)
    base = (total_in * pin + total_out * pout) / 1_000_000

    return {
        "model": model, "pages": page_count, "extractable_pages": extractable_pages,
        "skipped_pages": page_count - extractable_pages,
        "calls": 1 + section_calls + comp_count,
        "input_tokens": total_in, "output_tokens": total_out,
        "usd_base": round(base, 4),
        "usd_with_retries": round(base * 1.15, 4),
        "usd_batched": round(base * 0.5, 4),
    }
