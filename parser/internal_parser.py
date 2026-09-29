"""
Parser for KTU Student Examination Eligibility Details PDFs.

Expected source:
    Student Examination Eligibility Details

Extracted fields:
    - Registration Number
    - Internal Mark out of 50

Example:

    Register No :
    CEC23CS003

    Internals :
    47.0/50

becomes:

    {
        "CEC23CS003": 47
    }

The parser intentionally ignores:
    - Student name
    - Attendance
    - Leaves
    - Eligibility
    - Status
    - Other columns
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------------------------

# KTU registration numbers seen in the uploaded PDFs include:
#
#   CEC23CS003
#   CEC23CS057
#   LCEC23CS122
#
# LCEC is supported because the uploaded sample contains such records.
REGISTER_RE = re.compile(
    r"\bL?CEC\d{2}[A-Z]{2}\d{3}\b",
    re.IGNORECASE,
)


# Matches:
#
#   Internals : 47.0/50
#   Internal : 47/50
#
# The PDF may have line breaks between these parts. We flatten whitespace
# before using this expression.
INTERNAL_RE = re.compile(
    r"\bInternals?\s*:\s*"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"\s*/\s*50\b",
    re.IGNORECASE,
)


# Stronger pattern that directly connects:
#
#   Register No : CEC23CS003
#   ...
#   Internals : 47.0/50
#
# We allow up to 500 characters between registration number and internal mark
# because the PDF contains attendance and other fields between them.
REGISTER_TO_INTERNAL_RE = re.compile(
    r"(?:Register\s*No\s*:\s*)"
    r"(L?CEC\d{2}[A-Z]{2}\d{3})"
    r".{0,500}?"
    r"Internals?\s*:\s*"
    r"([0-9]+(?:\.[0-9]+)?)"
    r"\s*/\s*50\b",
    re.IGNORECASE | re.DOTALL,
)


# Text normally present in KTU internal eligibility PDFs.
HEADER_MARKERS = (
    "Students Examination Eligibility Details",
    "Student Examination Eligibility Details",
)


class InternalPDFError(ValueError):
    """
    Raised when an internal-mark PDF cannot be parsed reliably.
    """



# ---------------------------------------------------------------------------
# File / PDF helpers
# ---------------------------------------------------------------------------

def _validate_pdf_path(pdf_path: str | Path) -> Path:
    """
    Validate that the supplied file exists and is a PDF.
    """

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
            "The uploaded internal-mark file must be a PDF."
        )

    return path


def _read_pdf_text(pdf_path: str | Path) -> str:
    """
    Extract selectable text from every page of the PDF.
    """

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

    # Normalize common PDF whitespace problems.
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")

    return text


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _clean_registration_number(value: str) -> str:
    """
    Normalize a registration number.

    Example:
        "CEC23CS003 " -> "CEC23CS003"
    """

    value = value or ""

    # Remove spaces accidentally inserted by PDF extraction.
    value = re.sub(r"\s+", "", value)

    return value.upper()


def _clean_mark(value: str) -> int | float:
    """
    Convert a mark string to int/float.

    Examples:
        "47.0" -> 47
        "47.5" -> 47.5
    """

    number = float(value)

    if number.is_integer():
        return int(number)

    return number


# ---------------------------------------------------------------------------
# PDF validation
# ---------------------------------------------------------------------------

def _is_internal_report(text: str) -> bool:
    """
    Check whether the PDF appears to be a KTU internal eligibility report.
    """

    lowered = text.lower()

    has_title = any(
        marker.lower() in lowered
        for marker in HEADER_MARKERS
    )

    has_register_number = "register no" in lowered

    has_internal_field = "internals" in lowered

    return (
        has_title
        and has_register_number
        and has_internal_field
    )


# ---------------------------------------------------------------------------
# Primary parser
# ---------------------------------------------------------------------------

def _extract_with_structured_regex(
    text: str,
) -> Dict[str, int | float]:
    """
    Primary parsing method.

    Whitespace is flattened first because PDF extraction may produce:

        Internals :
        47.0/50

    instead of:

        Internals : 47.0/50
    """

    flat_text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    students: Dict[str, int | float] = {}

    for match in REGISTER_TO_INTERNAL_RE.finditer(flat_text):

        reg_no = _clean_registration_number(
            match.group(1)
        )

        internal_mark = _clean_mark(
            match.group(2)
        )

        # Keep only one value per registration number.
        #
        # setdefault() avoids accidentally replacing a valid record if a
        # malformed PDF contains duplicate text extraction.
        students.setdefault(
            reg_no,
            internal_mark,
        )

    return students


# ---------------------------------------------------------------------------
# Fallback parser
# ---------------------------------------------------------------------------

def _extract_by_student_blocks(
    text: str,
) -> Dict[str, int | float]:
    """
    Fallback parser.

    It separates the PDF into student blocks using registration numbers.

    Example:

        CEC23CS003
        ...
        Internals : 47.0/50

        CEC23CS004
        ...
        Internals : 47.0/50

    Each registration number gets its own block.
    """

    flat_text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    register_matches = list(
        REGISTER_RE.finditer(flat_text)
    )

    students: Dict[str, int | float] = {}

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

        if internal_match:

            internal_mark = _clean_mark(
                internal_match.group(1)
            )

            students.setdefault(
                reg_no,
                internal_mark,
            )

    return students


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_internal_marks(
    pdf_path: str | Path,
) -> Dict[str, int | float]:
    """
    Extract registration-number -> internal-mark mapping.

    Example return:

        {
            "CEC23CS003": 47,
            "CEC23CS004": 47,
            "CEC23CS005": 46,
            "CEC23CS006": 37,
        }

    Raises:
        InternalPDFError
            If the file is invalid, is not a supported KTU report,
            or no records can be extracted.
    """

    text = _read_pdf_text(pdf_path)

    # Validate file type/content.
    if not _is_internal_report(text):
        raise InternalPDFError(
            "This PDF does not appear to be a KTU "
            "Student Examination Eligibility Details report."
        )

    # Primary parser.
    students = _extract_with_structured_regex(
        text
    )

    # Fallback parser.
    if not students:
        students = _extract_by_student_blocks(
            text
        )

    # No usable records.
    if not students:
        raise InternalPDFError(
            "No registration numbers with internal marks "
            "were found in the PDF."
        )

    # -----------------------------------------------------------------------
    # Sanity check
    # -----------------------------------------------------------------------

    invalid_records = {}

    for reg_no, mark in students.items():

        if not isinstance(mark, (int, float)):
            invalid_records[reg_no] = mark
            continue

        if mark < 0 or mark > 50:
            invalid_records[reg_no] = mark

    if invalid_records:

        sample = ", ".join(
            f"{reg}={mark}"
            for reg, mark in list(
                invalid_records.items()
            )[:5]
        )

        raise InternalPDFError(
            "Invalid internal mark(s) detected: "
            f"{sample}"
        )

    return students


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------

def extract_internal_records(
    pdf_path: str | Path,
) -> List[dict]:
    """
    Return the extracted data as a list of dictionaries.

    Useful for displaying the data on the frontend.

    Example:

        [
            {
                "reg_no": "CEC23CS003",
                "internal_mark": 47
            },
            {
                "reg_no": "CEC23CS004",
                "internal_mark": 47
            }
        ]
    """

    mapping = extract_internal_marks(
        pdf_path
    )

    return [
        {
            "reg_no": reg_no,
            "internal_mark": mark,
        }
        for reg_no, mark in mapping.items()
    ]


# ---------------------------------------------------------------------------
# Optional command-line testing
# ---------------------------------------------------------------------------

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