"""
Result PDF parser for the ANSORA Mark Processing System.

Supports multi-branch university result PDFs. Course-code suggestions are
collected from every department section, and a manually entered course code
is extracted from every section in which that code is listed.

This lets the application process EC, CS, EE and other departments from the
same result PDF. Common courses appearing in multiple branches are collected
from all matching sections; the matcher then joins grades to the uploaded
internal-student registration numbers.

The grade text is returned as printed (for example A+, B+, F or Absent).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# REGULAR EXPRESSIONS
# ---------------------------------------------------------------------------

# Supports regular and lateral-entry registration numbers:
# CEC19EC003, LCEC19EC025, CEC21CS001, CEA20CS014, CEM21CS036.

REGISTER_RE = re.compile(
    r"(?<![A-Z0-9])L?CE[A-Z]?\d{2}[A-Z]{2}\d{3}(?![A-Z0-9])",
    re.IGNORECASE,
)

# Typical university course codes:
# ECT201, EET201, CST309, CSL331, etc.

COURSE_RE = re.compile(
    r"(?<![A-Z0-9])[A-Z]{2,5}\d{3}(?![A-Z0-9])",
    re.IGNORECASE,
)

# Each department begins with a heading followed by [Full Time].
#
# Examples:
# ELECTRONICS & COMMUNICATION ENGG[Full Time]
# COMPUTER SCIENCE & ENGINEERING[Full Time]
# ELECTRICAL AND ELECTRONICS ENGINEERING[Full Time]
# Artificial Intelligence and Data Science[Full Time]

BRANCH_HEADER_RE = re.compile(
    r"(?im)^[ \t]*(?P<branch>[A-Z][A-Z0-9 &.,()/+-]{2,}?)"
    r"[ \t]*\[[ \t]*Full[ \t]+Time[ \t]*\][^\n]*$"
)

REGISTER_TABLE_HEADER_RE = re.compile(
    r"\bRegister\s+No\b",
    re.IGNORECASE,
)

COURSE_GRADE_TEMPLATE = (
    r"(?<![A-Z0-9]){code}\s*\(\s*([^()]*)\s*\)"
)


# ---------------------------------------------------------------------------
# CUSTOM EXCEPTION
# ---------------------------------------------------------------------------

class ResultPDFError(ValueError):
    """Raised when a result PDF cannot be parsed reliably."""


# ---------------------------------------------------------------------------
# FILE HELPERS
# ---------------------------------------------------------------------------

def _validate_pdf_path(pdf_path: str | Path) -> Path:

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


def _read_pdf_text(pdf_path: str | Path) -> str:

    """Extract text from every page of the result PDF."""

    path = _validate_pdf_path(pdf_path)

    try:

        with fitz.open(path) as document:

            if len(document) == 0:

                raise ResultPDFError(
                    "The uploaded result PDF contains no pages."
                )

            pages = []

            for page in document:

                page_text = page.get_text("text")

                if page_text:

                    pages.append(page_text)

    except ResultPDFError:

        raise

    except Exception as exc:

        raise ResultPDFError(
            f"Could not open/read the result PDF: {exc}"
        ) from exc

    return "\n".join(pages).replace(
        "\xa0",
        " "
    ).replace(
        "\r",
        "\n"
    )


# ---------------------------------------------------------------------------
# COURSE-CODE AND REGISTRATION-NUMBER HANDLING
# ---------------------------------------------------------------------------

def _normalize_course_code(course_code: str) -> str:

    """
    Normalize manually entered course codes.

    Examples:
        " ect201 " -> "ECT201"
        "ECT 201"  -> "ECT201"
        "cst309"   -> "CST309"
    """

    value = re.sub(
        r"\s+",
        "",
        course_code or ""
    ).upper()

    if not re.fullmatch(
        r"[A-Z]{2,5}\d{3}",
        value
    ):

        raise ResultPDFError(
            "Invalid course code. Enter a course code with "
            "2–5 letters followed by 3 digits, "
            "for example ECT201, EET201 or CST309."
        )

    return value


def _clean_registration_number(value: str) -> str:

    """Normalize a registration number."""

    return re.sub(
        r"\s+",
        "",
        value or ""
    ).upper()


# ---------------------------------------------------------------------------
# DEPARTMENT SECTION HANDLING
# ---------------------------------------------------------------------------

def _get_branch_sections(
    text: str,
) -> List[Tuple[str, str]]:

    """
    Split the result PDF into department sections.

    Every [Full Time] department heading starts a new section.
    The section continues until the next department heading
    or the end of the PDF.
    """

    headers = list(
        BRANCH_HEADER_RE.finditer(text)
    )

    if not headers:

        # Compatibility fallback for a single-section PDF
        # that does not contain a [Full Time] heading.

        if (
            REGISTER_TABLE_HEADER_RE.search(text)
            and REGISTER_RE.search(text)
        ):

            return [
                ("Result", text)
            ]

        raise ResultPDFError(
            "Could not locate department sections in the result PDF. "
            "Please upload a valid university result PDF."
        )

    sections = []

    for index, header in enumerate(headers):

        start = header.end()

        if index + 1 < len(headers):

            end = headers[index + 1].start()

        else:

            end = len(text)

        branch_name = re.sub(
            r"\s+",
            " ",
            header.group("branch")
        ).strip()

        section_text = text[
            start:end
        ].strip()

        if section_text:

            sections.append(
                (
                    branch_name,
                    section_text
                )
            )

    if not sections:

        raise ResultPDFError(
            "Department sections were detected, "
            "but no section content was found."
        )

    return sections


def _get_course_area(section_text: str) -> str:

    """
    Return the course-list area before the student table.
    """

    marker = REGISTER_TABLE_HEADER_RE.search(
        section_text
    )

    if not marker:

        raise ResultPDFError(
            "Could not find the 'Register No' student table "
            "in a department section."
        )

    return section_text[
        :marker.start()
    ]


def _get_student_area(section_text: str) -> str:

    """Return the text after the student-table header."""

    marker = REGISTER_TABLE_HEADER_RE.search(
        section_text
    )

    if not marker:

        raise ResultPDFError(
            "Could not find the 'Register No' student table "
            "in a department section."
        )

    return section_text[
        marker.end():
    ]


def _course_codes_in_section(
    section_text: str,
) -> List[str]:

    """Extract unique course codes from one department's course table."""

    course_area = _get_course_area(
        section_text
    )

    codes = []

    for match in COURSE_RE.finditer(course_area):

        code = match.group(0).upper()

        if code not in codes:

            codes.append(code)

    return codes


