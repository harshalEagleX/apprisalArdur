#!/usr/bin/env python3
"""
QC Result Report Generator

Connects to SHAL database and generates formatted QC result reports
matching the structure shown in your review UI.

Usage:
    python generate_qc_report.py --qc-id 1
    python generate_qc_report.py --qc-id 1 --output json
    python generate_qc_report.py --qc-id 1 --output html > report.html
"""

import os
import json
import sys
import argparse
from typing import Optional, Dict, List, Any
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Install with: pip install psycopg2-binary")
    sys.exit(1)


class QCReportGenerator:
    """Generate QC result reports from SHAL database."""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            db_url: Database URL (postgresql://user:pass@host:port/db)
                   Falls back to environment variables or defaults
        """
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            os.getenv("DB_URL", "postgresql://shal:shal@localhost:5432/shal_qc")
        )
        self.conn = None
        self.connect()

    def connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(self.db_url)
            print(f"✓ Connected to database", file=sys.stderr)
        except psycopg2.Error as e:
            print(f"✗ Database connection failed: {e}", file=sys.stderr)
            sys.exit(1)

    def query(self, sql: str, params: Dict = None) -> List[Dict]:
        """Execute query and return results as list of dicts."""
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params or {})
                return cur.fetchall()
        except psycopg2.Error as e:
            print(f"✗ Query failed: {e}", file=sys.stderr)
            sys.exit(1)

    def get_qc_result(self, qc_result_id: int) -> Optional[Dict[str, Any]]:
        """Fetch QC result header info."""
        sql = """
        SELECT
            qr.id,
            qr.batch_file_id,
            bf.filename,
            bf.order_id,
            at.transaction_ref AS order_ref,
            at.document_status AS order_status,
            at.property_address AS transaction_property_address,
            at.id AS transaction_id,
            qr.qc_decision,
            qr.final_decision,
            qr.created_at,
            qr.reviewed_at,
            qr.python_response,
            COALESCE(qr.passed_count, 0) AS rules_passed,
            COALESCE(qr.failed_count, 0) AS rules_failed,
            COALESCE(qr.verify_count, 0) AS rules_verify,
            COALESCE(qr.total_rules, 0) - COALESCE(qr.passed_count, 0) -
            COALESCE(qr.failed_count, 0) - COALESCE(qr.verify_count, 0) AS rules_na,
            COALESCE(qr.total_rules, 0) AS total_rules
        FROM
            qc_result qr
            JOIN batch_file bf ON qr.batch_file_id = bf.id
            LEFT JOIN appraisal_transaction at ON at.id = bf.transaction_id
        WHERE
            qr.id = %(qc_result_id)s
            AND qr.superseded_at IS NULL
        """
        results = self.query(sql, {"qc_result_id": qc_result_id})
        if not results:
            return None
        row = results[0]
        extracted_fields = {}
        if row.get("python_response"):
            try:
                extracted_fields = json.loads(row["python_response"]).get("extracted_fields", {})
            except (json.JSONDecodeError, TypeError):
                extracted_fields = {}
        row["assignment_type"] = extracted_fields.get("assignment_type")
        row["extracted_property_address"] = extracted_fields.get("property_address") or row.get("transaction_property_address")
        return row

    def get_rules_by_section(self, qc_result_id: int) -> Dict[str, List[Dict]]:
        """Fetch all rules grouped by section."""
        sql = """
        SELECT 
            rul.id,
            rul.rule_id,
            rul.rule_name,
            rul.section,
            rul.status,
            rul.message,
            rul.details,
            rul.action_item,
            rul.needs_verification,
            rul.reviewer_verified,
            rul.reviewer_comment,
            rul.verified_at,
            rul.created_at
        FROM 
            qc_rule_result rul
        WHERE 
            rul.qc_result_id = %(qc_result_id)s
        ORDER BY 
            rul.section ASC,
            rul.rule_id ASC
        """
        results = self.query(sql, {"qc_result_id": qc_result_id})
        
        # Group by section
        by_section = {}
        for rule in results:
            section = rule["section"] or "GLOBAL"
            if section not in by_section:
                by_section[section] = []
            by_section[section].append(rule)
        
        return by_section

    def get_stats(self, qc_result_id: int) -> Dict[str, int]:
        """Get summary statistics."""
        sql = """
        SELECT 
            status,
            COUNT(*) AS count
        FROM 
            qc_rule_result
        WHERE 
            qc_result_id = %(qc_result_id)s
        GROUP BY 
            status
        """
        results = self.query(sql, {"qc_result_id": qc_result_id})
        stats = {row["status"]: row["count"] for row in results}
        return stats

    def generate_json_report(self, qc_result_id: int) -> str:
        """Generate report as JSON."""
        qc = self.get_qc_result(qc_result_id)
        if not qc:
            return json.dumps({"error": f"QC Result #{qc_result_id} not found"}, indent=2)

        rules = self.get_rules_by_section(qc_result_id)
        stats = self.get_stats(qc_result_id)

        report = {
            "qc_result_id": qc["id"],
            "batch_file_id": qc["batch_file_id"],
            "file_name": qc["filename"],
            "external_order_id": qc["order_ref"] or qc["order_id"],
            "order_status": qc["order_status"],
            "transaction_id": qc["transaction_id"],
            "assignment_type": qc["assignment_type"],
            "property_address": qc["extracted_property_address"],
            "qc_decision": qc["qc_decision"],
            "final_decision": qc["final_decision"],
            "qc_run_date": qc["created_at"].isoformat() if qc["created_at"] else None,
            "reviewed_at": qc["reviewed_at"].isoformat() if qc["reviewed_at"] else None,
            "statistics": {
                "passed": int(qc["rules_passed"]),
                "failed": int(qc["rules_failed"]),
                "verify_needed": int(qc["rules_verify"]),
                "not_applicable": int(qc["rules_na"]),
                "total": int(qc["total_rules"]),
            },
            "status_breakdown": stats,
            "rules_by_section": {
                section: [
                    {
                        "id": rule["id"],
                        "rule_id": rule["rule_id"],
                        "name": rule["rule_name"],
                        "status": rule["status"],
                        "message": rule["message"],
                        "details": rule["details"],
                        "action_item": rule["action_item"],
                        "reviewer_verified": rule["reviewer_verified"],
                        "reviewer_comment": rule["reviewer_comment"],
                        "verified_at": rule["verified_at"].isoformat() if rule["verified_at"] else None,
                    }
                    for rule in rules[section]
                ]
                for section in sorted(rules.keys())
            },
        }

        return json.dumps(report, indent=2)

    def generate_text_report(self, qc_result_id: int) -> str:
        """Generate report as formatted text."""
        qc = self.get_qc_result(qc_result_id)
        if not qc:
            return f"QC Result #{qc_result_id} not found"

        rules = self.get_rules_by_section(qc_result_id)
        stats = self.get_stats(qc_result_id)

        lines = []
        lines.append("=" * 80)
        lines.append(f"SHAL · QC RESULT #{qc['id']} · {qc['order_id']}")
        lines.append(f"{qc['filename']}")
        lines.append("=" * 80)
        lines.append("")

        # Header info
        lines.append(f"QC Decision:      {qc['qc_decision']}")
        lines.append(f"Final Decision:   {qc['final_decision']}")
        lines.append(f"QC Run Date:      {qc['created_at'].strftime('%d %b %Y, %H:%M') if qc['created_at'] else 'N/A'}")
        lines.append("")

        # Statistics
        lines.append("STATISTICS")
        lines.append("-" * 40)
        lines.append(f"  Passed:         {qc['rules_passed']}")
        lines.append(f"  Failed:         {qc['rules_failed']}")
        lines.append(f"  Verify Needed:  {qc['rules_verify']}")
        lines.append(f"  Not Applicable: {qc['rules_na']}")
        lines.append(f"  Total Rules:    {qc['total_rules']}")
        lines.append("")

        # Rules by section
        lines.append("RULES")
        lines.append("-" * 80)
        for section in sorted(rules.keys()):
            lines.append(f"\n{section}")
            lines.append("  " + "-" * 76)
            for rule in rules[section]:
                status_icon = {
                    "PASS": "✓",
                    "FAIL": "✗",
                    "VERIFY": "⚠",
                    "N/A": "○",
                }.get(rule["status"], "?")

                lines.append(f"  [{status_icon}] {rule['rule_id']} - {rule['rule_name']}")
                lines.append(f"      Status: {rule['status']}")

                if rule["message"]:
                    # Wrap long messages
                    msg_lines = [rule["message"][i:i+70] for i in range(0, len(rule["message"]), 70)]
                    for msg_line in msg_lines:
                        lines.append(f"      {msg_line}")

                if rule["reviewer_comment"]:
                    lines.append(f"      Reviewer: {rule['reviewer_comment']}")

                lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)

    def generate_html_report(self, qc_result_id: int) -> str:
        """Generate report as HTML."""
        qc = self.get_qc_result(qc_result_id)
        if not qc:
            return f"<html><body>QC Result #{qc_result_id} not found</body></html>"

        rules = self.get_rules_by_section(qc_result_id)

        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            "<meta charset='utf-8'>",
            "<title>QC Result #" + str(qc['id']) + "</title>",
            "<style>",
            "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; }",
            "  .header { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }",
            "  .title { font-size: 24px; font-weight: bold; }",
            "  .subtitle { font-size: 14px; color: #666; }",
            "  .stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin: 20px 0; }",
            "  .stat-box { border: 1px solid #ddd; padding: 10px; text-align: center; border-radius: 4px; }",
            "  .stat-number { font-size: 20px; font-weight: bold; }",
            "  .stat-label { font-size: 12px; color: #666; }",
            "  .section { margin-top: 30px; }",
            "  .section-title { font-size: 16px; font-weight: bold; background: #f0f0f0; padding: 10px; }",
            "  .rule { margin: 10px 0; padding: 10px; border-left: 4px solid #999; }",
            "  .rule.pass { border-left-color: green; background: #f0fff0; }",
            "  .rule.fail { border-left-color: red; background: #fff0f0; }",
            "  .rule.verify { border-left-color: orange; background: #fffaf0; }",
            "  .rule-id { font-weight: bold; }",
            "  .rule-message { margin-top: 5px; font-size: 13px; color: #333; }",
            "</style>",
            "</head>",
            "<body>",
            "<div class='header'>",
            f"  <div class='title'>QC Result #{qc['id']}</div>",
            f"  <div class='subtitle'>{qc['order_id']} · {qc['filename']}</div>",
            f"  <div class='subtitle'>Run: {qc['created_at'].strftime('%d %b %Y, %H:%M') if qc['created_at'] else 'N/A'}</div>",
            "</div>",
            "<div class='stats'>",
            f"  <div class='stat-box'><div class='stat-number'>{qc['rules_passed']}</div><div class='stat-label'>Passed</div></div>",
            f"  <div class='stat-box'><div class='stat-number'>{qc['rules_failed']}</div><div class='stat-label'>Failed</div></div>",
            f"  <div class='stat-box'><div class='stat-number'>{qc['rules_verify']}</div><div class='stat-label'>Verify</div></div>",
            f"  <div class='stat-box'><div class='stat-number'>{qc['rules_na']}</div><div class='stat-label'>N/A</div></div>",
            f"  <div class='stat-box'><div class='stat-number'>{qc['total_rules']}</div><div class='stat-label'>Total</div></div>",
            "</div>",
        ]

        # Add rules by section
        for section in sorted(rules.keys()):
            html_parts.append(f"<div class='section'>")
            html_parts.append(f"  <div class='section-title'>{section}</div>")

            for rule in rules[section]:
                status_lower = rule["status"].lower()
                html_parts.append(f"  <div class='rule {status_lower}'>")
                html_parts.append(f"    <span class='rule-id'>[{rule['rule_id']}]</span> {rule['rule_name']}")
                html_parts.append(f"    <div class='rule-message'><strong>Status:</strong> {rule['status']}</div>")

                if rule["message"]:
                    html_parts.append(f"    <div class='rule-message'>{rule['message']}</div>")

                if rule["reviewer_comment"]:
                    html_parts.append(f"    <div class='rule-message'><strong>Reviewer:</strong> {rule['reviewer_comment']}</div>")

                html_parts.append(f"  </div>")

            html_parts.append(f"</div>")

        html_parts.extend([
            "</body>",
            "</html>",
        ])

        return "\n".join(html_parts)

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate QC result reports from SHAL database")
    parser.add_argument("--qc-id", type=int, required=True, help="QC Result ID")
    parser.add_argument("--output", choices=["json", "text", "html"], default="text", help="Output format")
    parser.add_argument("--db-url", help="Database URL (defaults to .env or DB_URL env var)")

    args = parser.parse_args()

    generator = QCReportGenerator(args.db_url)

    try:
        if args.output == "json":
            print(generator.generate_json_report(args.qc_id))
        elif args.output == "html":
            print(generator.generate_html_report(args.qc_id))
        else:  # text
            print(generator.generate_text_report(args.qc_id))
    finally:
        generator.close()


if __name__ == "__main__":
    main()
