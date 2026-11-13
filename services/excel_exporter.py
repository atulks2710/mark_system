"""
ANSORA Mark Processing System
Excel Export Service

All assessment types (50, 75 and 100 marks) export the same columns:
Registration Number | Internal Mark | Course Grade | University Mark

CO1-CO8 calculations and columns are not included.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any

from openpyxl import Workbook
from openpyxl.styles import (
    Font,
    Alignment,
    PatternFill,
    Border,
    Side,
)
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter


class ExcelExportError(ValueError):
    """Raised when Excel export fails."""


# =========================================================
# CONSTANTS
# =========================================================

SUPPORTED_INTERNAL_SCALES = {50, 75, 100}



# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _normalize_course_code(course_code: str) -> str:

    if course_code is None:
        raise ExcelExportError(
            "Course code is required for Excel export."
        )

    code = re.sub(
        r"\s+",
        "",
        str(course_code).strip().upper()
    )

    if not code:
        raise ExcelExportError(
            "Course code cannot be empty."
        )

    return code


def _safe_filename(filename: str) -> str:

    filename = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        str(filename)
    )

    return filename.strip("._") or "marks"


def _resolve_internal_scale(
    results: List[dict],
    internal_max_mark: int | None
) -> int:

    candidate = internal_max_mark

    if candidate is None:

        for row in results:

            if row.get("internal_mark_scale") is not None:

                candidate = row["internal_mark_scale"]
                break

    # Backward compatibility with the previous application.
    if candidate is None:
        candidate = 50

    try:
        scale = int(candidate)

    except (TypeError, ValueError) as exc:

        raise ExcelExportError(
            "Internal assessment scale must be 50, 75 or 100."
        ) from exc

    if scale not in SUPPORTED_INTERNAL_SCALES:

        raise ExcelExportError(
            "Internal assessment scale must be 50, 75 or 100."
        )

    return scale


def _clean_numeric_value(
    value: Any,
    label: str,
    reg_no: str
):

    if value is None or value == "":
        return None

    if isinstance(value, bool):

        raise ExcelExportError(
            f"Invalid {label} for {reg_no}: {value!r}"
        )

    try:
        number = float(value)

    except (TypeError, ValueError) as exc:

        raise ExcelExportError(
            f"Invalid {label} for {reg_no}: {value!r}"
        ) from exc

    if (
        number != number
        or number in (
            float("inf"),
            float("-inf")
        )
    ):

        raise ExcelExportError(
            f"Invalid {label} for {reg_no}: {value!r}"
        )

    if number.is_integer():
        return int(number)

    return number


# =========================================================
# VALIDATE RESULTS
# =========================================================

def _validate_results(
    results: List[dict]
) -> List[dict]:

    if not isinstance(results, list):

        raise ExcelExportError(
            "Results must be provided as a list."
        )

    if not results:

        raise ExcelExportError(
            "There are no results to export."
        )

    cleaned_results = []
    seen_reg_numbers = set()

    for index, row in enumerate(results, start=1):

        if not isinstance(row, dict):

            raise ExcelExportError(
                f"Invalid result record at row {index}."
            )

        reg_no = str(
            row.get("reg_no")
            or row.get("registration_number")
            or ""
        ).strip().upper()

        if not reg_no:

            raise ExcelExportError(
                f"Registration number is missing at row {index}."
            )

        if reg_no in seen_reg_numbers:

            raise ExcelExportError(
                f"Duplicate registration number: {reg_no}"
            )

        seen_reg_numbers.add(reg_no)

        internal_mark = _clean_numeric_value(
            row.get("internal_mark"),
            "Internal Mark",
            reg_no
        )

        if internal_mark is None:

            raise ExcelExportError(
                f"Internal mark is missing for {reg_no}."
            )

        grade = row.get(
            "grade",
            "Not Found"
        )

        grade = str(
            grade if grade is not None else "Not Found"
        ).strip()

        university_mark = _clean_numeric_value(
            row.get("university_mark"),
            "University Mark",
            reg_no
        )

        cleaned = {
            "reg_no": reg_no,
            "internal_mark": internal_mark,
            "grade": grade or "Not Found",
            "university_mark": university_mark,
            "internal_mark_scale": row.get(
                "internal_mark_scale"
            )
        }


        cleaned_results.append(cleaned)

    return cleaned_results


# =========================================================
# EXCEL GENERATOR
# =========================================================

def generate_excel(
    results: List[dict],
    course_code: str,
    output_path: str | Path,
    *,
    summary: Dict[str, Any] | None = None,
    branch: str = "COMPUTER SCIENCE & ENGINEERING",
    semester: str = "",
    internal_max_mark: int | None = None,
) -> Path:

    """
    Generate a formatted Excel workbook.

    Assessment scale:
        50  = Regular Internal
        75  = Laboratory
        100 = Project

    Every assessment type exports only:
    Registration Number, Internal Mark, Course Grade and University Mark.
    """

    course_code = _normalize_course_code(
        course_code
    )

    results = _validate_results(
        results
    )

    scale = _resolve_internal_scale(
        results,
        internal_max_mark
    )

    output = Path(output_path)

    if output.suffix.lower() != ".xlsx":

        output = output.with_suffix(".xlsx")

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # -----------------------------------------------------
    # DYNAMIC HEADERS
    # -----------------------------------------------------

    headers = [
        "Registration Number",
        "Internal Mark",
        f"{course_code} Grade",
        "University Mark"
    ]

    # -----------------------------------------------------
    # CREATE WORKBOOK
    # -----------------------------------------------------

    workbook = Workbook()

    worksheet = workbook.active
    worksheet.title = "Marks"

    worksheet.sheet_view.showGridLines = False

    # -----------------------------------------------------
    # COLORS AND STYLES - ANSORA
    # -----------------------------------------------------

    title_fill = PatternFill(
        fill_type="solid",
        fgColor="171717"
    )

    header_fill = PatternFill(
        fill_type="solid",
        fgColor="8D6B24"
    )

    information_fill = PatternFill(
        fill_type="solid",
        fgColor="F3F0E8"
    )

    warning_fill = PatternFill(
        fill_type="solid",
        fgColor="FFF2CC"
    )

    title_font = Font(
        name="Arial",
        bold=True,
        size=16,
        color="D8C18A"
    )

    header_font = Font(
        name="Arial",
        bold=True,
        size=10,
        color="FFFFFF"
    )

    normal_font = Font(
        name="Arial",
        size=10,
        color="222222"
    )

    bold_font = Font(
        name="Arial",
        bold=True,
        size=10,
        color="222222"
    )

    thin_side = Side(
        style="thin",
        color="D6D3CD"
    )

    medium_side = Side(
        style="medium",
        color="8D6B24"
    )

    thin_border = Border(
        left=thin_side,
        right=thin_side,
        top=thin_side,
        bottom=thin_side
    )

    header_border = Border(
        left=medium_side,
        right=medium_side,
        top=medium_side,
        bottom=medium_side
    )

    center_alignment = Alignment(
        horizontal="center",
        vertical="center"
    )

    left_alignment = Alignment(
        vertical="center",
        wrap_text=True
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    last_column = len(headers)

    last_column_letter = get_column_letter(
        last_column
    )

    worksheet.merge_cells(
        f"A1:{last_column_letter}1"
    )

    worksheet["A1"] = "ANSORA MARK PROCESSING SYSTEM"

    worksheet["A1"].fill = title_fill
    worksheet["A1"].font = title_font

    worksheet["A1"].alignment = center_alignment

    worksheet.row_dimensions[1].height = 32

    # -----------------------------------------------------
    # ASSESSMENT INFORMATION
    # -----------------------------------------------------

    assessment_names = {
        50: "Regular Internal (50 Marks)",
        75: "Laboratory (75 Marks)",
        100: "Project (100 Marks)"
    }

    information_rows = [

        ("Course Code", course_code),

        ("Branch", branch),

        ("Semester", semester or "Not specified"),

        ("Assessment Type", assessment_names[scale]),

        ("Internal Mark Maximum", scale),

        ("Total Students", len(results))

    ]

    for row_number, (label, value) in enumerate(
        information_rows,
        start=2
    ):

        label_cell = worksheet.cell(
            row=row_number,
            column=1,
            value=label
        )

        value_cell = worksheet.cell(
            row=row_number,
            column=2,
            value=value
        )

        label_cell.font = bold_font
        label_cell.fill = information_fill
        label_cell.alignment = left_alignment
        label_cell.border = thin_border

        value_cell.font = normal_font
        value_cell.alignment = left_alignment
        value_cell.border = thin_border

    # -----------------------------------------------------
    # TABLE HEADERS
    # -----------------------------------------------------

    header_row = 9

    for column_number, header in enumerate(
        headers,
        start=1
    ):

        cell = worksheet.cell(
            row=header_row,
            column=column_number,
            value=header
        )

        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_alignment
        cell.border = header_border

    worksheet.row_dimensions[header_row].height = 30

    # -----------------------------------------------------
    # STUDENT DATA
    # -----------------------------------------------------

    first_data_row = header_row + 1

    for row_number, student in enumerate(
        results,
        start=first_data_row
    ):

        values = [

            student["reg_no"],

            student["internal_mark"],

            student["grade"],

            student["university_mark"]

        ]

        for column_number, value in enumerate(
            values,
            start=1
        ):

            cell = worksheet.cell(
                row=row_number,
                column=column_number,
                value=value
            )

            cell.font = normal_font
            cell.alignment = center_alignment
            cell.border = thin_border

            # Store marks as numeric Excel values.
            if (
                column_number >= 2
                and value is not None
            ):

                cell.number_format = "0.##"

        # Highlight missing and absent grades.
        if student["grade"].strip().upper() in {
            "NOT FOUND",
            "ABSENT"
        }:

            worksheet.cell(
                row=row_number,
                column=3
            ).fill = warning_fill

    last_data_row = (
        first_data_row + len(results) - 1
    )

    # -----------------------------------------------------
    # EXCEL TABLE
    # -----------------------------------------------------

    table_reference = (
        f"A{header_row}:"
        f"{last_column_letter}{last_data_row}"
    )

    table = Table(
        displayName="MarksTable",
        ref=table_reference
    )

    table_style = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )

    table.tableStyleInfo = table_style

    worksheet.add_table(table)

    # -----------------------------------------------------
    # COLUMN WIDTHS
    # -----------------------------------------------------

    widths = {
        1: 25,
        2: 16,
        3: 18,
        4: 17
    }

    for column_number, width in widths.items():

        worksheet.column_dimensions[
            get_column_letter(column_number)
        ].width = width

    # -----------------------------------------------------
    # SHEET SETTINGS
    # -----------------------------------------------------

    # Keep the worksheet fully scrollable (no frozen rows or columns).
    # This allows the user to scroll through the entire exported sheet.
    worksheet.freeze_panes = None
    worksheet.sheet_view.topLeftCell = "A1"
    worksheet.sheet_view.zoomScale = 90

    worksheet.auto_filter.ref = table_reference

    worksheet.page_setup.orientation = "landscape"

    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0

    worksheet.sheet_properties.pageSetUpPr.fitToPage = True

    worksheet.print_title_rows = f"1:{header_row}"

    # =====================================================
    # PROCESSING SUMMARY SHEET
    # =====================================================

    summary_sheet = workbook.create_sheet(
        "Processing Summary"
    )

    summary_sheet.sheet_view.showGridLines = False

    summary_sheet.merge_cells("A1:B1")

    summary_sheet["A1"] = "PROCESSING SUMMARY"

    summary_sheet["A1"].fill = title_fill
    summary_sheet["A1"].font = title_font
    summary_sheet["A1"].alignment = center_alignment

    summary_sheet.row_dimensions[1].height = 32

    # -----------------------------------------------------
    # AUTOMATIC SUMMARY
    # -----------------------------------------------------

    if summary is None:

        matched_count = sum(
            1
            for student in results
            if student["grade"].strip().upper()
            not in {"NOT FOUND", "ABSENT"}
        )

        missing_count = sum(
            1
            for student in results
            if student["grade"].strip().upper()
            == "NOT FOUND"
        )

        missing_reg_numbers = [
            student["reg_no"]
            for student in results
            if student["grade"].strip().upper()
            == "NOT FOUND"
        ]

        summary = {

            "total_internal_students": len(results),

            "total_result_students": "",

            "matched_students": matched_count,

            "missing_grades": missing_count,

            "result_only_students": "",

            "missing_grade_reg_numbers": missing_reg_numbers,

            "result_only_reg_numbers": []

        }

    # -----------------------------------------------------
    # SUMMARY DETAILS
    # -----------------------------------------------------

    summary_rows = [

        ("Course Code", course_code),

        ("Branch", branch),

        ("Semester", semester or "Not specified"),

        ("Assessment Type", assessment_names[scale]),

        ("Internal Mark Maximum", scale),

        (
            "Students in Internal PDF",
            summary.get(
                "total_internal_students",
                len(results)
            )
        ),

        (
            "Students in Result PDF",
            summary.get(
                "total_result_students",
                ""
            )
        ),

        (
            "Matched Students",
            summary.get(
                "matched_students",
                ""
            )
        ),

        (
            "Missing Grades",
            summary.get(
                "missing_grades",
                ""
            )
        ),

        (
            "Result-only Students",
            summary.get(
                "result_only_students",
                ""
            )
        )

    ]

    start_row = 3

    for row_number, (label, value) in enumerate(
        summary_rows,
        start=start_row
    ):

        label_cell = summary_sheet.cell(
            row=row_number,
            column=1,
            value=label
        )

        value_cell = summary_sheet.cell(
            row=row_number,
            column=2,
            value=value
        )

        label_cell.font = bold_font
        label_cell.fill = information_fill
        label_cell.alignment = left_alignment
        label_cell.border = thin_border

        value_cell.font = normal_font
        value_cell.alignment = left_alignment
        value_cell.border = thin_border

    # -----------------------------------------------------
    # MISSING GRADES SECTION
    # -----------------------------------------------------

    missing_start = (
        start_row + len(summary_rows) + 2
    )

    summary_sheet.merge_cells(
        start_row=missing_start,
        start_column=1,
        end_row=missing_start,
        end_column=2
    )

    missing_title = summary_sheet.cell(
        row=missing_start,
        column=1,
        value="STUDENTS WITHOUT MATCHED GRADE"
    )

    missing_title.fill = warning_fill
    missing_title.font = bold_font

    missing_reg_numbers = summary.get(
        "missing_grade_reg_numbers",
        []
    ) or []

    missing_row = missing_start + 1

    if missing_reg_numbers:

        for reg_no in missing_reg_numbers:

            first = summary_sheet.cell(
                row=missing_row,
                column=1,
                value=reg_no
            )

            second = summary_sheet.cell(
                row=missing_row,
                column=2,
                value="Grade not found"
            )

            first.font = normal_font
            second.font = normal_font

            first.border = thin_border
            second.border = thin_border

            missing_row += 1

    else:

        first = summary_sheet.cell(
            row=missing_row,
            column=1,
            value="None"
        )

        second = summary_sheet.cell(
            row=missing_row,
            column=2,
            value="All internal-mark students have a grade record."
        )

        first.border = thin_border
        second.border = thin_border

    # -----------------------------------------------------
    # RESULT-ONLY STUDENTS
    # -----------------------------------------------------

    result_only_start = missing_row + 2

    summary_sheet.merge_cells(
        start_row=result_only_start,
        start_column=1,
        end_row=result_only_start,
        end_column=2
    )

    result_only_title = summary_sheet.cell(
        row=result_only_start,
        column=1,
        value="RESULT-ONLY REGISTRATION NUMBERS"
    )

    result_only_title.fill = information_fill
    result_only_title.font = bold_font

    result_only_reg_numbers = summary.get(
        "result_only_reg_numbers",
        []
    ) or []

    result_only_row = result_only_start + 1

    if result_only_reg_numbers:

        for reg_no in result_only_reg_numbers:

            first = summary_sheet.cell(
                row=result_only_row,
                column=1,
                value=reg_no
            )

            second = summary_sheet.cell(
                row=result_only_row,
                column=2,
                value="Not present in internal PDF"
            )

            first.border = thin_border
            second.border = thin_border

            result_only_row += 1

    else:

        first = summary_sheet.cell(
            row=result_only_row,
            column=1,
            value="None"
        )

        second = summary_sheet.cell(
            row=result_only_row,
            column=2,
            value="No extra result records."
        )

        first.border = thin_border
        second.border = thin_border

    # -----------------------------------------------------
    # SUMMARY COLUMN WIDTHS
    # -----------------------------------------------------

    summary_sheet.column_dimensions["A"].width = 35
    summary_sheet.column_dimensions["B"].width = 48

    # Keep the summary sheet fully scrollable as well.
    summary_sheet.freeze_panes = None
    summary_sheet.sheet_view.topLeftCell = "A1"
    summary_sheet.sheet_view.zoomScale = 90

    # =====================================================
    # SAVE WORKBOOK
    # =====================================================

    try:

        workbook.save(output)

    except PermissionError as exc:

        raise ExcelExportError(
            "Could not save the Excel file. "
            "Make sure the file is not already open in Excel."
        ) from exc

    except Exception as exc:

        raise ExcelExportError(
            f"Could not create Excel file: {exc}"
        ) from exc

    return output


# =========================================================
# FILENAME HELPER
# =========================================================

def make_excel_filename(
    course_code: str
) -> str:

    course_code = _normalize_course_code(
        course_code
    )

    filename = f"{course_code}_Marks.xlsx"

    return _safe_filename(filename)


# =========================================================
# TESTING
# =========================================================

if __name__ == "__main__":

    from tempfile import TemporaryDirectory
    from openpyxl import load_workbook

    # ---------------------------------------------
    # Test 50-mark assessment
    # ---------------------------------------------

    demo_50 = [

        {
            "reg_no": "CEC23CS003",
            "internal_mark": 32,
            "grade": "C+",
            "university_mark": 69,
            "internal_mark_scale": 50
        },

        {
            "reg_no": "CEC23CS004",
            "internal_mark": 35,
            "grade": "P",
            "university_mark": 54,
            "internal_mark_scale": 50
        }

    ]

    # ---------------------------------------------
    # Test 75-mark assessment
    # ---------------------------------------------

    demo_75 = [

        {
            "reg_no": "CEC23CS100",
            "internal_mark": 63,
            "grade": "A",
            "university_mark": 84,
            "internal_mark_scale": 75
        }

    ]

    demo_100 = [
        {
            "reg_no": "CEC23CS101",
            "internal_mark": 88,
            "grade": "S",
            "university_mark": 100,
            "internal_mark_scale": 100
        }
    ]

    with TemporaryDirectory() as temp_dir:

        path_50 = generate_excel(
            demo_50,
            "CST309",
            Path(temp_dir) / "regular.xlsx",
            internal_max_mark=50
        )

        path_75 = generate_excel(
            demo_75,
            "LAB001",
            Path(temp_dir) / "lab.xlsx",
            internal_max_mark=75
        )

        path_100 = generate_excel(
            demo_100,
            "PROJ001",
            Path(temp_dir) / "project.xlsx",
            internal_max_mark=100
        )

        book_50 = load_workbook(path_50)
        book_75 = load_workbook(path_75)
        book_100 = load_workbook(path_100)

        headers_50 = [
            cell.value
            for cell in next(
                book_50["Marks"].iter_rows(
                    min_row=9,
                    max_row=9
                )
            )
        ]

        headers_75 = [
            cell.value
            for cell in next(
                book_75["Marks"].iter_rows(
                    min_row=9,
                    max_row=9
                )
            )
        ]

        expected_headers_50 = [
            "Registration Number",
            "Internal Mark",
            "CST309 Grade",
            "University Mark",
        ]
        expected_headers_75 = [
            "Registration Number",
            "Internal Mark",
            "LAB001 Grade",
            "University Mark",
        ]

        assert headers_50[:4] == expected_headers_50
        assert headers_75[:4] == expected_headers_75
        assert len(headers_50) == 4
        assert len(headers_75) == 4

        headers_100 = [
            cell.value
            for cell in book_100["Marks"].iter_rows(
                min_row=9,
                max_row=9
            ).__next__()
        ]

        expected_headers_100 = [
            "Registration Number",
            "Internal Mark",
            "PROJ001 Grade",
            "University Mark",
        ]

        assert headers_100[:4] == expected_headers_100
        assert len(headers_100) == 4

        # Both sheets must remain normally scrollable.
        for book in (book_50, book_75, book_100):
            assert book["Marks"].freeze_panes is None
            assert book["Processing Summary"].freeze_panes is None
            book.close()

        print("Excel export tests passed.")

        print(
            "50-mark: four columns only; worksheet is scrollable"
        )

        print(
            "75-mark: four columns only; worksheet is scrollable"
        )

        print(
            "100-mark: four columns only; worksheet is scrollable"
        )