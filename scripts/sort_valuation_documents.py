#!/usr/bin/env python3
"""Sort appraisal package PDFs into appraisal/contract/engagement folders.

The classifier reads only the first few pages of each PDF. It prefers embedded
PDF text and falls back to OpenCV-preprocessed Tesseract OCR when a document is
image-only or the extracted text is too thin to classify confidently.
"""

from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz
import numpy as np
import pytesseract


CATEGORIES = ("appraisal", "contract", "engagement")
MIN_EMBEDDED_WORDS = 40
RENDER_ZOOM = 2.0


@dataclass
class Classification:
    category: str
    confidence: int
    reason: str
    used_ocr: bool


@dataclass
class PdfRead:
    text: str
    used_ocr: bool


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+", text or ""))


def extract_embedded_text(pdf_path: Path, page_limit: int) -> tuple[str, int]:
    pieces: list[str] = []
    with fitz.open(pdf_path) as doc:
        pages = min(page_limit, len(doc))
        for index in range(pages):
            pieces.append(doc[index].get_text("text") or "")
    return "\n".join(pieces), pages


def read_pdf_text(pdf_path: Path, page_limit: int) -> PdfRead:
    embedded, _ = extract_embedded_text(pdf_path, page_limit)
    if word_count(embedded) >= MIN_EMBEDDED_WORDS:
        return PdfRead(embedded, False)
    return PdfRead(embedded + "\n" + ocr_first_pages(pdf_path, page_limit), True)


def ocr_first_pages(pdf_path: Path, page_limit: int) -> str:
    pieces: list[str] = []
    matrix = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)

    with fitz.open(pdf_path) as doc:
        for index in range(min(page_limit, len(doc))):
            pix = doc[index].get_pixmap(matrix=matrix, alpha=False)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
            gray = cv2.medianBlur(gray, 3)
            gray = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )[1]
            pieces.append(pytesseract.image_to_string(gray, config="--psm 6"))

    return "\n".join(pieces)


def score_text(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    haystack = normalize(text)
    scores = {category: 0 for category in CATEGORIES}
    hits = {category: [] for category in CATEGORIES}

    rules: dict[str, list[tuple[str, int, str]]] = {
        "engagement": [
            ("equity solutions usa, inc", 8, "Equity Solutions order header"),
            ("file id:", 6, "file id"),
            ("assigned:", 4, "assigned date"),
            ("service fee:", 4, "service fee"),
            ("lender specific instructions", 5, "lender instructions"),
            ("appraisal engagement letter", 6, "engagement letter"),
            ("order information", 8, "order information"),
            ("order number:", 6, "order number"),
            ("order type:", 5, "order type"),
            ("vendor`s fee", 4, "vendor fee"),
            ("vendor's fee", 4, "vendor fee"),
            ("assigned on:", 4, "assigned on"),
            ("borrower information", 4, "borrower information"),
        ],
        "appraisal": [
            ("appraisal of real property", 10, "appraisal cover"),
            ("uniform residential appraisal report", 10, "URAR"),
            ("form 1004", 8, "1004 form"),
            ("form 1073", 8, "1073 form"),
            ("1004uad", 7, "1004UAD"),
            ("total appraisal software", 8, "TOTAL software"),
            ("a la mode", 5, "a la mode"),
            ("opinion of value", 6, "opinion of value"),
            ("subject contract neighborhood site improvements", 7, "URAR sections"),
            ("appraisal update and/or completion report", 10, "1004D update"),
            ("appraiser's certification", 6, "certification"),
            ("uniform standards of professional appraisal practice", 5, "USPAP"),
            ("the statements of fact contained in this report are true", 5, "certification text"),
            ("lender case no.", 3, "lender case number"),
        ],
        "contract": [
            ("residential contract for sale and purchase", 10, "residential contract"),
            ("one to four family residential contract", 10, "TREC contract"),
            ("purchase agreement", 10, "purchase agreement"),
            ("seller agrees to sell", 8, "seller agrees to sell"),
            ("buyer agrees to buy", 8, "buyer agrees to buy"),
            ("seller shall sell and buyer shall buy", 8, "sale and purchase terms"),
            ("purchase of unit", 7, "purchase of unit"),
            ("property description", 5, "property description"),
            ("sales price", 5, "sales price"),
            ("cash portion of sales price", 6, "cash portion"),
            ("florida realtors", 4, "Florida Realtors"),
            ("texas real estate commission", 6, "TREC"),
            ("docusign envelope id", 3, "Docusign"),
            ("dotloop signature verification", 4, "dotloop"),
            ("condominium documents", 5, "condominium documents"),
        ],
    }

    for category, category_rules in rules.items():
        for needle, weight, label in category_rules:
            if needle in haystack:
                scores[category] += weight
                hits[category].append(label)

    return scores, hits


def classify_pdf(pdf_path: Path, page_limit: int) -> Classification:
    embedded, _ = extract_embedded_text(pdf_path, page_limit)
    scores, hits = score_text(embedded)
    used_ocr = False

    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]
    enough_text = word_count(embedded) >= MIN_EMBEDDED_WORDS

    if best_score < 8 or not enough_text:
        ocr_text = ocr_first_pages(pdf_path, page_limit)
        ocr_scores, ocr_hits = score_text(embedded + "\n" + ocr_text)
        scores = ocr_scores
        hits = ocr_hits
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        used_ocr = True

    if best_score <= 0:
        return Classification("unknown", 0, "no matching document markers", used_ocr)

    reasons = ", ".join(hits[best_category][:3]) or "keyword score"
    return Classification(best_category, best_score, reasons, used_ocr)


