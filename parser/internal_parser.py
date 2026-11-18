"""
Internal marks PDF parser for the ANSORA Mark Processing System.

Extracts registration numbers and internal marks from Student Examination
Eligibility Details reports.

Supported denominators: 50, 75 and 100.
Marks are returned exactly as printed; no rescaling is performed.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# PyMuPDF's preferred import is ``pymupdf``. The ``fitz`` fallback keeps
# compatibility with environments that expose only the older module name.
try:
    import pymupdf
except ImportError:  # pragma: no cover - depends on installed PyMuPDF version
    import fitz as pymupdf


SUPPORTED_DENOMINATORS = {50, 75, 100}

# Examples: CEC19CS001, CEC23CS057, LCEC23CS122
REGISTER_RE = re.compile(
    r"(?<![A-Z0-9])L?CEC\d{2}[A-Z]{2}\d{3}(?![A-Z0-9])",
    re.IGNORECASE,
)

# Supports the labels found in different versions of the report:
#   Internals : 36.0/50
#   Internal : 36.0/50
#   Internal Mark : 36.0/50
#   Internal Marks : 36.0/50
#   Internal Marks
#   : 36.0/50
INTERNAL_MARK_RE = re.compile(
    r"\b(?:internals?|internal\s+marks?)\s*:?\s*"
    r"([0-9]+(?:\.[0-9]+)?)\s*/\s*(50|75|100)\b",
    re.IGNORECASE,
)

HEADER_RE = re.compile(
    r"\bstudents?\s+examination\s+eligibility\s+details\b",
    re.IGNORECASE,
)


class InternalPDFError(ValueError):
    """Raised when an internal marks PDF cannot be parsed reliably."""


def _validate_pdf_path(pdf_path: str | Path) -> Path:
    """Validate the uploaded path before opening the PDF."""
    path = Path(pdf_path)

    if not path.exists():
        raise InternalPDFError(f"PDF file not found: {path}")

    if not path.is_file():
        raise InternalPDFError(f"The supplied path is not a file: {path}")

    if path.suffix.lower() != ".pdf":
        raise InternalPDFError("The uploaded internal marks file must be a PDF.")

    return path


def _read_pdf_text(pdf_path: str | Path) -> str:
    """Extract selectable text from all pages of the PDF."""
    path = _validate_pdf_path(pdf_path)

    try:
        with pymupdf.open(path) as document:
            if len(document) == 0:
                raise InternalPDFError("The uploaded PDF contains no pages.")

            page_texts = []
            for page in document:
                page_text = page.get_text("text") or ""
                if page_text.strip():
                    page_texts.append(page_text)

    except InternalPDFError:
        raise
    except Exception as exc:
        raise InternalPDFError(
            f"Could not open or read the PDF: {exc}"
        ) from exc

    text = "\n".join(page_texts)
    return text.replace("\xa0", " ").replace("\r", "\n")


def _normalize_text(text: str) -> str:
    """Collapse whitespace so labels and values split over lines still match."""
    text = text.replace("\xa0", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _clean_registration_number(value: str) -> str:
    """Normalize registration numbers to uppercase without embedded spaces."""
    return re.sub(r"\s+", "", value or "").upper()


def _clean_mark(value: str) -> int | float:
    """Convert a mark string to an integer or float."""
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise InternalPDFError(f"Invalid internal mark value: {value!r}") from exc

    if not math.isfinite(number):
        raise InternalPDFError(f"Invalid internal mark value: {value!r}")

    return int(number) if number.is_integer() else number


def _is_internal_report(text: str) -> bool:
    """Accept both singular/plural report titles and both internal field names."""
    normalized = _normalize_text(text)

    has_title = bool(HEADER_RE.search(normalized))
    has_registration_label = bool(
        re.search(r"\bRegister\s*No\s*:", normalized, re.IGNORECASE)
    )
    has_internal_label = bool(
        re.search(
            r"\b(?:Internals?|Internal\s+Marks?)\b",
            normalized,
            re.IGNORECASE,
        )
    )

    return has_title and has_registration_label and has_internal_label


def _extract_by_student_blocks(
    text: str,
) -> Dict[str, Tuple[int | float, int]]:
    """
    Extract one internal mark from each student block.

    A block starts at a registration number and ends immediately before the
    next registration number. This supports the PDF layout where the
    registration number, the 'Internals :' label, and the mark are on
    separate lines or in separate table cells.
    """
    flat_text = _normalize_text(text)
    register_matches = list(REGISTER_RE.finditer(flat_text))
    records: Dict[str, Tuple[int | float, int]] = {}

    for index, register_match in enumerate(register_matches):
        reg_no = _clean_registration_number(register_match.group(0))

        block_start = register_match.end()
        block_end = (
            register_matches[index + 1].start()
            if index + 1 < len(register_matches)
            else len(flat_text)
        )
        student_block = flat_text[block_start:block_end]

        mark_match = INTERNAL_MARK_RE.search(student_block)
        if not mark_match:
            continue

        mark = _clean_mark(mark_match.group(1))
        denominator = int(mark_match.group(2))

        # Do not silently replace a duplicate registration number.
        existing = records.get(reg_no)
        current = (mark, denominator)
        if existing is not None and existing != current:
            raise InternalPDFError(
                f"Conflicting internal marks found for {reg_no}: "
                f"{existing[0]}/{existing[1]} and {mark}/{denominator}."
            )

        records[reg_no] = current

    return records


def _validate_records(
    records: Dict[str, Tuple[int | float, int]],
    expected_denominator: Optional[int] = None,
) -> Dict[str, int | float]:
    """Validate denominators and mark ranges without rescaling marks."""
    students: Dict[str, int | float] = {}
    invalid_records = {}

    for reg_no, (mark, denominator) in records.items():
        if denominator not in SUPPORTED_DENOMINATORS:
            invalid_records[reg_no] = f"{mark}/{denominator} (unsupported scale)"
            continue

        if (
            expected_denominator is not None
            and denominator != expected_denominator
        ):
            invalid_records[reg_no] = (
                f"{mark}/{denominator}; expected /{expected_denominator}"
            )
            continue

        if not isinstance(mark, (int, float)) or not math.isfinite(float(mark)):
            invalid_records[reg_no] = repr(mark)
            continue

        if mark < 0 or mark > denominator:
            invalid_records[reg_no] = f"{mark}/{denominator} (out of range)"
            continue

        students[reg_no] = mark

    if invalid_records:
        examples = ", ".join(
            f"{reg}={value}"
            for reg, value in list(invalid_records.items())[:5]
        )
        raise InternalPDFError(
            "Invalid internal mark(s) detected. Check the marks and selected "
            f"assessment type. Examples: {examples}"
        )

    return students


def extract_internal_marks(
    pdf_path: str | Path,
    expected_denominator: Optional[int] = None,
) -> Dict[str, int | float]:
    """
    Extract a mapping of registration number to printed internal mark.

    Args:
        pdf_path: Path to the internal marks PDF.
        expected_denominator: Optional selected assessment scale (50, 75, 100).

    Returns:
        Example: {"CEC19CS001": 36, "CEC19CS002": 36}
    """
    if (
        expected_denominator is not None
        and expected_denominator not in SUPPORTED_DENOMINATORS
    ):
        raise InternalPDFError(
            "Expected denominator must be 50, 75 or 100."
        )

    text = _read_pdf_text(pdf_path)

    if not _is_internal_report(text):
        raise InternalPDFError(
            "This PDF does not appear to be a Student Examination Eligibility "
            "Details report. Please upload the correct internal marks PDF."
        )

    records = _extract_by_student_blocks(text)

    if not records:
        raise InternalPDFError(
            "No registration numbers with supported internal marks "
            "(out of 50, 75 or 100) were found in the PDF. "
            "The report may use an unsupported layout or may be image-only."
        )

    students = _validate_records(
        records,
        expected_denominator=expected_denominator,
    )

    if not students:
        raise InternalPDFError("No valid student internal marks were found in the PDF.")

    return students


def extract_internal_records(
    pdf_path: str | Path,
    expected_denominator: Optional[int] = None,
) -> List[dict]:
    """Return extracted marks as a list of {reg_no, internal_mark} records."""
    mapping = extract_internal_marks(
        pdf_path,
        expected_denominator=expected_denominator,
    )

    return [
        {"reg_no": reg_no, "internal_mark": mark}
        for reg_no, mark in mapping.items()
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) not in (2, 3):
        print(
            "Usage:\n"
            "python internal_parser.py <internal_pdf_path> [50|75|100]"
        )
        raise SystemExit(1)

    pdf_file = sys.argv[1]
    selected_denominator = None

    if len(sys.argv) == 3:
        try:
            selected_denominator = int(sys.argv[2])
        except ValueError:
            print("ERROR: Denominator must be 50, 75 or 100.")
            raise SystemExit(1)

    try:
        extracted = extract_internal_marks(
            pdf_file,
            expected_denominator=selected_denominator,
        )
        print(f"\nSuccessfully extracted {len(extracted)} students.\n")
        for reg_no, mark in extracted.items():
            print(f"{reg_no} -> {mark}")

    except InternalPDFError as exc:
        print(f"\nERROR: {exc}")
        raise SystemExit(1)
