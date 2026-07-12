"""
persistence.models (persist-1.0.0) — SHALqc.md §2 / §15 schema.

SQLAlchemy declarative models for the audit trail. The mandatory §15 keys are
present from day one even though the revision-diff UI ships later — retrofitting
`(order_id, revision_no, package_hash, fingerprint)` would be a migration; adding
the diff on top of them is a feature.

Tables:
  orders      — one row per business order_id
  runs        — one row per processing run (order_id, revision_no, package_hash,
                fingerprint) — same order resubmitted with a new hash ⇒ revision++
  findings    — one row per emitted verdict (for the revision diff join key)
  corrections — reviewer decisions posted back (feeds normalizer/threshold tuning)
  config_audit— every routing/profile change (who, what, before/after hash, ts)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__version__ = "persist-1.0.0"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    amc_code: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Run(Base):
    __tablename__ = "runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer, default=0)
    package_hash: Mapped[str] = mapped_column(String(64), index=True)   # §14 G-3 idempotency
    fingerprint: Mapped[str] = mapped_column(String(80), default="")     # §1 reproducibility
    amc_code: Mapped[str] = mapped_column(String(32), default="")
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (UniqueConstraint("order_id", "package_hash", name="uq_run_order_hash"),)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(32))
    message_key: Mapped[str] = mapped_column(String(64), default="")
    root_field: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text, default="")


class ItemVerdict(Base):
    """One row per checklist item per run — the reviewer-grade verdict Java queries
    (status, description, coordinates, provenance). Joined to LLMInteraction via
    llm_interaction_id, and later to reviewer decisions (the agreement loop)."""
    __tablename__ = "item_verdicts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    section: Mapped[str] = mapped_column(String(32), default="")
    card_group: Mapped[str] = mapped_column(String(24), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    item_name: Mapped[str] = mapped_column(Text, default="")
    check_text: Mapped[str] = mapped_column(Text, default="")
    reject_text: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    found: Mapped[str] = mapped_column(Text, default="")
    reviewer_line: Mapped[str] = mapped_column(Text, default="")
    suggested_wording: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    decided_by: Mapped[str] = mapped_column(String(40), default="")
    bound_by: Mapped[str] = mapped_column(String(20), default="")
    binder_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)   # incl page/bbox
    primary_location: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_interaction_id: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (UniqueConstraint("run_id", "item_id", name="uq_item_verdict_run_item"),)


class LLMInteraction(Base):
    """One row per stored LLM exchange for one item — request packet, parsed
    response, raw model text, and call metadata. Enables replay + reviewer drill-in
    ("what did the model see and say for this check")."""
    __tablename__ = "llm_interactions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    call_type: Mapped[str] = mapped_column(String(64), default="")
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    batch_id: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(24), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    ms: Mapped[float] = mapped_column(Float, default=0.0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Correction(Base):
    __tablename__ = "corrections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(32))
    field: Mapped[str] = mapped_column(String(64), default="")
    reviewer_decision: Mapped[str] = mapped_column(String(32), default="")
    corrected_value: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConfigAudit(Base):
    __tablename__ = "config_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    who: Mapped[str] = mapped_column(String(64), default="")
    what: Mapped[str] = mapped_column(String(64))          # e.g. "routing.yaml" | "AMC001.yaml"
    before_hash: Mapped[str] = mapped_column(String(80), default="")
    after_hash: Mapped[str] = mapped_column(String(80), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