def unique_destination(destination: Path, source: Path | None = None) -> Path:
    if source and destination.exists():
        try:
            if destination.samefile(source):
                return destination
        except FileNotFoundError:
            pass

    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def compact_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def clean_address_candidate(address: str) -> str:
    address = re.sub(r"\s+", " ", address or "").strip(" ,.;:-")
    address = re.sub(r"\bMap Link\b", "", address, flags=re.IGNORECASE).strip(" ,.;:-")
    address = re.sub(r"\(\s*Additional Resources\s*\)", "", address, flags=re.IGNORECASE)

    if "," in address:
        address = address.split(",", 1)[0]

    address = re.sub(r"\s+\d{5}(?:-\d{4})?\s*$", "", address).strip(" ,.;:-")
    address = re.sub(r"\s+(?:county)\b.*$", "", address, flags=re.IGNORECASE)
    return format_street_address(address)


def format_street_address(address: str) -> str:
    address = re.sub(r"\s+", " ", address or "").strip(" ,.;:-")
    if not address:
        return ""

    suffixes = {
        "aly": "Aly",
        "avenue": "Ave",
        "ave": "Ave",
        "boulevard": "Blvd",
        "blvd": "Blvd",
        "circle": "Cir",
        "cir": "Cir",
        "court": "Ct",
        "ct": "Ct",
        "drive": "Dr",
        "dr": "Dr",
        "lane": "Ln",
        "ln": "Ln",
        "parkway": "Pkwy",
        "pkwy": "Pkwy",
        "place": "Pl",
        "pl": "Pl",
        "road": "Rd",
        "rd": "Rd",
        "street": "St",
        "st": "St",
        "terrace": "Ter",
        "ter": "Ter",
        "trace": "Trace",
        "trail": "Trl",
        "trl": "Trl",
        "unit": "Unit",
        "apt": "Apt",
        "suite": "Suite",
        "ste": "Ste",
    }
    directions = {"n", "s", "e", "w", "ne", "nw", "se", "sw"}

    words = []
    for word in address.split():
        bare = re.sub(r"[^A-Za-z0-9]", "", word)
        lower = bare.lower()
        if lower in directions:
            words.append(lower.upper())
        elif lower in suffixes:
            words.append(suffixes[lower])
        elif re.fullmatch(r"\d+(?:st|nd|rd|th)", lower):
            words.append(lower[:-2] + lower[-2:])
        elif word.isupper() and len(word) <= 4 and not word.isdigit():
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:].lower())

    return " ".join(words).strip()


