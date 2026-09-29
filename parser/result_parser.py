"""
Parser for KTU Result PDFs.

The teacher manually enters a course code, for example:

    CST309
    CST305
    CST303
    CST301
    CST307
    HUT300
    MCN301
    CSL331
    CSL333

The parser then:

    1. Opens the result PDF.
    2. Locates the Computer Science & Engineering section.
    3. Finds the course-code table in that section.
    4. Validates the manually entered course code.
    5. Reads CSE student result records.
    6. Extracts ONLY the selected course grade.

Examples:

    CEC23CS003 ... CST309(A) ...
        -> "A"

    CEC23CS005 ... CST309(B+) ...
        -> "B+"

    CEC23CS006 ... CST309(F) ...
        -> "F"

    CEC23CS076 ... CST309(Absent) ...
        -> "Absent"

The grade is returned exactly as present in the PDF.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Regular expressions
# ---------------------------------------------------------------------------

REGISTER_RE = re.compile(
    r"\bL?CEC\d{2}[A-Z]{2}\d{3}\b",
    re.IGNORECASE,
)


# KTU course codes in the supplied PDF include:
#
#   CST307
#   HUT300
#   CST301
#   CST303
#   CST305
#   CST309
#   MCN301
#   CSL331
#   CSL333
#
# This intentionally supports several letters before the three-digit number.
COURSE_RE = re.compile(
    r"\b[A-Z]{2,5}\d{3}\b",
    re.IGNORECASE,
)


# Branch heading in the uploaded result PDF:
#
# COMPUTER SCIENCE & ENGINEERING[Full Time]
# (Generated on ...)
#
# We also support:
#
# COMPUTER SCIENCE AND ENGINEERING[Full Time]
CSE_HEADER_RE = re.compile(
    r"(?im)^"
    r"\s*COMPUTER\s+SCIENCE\s*"
    r"(?:&|AND)\s*"
    r"ENGINEERING\s*"
    r"\[Full\s+Time\]"
    r".*$"
)


# Generic next-branch heading.
#
# This lets us stop at:
#
# ELECTRICAL AND ELECTRONICS ENGINEERING[Full Time] ...
#
# or:
#
# Artificial Intelligence and Data Science[Full Time] ...
NEXT_BRANCH_RE = re.compile(
    r"(?im)^"
    r"\s*.+"
    r"\[Full\s+Time\]"
    r"\s*\(Generated\s+on:.*$"
)


class ResultPDFError(ValueError):
    """
    Raised when a result PDF cannot be parsed reliably.
    """



# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _validate_pdf_path(
    pdf_path: str | Path,
) -> Path:
    """
    Validate result PDF path.
    """

    path = Path(pdf_path)

    if not path.exists():
        raise ResultPDFError(
            f"PDF file not found: {path}"
        )

    if not path.is_file():
        raise ResultPDFError(
            f"The supplied path is not a file: {path}"
        )

    if path.suffix.lower() != ".pdf":
        raise ResultPDFError(
            "The uploaded result file must be a PDF."
        )

    return path


def _read_pdf_text(
    pdf_path: str | Path,
) -> str:
    """
    Extract text from every result-PDF page.
    """

    path = _validate_pdf_path(
        pdf_path
    )

    try:

        with fitz.open(path) as document:

            pages = []

            for page in document:

                page_text = page.get_text(
                    "text"
                )

                if page_text:
                    pages.append(page_text)

    except Exception as exc:

        raise ResultPDFError(
            f"Could not open/read the PDF: {exc}"
        ) from exc

    text = "\n".join(pages)

    text = text.replace(
        "\xa0",
        " ",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    return text


# ---------------------------------------------------------------------------
# Course-code handling
# ---------------------------------------------------------------------------

def _normalize_course_code(
    course_code: str,
) -> str:
    """
    Normalize manually entered course code.

    Example:

        " cst309 " -> "CST309"
        "CST 309"  -> "CST309"
    """

    value = course_code or ""

    # Remove whitespace so accidental "CST 309" is accepted.
    value = re.sub(
        r"\s+",
        "",
        value,
    )

    value = value.upper()

    # Validate common KTU course-code structure.
    if not re.fullmatch(
        r"[A-Z]{2,5}\d{3}",
        value,
    ):
        raise ResultPDFError(
            "Invalid course code. "
            "Enter a code such as CST309, CST305, "
            "CST303, HUT300, or CSL331."
        )

    return value


def _clean_registration_number(
    value: str,
) -> str:
    """
    Normalize registration number.
    """

    value = value or ""

    return re.sub(
        r"\s+",
        "",
        value,
    ).upper()


# ---------------------------------------------------------------------------
# Locate the CSE branch
# ---------------------------------------------------------------------------

def _get_cse_section(
    text: str,
) -> str:
    """
    Extract only the Computer Science & Engineering section.

    Why this matters:

    The uploaded KTU result PDF contains multiple branches, including:

        Electronics & Communication Engineering
        Computer Science & Engineering
        Electrical and Electronics Engineering
        Artificial Intelligence and Data Science

    We must NOT accidentally extract a student's result from another branch.
    """

    # First try the precise heading pattern.
    start_match = CSE_HEADER_RE.search(
        text
    )

    if start_match:

        start = start_match.start()

    else:

        # Fallback for spacing/punctuation variations.
        fallback = re.search(
            r"(?is)"
            r"COMPUTER\s+SCIENCE\s*"
            r"(?:&|AND)\s*"
            r"ENGINEERING"
            r".{0,150}?"
            r"\[Full\s+Time\]",
            text,
        )

        if not fallback:

            raise ResultPDFError(
                "Computer Science & Engineering "
                "section was not found in the result PDF."
            )

        start = fallback.start()

    # Everything after CSE heading.
    cse_text = text[start:]

    # Find the next branch heading.
    next_branch_positions = []

    for match in NEXT_BRANCH_RE.finditer(
        cse_text
    ):

        # Ignore the CSE heading itself.
        if match.start() <= 0:
            continue

        next_branch_positions.append(
            match.start()
        )

    if next_branch_positions:

        end = min(
            next_branch_positions
        )

        cse_text = cse_text[:end]

    return cse_text


# ---------------------------------------------------------------------------
# Course-code list
# ---------------------------------------------------------------------------

def _get_course_area(
    cse_section: str,
) -> str:
    """
    Return the portion containing the course-code table.

    In the uploaded PDF, this appears before:

        Register No
        Course Code (Grade)
    """

    marker = re.search(
        r"(?i)\bRegister\s+No\b",
        cse_section,
    )

    if not marker:

        raise ResultPDFError(
            "Could not find the student result table "
            "inside the CSE section."
        )

    return cse_section[
        :marker.start()
    ]


def extract_result_course_codes(
    pdf_path: str | Path,
) -> List[str]:
    """
    Extract course codes listed in the CSE section.

    Example result:

        [
            "CST307",
            "HUT300",
            "CST301",
            "CST303",
            "CST305",
            "CST309",
            "MCN301",
            "CSL331",
            "CSL333"
        ]
    """

    text = _read_pdf_text(
        pdf_path
    )

    cse_section = _get_cse_section(
        text
    )

    course_area = _get_course_area(
        cse_section
    )

    codes: List[str] = []

    for match in COURSE_RE.finditer(
        course_area
    ):

        code = match.group(
            0
        ).upper()

        if code not in codes:
            codes.append(code)

    return codes


def _validate_course_code_in_section(
    cse_section: str,
    course_code: str,
) -> None:
    """
    Confirm that the manually entered course code exists
    in the CSE course list.
    """

    course_area = _get_course_area(
        cse_section
    )

    listed_codes = {
        match.group(0).upper()
        for match in COURSE_RE.finditer(
            course_area
        )
    }

    if course_code not in listed_codes:

        available = ", ".join(
            sorted(listed_codes)
        )

        raise ResultPDFError(
            f"Course code {course_code} was not found "
            "in the Computer Science & Engineering "
            f"section.\n\n"
            f"Available course codes: {available}"
        )


# ---------------------------------------------------------------------------
# Student blocks
# ---------------------------------------------------------------------------

def _extract_student_blocks(
    cse_section: str,
) -> List[Tuple[str, str]]:
    """
    Split the CSE result section into student records.

    Example:

        CEC23CS003
        MCN301(B), CST301(A+), CST303(B+),
        CST305(B+), CST307(C+), CST309(A),
        CSL331(B), CSL333(S)

    becomes:

        (
            "CEC23CS003",
            "MCN301(B), CST301(A+), ... CST309(A), ..."
        )
    """

    matches = list(
        REGISTER_RE.finditer(
            cse_section
        )
    )

    if not matches:

        raise ResultPDFError(
            "No CSE registration numbers were found "
            "in the result PDF."
        )

    blocks: List[
        Tuple[str, str]
    ] = []

    for index, match in enumerate(
        matches
    ):

        reg_no = _clean_registration_number(
            match.group(0)
        )

        start = match.end()

        if index + 1 < len(matches):

            end = matches[
                index + 1
            ].start()

        else:

            end = len(
                cse_section
            )

        student_text = cse_section[
            start:end
        ]

        blocks.append(
            (
                reg_no,
                student_text,
            )
        )

    return blocks


# ---------------------------------------------------------------------------
# Grade extraction
# ---------------------------------------------------------------------------

def _extract_grade_from_block(
    student_text: str,
    course_code: str,
) -> str | None:
    """
    Find:

        CST309(A)
        CST309(B+)
        CST309(F)
        CST309(Absent)

    and return the value inside parentheses.
    """

    grade_pattern = re.compile(
        rf"\b{re.escape(course_code)}"
        rf"\s*\(([^)]*)\)",
        re.IGNORECASE,
    )

    match = grade_pattern.search(
        student_text
    )

    if not match:
        return None

    grade = match.group(
        1
    ).strip()

    if not grade:
        return None

    return grade


# ---------------------------------------------------------------------------
# Main public parser
# ---------------------------------------------------------------------------

def extract_result_grades(
    pdf_path: str | Path,
    course_code: str,
) -> Dict[str, str]:
    """
    Extract registration-number -> selected-course-grade mapping.

    The teacher manually provides course_code.

    Example:

        grades = extract_result_grades(
            "S5 Result-CEC.pdf",
            "CST309"
        )

        grades["CEC23CS003"]
            -> "A"

        grades["CEC23CS005"]
            -> "B+"

        grades["CEC23CS006"]
            -> "F"

    Notes:
        - Course code is NOT automatically selected.
        - Course code is normalized only for formatting.
        - Grades are preserved as written:
            A
            A+
            B+
            C
            C+
            D
            P
            F
            S
            Absent
    """

    # -----------------------------------------------------------------------
    # Step 1: normalize teacher's input
    # -----------------------------------------------------------------------

    course_code = _normalize_course_code(
        course_code
    )

    # -----------------------------------------------------------------------
    # Step 2: read PDF
    # -----------------------------------------------------------------------

    text = _read_pdf_text(
        pdf_path
    )

    # -----------------------------------------------------------------------
    # Step 3: locate CSE section
    # -----------------------------------------------------------------------

    cse_section = _get_cse_section(
        text
    )

    # -----------------------------------------------------------------------
    # Step 4: validate manual course code
    # -----------------------------------------------------------------------

    _validate_course_code_in_section(
        cse_section,
        course_code,
    )

    # -----------------------------------------------------------------------
    # Step 5: split CSE student records
    # -----------------------------------------------------------------------

    student_blocks = _extract_student_blocks(
        cse_section
    )

    grades: Dict[str, str] = {}

    duplicate_registration_numbers = set()

    # -----------------------------------------------------------------------
    # Step 6: extract only selected course
    # -----------------------------------------------------------------------

    for reg_no, student_text in student_blocks:

        grade = _extract_grade_from_block(
            student_text,
            course_code,
        )

        if reg_no in grades:

            duplicate_registration_numbers.add(
                reg_no
            )

            # Keep first valid extracted value.
            continue

        if grade is not None:

            grades[reg_no] = grade

    # -----------------------------------------------------------------------
    # Step 7: duplicate validation
    # -----------------------------------------------------------------------

    if duplicate_registration_numbers:

        duplicates = ", ".join(
            sorted(
                duplicate_registration_numbers
            )
        )

        raise ResultPDFError(
            "Duplicate registration number(s) found "
            f"in the CSE result section: {duplicates}"
        )

    # -----------------------------------------------------------------------
    # Step 8: no grades found
    # -----------------------------------------------------------------------

    if not grades:

        raise ResultPDFError(
            f"Course code {course_code} was found, "
            "but no student grades for it could be extracted."
        )

    return grades


# ---------------------------------------------------------------------------
# Optional detailed parser
# ---------------------------------------------------------------------------

def extract_result_records(
    pdf_path: str | Path,
    course_code: str,
) -> List[dict]:
    """
    Convenience helper for frontend usage.

    Returns:

        [
            {
                "reg_no": "CEC23CS003",
                "grade": "A"
            },
            ...
        ]
    """

    grades = extract_result_grades(
        pdf_path,
        course_code,
    )

    return [
        {
            "reg_no": reg_no,
            "grade": grade,
        }
        for reg_no, grade in grades.items()
    ]


# ---------------------------------------------------------------------------
# Optional command-line testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    import sys

    if len(sys.argv) != 3:

        print(
            "Usage:\n"
            "python result_parser.py "
            "<result_pdf_path> <course_code>\n\n"
            "Example:\n"
            "python result_parser.py "
            "\"S5 Result-CEC.pdf\" CST309"
        )

        raise SystemExit(1)

    pdf_path = sys.argv[1]
    course_code = sys.argv[2]

    try:

        # Show available courses first.
        codes = extract_result_course_codes(
            pdf_path
        )

        print(
            "\nCSE course codes found:"
        )

        print(
            ", ".join(codes)
        )

        # Process manually selected course.
        grades = extract_result_grades(
            pdf_path,
            course_code,
        )

        print(
            f"\nSuccessfully extracted "
            f"{len(grades)} grades for "
            f"{course_code.upper()}.\n"
        )

        # Print first 20 records.
        for reg_no, grade in list(
            grades.items()
        )[:20]:

            print(
                f"{reg_no} -> {grade}"
            )

    except ResultPDFError as exc:

        print(
            f"\nERROR: {exc}"
        )

        raise SystemExit(1)