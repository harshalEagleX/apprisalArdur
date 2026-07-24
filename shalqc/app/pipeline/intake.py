"""
pipeline/intake.py — SHALqc.md §3.1 Intake & classification.

1. Unzip the package. A manifest (if present) declares amc_code, order_id,
   revision_flag. No manifest ⇒ amc_code is resolved from the engagement
   letter's letterhead (best-effort here; the full AMC-profile fingerprinting
   system is SHALqc.md §6, out of scope for this build) else falls back to
   the `_base` profile.
2. Classify each file: appraisal PDF (UAD form markers), MISMO XML,
   engagement letter, purchase contract (purchase orders only).
3. G-0 gate: a missing appraisal PDF, or an unparseable XML on an
   XML-expected order, is a non-overridable HOLD/BLOCKED. A missing
   engagement letter is NOT a G-0 failure — intake proceeds and the
   downstream cross-document rules resolve NOT_APPLICABLE with a HOLD
   finding ("engagement letter not provided"); that finding itself is a
   rules-layer concern (Part 5), out of scope here.
4. Folder boundary = order boundary. This is deliberate: a prior failure mode
   used the filename stem to group a package's files, which silently merged
   unrelated orders that happened to share a stem prefix. `assemble_order`
   always takes a directory and classifies everything inside it as one order.
"""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

__version__ = "ink-1.0.0"

logger = logging.getLogger(__name__)

# UAD 1004-family reports run long; an engagement letter or contract is short.
_APPRAISAL_MIN_PAGES = 8
_UAD_MARKERS = (
    "uniform residential appraisal report",
    "urar",
    "sales comparison approach",
    "reconciliation",
)
_ENGAGEMENT_MARKERS = ("engagement letter", "order form", "assignment order", "appraisal order",
                       "standards of engagement", "engagement instructions")
_CONTRACT_MARKERS = ("purchase agreement", "sales contract", "purchase and sale agreement")

# 2026-07-18: ESNC-0006152's 5-page EngagementLetter.pdf classified as "unknown"
# — too long for the `pages <= 3` fallback, and its wording ("STANDARDS OF
# ENGAGEMENT", "Standard Appraisal Engagement Instructions") matched none of the
# phrase markers. The whole engagement comparison then degraded silently for that
# order: every "must match the engagement letter" check had no counterpart to
# compare against. Phrase markers alone are brittle because each AMC titles its
# letter differently, so back them with a STRUCTURAL signal.
#
# Measured over all 18 PDFs in the 7 test orders: every engagement letter (7/7)
# carries 9 of these order-form tokens, appraisal reports carry 5-7, and purchase
# contracts 0-4 — cleanly separable. Only applied to PDFs shorter than an
# appraisal report, so a long scanned report can never be captured by it.
_ORDER_FORM_TOKENS = ("borrower", "lender", "loan number", "due date", "appraisal fee",
                      "property address", "order id", "file number", "client",
                      "inspection", "appraiser", "engagement")
_ORDER_FORM_TOKEN_FLOOR = 6

# ── §14 G-1 package-safety limits ───────────────────────────────────────────
_MAX_PACKAGE_BYTES = 200 * 1024 * 1024   # 200 MB cap
_MAX_ZIP_RATIO = 100                     # uncompressed:compressed ≤ 100:1 (zip-bomb guard)
# §14 G-2 XML-belongs-to-report token-overlap floor.
_XML_MATCH_FLOOR = 0.8


@dataclass
class OrderDocuments:
    """Everything intake found for one order — one folder, one order (§3.1.4)."""

    order_dir: Path
    appraisal_pdf: Optional[Path] = None
    xml: Optional[Path] = None
    engagement_letter: Optional[Path] = None
    contract: Optional[Path] = None
    unclassified: List[Path] = field(default_factory=list)

    amc_code: Optional[str] = None
    order_id: Optional[str] = None
    revision_flag: bool = False

    # §14 gate outputs
    package_hash: Optional[str] = None      # G-3: sha256 over all package bytes
    xml_overlay_disabled: bool = False      # G-2: XML didn't match the report → PDF-only
    vendor: str = "unknown"                 # CORE §9: rendering vendor (TOTAL/ACI/…)

    status: str = "OK"                 # "OK" | "BLOCKED"
    hold_reason: Optional[str] = None  # set only when status == "BLOCKED"