# ---------------------------------------------------------------------------
# PUBLIC COURSE-CODE SUGGESTION API
# ---------------------------------------------------------------------------

def extract_result_course_codes(
    pdf_path: str | Path,
) -> List[str]:

    """
    Return course codes from ALL department sections in the PDF.

    Example:
        ECT201
        ECT203
        CST201
        EET201
        MAT201

    The teacher still manually selects or enters the course code.
    """

    text = _read_pdf_text(
        pdf_path
    )

    sections = _get_branch_sections(
        text
    )

    all_codes = []

    for _branch_name, section_text in sections:

        try:

            section_codes = _course_codes_in_section(
                section_text
            )

        except ResultPDFError:

            continue

        for code in section_codes:

            if code not in all_codes:

                all_codes.append(code)

    if not all_codes:

        raise ResultPDFError(
            "No course codes were found in the department course tables."
        )

    return all_codes


# ---------------------------------------------------------------------------
# STUDENT-BLOCK AND GRADE EXTRACTION
# ---------------------------------------------------------------------------

def _extract_student_blocks(
    section_text: str,
) -> List[Tuple[str, str]]:

    """
    Split one department's student-result table into registration-number
    blocks. Each block runs from one registration number to the next.
    """

    student_area = _get_student_area(
        section_text
    )

    matches = list(
        REGISTER_RE.finditer(student_area)
    )

    if not matches:

        return []

    blocks = []

    for index, match in enumerate(matches):

        reg_no = _clean_registration_number(
            match.group(0)
        )

        start = match.end()

        if index + 1 < len(matches):

            end = matches[
                index + 1
            ].start()

        else:

            end = len(student_area)

        blocks.append(
            (
                reg_no,
                student_area[start:end]
            )
        )

    return blocks


def _extract_grade_from_block(
    student_text: str,
    course_code: str,
) -> str | None:

    """
    Extract the grade for the selected course from one student's record.

    Examples:
        ECT201(C)      -> C
        EET201(A+)     -> A+
        CST309(Absent) -> Absent
    """

    pattern = re.compile(
        COURSE_GRADE_TEMPLATE.format(
            code=re.escape(course_code)
        ),
        re.IGNORECASE
    )

    match = pattern.search(
        student_text
    )

    if not match:

        return None

    grade = match.group(1).strip()

    return grade or None


