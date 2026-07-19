"""
normalize.dates — SHALqc.md §17 "Date discipline": one shared parser.

Accepts mm/dd/yyyy, m/d/yy, and ISO; 2-digit years pivot at 50 (config-driven);
all dates are stored ISO (YYYY-MM-DD); the service timezone is fixed UTC;
comparisons are date-only unless a rule states otherwise.

Every rule and every extractor that touches a date routes through here — there
is no second date parser anywhere in SHALqc (P6: normalize before compare, once).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

__version__ = "nrm-1.0.0"

_PIVOT = 50  # yy < 50 -> 20yy, else 19yy (overridable via normalizer.yaml)

# mm/dd/yyyy, m-d-yy, mm.dd.yyyy
_MDY_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
# yyyy-mm-dd (ISO) or yyyy/mm/dd
_ISO_RE = re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")


def set_pivot(pivot: int) -> None:
    """Let the normalizer push the configured pivot in (nrm-1.0.0 §17)."""
    global _PIVOT
    _PIVOT = int(pivot)


def parse_date(raw) -> Optional[date]:
    """Parse a date string in any accepted shape → datetime.date, or None.

    ISO (year-first) is tried before M/D/Y so an unambiguous ISO string is never
    misread as month-first.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    m = _ISO_RE.search(s)
    if m:
        yy, mm, dd = (int(x) for x in m.groups())
        return _safe_date(yy, mm, dd)

    m = _MDY_RE.search(s)
    if m:
        mm, dd, yy = (int(x) for x in m.groups())
        if yy < 100:
            yy += 2000 if yy < _PIVOT else 1900
        return _safe_date(yy, mm, dd)

    return None


def _safe_date(yy: int, mm: int, dd: int) -> Optional[date]:
    if not (1 <= mm <= 12 and 1 <= dd <= 31 and 1900 <= yy <= 2099):
        return None
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def to_iso(raw) -> Optional[str]:
    """Canonical ISO string (YYYY-MM-DD) for any accepted date, or None."""
    d = parse_date(raw)
    return d.isoformat() if d else None


def to_display(raw) -> Optional[str]:
    """URAR display form (MM/DD/YYYY) for any accepted date, or None. MISMO stores
    dates ISO, but the appraisal form (and the AMC checks that read it) use
    MM/DD/YYYY — present the value the way the form does so a valid date is never
    mistaken for a wrong-format entry. Generic: any date-typed value, any AMC."""
    d = parse_date(raw)
    return d.strftime("%m/%d/%Y") if d else None


def year_of(raw) -> int:
    """First plausible 4-digit year in the text; 0 when none. Shared by the
    tax-year / year-built / effective-date arithmetic rules."""
    m = re.search(r"\b(18|19|20)\d{2}\b", str(raw or ""))
    return int(m.group(0)) if m else 0