def safe_extract_zip(zip_path, dest_dir) -> Path:
    """Unzip a package with the §14 G-1 safety checks, then extract.

    Raises ValueError (→ the API turns it into a 422 `package_unsafe`, never a
    5xx) on: path traversal (`../` / absolute member), an over-cap package
    (>200 MB uncompressed), or a zip-bomb (uncompressed:compressed > 100:1).
    """
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = str(dest_dir.resolve())

    with zipfile.ZipFile(str(zip_path)) as zf:
        total_uncompressed = 0
        total_compressed = 0
        for member in zf.infolist():
            # path-traversal guard
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(dest_root):
                raise ValueError(f"unsafe path in package: {member.filename}")
            total_uncompressed += member.file_size
            total_compressed += member.compress_size
        if total_uncompressed > _MAX_PACKAGE_BYTES:
            raise ValueError(f"package too large: {total_uncompressed} bytes (cap {_MAX_PACKAGE_BYTES})")
        if total_compressed > 0 and (total_uncompressed / total_compressed) > _MAX_ZIP_RATIO:
            raise ValueError(
                f"zip-bomb guard: ratio {total_uncompressed / total_compressed:.0f}:1 exceeds {_MAX_ZIP_RATIO}:1")
        zf.extractall(str(dest_dir))
    return dest_dir


def package_sha256(path) -> str:
    """§14 G-3 idempotency key — sha256 over the raw package bytes (a file) or,
    for an already-unpacked folder, over every file's bytes in a stable order."""
    import hashlib

    path = Path(path)
    h = hashlib.sha256()
    if path.is_file():
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    else:
        for p in sorted(path.rglob("*")):
            if p.is_file() and not p.name.startswith("manifest."):
                h.update(p.relative_to(path).as_posix().encode("utf-8"))
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
    return h.hexdigest()


def _is_pdf_encrypted(path: Path) -> bool:
    """§14 G-1 encrypted/corrupt PDF detection."""
    import fitz

    try:
        doc = fitz.open(str(path))
    except Exception:
        return True   # unreadable ⇒ treat as blocked (corrupt)
    try:
        return bool(doc.needs_pass)
    finally:
        doc.close()


def _pdf_text_sample(path: Path, max_pages: int = 3) -> str:
    import fitz

    try:
        doc = fitz.open(str(path))
    except Exception:
        return ""
    try:
        return "\n".join(doc[i].get_text("text") for i in range(min(max_pages, len(doc)))).lower()
    finally:
        doc.close()


def _pdf_page_count(path: Path) -> int:
    import fitz

    try:
        doc = fitz.open(str(path))
    except Exception:
        return 0
    try:
        return len(doc)
    finally:
        doc.close()


def _is_mismo_xml(path: Path) -> bool:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError:
        return False
    except OSError:
        return False
    # MISMO 2.6 GSE appraisal XML roots carry these top-level sections.
    tags = {child.tag for child in root}
    return bool(tags & {"REPORT", "PROPERTY", "PARTIES", "VALUATION"})


def classify_file(path: Path) -> str:
    """Return one of "appraisal_pdf" | "mismo_xml" | "engagement_letter" |
    "contract" | "unknown"."""
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return "mismo_xml" if _is_mismo_xml(path) else "unknown"
    if suffix != ".pdf":
        return "unknown"

    pages = _pdf_page_count(path)
    # Sample 6 pages, not 3: the URAR form's UAD markers ("sales comparison
    # approach", "reconciliation") sit a few pages IN, past the cover. A shallow
    # 3-page sample missed them, so a 30+ page report whose scope merely QUOTES
    # "sales contract" fell through to the contract branch → appraisal_pdf stayed
    # None → the whole order was G-0 blocked ("appraisal PDF not found"). This is
    # the exact EBER96709 failure.
    text = _pdf_text_sample(path, max_pages=6)
    uad_count = sum(1 for m in _UAD_MARKERS if m in text)
    eng_hit = any(m in text for m in _ENGAGEMENT_MARKERS)

    # 1) Order pack / engagement letter, identified by its OWN specific markers
    #    ("engagement letter", "appraisal order", "engagement instructions", …) which
    #    never appear in an appraisal REPORT body. This precedes the length+UAD signal
    #    below because an Equity order pack can run 12 pages and QUOTE a UAD term once —
    #    that previously tripped the appraisal branch and silently dropped the whole
    #    engagement (ESPA-0005366: engagement=None → EVERY cross-doc check went N/A).
    #    A real report is UAD-DENSE (>=2 markers in the first 6 pages); an order pack
    #    that merely names the form is UAD-sparse (<=1), so engagement-markers + sparse
    #    ⇒ engagement, regardless of page count.
    if eng_hit and uad_count <= 1:
        return "engagement_letter"
    # 2) Definitive appraisal signal (UAD/URAR markers on a long report). Checked
    #    before the contract branch so an appraisal that mentions "sales contract" is
    #    never a contract; the UAD-density guard above already routed any order pack.
    if pages >= _APPRAISAL_MIN_PAGES and uad_count >= 1:
        return "appraisal_pdf"
    # 2b) Engagement markers on a UAD-dense doc are extremely unlikely, but keep the
    #     any-length engagement fallback for short packs the density test didn't catch.
    if eng_hit:
        return "engagement_letter"
    # 3) A purchase contract is a SHORT document; its markers apply only below the
    #    appraisal floor (a long PDF with a contract phrase is the appraisal).
    if pages < _APPRAISAL_MIN_PAGES and any(m in text for m in _CONTRACT_MARKERS):
        return "contract"
    # 4) A long PDF with no distinguishing markers is still the appraisal report
    #    (scanned reports miss text markers) — never drop the largest document.
    if pages >= _APPRAISAL_MIN_PAGES:
        return "appraisal_pdf"
    # 5) Short PDFs: a 1-3 page doc is a letter; an order-form-dense short PDF is an
    #    order form this AMC titles differently (see _ORDER_FORM_TOKENS).
    if pages <= 3:
        return "engagement_letter"
    if sum(1 for t in _ORDER_FORM_TOKENS if t in text) >= _ORDER_FORM_TOKEN_FLOOR:
        return "engagement_letter"
    return "unknown"


