"""B3 — judge self-consistency reconciliation (deterministic, no live LLM).

Drives judge_all_consistent with a scripted fake client so each pass returns a
chosen status per item, exercising: unanimous decisive → kept; non-unanimous
decisive → downgraded to REVIEW; non-decisive → untouched; n=1 → plain judge_all.
"""
import json
from types import SimpleNamespace

from app.language import judge_v2 as J


class _FakePacket:
    def __init__(self, item_id, scope):
        self.item_id = item_id
        self.scope = scope

    def to_json(self):
        return {"item_id": self.item_id}


class _FakeClient:
    """available=True; returns, per item, the status scripted for the current pass.

    Pass index is read from the ':scN' call_suffix judge_all_consistent appends, so
    this also proves each re-judge pass gets a DISTINCT cache key (fresh sample)."""
    available = True

    def __init__(self, script):
        self.script = script            # {item_id: [pass0_status, pass1_status, ...]}
        self.seen_call_types = []

    def complete(self, call_type, system, payload, max_tokens=None, reasoning_effort=None):
        self.seen_call_types.append(call_type)
        idx = int(call_type.rsplit(":sc", 1)[1]) if ":sc" in call_type else 0
        verds = []
        for pk in json.loads(payload)["packets"]:
            iid = pk["item_id"]
            seq = self.script[iid]
            st = seq[min(idx, len(seq) - 1)]
            verds.append({"item_id": iid, "status": st, "reviewer_line": "placeholder",
                          "fired_branch": None, "confidence": 0.9, "evidence": []})
        return SimpleNamespace(ok=True, data={"verdicts": verds}, call=None, raw=None)


def _packets():
    return {"subject": [_FakePacket("EQ-STABLE", "subject"),
                        _FakePacket("EQ-FLIP", "subject"),
                        _FakePacket("EQ-REVIEW", "subject")]}


def test_unanimous_kept_split_downgraded_nondecisive_untouched():
    script = {
        "EQ-STABLE": ["SATISFIED", "SATISFIED", "SATISFIED"],       # 3/3 → keep
        "EQ-FLIP":   ["SATISFIED", "NOT_SATISFIED", "SATISFIED"],   # 2/1 → REVIEW
        "EQ-REVIEW": ["REVIEW", "REVIEW", "REVIEW"],                # not decisive → skip
    }
    client = _FakeClient(script)
    verdicts, failed, metas, timing = J.judge_all_consistent(client, _packets(), n=3)

    assert verdicts["EQ-STABLE"]["status"] == "SATISFIED"
    assert verdicts["EQ-STABLE"]["confidence"] == 1.0
    assert "judge_unstable" not in verdicts["EQ-STABLE"]

    assert verdicts["EQ-FLIP"]["status"] == "REVIEW"
    assert verdicts["EQ-FLIP"]["confidence"] == 0.67            # 2 of 3 agree
    assert verdicts["EQ-FLIP"]["fired_branch"] is None
    assert verdicts["EQ-FLIP"]["judge_unstable"]["majority"] == "SATISFIED"
    assert 8 <= len(verdicts["EQ-FLIP"]["reviewer_line"]) <= 240

    assert verdicts["EQ-REVIEW"]["status"] == "REVIEW"          # untouched, no resample
    assert "judge_unstable" not in verdicts["EQ-REVIEW"]

    assert timing["self_consistency_n"] == 3
    assert timing["self_consistency_checked"] == 2              # only the 2 decisive
    assert timing["self_consistency_unstable"] == 1


def test_extra_passes_use_distinct_cache_suffixes():
    script = {"EQ-STABLE": ["SATISFIED"] * 3, "EQ-FLIP": ["SATISFIED"] * 3,
              "EQ-REVIEW": ["REVIEW"]}
    client = _FakeClient(script)
    J.judge_all_consistent(client, _packets(), n=3)
    # pass 1 has no suffix; the two re-judge passes carry :sc1 and :sc2
    assert any(ct.endswith(":sc1") for ct in client.seen_call_types)
    assert any(ct.endswith(":sc2") for ct in client.seen_call_types)
    assert any(":sc" not in ct for ct in client.seen_call_types)


def test_n1_is_plain_single_pass():
    script = {"EQ-STABLE": ["SATISFIED"], "EQ-FLIP": ["NOT_SATISFIED"],
              "EQ-REVIEW": ["REVIEW"]}
    client = _FakeClient(script)
    verdicts, failed, metas, timing = J.judge_all_consistent(client, _packets(), n=1)
    # no re-judging, no downgrade, no self-consistency telemetry, no :sc suffixes
    assert verdicts["EQ-FLIP"]["status"] == "NOT_SATISFIED"
    assert "self_consistency_n" not in timing
    assert all(":sc" not in ct for ct in client.seen_call_types)
