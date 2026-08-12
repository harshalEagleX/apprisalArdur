"""The 3.6 cards must speak the vocabulary Java and the reviewer page already use.

Nothing crashes when a card invents a group name — which is exactly why this
needs a test. Java places a card on the reviewer's queue with
`!"informational".equals(group)`, and the reviewer page filters with
`cardGroup !== "informational"`. A card grouped `looks_good` therefore satisfies
neither consumer's idea of "harmless" and lands in the queue, so a ninety-item
checklist of mostly-passing items would bury the few that matter.

These tests encode the consumers' rules directly rather than trusting a name, so
a rename on either side fails here instead of in a reviewer's face.
"""
from __future__ import annotations

import pytest

from app.extraction.vision.checklist_cards import summarize, to_cards
from app.extraction.vision.checklist_vision import (CANNOT_EVALUATE, FAIL, PASS,
                                                    VERIFY, ChecklistAnswer)

# Java: ShalqcResponseMapper.mapStatus
_JAVA_STATUS = {"SATISFIED": "PASS", "NOT_SATISFIED": "FAIL", "REVIEW": "VERIFY",
                "NOT_APPLICABLE": "NOT_APPLICABLE", "CANNOT_EVALUATE": "VERIFY"}
_OFF_QUEUE_GROUP = "informational"


def _java_on_queue(card: dict) -> bool:
    """Exactly ShalqcResponseMapper.toRuleResult's reviewRequired."""
    status = _JAVA_STATUS.get(card["status"], "VERIFY")
    informational = card["group"] == _OFF_QUEUE_GROUP
    return (not informational) and status in ("FAIL", "VERIFY")


def _java_blocking(card: dict) -> bool:
    return (card.get("severity") == "rejectable"
            and card["status"] == "NOT_SATISFIED")


def _answer(status: str, rule_id: str = "U36-X-1", **kw) -> ChecklistAnswer:
    return ChecklistAnswer(
        rule_id=rule_id, checklist_number=kw.pop("number", 1),
        section=kw.pop("section", "site"), question=kw.pop("question", "Is it so?"),
        status=status, evidence=kw.pop("evidence", ["something printed"]),
        pages=kw.pop("pages", [3]), **kw)


def _item(rule_id: str = "U36-X-1", **kw) -> dict:
    return {"rule_id": rule_id, "item": "an item", "binding": kw.pop("binding", "bound"),
            "reject_as": kw.pop("reject_as", []), **kw}


def test_passing_cards_stay_off_the_reviewer_queue():
    cards = to_cards([_answer(PASS)], [_item()])
    assert cards[0]["group"] == _OFF_QUEUE_GROUP
    assert not _java_on_queue(cards[0])


@pytest.mark.parametrize("status", [FAIL, VERIFY, CANNOT_EVALUATE])
def test_unresolved_cards_reach_the_reviewer(status):
    cards = to_cards([_answer(status)], [_item()])
    assert cards[0]["group"] != _OFF_QUEUE_GROUP
    assert _java_on_queue(cards[0]), f"{status} must reach a human"


def test_missing_document_is_needs_data_not_a_generic_verify():
    """The frontend chips `needs_data` as "Couldn't auto-judge" — a different and
    more useful message than "please verify", because nobody can act on it until
    the document arrives."""
    cards = to_cards([_answer(CANNOT_EVALUATE)], [_item()])
    assert cards[0]["group"] == "needs_data"


def test_only_an_amc_rejectable_item_can_block():
    plain = to_cards([_answer(FAIL)], [_item()])[0]
    assert not _java_blocking(plain), "no reject wording => never BLOCKING"

    authored = to_cards([_answer(FAIL)],
                        [_item(reject_as=["Please correct the site size."])])[0]
    assert authored["group"] == "recommended_reject"
    assert _java_blocking(authored)


def test_visual_items_request_the_photo_badge():
    visual = to_cards([_answer(VERIFY)], [_item(binding="visual")])[0]
    assert visual["photo_verification_required"] is True
    textual = to_cards([_answer(VERIFY)], [_item(binding="bound")])[0]
    assert textual["photo_verification_required"] is False


def test_a_card_without_visible_evidence_is_guarded():
    """An answer citing nothing on the page is the shape of a confabulation, and
    the reviewer should be told so rather than shown a bare assertion."""
    card = to_cards([_answer(VERIFY, evidence=[])], [_item()])[0]
    assert "no visible evidence cited" in card["guardrails"]


def test_summary_queue_matches_what_the_consumers_compute():
    answers = [_answer(PASS, rule_id="a", number=1),
               _answer(VERIFY, rule_id="b", number=2),
               _answer(CANNOT_EVALUATE, rule_id="c", number=3)]
    items = [_item("a"), _item("b"), _item("c")]
    cards = to_cards(answers, items)
    reported = summarize(cards)
    assert reported["queue"] == sum(1 for c in cards if c["group"] != _OFF_QUEUE_GROUP)
    assert reported["off_queue"] == 1
    assert reported["needs_data"] == 1
