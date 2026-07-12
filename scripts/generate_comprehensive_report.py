#!/usr/bin/env python3
"""Generate comprehensive QC results report combining all QC results with full details."""

import subprocess
import json
import sys
from datetime import datetime

def discover_qc_ids(db_url):
    """Find the current (non-superseded) QC result IDs in the database via psql."""
    result = subprocess.run(
        ["psql", db_url, "-t", "-A", "-c",
         "SELECT id FROM qc_result WHERE superseded_at IS NULL ORDER BY id"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Could not query qc_result ids via psql: {result.stderr}", file=sys.stderr)
        return []
    return [int(line) for line in result.stdout.strip().split('\n') if line.strip()]


def run_qc_report(qc_id, db_url):
    """Run report generator and return JSON output."""
    cmd = [
        "/opt/homebrew/Caskroom/miniconda/base/envs/shal/bin/python",
        "scripts/generate_qc_report.py",
        "--qc-id", str(qc_id),
        "--db-url", db_url,
        "--output", "json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="/Users/eaglex/Documents/indevelopment/eaglex/SHAL")
    
    if result.returncode != 0:
        print(f"Error generating QC #{qc_id}: {result.stderr}", file=sys.stderr)
        return None
    
    # Skip the "✓ Connected to database" line and parse JSON
    lines = result.stdout.strip().split('\n')
    json_start = next((i for i, line in enumerate(lines) if line.startswith('{')), 0)
    return json.loads('\n'.join(lines[json_start:]))

def format_review_date(iso_str):
    """Format an ISO timestamp like '8 Jul 2026, 21:45' (no leading zero on day)."""
    if not iso_str:
        return "N/A"
    dt = datetime.fromisoformat(iso_str)
    return f"{dt.day} {dt.strftime('%b %Y, %H:%M')}"


def format_qc_report(data, qc_num):
    """Format a single QC result matching the review-UI layout (order/decision header,
    stat block, then RULE/SECTION/RESULT/OUTPUT rows grouped fail -> override -> pass -> n/a)."""
    lines = []

    stats = data['statistics']
    failed = stats['failed']
    verify = stats['verify_needed']
    passed = stats['passed']
    na = stats['not_applicable']
    total = stats['total']

    # Header
    assignment_type = (data.get('assignment_type') or 'UNKNOWN').upper()
    lines.append("=" * 100)
    lines.append(f"SHAL · QC RESULT #{data['qc_result_id']} · {assignment_type}")
    lines.append(f"{data['external_order_id']}")
    lines.append(f"{data['file_name']}")
    lines.append("/")
    lines.append(f"Order {data.get('property_address') or ''}")
    lines.append("/")
    reviewed = data.get('reviewed_at') or data.get('qc_run_date')
    lines.append(f"reviewed {format_review_date(reviewed)}")
    lines.append("=" * 100)
    lines.append("")

    # Decision Summary
    lines.append("FINAL DECISION")
    lines.append("-" * 100)
    decision = data['qc_decision']

    if decision == "AUTO_FAIL":
        lines.append("FAIL")
        lines.append(f"{failed} confirmed failure{'s' if failed != 1 else ''} · TO_VERIFY resolved")
    elif decision == "TO_VERIFY":
        lines.append("TO_VERIFY")
        lines.append(f"{verify} override{'s' if verify != 1 else ''} / verified needed")
    elif decision == "AUTO_PASS":
        lines.append("PASS")
        lines.append("All rules passed or not applicable")
    else:
        lines.append(decision)

    lines.append("")
    lines.append(f"{total}")
    lines.append("Rules run")
    lines.append(f"{failed}")
    lines.append("Failed")
    lines.append(f"{verify}")
    lines.append("Overrides / verified")
    lines.append(f"{passed}")
    lines.append("Auto-passed")
    lines.append(f"{na}")
    lines.append("Not applicable")
    lines.append(f"{total} rules")
    lines.append("")

    # Rules table: grouped fail -> override -> pass -> n/a, preserving the
    # section-ASC/rule_id-ASC order already produced by the SQL query.
    lines.append("RULE\tSECTION\tRESULT\tOUTPUT")
    lines.append("-" * 100)

    status_order = {"fail": 0, "verify": 1, "pass": 2, "not_applicable": 3}
    status_display_map = {"pass": "Pass", "fail": "Fail", "verify": "Override", "not_applicable": "N/A"}

    all_rules = []
    for section in sorted(data['rules_by_section'].keys()):
        for rule in data['rules_by_section'][section]:
            all_rules.append((section, rule))
    all_rules.sort(key=lambda sr: status_order.get((sr[1]['status'] or '').lower(), 4))

    for section, rule in all_rules:
        status = (rule['status'] or '').lower()
        status_display = status_display_map.get(status, (rule['status'] or 'UNKNOWN').upper())
        message = rule['message'] if rule['message'] else rule['details'] if rule['details'] else ''

        lines.append(rule['rule_id'])
        lines.append(rule['name'])
        lines.append(f"{section}\t{status_display}\t{message}")

        if rule.get('reviewer_comment'):
            lines.append(f"Reviewer: {rule['reviewer_comment']}")

        lines.append("")

    lines.append("=" * 100)
    lines.append("")
    return "\n".join(lines)

def main():
    db_url = "postgresql://shal:shal@localhost:5432/shal_qc"
    output_file = "/Users/eaglex/Documents/indevelopment/eaglex/SHAL/QC_RESULTS_FULL_REPORT.txt"
    
    # Summary data
    qc_data = {}
    
    print("Generating comprehensive QC report...", file=sys.stderr)

    qc_ids = discover_qc_ids(db_url)
    print(f"Found {len(qc_ids)} current QC result(s): {qc_ids}", file=sys.stderr)

    # Fetch all QC results
    for qc_id in qc_ids:
        print(f"Fetching QC #{qc_id}...", file=sys.stderr)
        data = run_qc_report(qc_id, db_url)
        if data:
            qc_data[qc_id] = data
    
    # Generate report
    with open(output_file, 'w') as f:
        # Title
        f.write("╔" + "=" * 98 + "╗\n")
        f.write("║" + " " * 30 + "SHAL QC RESULTS SUMMARY" + " " * 45 + "║\n")
        f.write("║" + " " * 35 + f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}" + " " * 33 + "║\n")
        f.write("╚" + "=" * 98 + "╝\n")
        f.write("\n")
        
        # Summary Table
        f.write("QC Results Summary\n")
        f.write("=" * 100 + "\n")
        f.write(f"{'QC #':<6} {'File':<30} {'Status':<15} {'Pass':<8} {'Fail':<8} {'Verify':<10} {'N/A':<8} {'Total':<8}\n")
        f.write("-" * 100 + "\n")
        
        for qc_id in sorted(qc_data.keys()):
            data = qc_data[qc_id]
            f.write(f"#{qc_id:<5} {data['file_name']:<30} {data['qc_decision']:<15} "
                   f"{data['statistics']['passed']:<8} {data['statistics']['failed']:<8} "
                   f"{data['statistics']['verify_needed']:<10} {data['statistics']['not_applicable']:<8} "
                   f"{data['statistics']['total']:<8}\n")
        
        f.write("=" * 100 + "\n")
        f.write("\n" * 2)
        
        # Detailed reports
        f.write("DETAILED QC RESULTS\n")
        f.write("=" * 100 + "\n\n")
        
        for qc_id in sorted(qc_data.keys()):
            f.write(format_qc_report(qc_data[qc_id], qc_id))
            f.write("\n\n")
        
        # Footer
        f.write("=" * 100 + "\n")
        f.write("End of Report\n")
        f.write("=" * 100 + "\n")
    
    print(f"✓ Report saved to: {output_file}", file=sys.stderr)
    print(output_file)

if __name__ == "__main__":
    main()