def _read_manifest(order_dir: Path) -> dict:
    for name in ("manifest.json", "manifest.yaml", "manifest.yml"):
        p = order_dir / name
        if not p.exists():
            continue
        try:
            if p.suffix == ".json":
                import json
                return json.loads(p.read_text(encoding="utf-8"))
            import yaml
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("intake: manifest at %s unreadable: %s", p, exc)
    return {}


def _amc_from_letterhead(engagement_letter: Optional[Path]) -> Optional[str]:
    """Best-effort letterhead match. Full AMC fingerprinting (SHALqc.md §6) is
    out of scope here — this only recognizes an amc_code if it is literally
    present as an "AMC:"-style token in the engagement letter text; anything
    else is deferred to the `_base` profile fallback."""
    if not engagement_letter:
        return None
    text = _pdf_text_sample(engagement_letter, max_pages=1)
    import re
    m = re.search(r"\bamc\s*(?:code|id)?\s*[:#]\s*([A-Z0-9\-]{3,20})\b", text, re.I)
    return m.group(1).upper() if m else None


def _is_archive_artifact(path: Path) -> bool:
    """Junk a macOS-created zip carries alongside the real documents.

    2026-07-18: `__MACOSX/…/._445 Sparrow Way.pdf` (an AppleDouble resource fork,
    a few KB of binary metadata) was being classified as a real document. It is
    not a readable PDF, so `_pdf_page_count` returns 0, the `pages <= 3` rule
    fires, and the junk file CLAIMED THE ENGAGEMENT-LETTER SLOT — the engagement
    stage then failed to open it and every "must match the engagement letter"
    check for that order silently lost its counterpart. Same failure class as the
    ESNC-0006152 misclassification, from the opposite direction.

    Also covers Windows `Thumbs.db` / `desktop.ini` and generic dotfiles, none of
    which are ever order documents.
    """
    if "__MACOSX" in path.parts:
        return True
    name = path.name
    return (name.startswith("._")            # AppleDouble resource fork
            or name.startswith(".")          # any dotfile (.DS_Store, …)
            or name.lower() in {"thumbs.db", "desktop.ini"})


