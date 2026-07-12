#!/usr/bin/env python3
"""
Extraction Data Report Generator

Dumps what the OCR/vision pipeline actually extracted from each order's
documents (field values + confidence) and how the system classified the
document (assignment type, form type, extraction method/model), pulled
straight from qc_result.python_response.

Usage:
    python generate_extraction_report.py --qc-id 1
    python generate_extraction_report.py --qc-id 1 --output json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


def discover_qc_ids(db_url):
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM qc_result WHERE superseded_at IS NULL ORDER BY id")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def fetch(qc_id: int, db_url: str) -> Optional[dict]:
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    qr.id, qr.batch_file_id, qr.python_response, qr.qc_decision,
                    qr.created_at, qr.extraction_method AS db_extraction_method,
                    bf.filename, at.transaction_ref, at.property_address AS txn_property_address
                FROM qc_result qr
                JOIN batch_file bf ON qr.batch_file_id = bf.id
                LEFT JOIN appraisal_transaction at ON at.id = bf.transaction_id
                WHERE qr.id = %(qc_id)s AND qr.superseded_at IS NULL
                """,
                {"qc_id": qc_id},
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not row["python_response"]:
        return None
    payload = json.loads(row["python_response"])
    payload["_qc_result_id"] = row["id"]
    payload["_filename"] = row["filename"]
    payload["_transaction_ref"] = row["transaction_ref"]
    payload["_txn_property_address"] = row["txn_property_address"]
    payload["_qc_decision"] = row["qc_decision"]
    payload["_created_at"] = row["created_at"].isoformat() if row["created_at"] else None
    return payload


def format_text(payload: dict) -> str:
    ef = payload.get("extracted_fields") or {}
    fc = payload.get("field_confidence") or {}

    lines = []
    lines.append("=" * 100)
    lines.append(f"SHAL · EXTRACTION DATA · QC RESULT #{payload['_qc_result_id']} · {payload.get('_transaction_ref')}")
    lines.append(f"{payload.get('_filename')}")
    lines.append(f"Property: {ef.get('property_address') or payload.get('_txn_property_address') or 'N/A'}")
    lines.append(f"Extracted: {payload.get('_created_at')}")
    lines.append("=" * 100)
    lines.append("")

    lines.append("HOW THE SYSTEM CLASSIFIED THIS DOCUMENT")
    lines.append("-" * 100)
    lines.append(f"Extraction method:   {payload.get('extraction_method')}")
    lines.append(f"Model provider:      {payload.get('model_provider')}")
    lines.append(f"Model name:          {payload.get('model_name')}")
    lines.append(f"Vision model:        {payload.get('vision_model')}")
    lines.append(f"Assignment type:     {ef.get('assignment_type')}")
    lines.append(f"Form type:           {ef.get('form_type')}")
    lines.append(f"Report type:         {ef.get('appraisal_report_type')}")
    lines.append(f"Cache hit:           {payload.get('cache_hit')}")
    lines.append(f"Processing time:     {payload.get('processing_time_ms')} ms")
    lines.append(f"Rule engine version: {payload.get('rule_engine_version')}")
    missing_docs = payload.get("missing_supporting_documents") or []
    lines.append(f"Missing supporting documents: {', '.join(missing_docs) if missing_docs else 'None'}")
    lines.append(f"Blocking: {payload.get('blocking')}  Blocking rules: {payload.get('blocking_rules') or 'None'}")
    notices = payload.get("processing_notices") or []
    if notices:
        lines.append("Processing notices:")
        for n in notices:
            lines.append(f"  - {n}")
    lines.append("")

    lines.append("EXTRACTED FIELDS (value · confidence)")
    lines.append("-" * 100)
    for field, value in ef.items():
        if value in (None, "", [], {}):
            continue
        conf = fc.get(field)
        conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"
        lines.append(f"{field:<40} {str(value):<50} conf={conf_str}")
    lines.append("")

    empty_fields = [f for f, v in ef.items() if v in (None, "", [], {})]
    if empty_fields:
        lines.append(f"FIELDS NOT EXTRACTED / EMPTY ({len(empty_fields)})")
        lines.append("-" * 100)
        for field in empty_fields:
            lines.append(f"  - {field}")
        lines.append("")

    action_items = payload.get("action_items") or []
    if action_items:
        lines.append(f"ACTION ITEMS ({len(action_items)})")
        lines.append("-" * 100)
        for item in action_items:
            if isinstance(item, dict):
                lines.append(f"  - [{item.get('rule_id', '?')}] {item.get('message') or item.get('description') or item}")
            else:
                lines.append(f"  - {item}")
        lines.append("")

    lines.append("=" * 100)
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Dump extraction data from SHAL database")
    parser.add_argument("--qc-id", type=int, help="QC Result ID (omit to dump all current results)")
    parser.add_argument("--output", choices=["json", "text"], default="text")
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL", "postgresql://shal:shal@localhost:5432/shal_qc"))
    args = parser.parse_args()

    qc_ids = [args.qc_id] if args.qc_id else discover_qc_ids(args.db_url)

    for qc_id in qc_ids:
        payload = fetch(qc_id, args.db_url)
        if not payload:
            print(f"QC Result #{qc_id} not found or has no extraction data", file=sys.stderr)
            continue
        if args.output == "json":
            print(json.dumps(payload, indent=2))
        else:
            print(format_text(payload))


if __name__ == "__main__":
    main()
