"""
Internal marks PDF parser for the ANSORA Mark Processing System.

Supports internal marks out of 50, 75 and 100.
Extracted marks are not rescaled.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF


# =========================================================
# REGULAR EXPRESSIONS
# =========================================================

REGISTER_RE = re.compile(
    r"\bL?CEC\d{2}[A-Z]{2}\d{3}\b",
    re.IGNORECASE,
)

INTERNAL_RE = re.compile(
    r"\bInternals?\s*:\s*"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"\s*/\s*"
    r"(50|75|100)\b",
    re.IGNORECASE,
)

REGISTER_TO_INTERNAL_RE = re.compile(
    r"\bRegister\s*No\s*:\s*"
    r"(L?CEC\d{2}[A-Z]{2}\d{3})\b"
    r".{0,700}?"
    r"\bInternals?\s*:\s*"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"\s*/\s*"
    r"(50|75|100)\b",
    re.IGNORECASE | re.DOTALL,
)

HEADER_MARKERS = (
    "Students Examination Eligibility Details",
    "Student Examination Eligibility Details",
)


# =========================================================
# CUSTOM EXCEPTION
# =========================================================

class InternalPDFError(ValueError):
    """Raised when an internal marks PDF cannot be parsed."""


# =========================================================
# PDF HELPERS
# =========================================================

def _validate_pdf_path(pdf_path: str | Path) -> Path:

    path = Path(pdf_path)

    if not path.exists():
        raise InternalPDFError(
            f"PDF file not found: {path}"
        )

    if not path.is_file():
        raise InternalPDFError(
            f"The supplied path is not a file: {path}"
        )

    if path.suffix.lower() != ".pdf":
        raise InternalPDFError(
            "The uploaded internal marks file must be a PDF."
        )

    return path


def _read_pdf_text(pdf_path: str | Path) -> str:

    path = _validate_pdf_path(pdf_path)

    try:

        with fitz.open(path) as document:

            pages = []

            for page in document:

                page_text = page.get_text("text")

                if page_text:
                    pages.append(page_text)

    except Exception as exc:

        raise InternalPDFError(
            f"Could not open/read the PDF: {exc}"
        ) from exc

    text = "\n".join(pages)

    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")

    return text


# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def _clean_registration_number(value: str) -> str:

    return re.sub(
        r"\s+",
        "",
        value or ""
    ).upper()


def _clean_mark(value: str) -> int | float:

    try:

        number = float(
            value.replace(",", "").strip()
        )

    except (TypeError, ValueError) as exc:

        raise InternalPDFError(
            f"Invalid internal mark value: {value!r}"
        ) from exc

    if number.is_integer():
        return int(number)

    return number


def _is_internal_report(text: str) -> bool:

    lowered = text.lower()

    has_title = any(
        marker.lower() in lowered
        for marker in HEADER_MARKERS
    )

    has_register_number = "register no" in lowered

    has_internal_field = (
        "internals" in lowered or
        "internal :" in lowered
    )

    return (
        has_title
        and has_register_number
        and has_internal_field
    )


# =========================================================
# PRIMARY PARSER
# =========================================================

def _extract_with_structured_regex(
    text: str,
) -> Dict[str, Tuple[int | float, int]]:

    flat_text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    records = {}

    for match in REGISTER_TO_INTERNAL_RE.finditer(flat_text):

        reg_no = _clean_registration_number(
            match.group(1)
        )

        internal_mark = _clean_mark(
            match.group(2)
        )

        denominator = int(
            match.group(3)
        )

        records.setdefault(
            reg_no,
            (internal_mark, denominator)
        )

    return records


# =========================================================
# FALLBACK PARSER
# =========================================================

def _extract_by_student_blocks(
    text: str,
) -> Dict[str, Tuple[int | float, int]]:

    flat_text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    register_matches = list(
        REGISTER_RE.finditer(flat_text)
    )

    records = {}

    for index, match in enumerate(register_matches):

        reg_no = _clean_registration_number(
            match.group(0)
        )

        start = match.end()

        if index + 1 < len(register_matches):
            end = register_matches[index + 1].start()
        else:
            end = len(flat_text)

        student_block = flat_text[start:end]

        internal_match = INTERNAL_RE.search(
            student_block
        )

        if not internal_match:
            continue

        internal_mark = _clean_mark(
            internal_match.group(1)
        )

        denominator = int(
            internal_match.group(2)
        )

        records.setdefault(
            reg_no,
            (internal_mark, denominator)
        )

    return records


# =========================================================
# VALIDATE EXTRACTED MARKS
# =========================================================

def _validate_records(
    records: Dict[str, Tuple[int | float, int]],
) -> Dict[str, int | float]:

    supported_denominators = {
        50,
        75,
        100
    }

    invalid_records = {}

    students = {}

    for reg_no, (mark, denominator) in records.items():

        if denominator not in supported_denominators:

            invalid_records[reg_no] = (
                f"{mark}/{denominator}"
            )

            continue

        if not isinstance(mark, (int, float)):

            invalid_records[reg_no] = mark

            continue

        if mark < 0 or mark > denominator:

            invalid_records[reg_no] = (
                f"{mark}/{denominator}"
            )

            continue

        students[reg_no] = mark

    if invalid_records:

        sample = ", ".join(
            f"{reg}={value}"
            for reg, value in list(
                invalid_records.items()
            )[:5]
        )

        raise InternalPDFError(
            "Invalid internal mark(s) detected. "
            "Marks must be between 0 and the denominator "
            f"printed in the PDF. Examples: {sample}"
        )

    return students


# =========================================================
# PUBLIC API
# =========================================================

def extract_internal_marks(
    pdf_path: str | Path,
) -> Dict[str, int | float]:

    text = _read_pdf_text(pdf_path)

    if not _is_internal_report(text):

        raise InternalPDFError(
            "This PDF does not appear to be a Student Examination "
            "Eligibility Details report."
        )

    # Primary parser
    records = _extract_with_structured_regex(text)

    # Fallback parser
    if not records:

        records = _extract_by_student_blocks(text)

    if not records:

        raise InternalPDFError(
            "No registration numbers with supported internal marks "
            "(out of 50, 75 or 100) were found in the PDF."
        )

    students = _validate_records(records)

    if not students:

        raise InternalPDFError(
            "No valid student internal marks were found in the PDF."
        )

    return students


# =========================================================
# CONVENIENCE HELPER
# =========================================================

def extract_internal_records(
    pdf_path: str | Path,
) -> List[dict]:

    mapping = extract_internal_marks(pdf_path)

    return [
        {
            "reg_no": reg_no,
            "internal_mark": mark
        }

        for reg_no, mark in mapping.items()
    ]


# =========================================================
# COMMAND LINE TESTING
# =========================================================

if __name__ == "__main__":

    import sys

    if len(sys.argv) != 2:

        print(
            "Usage:\n"
            "python internal_parser.py <internal_pdf_path>"
        )

        raise SystemExit(1)

    try:

        data = extract_internal_marks(
            sys.argv[1]
        )

        print(
            f"\nSuccessfully extracted "
            f"{len(data)} students.\n"
        )

        for reg_no, mark in data.items():

            print(
                f"{reg_no} -> {mark}"
            )

    except InternalPDFError as exc:

        print(
            f"\nERROR: {exc}"
        )

        raise SystemExit(1)