def _validate_course_code_in_sections(
    sections: List[Tuple[str, str]],
    course_code: str,
) -> List[Tuple[str, str]]:

    """
    Find every department section whose course table lists
    the requested code.

    This is intentionally NOT restricted to Computer Science.

    If a common course appears in multiple departments,
    all those sections are returned.
    """

    matching_sections = []

    all_available_codes = []

    for branch_name, section_text in sections:

        try:

            codes = _course_codes_in_section(
                section_text
            )

        except ResultPDFError:

            continue

        for code in codes:

            if code not in all_available_codes:

                all_available_codes.append(code)

        if course_code in codes:

            matching_sections.append(
                (
                    branch_name,
                    section_text
                )
            )

    if not matching_sections:

        available = ", ".join(
            all_available_codes
        )

        if available:

            raise ResultPDFError(
                f"Course code {course_code} was not found "
                "in the uploaded result PDF.\n\n"
                f"Available course codes: {available}"
            )

        raise ResultPDFError(
            "No course-code tables were found in the uploaded result PDF."
        )

    return matching_sections


# ---------------------------------------------------------------------------
# MAIN PUBLIC PARSER
# ---------------------------------------------------------------------------

def extract_result_grades(
    pdf_path: str | Path,
    course_code: str,
) -> Dict[str, str]:

    """
    Extract registration-number -> selected-course-grade mapping.

    The selected course may belong to ANY department section in the PDF.

    If the same course code is listed in multiple departments
    (for example MAT201 or MCN201), grades are gathered from
    all matching sections.

    The application later matches these grades against the
    internal PDF registration numbers.
    """

    selected_code = _normalize_course_code(
        course_code
    )

    text = _read_pdf_text(
        pdf_path
    )

    sections = _get_branch_sections(
        text
    )

    matching_sections = _validate_course_code_in_sections(
        sections,
        selected_code
    )

    grades = {}

    duplicate_conflicts = {}

    for _branch_name, section_text in matching_sections:

        student_blocks = _extract_student_blocks(
            section_text
        )

        for reg_no, student_text in student_blocks:

            grade = _extract_grade_from_block(
                student_text,
                selected_code
            )

            if grade is None:

                continue

            if reg_no in grades:

                # Same registration and same grade:
                # Ignore the repeated record.
                #
                # Same registration but different grade:
                # Report an ambiguity.

                if grades[reg_no].casefold() != grade.casefold():

                    duplicate_conflicts[reg_no] = (
                        grades[reg_no],
                        grade
                    )

                continue

            grades[reg_no] = grade

    if duplicate_conflicts:

        examples = ", ".join(
            f"{reg}={old}/{new}"
            for reg, (old, new) in list(
                duplicate_conflicts.items()
            )[:5]
        )

        raise ResultPDFError(
            "Conflicting grades were found for duplicate "
            "registration numbers in the result PDF: "
            f"{examples}"
        )

    if not grades:

        raise ResultPDFError(
            f"Course code {selected_code} was found in the course table, "
            "but no student grades for it could be extracted."
        )

    return grades


# ---------------------------------------------------------------------------
# OPTIONAL DETAILED PARSER
# ---------------------------------------------------------------------------

def extract_result_records(
    pdf_path: str | Path,
    course_code: str,
) -> List[dict]:

    """
    Return selected-course grades as a list of records.
    """

    grades = extract_result_grades(
        pdf_path,
        course_code
    )

    return [
        {
            "reg_no": reg_no,
            "grade": grade
        }
        for reg_no, grade in grades.items()
    ]


# ---------------------------------------------------------------------------
# COMMAND-LINE TESTING
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    import sys

    if len(sys.argv) not in (2, 3):

        print(
            "Usage:\n"
            "python result_parser.py <result_pdf_path> [COURSE_CODE]\n\n"
            "Examples:\n"
            'python result_parser.py "result_CEC.pdf"\n'
            'python result_parser.py "result_CEC.pdf" ECT201'
        )

        raise SystemExit(1)

    pdf_path = sys.argv[1]

    try:

        available_codes = extract_result_course_codes(
            pdf_path
        )

        print(
            "\nCourse codes found across all departments:\n"
        )

        print(
            ", ".join(available_codes)
        )

        if len(sys.argv) == 3:

            selected_course = sys.argv[2]

            grades = extract_result_grades(
                pdf_path,
                selected_course
            )

            print(
                f"\nSuccessfully extracted {len(grades)} grades "
                f"for {selected_course.upper()}.\n"
            )

            for reg_no, grade in list(
                grades.items()
            )[:30]:

                print(
                    f"{reg_no} -> {grade}"
                )

    except ResultPDFError as exc:

        print(
            f"\nERROR: {exc}"
        )

        raise SystemExit(1)