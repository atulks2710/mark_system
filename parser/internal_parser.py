"""
Internal marks PDF parser for the ANSORA Mark Processing System.

Supports internal marks out of 50, 75 and 100.
Extracted marks are not rescaled.

Supports:
- Student Examination Eligibility Details reports
- Students Examination Eligibility Details reports
- Registration numbers on separate lines
- Internal marks on separate lines
- Registration numbers with optional leading L
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import fitz


# =========================================================
# REGULAR EXPRESSIONS
# =========================================================

# Matches registration numbers such as:
# CEC19CS001
# LCEC19CS060

REGISTER_RE = re.compile(
    r"(?<![A-Z0-9])L?CEC\d{2}[A-Z]{2}\d{3}(?![A-Z0-9])",
    re.IGNORECASE
)


# Matches:
# Internal Marks : 58.0/75
# Internal Marks
# : 58.0/75

INTERNAL_MARK_RE = re.compile(
    r"\bInternal\s+Marks?\s*:?\s*"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"\s*/\s*"
    r"(50|75|100)\b",
    re.IGNORECASE
)


# Accepts both singular and plural report titles.

HEADER_RE = re.compile(
    r"\bStudents?\s+Examination\s+Eligibility\s+Details\b",
    re.IGNORECASE
)


# =========================================================
# CUSTOM EXCEPTION
# =========================================================

class InternalPDFError(ValueError):
    """Raised when an internal marks PDF cannot be parsed."""


# =========================================================
# PDF VALIDATION
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


# =========================================================
# READ PDF TEXT
# =========================================================

def _read_pdf_text(pdf_path: str | Path) -> str:

    path = _validate_pdf_path(pdf_path)

    try:

        pages = []

        with fitz.open(path) as document:

            if len(document) == 0:

                raise InternalPDFError(
                    "The uploaded PDF contains no pages."
                )

            for page in document:

                page_text = page.get_text("text")

                if page_text:

                    pages.append(page_text)

        text = "\n".join(pages)

    except InternalPDFError:

        raise

    except Exception as exc:

        raise InternalPDFError(
            f"Could not open or read the PDF: {exc}"
        ) from exc

    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")

    return text


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def _normalize_text(text: str) -> str:

    """
    Convert multiple spaces and line breaks into single spaces.

    Example:

    Register No :
    CEC19CS001

    becomes:

    Register No : CEC19CS001
    """

    text = text.replace("\xa0", " ")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


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


# =========================================================
# REPORT VALIDATION
# =========================================================

def _is_internal_report(text: str) -> bool:

    normalized = _normalize_text(text)

    has_title = bool(
        HEADER_RE.search(normalized)
    )

    has_register_number = bool(
        re.search(
            r"\bRegister\s*No\s*:",
            normalized,
            re.IGNORECASE
        )
    )

    has_internal_marks = bool(
        re.search(
            r"\bInternal\s+Marks?\b",
            normalized,
            re.IGNORECASE
        )
    )

    return (
        has_title
        and has_register_number
        and has_internal_marks
    )


# =========================================================
# STUDENT BLOCK EXTRACTION
# =========================================================

def _extract_by_student_blocks(
    text: str,
) -> Dict[str, Tuple[int | float, int]]:

    """
    Extract student marks by identifying each registration number.

    Each student's record starts at their registration number
    and ends immediately before the next registration number.

    This handles PDFs where registration numbers and internal
    marks appear on separate lines or in separate table cells.
    """

    flat_text = _normalize_text(text)

    register_matches = list(
        REGISTER_RE.finditer(flat_text)
    )

    records: Dict[str, Tuple[int | float, int]] = {}

    if not register_matches:

        return records

    for index, register_match in enumerate(register_matches):

        # Extract registration number.

        reg_no = _clean_registration_number(
            register_match.group(0)
        )

        # Identify the current student's text block.

        start = register_match.end()

        if index + 1 < len(register_matches):

            end = register_matches[index + 1].start()

        else:

            end = len(flat_text)

        student_block = flat_text[start:end]

        # Find internal marks inside this student's block.

        internal_match = INTERNAL_MARK_RE.search(
            student_block
        )

        if not internal_match:

            continue

        # Extract mark.

        internal_mark = _clean_mark(
            internal_match.group(1)
        )

        # Extract denominator.

        denominator = int(
            internal_match.group(2)
        )

        # Store the record.

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
    expected_denominator: Optional[int] = None,
) -> Dict[str, int | float]:

    supported_denominators = {
        50,
        75,
        100
    }

    students: Dict[str, int | float] = {}

    invalid_records = {}

    for reg_no, (mark, denominator) in records.items():

        # Check supported denominator.

        if denominator not in supported_denominators:

            invalid_records[reg_no] = (
                f"{mark}/{denominator}"
            )

            continue

        # Optionally check against the selected assessment type.

        if (
            expected_denominator is not None
            and denominator != expected_denominator
        ):

            invalid_records[reg_no] = (
                f"{mark}/{denominator}; "
                f"expected /{expected_denominator}"
            )

            continue

        # Check numeric value.

        if not isinstance(mark, (int, float)):

            invalid_records[reg_no] = mark

            continue

        # Check the mark range.

        if mark < 0 or mark > denominator:

            invalid_records[reg_no] = (
                f"{mark}/{denominator}"
            )

            continue

        students[reg_no] = mark

    # Report invalid records.

    if invalid_records:

        sample = ", ".join(
            f"{reg}={value}"
            for reg, value in list(
                invalid_records.items()
            )[:5]
        )

        raise InternalPDFError(
            "Invalid internal mark(s) detected. "
            "Please check the marks and selected assessment type. "
            f"Examples: {sample}"
        )

    return students


# =========================================================
# PUBLIC API
# =========================================================

def extract_internal_marks(
    pdf_path: str | Path,
    expected_denominator: Optional[int] = None,
) -> Dict[str, int | float]:

    """
    Extract registration numbers and internal marks.

    Returns:

    {
        "CEC19CS001": 58,
        "CEC19CS002": 53,
        "CEC19CS003": 52
    }

    The original marks are retained.
    No automatic rescaling is performed.

    expected_denominator is optional.
    Set it to 50, 75 or 100 to validate the selected scale.
    """

    if (
        expected_denominator is not None
        and expected_denominator not in {50, 75, 100}
    ):

        raise InternalPDFError(
            "Expected denominator must be 50, 75 or 100."
        )

    # Read PDF.

    text = _read_pdf_text(pdf_path)

    # Validate report format.

    if not _is_internal_report(text):

        raise InternalPDFError(
            "This PDF does not appear to be a "
            "Student Examination Eligibility Details report. "
            "Please upload the correct internal marks PDF."
        )

    # Extract student records.

    records = _extract_by_student_blocks(text)

    if not records:

        raise InternalPDFError(
            "No registration numbers with supported internal "
            "marks (out of 50, 75 or 100) were found in the PDF."
        )

    # Validate extracted marks.

    students = _validate_records(
        records,
        expected_denominator=expected_denominator
    )

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
    expected_denominator: Optional[int] = None,
) -> List[dict]:

    mapping = extract_internal_marks(
        pdf_path,
        expected_denominator=expected_denominator
    )

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

        data = extract_internal_marks(
            pdf_file,
            expected_denominator=selected_denominator
        )

        print(
            f"\nSuccessfully extracted {len(data)} students.\n"
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