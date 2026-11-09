"""
Matching and derived-mark calculation service for ANSORA.

Responsibilities:
- Match internal marks and result grades.
- Retain every internal student.
- Convert grades into University Marks.
- Calculate CO1-CO8 only for 50-mark assessments.
- Leave calculated values blank for Absent and Not Found.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List


class MatchingError(ValueError):
    """Raised when extracted datasets cannot be matched reliably."""


# =========================================================
# GRADE TO UNIVERSITY MARK MAPPING
# =========================================================

GRADE_TO_UNIVERSITY_MARK = {
    "S": 100,
    "A+": 89,
    "A": 84,
    "B+": 79,
    "B": 74,
    "C+": 69,
    "C": 64,
    "D": 59,
    "P": 54,
    "F": 0,
    "FE": 0,
}

SUPPORTED_INTERNAL_SCALES = {50, 75, 100}

CO_COLUMNS = tuple(
    f"co{i}" for i in range(1, 9)
)


# =========================================================
# NORMALIZATION HELPERS
# =========================================================

def normalize_registration_number(value: Any) -> str:

    if value is None:
        return ""

    return "".join(
        str(value).strip().upper().split()
    )


def _normalize_reg_no(value: Any) -> str:

    return normalize_registration_number(value)


def normalize_grade(value: Any) -> str:

    if value is None:
        return ""

    grade = str(value).strip().upper()

    if grade in {"ABSENT", "AB", "A.B."}:
        return "Absent"

    if grade in {
        "NOT FOUND",
        "NOTFOUND",
        "N/A",
        "NA",
        ""
    }:
        return "Not Found"

    return grade


def _normalize_grade(value: Any) -> str:

    return normalize_grade(value)


def _to_number(
    value: Any,
    field_name: str = "mark"
) -> Decimal:

    try:

        number = Decimal(
            str(value).strip()
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
        AttributeError
    ) as exc:

        raise MatchingError(
            f"Invalid {field_name}: {value!r}"
        ) from exc

    if not number.is_finite():

        raise MatchingError(
            f"Invalid {field_name}: {value!r}"
        )

    return number


def _display_number(
    value: Decimal | int | float | None
):

    if value is None:
        return None

    number = (
        value
        if isinstance(value, Decimal)
        else Decimal(str(value))
    )

    if number == number.to_integral_value():
        return int(number)

    return float(number)


# =========================================================
# UNIVERSITY MARK CALCULATION
# =========================================================

def get_university_mark(
    grade: Any
) -> int | None:

    """
    Convert a grade into its corresponding University Mark.

    Unknown grades, Absent and Not Found return None.
    F and FE return 0.
    """

    normalized = normalize_grade(grade)

    if normalized in {
        "",
        "Absent",
        "Not Found"
    }:

        return None

    return GRADE_TO_UNIVERSITY_MARK.get(
        normalized
    )


# =========================================================
# CO MARK CALCULATION
# =========================================================

def calculate_co_mark(
    internal_mark: Any,
    university_mark: Any,
    internal_max_mark: int = 50
) -> int | None:

    """
    Calculate CO marks for regular 50-mark assessments.

    Formula:

    ROUND(
        ((Internal Mark + University Mark) / 150) * 100,
        0
    )

    Uses ROUND_HALF_UP.

    CO marks are not calculated for 75 or 100 marks.
    """

    if int(internal_max_mark) != 50:
        return None

    if (
        internal_mark is None
        or university_mark is None
    ):
        return None

    internal = _to_number(
        internal_mark,
        "internal mark"
    )

    university = _to_number(
        university_mark,
        "University Mark"
    )

    value = (
        (internal + university)
        / Decimal("150")
    ) * Decimal("100")

    rounded = value.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP
    )

    return int(rounded)


# =========================================================
# CALCULATE ALL DERIVED MARKS
# =========================================================

def calculate_derived_marks(
    internal_mark: Any,
    grade: Any,
    internal_max_mark: int = 50
) -> dict:

    try:

        scale = int(internal_max_mark)

    except (TypeError, ValueError) as exc:

        raise MatchingError(
            "Internal assessment scale must be 50, 75 or 100."
        ) from exc

    if scale not in SUPPORTED_INTERNAL_SCALES:

        raise MatchingError(
            "Internal assessment scale must be 50, 75 or 100."
        )

    university_mark = get_university_mark(
        grade
    )

    if scale == 50:

        co_mark = calculate_co_mark(
            internal_mark,
            university_mark,
            internal_max_mark=scale
        )

    else:

        co_mark = None

    result = {
        "university_mark": university_mark
    }

    for column in CO_COLUMNS:

        result[column] = co_mark

    return result


# =========================================================
# INTERNAL MARK VALIDATION
# =========================================================

def _validate_internal_marks(
    internal_marks: Dict[str, Any],
    internal_max_mark: int | None = None
) -> Dict[str, int | float]:

    if not isinstance(internal_marks, dict):

        raise MatchingError(
            "Internal marks data must be a dictionary."
        )

    if internal_max_mark is not None:

        try:
            scale = int(internal_max_mark)

        except (TypeError, ValueError) as exc:

            raise MatchingError(
                "Internal assessment scale must be 50, 75 or 100."
            ) from exc

        if scale not in SUPPORTED_INTERNAL_SCALES:

            raise MatchingError(
                "Internal assessment scale must be 50, 75 or 100."
            )

    else:

        scale = None

    normalized = {}

    for raw_reg_no, raw_mark in internal_marks.items():

        reg_no = normalize_registration_number(
            raw_reg_no
        )

        if not reg_no:
            continue

        mark = _to_number(
            raw_mark,
            f"internal mark for {reg_no}"
        )

        if mark < 0:

            raise MatchingError(
                f"Internal mark for {reg_no} "
                f"cannot be negative: {raw_mark}"
            )

        if (
            scale is not None
            and mark > Decimal(scale)
        ):

            raise MatchingError(
                f"Internal mark for {reg_no} "
                f"is outside the valid range "
                f"0-{scale}: {raw_mark}"
            )

        normalized[reg_no] = _display_number(
            mark
        )

    if not normalized:

        raise MatchingError(
            "No valid internal-mark records were found."
        )

    return normalized


# =========================================================
# GRADE VALIDATION
# =========================================================

def _validate_grades(
    grades: Dict[str, Any]
) -> Dict[str, str]:

    if not isinstance(grades, dict):

        raise MatchingError(
            "Result grades data must be a dictionary."
        )

    normalized = {}

    for raw_reg_no, raw_grade in grades.items():

        reg_no = normalize_registration_number(
            raw_reg_no
        )

        if not reg_no:
            continue

        grade = normalize_grade(
            raw_grade
        )

        if not grade or grade == "Not Found":
            continue

        normalized[reg_no] = grade

    return normalized


# =========================================================
# MAIN MATCHING FUNCTION
# =========================================================

def merge_mark_data(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
    course_code: str = "",
    internal_max_mark: int = 50,
    internal_mark_scale: int | None = None,
    assessment_scale: int | None = None
) -> List[dict]:

    """
    Match internal marks and grades using registration number.

    All internal students are retained.

    Missing grades are displayed as Not Found.

    The assessment scale controls the CO calculations.
    """

    if internal_mark_scale is not None:

        internal_max_mark = internal_mark_scale

    if assessment_scale is not None:

        internal_max_mark = assessment_scale

    try:

        scale = int(internal_max_mark)

    except (TypeError, ValueError) as exc:

        raise MatchingError(
            "Internal assessment scale must be 50, 75 or 100."
        ) from exc

    if scale not in SUPPORTED_INTERNAL_SCALES:

        raise MatchingError(
            "Internal assessment scale must be 50, 75 or 100."
        )

    normalized_internal = _validate_internal_marks(
        internal_marks,
        internal_max_mark=scale
    )

    normalized_grades = _validate_grades(
        grades
    )

    results = []

    for reg_no, internal_mark in normalized_internal.items():

        grade = normalized_grades.get(
            reg_no,
            "Not Found"
        )

        derived = calculate_derived_marks(
            internal_mark,
            grade,
            internal_max_mark=scale
        )

        row = {
            "reg_no": reg_no,
            "registration_number": reg_no,
            "internal_mark": internal_mark,
            "grade": grade,
            "university_mark": derived["university_mark"],
            "internal_mark_scale": scale,
            "course_code": course_code or ""
        }

        for column in CO_COLUMNS:

            row[column] = derived[column]

        results.append(row)

    return results


# =========================================================
# PROCESSING SUMMARY
# =========================================================

def create_processing_summary(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
    internal_max_mark: int | None = None
) -> dict:

    normalized_internal = _validate_internal_marks(
        internal_marks,
        internal_max_mark=internal_max_mark
    )

    normalized_grades = _validate_grades(
        grades
    )

    internal_reg_numbers = set(
        normalized_internal.keys()
    )

    result_reg_numbers = set(
        normalized_grades.keys()
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

        "total_internal_students":
            len(internal_reg_numbers),

        "total_students":
            len(internal_reg_numbers),

        "total_result_students":
            len(result_reg_numbers),

        "matched_students":
            len(matched),

        "missing_grades":
            len(missing_grades),

        "missing_students":
            len(missing_grades),

        "result_only_students":
            len(result_only),

        "missing_grade_reg_numbers":
            sorted(missing_grades),

        "missing_reg_nos":
            sorted(missing_grades),

        "result_only_reg_numbers":
            sorted(result_only)

    }


# =========================================================
# COMBINED PROCESSING HELPER
# =========================================================

def process_and_summarize(
    internal_marks: Dict[str, Any],
    grades: Dict[str, Any],
    course_code: str = "",
    internal_max_mark: int = 50
) -> dict:

    results = merge_mark_data(
        internal_marks,
        grades,
        course_code=course_code,
        internal_max_mark=internal_max_mark
    )

    summary = create_processing_summary(
        internal_marks,
        grades,
        internal_max_mark=internal_max_mark
    )

    return {
        "results": results,
        "summary": summary
    }


# =========================================================
# MISSING GRADE HELPER
# =========================================================

def find_missing_grades(
    results: List[dict]
) -> List[str]:

    missing = []

    for row in results:

        if normalize_grade(
            row.get("grade")
        ) == "Not Found":

            reg_no = normalize_registration_number(
                row.get("reg_no")
                or row.get("registration_number")
            )

            if reg_no:
                missing.append(reg_no)

    return sorted(set(missing))


# =========================================================
# COUNT HELPERS
# =========================================================

def count_matched_students(
    results: List[dict]
) -> int:

    return sum(
        1
        for row in results
        if normalize_grade(
            row.get("grade")
        ) != "Not Found"
    )


def count_missing_students(
    results: List[dict]
) -> int:

    return sum(
        1
        for row in results
        if normalize_grade(
            row.get("grade")
        ) == "Not Found"
    )


# =========================================================
# TESTING
# =========================================================

if __name__ == "__main__":

    internal_example = {
        "CEC23CS003": 32,
        "CEC23CS004": 35,
        "CEC23CS005": 28,
        "CEC23CS006": 38
    }

    grades_example = {
        "CEC23CS003": "C+",
        "CEC23CS004": "P",
        "CEC23CS005": "F",
        "CEC23CS006": "B"
    }

    try:

        output = process_and_summarize(
            internal_example,
            grades_example,
            course_code="DEMO",
            internal_max_mark=50
        )

        print("\n50-MARK ASSESSMENT RESULTS")

        for row in output["results"]:

            print(
                row["reg_no"],
                row["internal_mark"],
                row["grade"],
                row["university_mark"],
                [
                    row[column]
                    for column in CO_COLUMNS
                ]
            )

        print("\n75-MARK ASSESSMENT CHECK")

        lab_rows = merge_mark_data(
            {"CEC23CS100": 63},
            {"CEC23CS100": "A"},
            course_code="LAB",
            internal_max_mark=75
        )

        print(lab_rows[0])

        print("\nSUMMARY")

        for key, value in output["summary"].items():

            print(f"{key}: {value}")

    except MatchingError as exc:

        print(f"ERROR: {exc}")