def sanitize_filename_part(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "Unknown Property"


def extract_property_address(text: str) -> str:
    raw = text or ""
    lines = compact_lines(raw)

    for index, line in enumerate(lines):
        if line.lower().rstrip(":") == "property":
            collected: list[str] = []
            for candidate in lines[index + 1 : index + 6]:
                lower = candidate.lower()
                if lower == "map link":
                    continue
                if lower.endswith(" county") or lower.startswith(
                    ("intended use:", "purchase price:", "property type:", "occupancy:")
                ):
                    break
                collected.append(candidate)
                if "," in candidate or looks_like_street_address(candidate):
                    break

            address = clean_address_candidate(" ".join(collected))
            if address and looks_like_street_address(address):
                return address

        if line.lower().rstrip(":") == "property address":
            collected = []
            for candidate in lines[index + 1 : index + 5]:
                lower = candidate.lower()
                if lower.startswith(("property county:", "order priority:", "uad report needed:")):
                    break
                collected.append(candidate)
                if looks_like_street_address(candidate):
                    break

            address = clean_address_candidate(" ".join(collected))
            if address and looks_like_street_address(address):
                return address

    patterns = [
        r"(?is)\bProperty Address:\s*(.+?)(?:\(\s*Additional Resources\s*\)|\n\s*Property County:|\n\s*Order Priority:)",
        r"(?is)\bProperty:\s*Map Link\s*(.+?)(?:\n\s*[A-Za-z -]+ County\b|\n\s*Intended Use:)",
        r"(?is)\bknown as\s+(.+?)(?:\s*\(address/zip code\)|\n)",
        r"(?is)\bStreet address,\s*city,\s*zip:\s*_*\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            address = clean_address_candidate(match.group(1))
            if address:
                return address

    for index, line in enumerate(lines):
        if line.lower() == "appraisal of real property":
            for candidate in lines[index + 1 : index + 5]:
                address = clean_address_candidate(candidate)
                if looks_like_street_address(address):
                    return address

    for index, line in enumerate(lines):
        if looks_like_street_address(line):
            candidate = clean_address_candidate(line)
            if candidate and index + 1 < len(lines) and re.fullmatch(r"(?:unit|apt|suite|ste)?\s*[A-Za-z0-9-]+", lines[index + 1], re.IGNORECASE):
                if not re.search(r"\b(?:FL|GA|TX|WV|MI|AZ)\b", lines[index + 1]):
                    candidate = format_street_address(f"{candidate} Unit {lines[index + 1]}")
            return candidate

    return ""


def looks_like_street_address(value: str) -> bool:
    return bool(
        re.search(r"\b\d{1,6}\b", value or "")
        and re.search(
            r"\b(?:aly|avenue|ave|boulevard|blvd|circle|cir|court|ct|drive|dr|lane|ln|parkway|pkwy|place|pl|road|rd|street|st|terrace|ter|trace|trail|trl)\b",
            value or "",
            re.IGNORECASE,
        )
    )


def filename_for(category: str, address: str) -> str:
    address = sanitize_filename_part(address)
    if category == "contract":
        return f"{address} CONTRACT.pdf"
    if category == "engagement":
        return f"{address} Order form.pdf"
    if category == "unknown":
        return f"{address} UNKNOWN.pdf"
    return f"{address}.pdf"


def iter_order_pdfs(root: Path) -> list[Path]:
    pdfs: list[Path] = []
    for order_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for pdf_path in sorted(order_dir.glob("*.pdf")):
            if pdf_path.parent.name not in CATEGORIES:
                pdfs.append(pdf_path)
    return pdfs


def iter_categorized_pdfs(order_dir: Path) -> list[Path]:
    pdfs: list[Path] = []
    for category in CATEGORIES + ("unknown",):
        category_dir = order_dir / category
        if category_dir.is_dir():
            pdfs.extend(sorted(category_dir.glob("*.pdf")))
    return pdfs


def category_for_path(pdf_path: Path) -> str:
    if pdf_path.parent.name in CATEGORIES or pdf_path.parent.name == "unknown":
        return pdf_path.parent.name
    return classify_pdf(pdf_path, 4).category


def best_order_address(order_dir: Path, page_limit: int) -> str:
    pdfs = iter_categorized_pdfs(order_dir) + sorted(order_dir.glob("*.pdf"))
    address_by_category: dict[str, str] = {}

    for pdf_path in pdfs:
        read = read_pdf_text(pdf_path, page_limit)
        address = extract_property_address(read.text)
        if address:
            address_by_category.setdefault(category_for_path(pdf_path), address)

    for category in ("engagement", "appraisal", "contract", "unknown"):
        if category in address_by_category:
            return address_by_category[category]

    return ""


def rename_sorted_documents(root: Path, page_limit: int, dry_run: bool) -> int:
    renamed = 0
    failures = 0

    for order_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        address = best_order_address(order_dir, page_limit)
        if not address:
            categorized = iter_categorized_pdfs(order_dir)
            if categorized:
                failures += 1
                print(f"could not find property address for {order_dir}")
            continue

        for pdf_path in list(iter_categorized_pdfs(order_dir)):
            category = pdf_path.parent.name
            destination = unique_destination(
                pdf_path.parent / filename_for(category, address),
                source=pdf_path,
            )

            if destination == pdf_path:
                continue

            action = "would rename" if dry_run else "renamed"
            print(f"{action}: {pdf_path} -> {destination}")
            renamed += 1

            if not dry_run:
                pdf_path.rename(destination)

    if renamed == 0 and failures == 0:
        print(f"No categorized PDFs needed renaming under {root}")

    return 1 if failures else 0


def sort_documents(root: Path, page_limit: int, dry_run: bool) -> int:
    if not root.exists():
        raise FileNotFoundError(f"Sort root does not exist: {root}")

    pdfs = iter_order_pdfs(root)
    if not pdfs:
        print(f"No unsorted PDFs found under {root}")
        return 0

    failures = 0
    for pdf_path in pdfs:
        classification = classify_pdf(pdf_path, page_limit)
        order_dir = pdf_path.parent
        target_dir = order_dir / classification.category

        if classification.category == "unknown":
            failures += 1
            target_dir = order_dir / "unknown"

        destination = unique_destination(target_dir / pdf_path.name, source=pdf_path)
        action = "would move" if dry_run else "moved"
        ocr_note = " with OCR" if classification.used_ocr else ""

        print(
            f"{action}: {pdf_path} -> {destination} "
            f"[{classification.category}, score={classification.confidence}{ocr_note}; "
            f"{classification.reason}]"
        )

        if not dry_run:
            target_dir.mkdir(exist_ok=True)
            shutil.move(str(pdf_path), str(destination))

    return 1 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sort valuation package PDFs into appraisal, contract, and engagement folders."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default="uploads/sort",
        type=Path,
        help="Folder containing per-order subfolders of PDFs.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=4,
        help="Number of initial pages to read/OCR from each PDF.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and print moves without changing files.",
    )
    parser.add_argument(
        "--no-rename",
        action="store_true",
        help="Only sort files into folders; do not rename categorized PDFs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sort_status = sort_documents(args.root, args.pages, args.dry_run)
    rename_status = 0
    if not args.no_rename:
        rename_status = rename_sorted_documents(args.root, args.pages, args.dry_run)
    return sort_status or rename_status


if __name__ == "__main__":
    raise SystemExit(main())
