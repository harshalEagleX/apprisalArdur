"""UAD 3.6 structural router — CLI over app.extraction.vision.structural_router.

Detection only: no model calls, so this runs against any report for free and
answers "would the router find this document's structure?" before spending
anything on labelling it.

This is deliberately a THIN wrapper. The detector lives in the app module and is
pinned by tests/test_extraction/test_structural_router.py; a second copy here
would drift from it, and the failure mode of this detector is silent
under-counting, which drift would hide.

Usage:
    python 3.6/section_router.py <report.pdf>

Exit code is 1 when the health check finds something that makes the map
untrustworthy, so this is usable as a gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extraction.vision.structural_router import (  # noqa: E402
    check_health, detect_all)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    pdf = sys.argv[1]
    dpi = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    try:
        import fitz
        with fitz.open(pdf) as doc:
            pages = list(range(1, doc.page_count + 1))
    except Exception as exc:
        print(f"cannot open {pdf}: {exc}")
        return 2

    bands_by_page = detect_all(pdf, pages, dpi=dpi)
    flat = [b for p in sorted(bands_by_page) for b in bands_by_page[p]]
    tabs = [b for b in flat if b.kind == "section_tab"]
    rows = [b for b in flat if b.kind == "row_group"]

    print(f"pages={len(pages)}  bands={len(flat)}  "
          f"section_tabs={len(tabs)}  row_groups={len(rows)}  (dpi={dpi})")
    if tabs and rows:
        print(f"width separation: tabs "
              f"[{min(b.width_frac for b in tabs):.2f}, {max(b.width_frac for b in tabs):.2f}]  "
              f"row_groups [{min(b.width_frac for b in rows):.2f}, "
              f"{max(b.width_frac for b in rows):.2f}]")
    print(f"no-tab pages (inherit from predecessor): "
          f"{[p for p, b in bands_by_page.items() if not b]}")

    for page, bands in sorted(bands_by_page.items()):
        if not bands:
            continue
        desc = "  ".join(f"{b.kind[0].upper()}@{b.y_frac:.3f}" for b in bands)
        print(f"  p{page:>3}: {len(bands)}  {desc}")

    alarms = check_health(bands_by_page)
    if alarms:
        print("\nHEALTH ALARMS:")
        for alarm in alarms:
            print(f"  ! {alarm}")
        return 1

    print("\nhealth: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
