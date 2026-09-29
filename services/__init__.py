"""
Services package for the KTU Mark Processing System.

Contains:
    - Data matching
    - Excel generation
"""
from .matcher import (
    MatchingError,
    merge_mark_data,
    create_processing_summary,
    process_and_summarize,
    find_missing_grades,
    count_matched_students,
    count_missing_students,
)

from .excel_exporter import (
    ExcelExportError,
    generate_excel,
    make_excel_filename,
)


__all__ = [
    "MatchingError",
    "merge_mark_data",
    "create_processing_summary",
    "process_and_summarize",
    "find_missing_grades",
    "count_matched_students",
    "count_missing_students",

    "ExcelExportError",
    "generate_excel",
    "make_excel_filename",
]