def assemble_order(order_dir) -> OrderDocuments:
    """Classify every file in `order_dir` as one order (§3.1.4: folder
    boundary = order boundary — never a filename stem)."""
    order_dir = Path(order_dir)
    order = OrderDocuments(order_dir=order_dir)

    manifest = _read_manifest(order_dir)
    order.amc_code = manifest.get("amc_code")
    order.order_id = manifest.get("order_id") or order_dir.name
    order.revision_flag = bool(manifest.get("revision_flag", False))

    for path in sorted(order_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("manifest."):
            continue
        if _is_archive_artifact(path):
            continue
        kind = classify_file(path)
        if kind == "appraisal_pdf" and order.appraisal_pdf is None:
            order.appraisal_pdf = path
        elif kind == "mismo_xml" and order.xml is None:
            order.xml = path
        elif kind == "engagement_letter" and order.engagement_letter is None:
            order.engagement_letter = path
        elif kind == "contract" and order.contract is None:
            order.contract = path
        else:
            order.unclassified.append(path)

    if not order.amc_code:
        # Dynamic AMC resolution (no engine hardcoding): let any profile that
        # declares a `resolve` block self-select from the engagement text or the
        # order-id prefix. Falls back to the letterhead regex, then `_base`.
        eng_text = _pdf_text_sample(order.engagement_letter, max_pages=1) if order.engagement_letter else ""
        from app.profiles.loader import profile_loader
        order.amc_code = (profile_loader.resolve_amc(eng_text, order.order_id or "")
                          or _amc_from_letterhead(order.engagement_letter))

    order.package_hash = package_sha256(order_dir)   # §14 G-3 idempotency key

    if order.appraisal_pdf:                            # CORE §9 vendor detection
        try:
            from app.extraction.template_positions import detect_vendor
            order.vendor = detect_vendor(order.appraisal_pdf)
        except Exception:
            order.vendor = "unknown"

    apply_g0_gate(order)
    if order.status == "OK":
        apply_g1_pdf_gate(order)       # encrypted/corrupt PDF (zip-level G-1 is in safe_extract_zip)
    if order.status == "OK":
        apply_g2_xml_gate(order)       # XML-belongs-to-report → maybe disable overlay
    return order


def apply_g0_gate(order: OrderDocuments) -> OrderDocuments:
    """SHALqc.md §3.1.3 — non-overridable HOLD/BLOCKED gate.

    Missing appraisal PDF, or an unparseable XML when an XML file IS present
    in the package (i.e. the order is "XML-expected" but the XML is broken),
    blocks the order. A package with no XML at all is not a G-0 failure —
    PDF-only orders are a supported degraded mode (SHALqc.md P3/P6).
    """
    if order.appraisal_pdf is None:
        order.status = "BLOCKED"
        order.hold_reason = "blocked_missing_doc: appraisal PDF not found in order package"
        return order

    xml_candidates = [p for p in order.unclassified if p.suffix.lower() == ".xml"]
    if order.xml is None and xml_candidates:
        order.status = "BLOCKED"
        order.hold_reason = "blocked_missing_doc: XML present but not parseable as MISMO 2.6"
        return order

    order.status = "OK"
    order.hold_reason = None
    return order


def apply_g1_pdf_gate(order: OrderDocuments) -> OrderDocuments:
    """§14 G-1 — an encrypted/corrupt appraisal PDF blocks the run rather than
    crashing extraction downstream (never a 5xx)."""
    if order.appraisal_pdf and _is_pdf_encrypted(order.appraisal_pdf):
        order.status = "BLOCKED"
        order.hold_reason = "pdf_unreadable: appraisal PDF is encrypted or corrupt"
    return order


def apply_g2_xml_gate(order: OrderDocuments) -> OrderDocuments:
    """§14 G-2 — the XML must belong to THIS report. Compare the XML subject
    ADDRESS and BORROWER (separately) against a direct read of the PDF's form
    pages; the overlay is kept if EITHER clears the 0.8 token-overlap floor
    ("on at least one of the two", §14). Only when NEITHER clears it is the XML
    overlay DISABLED (PDF-only mode) so a wrong-order XML never poisons the
    merge. Soft-degrade (not a BLOCK): the report still runs on the PDF alone.
    """
    if order.xml is None or order.appraisal_pdf is None:
        return order
    try:
        from app.extraction.xml_extractor import extract_xml
        xfs = extract_xml(order.xml)
        addr_tokens = _tokens(" ".join(filter(None, [
            xfs.value("property_address"), xfs.value("city"), xfs.value("zip_code")])))
        borrower_tokens = _tokens(xfs.value("borrower_name") or "")
        # sample the form pages (1-3) — a cover page can push the subject block
        # off page 1, so a single-page read spuriously fails valid orders.
        pdf_tokens = _tokens(_pdf_text_sample(order.appraisal_pdf, max_pages=3))

        def _overlap(toks):
            return (len(toks & pdf_tokens) / len(toks)) if toks else 0.0

        addr_ov, borr_ov = _overlap(addr_tokens), _overlap(borrower_tokens)
        best = max(addr_ov, borr_ov)
        if not addr_tokens and not borrower_tokens:
            return order   # nothing to check → leave XML enabled
        if best < _XML_MATCH_FLOOR:
            order.xml_overlay_disabled = True
            order.hold_reason = (order.hold_reason or "") + (
                f" xml_document_mismatch: XML/report overlap (addr {addr_ov:.2f}, "
                f"borrower {borr_ov:.2f}) < {_XML_MATCH_FLOOR} — XML overlay disabled (PDF-only).")
            logger.warning("G-2: XML overlay disabled for %s (addr %.2f, borrower %.2f)",
                           order.order_id, addr_ov, borr_ov)
    except Exception as exc:
        logger.warning("G-2 gate could not evaluate for %s: %s — leaving XML enabled", order.order_id, exc)
    return order


def _tokens(text: str) -> set:
    import re
    return {t for t in re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split() if len(t) > 1}
