"""
Matching service for the KTU Mark Processing System.

This module combines the data extracted from:

1. Internal Mark PDF
   {
       "CEC23CS003": 47,
       "CEC23CS004": 47,
       ...
   }

2. Result PDF for the manually selected course
   {
       "CEC23CS003": "A",
       "CEC23CS004": "A",
       ...
   }

The registration number is the unique matching key.

The final output is:

[
    {
        "reg_no": "CEC23CS003",
        "internal_mark": 47,
        "grade": "A"
    },
    ...
]

The service does NOT calculate, modify, or reinterpret grades.
It preserves the grade extracted by the result parser.
"""

from __future__ import annotations

from typing import Dict, List, Any


class MatchingError(ValueError):
    """
    Raised when the extracted datasets cannot be matched properly.
    """



# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize_reg_no(value: Any) -> str:
    """
    Normalize a registration number.

    Examples:

        "cec23cs003" -> "CEC23CS003"
        " CEC23CS003 " -> "CEC23CS003"
        "CEC 23 CS 003" -> "CEC23CS003"
    """

    if value is None:
        return ""

    value = str(value).strip().upper()

    # Registration numbers should not contain spaces.
    value = "".join(value.split())

    return value


def _normalize_grade(value: Any) -> str:
    """
    Normalize grade for storage/display.

    We only remove surrounding whitespace and convert to uppercase.

    We do NOT change:
        A+ -> A+
        B+ -> B+
        Absent -> Absent

    The actual meaning is preserved.
    """

    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() == "absent":
        return "Absent"

    return value.upper()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_internal_marks(
    internal_marks: Dict[str, Any],
) -> Dict[str, int | float]:
    """
    Validate and normalize the internal-mark dictionary.
    """

    if not isinstance(internal_marks, dict):
        raise MatchingError(
            "Internal marks data must be a dictionary."
        )

    normalized: Dict[str, int | float] = {}

    for raw_reg_no, raw_mark in internal_marks.items():

        reg_no = _normalize_reg_no(
            raw_reg_no
        )

        if not reg_no:
            continue

        try:
            mark = float(raw_mark)
        except (TypeError, ValueError):

            raise MatchingError(
                f"Invalid internal mark for "
                f"{reg_no}: {raw_mark}"
            )

        if mark < 0 or mark > 50:

            raise MatchingError(
                f"Internal mark for {reg_no} "
                f"is outside the valid range 0-50: {mark}"
            )

        if mark.is_integer():
            normalized[reg_no] = int(mark)
        else:
            normalized[reg_no] = mark

    if not normalized:
        raise MatchingError(
            "No valid internal-mark records were found."
        )

    return normalized


def _validate_grades(
    grades: Dict[str, Any],
) -> Dict[str, str]:
    """
    Validate and normalize the result-grade dictionary.
    """

    if not isinstance(grades, dict):
        raise MatchingError(
            "Result grades data must be a dictionary."
        )

    normalized: Dict[str, str] = {}

    for raw_reg_no, raw_grade in grades.items():

        reg_no = _normalize_reg_no(
            raw_reg_no
        )

        if not reg_no:
            continue

        grade = _normalize_grade(
            raw_grade
        )

        if not grade:
            continue

        normalized[reg_no] = grade

    if not normalized:
        raise MatchingError(
            "No valid grade records were found."
        )

    return normalized


# ---------------------------------------------------------------------------
# Main matching function
# ---------------------------------------------------------------------------

