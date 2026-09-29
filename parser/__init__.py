"""
PDF parser package for the KTU Mark Processing System.

This package exposes the two main parsing functions:
    - extract_internal_marks()
    - extract_result_grades()

It also exposes extract_result_course_codes(), which can be used
by the frontend to show available course codes as suggestions.

The teacher still manually selects/types the actual course code.
"""

from .internal_parser import (
    InternalPDFError,
    extract_internal_marks,
    extract_internal_records,
)

from .result_parser import (
    ResultPDFError,
    extract_result_grades,
    extract_result_course_codes,
)

__all__ = [
    "InternalPDFError",
    "ResultPDFError",
    "extract_internal_marks",
    "extract_internal_records",
    "extract_result_grades",
    "extract_result_course_codes",
]