def merge_mark_data(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
) -> List[dict]:
    """
    Merge internal marks and course grades using registration number.

    Parameters
    ----------
    internal_marks:
        Dictionary containing registration number -> internal mark.

    grades:
        Dictionary containing registration number -> grade.

    Returns
    -------
    list of dictionaries

    Example:

        [
            {
                "reg_no": "CEC23CS003",
                "internal_mark": 47,
                "grade": "A"
            },
            {
                "reg_no": "CEC23CS004",
                "internal_mark": 47,
                "grade": "A"
            }
        ]

    Important:
        Every student from the internal-mark PDF is retained.

        If a grade is not found, the result gets:

            "Not Found"

        instead of silently removing the student.
    """

    internal_marks = _validate_internal_marks(
        internal_marks
    )

    grades = _validate_grades(
        grades
    )

    results: List[dict] = []

    for reg_no, internal_mark in internal_marks.items():

        grade = grades.get(
            reg_no,
            "Not Found",
        )

        results.append(
            {
                "reg_no": reg_no,
                "internal_mark": internal_mark,
                "grade": grade,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Detailed matching information
# ---------------------------------------------------------------------------

def create_processing_summary(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
) -> dict:
    """
    Create a detailed summary of the matching operation.

    Example return:

        {
            "total_internal_students": 61,
            "total_result_students": 120,
            "matched_students": 59,
            "missing_grades": 2,
            "result_only_students": 61,
            "missing_grade_reg_numbers": [...],
            "result_only_reg_numbers": [...]
        }

    This information can be displayed by the frontend.
    """

    internal_marks = _validate_internal_marks(
        internal_marks
    )

    grades = _validate_grades(
        grades
    )

    internal_reg_numbers = set(
        internal_marks.keys()
    )

    result_reg_numbers = set(
        grades.keys()
    )

    matched = (
        internal_reg_numbers
        & result_reg_numbers
    )

    missing_grades = (
        internal_reg_numbers
        - result_reg_numbers
    )

    result_only = (
        result_reg_numbers
        - internal_reg_numbers
    )

    return {
        "total_internal_students": len(
            internal_reg_numbers
        ),

        "total_result_students": len(
            result_reg_numbers
        ),

        "matched_students": len(
            matched
        ),

        "missing_grades": len(
            missing_grades
        ),

        "result_only_students": len(
            result_only
        ),

        "missing_grade_reg_numbers": sorted(
            missing_grades
        ),

        "result_only_reg_numbers": sorted(
            result_only
        ),
    }


# ---------------------------------------------------------------------------
# Combined processing helper
# ---------------------------------------------------------------------------

def process_and_summarize(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
) -> dict:
    """
    Perform both matching and summary generation.

    This is convenient for app.py.

    Example:

        processed = process_and_summarize(
            internal_marks,
            grades
        )

        processed["results"]
        processed["summary"]
    """

    results = merge_mark_data(
        internal_marks,
        grades,
    )

    summary = create_processing_summary(
        internal_marks,
        grades,
    )

    return {
        "results": results,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Utility functions for frontend
# ---------------------------------------------------------------------------

def find_missing_grades(
    results: List[dict],
) -> List[str]:
    """
    Return registrations where the selected course grade was not found.
    """

    missing = []

    for row in results:

        if row.get("grade") == "Not Found":

            reg_no = _normalize_reg_no(
                row.get("reg_no")
            )

            if reg_no:
                missing.append(reg_no)

    return sorted(
        set(missing)
    )


def count_matched_students(
    results: List[dict],
) -> int:
    """
    Count students for whom a grade was successfully found.
    """

    return sum(
        1
        for row in results
        if row.get("grade") != "Not Found"
    )


def count_missing_students(
    results: List[dict],
) -> int:
    """
    Count students for whom a grade was not found.
    """

    return sum(
        1
        for row in results
        if row.get("grade") == "Not Found"
    )


# ---------------------------------------------------------------------------
# Optional command-line test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # Small demonstration test.

    internal_example = {
        "CEC23CS003": 47,
        "CEC23CS004": 47,
        "CEC23CS005": 46,
        "CEC23CS006": 37,
    }

    grades_example = {
        "CEC23CS003": "A",
        "CEC23CS004": "A",
        "CEC23CS005": "B+",
        "CEC23CS006": "F",
    }

    try:

        output = process_and_summarize(
            internal_example,
            grades_example,
        )

        print(
            "\nFINAL RESULTS\n"
        )

        for row in output["results"]:

            print(
                f"{row['reg_no']} | "
                f"{row['internal_mark']} | "
                f"{row['grade']}"
            )

        print(
            "\nSUMMARY\n"
        )

        for key, value in output["summary"].items():

            print(
                f"{key}: {value}"
            )

    except MatchingError as exc:

        print(
            f"ERROR: {exc}"
        )