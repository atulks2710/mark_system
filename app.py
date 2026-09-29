"""
MAIN FLASK APPLICATION
======================

KTU Mark Processing System

Workflow:

1. Teacher uploads Internal Mark PDF.
2. Server extracts:
       Registration Number
       Internal Mark
3. Teacher manually enters Course Code.
4. Teacher uploads Result PDF.
5. Server:
       - Locates Computer Science & Engineering section
       - Uses the manually entered course code
       - Extracts grades
6. Registration numbers are matched.
7. Final table is returned to frontend.
8. Teacher can download Excel file.

Project structure expected:

mark_processing_system/
│
├── app.py
│
├── parser/
│   ├── __init__.py
│   ├── internal_parser.py
│   └── result_parser.py
│
├── services/
│   ├── __init__.py
│   ├── matcher.py
│   └── excel_exporter.py
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
│
├── storage/
│   └── temp/
│
├── templates/
│   └── index.html
│
└── requirements.txt
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timedelta

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)

from werkzeug.utils import secure_filename


# ---------------------------------------------------------------------------
# IMPORT OUR OWN MODULES
# ---------------------------------------------------------------------------

from parser import (
    InternalPDFError,
    ResultPDFError,
    extract_internal_marks,
    extract_result_grades,
    extract_result_course_codes,
)

from services import (
    MatchingError,
    merge_mark_data,
    create_processing_summary,
    ExcelExportError,
    generate_excel,
    make_excel_filename,
)


# ---------------------------------------------------------------------------
# FLASK APPLICATION
# ---------------------------------------------------------------------------

app = Flask(__name__)


# ---------------------------------------------------------------------------
# APPLICATION CONFIGURATION
# ---------------------------------------------------------------------------

BASE_DIR = Path(
    __file__
).resolve().parent


STORAGE_DIR = (
    BASE_DIR
    / "storage"
)


TEMP_DIR = (
    STORAGE_DIR
    / "temp"
)


# Maximum upload size.
#
# 20 MB should be more than enough for normal KTU result PDFs.
MAX_FILE_SIZE = 20 * 1024 * 1024


app.config[
    "MAX_CONTENT_LENGTH"
] = MAX_FILE_SIZE


# Allowed file extension.
ALLOWED_EXTENSIONS = {
    ".pdf"
}


# Temporary sessions expire after this amount of time.
SESSION_EXPIRY_MINUTES = 60


# Create temp folder automatically.
TEMP_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# IN-MEMORY PROCESSING SESSIONS
# ---------------------------------------------------------------------------
#
# We are intentionally not using MongoDB/database for Version 1.
#
# The teacher's processing session is temporarily held in memory:
#
# jobs = {
#
#     "job-id": {
#
#         "created_at": datetime,
#
#         "internal_pdf": "...",
#
#         "result_pdf": "...",
#
#         "internal_marks": {...},
#
#         "grades": {...},
#
#         "course_code": "CST309",
#
#         "results": [...]
#
#     }
#
# }
#
# Later, this can be replaced with a database if required.
# ---------------------------------------------------------------------------

jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    """
    Check whether uploaded file has a PDF extension.
    """

    if not filename:
        return False

    extension = Path(
        filename
    ).suffix.lower()

    return extension in ALLOWED_EXTENSIONS


def create_job() -> str:
    """
    Create a unique processing session.

    Returns:
        UUID string
    """

    job_id = str(
        uuid.uuid4()
    )

    jobs[job_id] = {
        "created_at": datetime.now(),
        "internal_pdf": None,
        "result_pdf": None,
        "internal_filename": None,
        "result_filename": None,
        "internal_marks": {},
        "grades": {},
        "course_code": None,
        "results": [],
        "summary": {},
        "branch": "COMPUTER SCIENCE & ENGINEERING",
        "semester": "",
    }

    return job_id


def get_job(job_id: str) -> dict | None:
    """
    Retrieve an existing processing session.
    """

    return jobs.get(
        job_id
    )


def save_uploaded_file(
    uploaded_file,
    job_id: str,
    prefix: str,
) -> Path:
    """
    Save uploaded PDF into a unique temporary location.

    Example:
        storage/temp/
            abc123_internal_Report.pdf
    """

    original_filename = secure_filename(
        uploaded_file.filename
    )

    if not original_filename:
        raise ValueError(
            "Invalid filename."
        )

    extension = Path(
        original_filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only PDF files are allowed."
        )

    safe_name = (
        f"{job_id}_{prefix}_"
        f"{original_filename}"
    )

    destination = (
        TEMP_DIR
        / safe_name
    )

    uploaded_file.save(
        destination
    )

    return destination


def remove_file(path: str | Path | None) -> None:
    """
    Safely delete a temporary file.
    """

    if not path:
        return

    try:

        file_path = Path(
            path
        )

        if file_path.exists():
            file_path.unlink()

    except Exception:
        # Cleanup should never crash the application.
        pass


def cleanup_old_jobs() -> None:
    """
    Remove old processing sessions.

    This prevents storage/memory from growing forever.
    """

    now = datetime.now()

    expired_job_ids = []

    for job_id, job in jobs.items():

        created_at = job.get(
            "created_at"
        )

        if not created_at:
            expired_job_ids.append(
                job_id
            )
            continue

        age = (
            now - created_at
        )

        if age > timedelta(
            minutes=SESSION_EXPIRY_MINUTES
        ):

            expired_job_ids.append(
                job_id
            )

    for job_id in expired_job_ids:

        job = jobs.pop(
            job_id,
            None
        )

        if not job:
            continue

        remove_file(
            job.get(
                "internal_pdf"
            )
        )

        remove_file(
            job.get(
                "result_pdf"
            )
        )


def json_error(
    message: str,
    status_code: int = 400,
):
    """
    Return a consistent JSON error response.
    """

    return jsonify(
        {
            "success": False,
            "error": message,
        }
    ), status_code


# ---------------------------------------------------------------------------
# HOME PAGE
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """
    Render the main website.
    """

    return render_template(
        "index.html"
    )


# ---------------------------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """
    Simple endpoint to check whether Flask is running.
    """

    return jsonify(
        {
            "success": True,
            "message": "Mark Processing System is running.",
        }
    )


# ---------------------------------------------------------------------------
# STEP 1
# UPLOAD INTERNAL PDF
# ---------------------------------------------------------------------------

@app.post("/api/upload-internal")
def upload_internal():
    """
    Receive and process the Internal Mark PDF.

    Expected form field:

        internal_pdf

    Response:

        {
            "success": true,
            "job_id": "...",
            "student_count": 61,
            "students": [...]
        }
    """

    # Remove expired jobs first.
    cleanup_old_jobs()

    # Check whether file was submitted.
    if "internal_pdf" not in request.files:

        return json_error(
            "Please select the Internal Mark PDF."
        )

    uploaded_file = request.files[
        "internal_pdf"
    ]

    # Browser may submit an empty filename.
    if not uploaded_file.filename:

        return json_error(
            "No Internal Mark PDF was selected."
        )

    # Check extension.
    if not allowed_file(
        uploaded_file.filename
    ):

        return json_error(
            "Invalid file type. "
            "Please upload a PDF file."
        )

    # Create processing session.
    job_id = create_job()

    job = jobs[
        job_id
    ]

    try:

        # Save uploaded PDF.
        internal_path = save_uploaded_file(
            uploaded_file,
            job_id,
            "internal",
        )

        job[
            "internal_pdf"
        ] = str(
            internal_path
        )

        job[
            "internal_filename"
        ] = secure_filename(
            uploaded_file.filename
        )

        # Parse internal marks.
        internal_marks = extract_internal_marks(
            internal_path
        )

        # Store extracted data.
        job[
            "internal_marks"
        ] = internal_marks

        # Convert to frontend-friendly list.
        students = [
            {
                "reg_no": reg_no,
                "internal_mark": mark,
            }
            for reg_no, mark
            in internal_marks.items()
        ]

        # Return success.
        return jsonify(
            {
                "success": True,

                "job_id": job_id,

                "student_count": len(
                    internal_marks
                ),

                "students": students,

                "message": (
                    "Internal Mark PDF processed successfully."
                ),
            }
        )

    except InternalPDFError as exc:

        # Delete failed session/files.
        remove_file(
            job.get(
                "internal_pdf"
            )
        )

        jobs.pop(
            job_id,
            None,
        )

        return json_error(
            str(exc)
        )

    except Exception as exc:

        remove_file(
            job.get(
                "internal_pdf"
            )
        )

        jobs.pop(
            job_id,
            None,
        )

        app.logger.exception(
            "Unexpected error while processing Internal PDF."
        )

        return json_error(
            f"Unexpected error while processing PDF: {exc}",
            500,
        )


# ---------------------------------------------------------------------------
# GET EXTRACTED INTERNAL DATA
# ---------------------------------------------------------------------------

@app.get("/api/internal/<job_id>")
def get_internal_data(
    job_id: str,
):
    """
    Return extracted internal marks for an existing session.
    """

    cleanup_old_jobs()

    job = get_job(
        job_id
    )

    if not job:

        return json_error(
            "Processing session not found or expired.",
            404,
        )

    internal_marks = job.get(
        "internal_marks",
        {}
    )

    students = [
        {
            "reg_no": reg_no,
            "internal_mark": mark,
        }
        for reg_no, mark
        in internal_marks.items()
    ]

    return jsonify(
        {
            "success": True,
            "job_id": job_id,
            "student_count": len(
                students
            ),
            "students": students,
        }
    )


# ---------------------------------------------------------------------------
# GET AVAILABLE CSE COURSE CODES
# ---------------------------------------------------------------------------

@app.post("/api/course-codes")
def get_course_codes():
    """
    Read the Result PDF and return course codes from the
    Computer Science & Engineering section.

    IMPORTANT:
        This endpoint does NOT automatically choose a course.

    It is only intended to provide optional suggestions to the frontend.

    The teacher still manually enters/selects the actual course code.
    """

    if "result_pdf" not in request.files:

        return json_error(
            "Please upload the Result PDF."
        )

    uploaded_file = request.files[
        "result_pdf"
    ]

    if not uploaded_file.filename:

        return json_error(
            "No Result PDF was selected."
        )

    if not allowed_file(
        uploaded_file.filename
    ):

        return json_error(
            "Invalid file type. "
            "Please upload a PDF file."
        )

    # Temporary ID for this operation.
    temp_id = str(
        uuid.uuid4()
    )

    try:

        temp_path = save_uploaded_file(
            uploaded_file,
            temp_id,
            "course-list",
        )

        course_codes = extract_result_course_codes(
            temp_path
        )

        return jsonify(
            {
                "success": True,
                "course_codes": course_codes,
            }
        )

    except ResultPDFError as exc:

        return json_error(
            str(exc)
        )

    except Exception as exc:

        app.logger.exception(
            "Unexpected error while reading course codes."
        )

        return json_error(
            f"Unexpected error while reading Result PDF: {exc}",
            500,
        )

    finally:

        # Delete temporary course-list PDF.
        remove_file(
            TEMP_DIR
            / f"{temp_id}_course-list_"
            f"{secure_filename(uploaded_file.filename)}"
        )


# ---------------------------------------------------------------------------
# STEP 2
# PROCESS RESULT PDF
# ---------------------------------------------------------------------------

@app.post("/api/process-result")
def process_result():
    """
    Process Result PDF using the manually entered course code.

    Expected form fields:

        job_id
        course_code
        result_pdf

    The course code is ALWAYS supplied by the teacher.

    Example:

        course_code = CST309
    """

    cleanup_old_jobs()

    # ---------------------------------------------------------------
    # JOB ID
    # ---------------------------------------------------------------

    job_id = (
        request.form.get(
            "job_id",
            "",
        )
        .strip()
    )

    if not job_id:

        return json_error(
            "Processing session ID is missing."
        )

    job = get_job(
        job_id
    )

    if not job:

        return json_error(
            "Processing session not found or expired. "
            "Please upload the Internal Mark PDF again.",
            404,
        )

    # ---------------------------------------------------------------
    # COURSE CODE
    # ---------------------------------------------------------------

    course_code = (
        request.form.get(
            "course_code",
            "",
        )
        .strip()
        .upper()
    )

    if not course_code:

        return json_error(
            "Please enter the course code."
        )

    # ---------------------------------------------------------------
    # RESULT PDF
    # ---------------------------------------------------------------

    if "result_pdf" not in request.files:

        return json_error(
            "Please select the Result PDF."
        )

    uploaded_file = request.files[
        "result_pdf"
    ]

    if not uploaded_file.filename:

        return json_error(
            "No Result PDF was selected."
        )

    if not allowed_file(
        uploaded_file.filename
    ):

        return json_error(
            "Invalid file type. "
            "Please upload a PDF file."
        )

    # ---------------------------------------------------------------
    # SAVE RESULT PDF
    # ---------------------------------------------------------------

    try:

        result_path = save_uploaded_file(
            uploaded_file,
            job_id,
            "result",
        )

        # If an earlier result PDF exists, remove it.
        old_result = job.get(
            "result_pdf"
        )

        if old_result:

            old_path = Path(
                old_result
            )

            if old_path != result_path:

                remove_file(
                    old_path
                )

        job[
            "result_pdf"
        ] = str(
            result_path
        )

        job[
            "result_filename"
        ] = secure_filename(
            uploaded_file.filename
        )

        # ---------------------------------------------------------------
        # EXTRACT GRADES
        # ---------------------------------------------------------------

        grades = extract_result_grades(
            result_path,
            course_code,
        )

        job[
            "grades"
        ] = grades

        job[
            "course_code"
        ] = course_code

        # ---------------------------------------------------------------
        # MATCH DATA
        # ---------------------------------------------------------------

        internal_marks = job.get(
            "internal_marks",
            {}
        )

        if not internal_marks:

            return json_error(
                "No internal-mark data exists for this session. "
                "Please upload the Internal Mark PDF again."
            )

        results = merge_mark_data(
            internal_marks,
            grades,
        )

        # ---------------------------------------------------------------
        # SUMMARY
        # ---------------------------------------------------------------

        summary = create_processing_summary(
            internal_marks,
            grades,
        )

        # Save everything into job.
        job[
            "results"
        ] = results

        job[
            "summary"
        ] = summary

        # ---------------------------------------------------------------
        # FRONTEND RESPONSE
        # ---------------------------------------------------------------

        return jsonify(
            {
                "success": True,

                "job_id": job_id,

                "course_code": course_code,

                "total_students": len(
                    results
                ),

                "matched_students": summary[
                    "matched_students"
                ],

                "missing_grades": summary[
                    "missing_grades"
                ],

                "result_only_students": summary[
                    "result_only_students"
                ],

                "missing_grade_reg_numbers":
                    summary[
                        "missing_grade_reg_numbers"
                    ],

                "result_only_reg_numbers":
                    summary[
                        "result_only_reg_numbers"
                    ],

                "rows": results,

                "message": (
                    f"{course_code} grades processed successfully."
                ),
            }
        )

    except ResultPDFError as exc:

        return json_error(
            str(exc)
        )

    except MatchingError as exc:

        return json_error(
            str(exc)
        )

    except Exception as exc:

        app.logger.exception(
            "Unexpected error while processing Result PDF."
        )

        return json_error(
            f"Unexpected error while processing Result PDF: {exc}",
            500,
        )


# ---------------------------------------------------------------------------
# REPROCESS EXISTING RESULT PDF WITH ANOTHER COURSE CODE
# ---------------------------------------------------------------------------

@app.post("/api/change-course")
def change_course():
    """
    Reprocess the already uploaded Result PDF using a new
    manually entered course code.

    This means the teacher does NOT have to upload the
    Internal PDF again.

    Example:

        Previously:
            CST309

        Teacher changes to:
            CST305

        The same Result PDF is processed again.
    """

    cleanup_old_jobs()

    job_id = (
        request.form.get(
            "job_id",
            "",
        )
        .strip()
    )

    course_code = (
        request.form.get(
            "course_code",
            "",
        )
        .strip()
        .upper()
    )

    if not job_id:

        return json_error(
            "Processing session ID is missing."
        )

    job = get_job(
        job_id
    )

    if not job:

        return json_error(
            "Processing session not found or expired.",
            404,
        )

    if not course_code:

        return json_error(
            "Please enter the new course code."
        )

    result_pdf = job.get(
        "result_pdf"
    )

    if not result_pdf:

        return json_error(
            "No Result PDF is stored in this session."
        )

    result_path = Path(
        result_pdf
    )

    if not result_path.exists():

        return json_error(
            "The stored Result PDF is no longer available. "
            "Please upload it again."
        )

    try:

        # ---------------------------------------------------------------
        # Extract grade using new manually entered course code
        # ---------------------------------------------------------------

        grades = extract_result_grades(
            result_path,
            course_code,
        )

        internal_marks = job.get(
            "internal_marks",
            {}
        )

        if not internal_marks:

            return json_error(
                "Internal-mark data is missing."
            )

        # ---------------------------------------------------------------
        # Match again
        # ---------------------------------------------------------------

        results = merge_mark_data(
            internal_marks,
            grades,
        )

        summary = create_processing_summary(
            internal_marks,
            grades,
        )

        # ---------------------------------------------------------------
        # Update job
        # ---------------------------------------------------------------

        job[
            "course_code"
        ] = course_code

        job[
            "grades"
        ] = grades

        job[
            "results"
        ] = results

        job[
            "summary"
        ] = summary

        # ---------------------------------------------------------------
        # Response
        # ---------------------------------------------------------------

        return jsonify(
            {
                "success": True,

                "job_id": job_id,

                "course_code": course_code,

                "total_students": len(
                    results
                ),

                "matched_students":
                    summary[
                        "matched_students"
                    ],

                "missing_grades":
                    summary[
                        "missing_grades"
                    ],

                "result_only_students":
                    summary[
                        "result_only_students"
                    ],

                "missing_grade_reg_numbers":
                    summary[
                        "missing_grade_reg_numbers"
                    ],

                "result_only_reg_numbers":
                    summary[
                        "result_only_reg_numbers"
                    ],

                "rows": results,

                "message": (
                    f"Course changed to {course_code} "
                    "and results were reprocessed."
                ),
            }
        )

    except ResultPDFError as exc:

        return json_error(
            str(exc)
        )

    except MatchingError as exc:

        return json_error(
            str(exc)
        )

    except Exception as exc:

        app.logger.exception(
            "Unexpected error while changing course."
        )

        return json_error(
            f"Unexpected error while reprocessing: {exc}",
            500,
        )


# ---------------------------------------------------------------------------
# GET CURRENT RESULTS
# ---------------------------------------------------------------------------

@app.get("/api/results/<job_id>")
def get_results(
    job_id: str,
):
    """
    Return the current processed results for a session.
    """

    cleanup_old_jobs()

    job = get_job(
        job_id
    )

    if not job:

        return json_error(
            "Processing session not found or expired.",
            404,
        )

    results = job.get(
        "results",
        []
    )

    summary = job.get(
        "summary",
        {}
    )

    return jsonify(
        {
            "success": True,

            "job_id": job_id,

            "course_code": job.get(
                "course_code"
            ),

            "total_students": len(
                results
            ),

            "matched_students":
                summary.get(
                    "matched_students",
                    0,
                ),

            "missing_grades":
                summary.get(
                    "missing_grades",
                    0,
                ),

            "result_only_students":
                summary.get(
                    "result_only_students",
                    0,
                ),

            "missing_grade_reg_numbers":
                summary.get(
                    "missing_grade_reg_numbers",
                    [],
                ),

            "result_only_reg_numbers":
                summary.get(
                    "result_only_reg_numbers",
                    [],
                ),

            "rows": results,
        }
    )


# ---------------------------------------------------------------------------
# EXCEL EXPORT
# ---------------------------------------------------------------------------

@app.get("/api/export/<job_id>")
def export_excel(
    job_id: str,
):
    """
    Generate and download the final Excel workbook.
    """

    cleanup_old_jobs()

    job = get_job(
        job_id
    )

    if not job:

        return json_error(
            "Processing session not found or expired.",
            404,
        )

    results = job.get(
        "results",
        []
    )

    course_code = job.get(
        "course_code"
    )

    summary = job.get(
        "summary",
        {}
    )

    if not results:

        return json_error(
            "There are no processed results to export."
        )

    if not course_code:

        return json_error(
            "Course code is missing. "
            "Please process the result again."
        )

    # -----------------------------------------------------------------------
    # Generate filename
    # -----------------------------------------------------------------------

    filename = make_excel_filename(
        course_code
    )

    output_path = (
        TEMP_DIR
        / f"{job_id}_{filename}"
    )

    try:

        generated_file = generate_excel(
            results=results,

            course_code=course_code,

            output_path=output_path,

            summary=summary,

            branch=job.get(
                "branch",
                "COMPUTER SCIENCE & ENGINEERING",
            ),

            semester=job.get(
                "semester",
                "",
            ),
        )

        return send_file(
            generated_file,

            as_attachment=True,

            download_name=filename,

            mimetype=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

    except ExcelExportError as exc:

        return json_error(
            str(exc)
        )

    except Exception as exc:

        app.logger.exception(
            "Unexpected error while generating Excel."
        )

        return json_error(
            f"Could not generate Excel file: {exc}",
            500,
        )


# ---------------------------------------------------------------------------
# DELETE / START NEW SESSION
# ---------------------------------------------------------------------------

@app.delete("/api/session/<job_id>")
def delete_session(
    job_id: str,
):
    """
    Delete a processing session and temporary files.
    """

    job = jobs.pop(
        job_id,
        None,
    )

    if not job:

        return json_error(
            "Processing session not found.",
            404,
        )

    remove_file(
        job.get(
            "internal_pdf"
        )
    )

    remove_file(
        job.get(
            "result_pdf"
        )
    )

    return jsonify(
        {
            "success": True,
            "message": (
                "Processing session deleted."
            ),
        }
    )


# ---------------------------------------------------------------------------
# FILE SIZE ERROR
# ---------------------------------------------------------------------------

@app.errorhandler(
    413
)
def request_entity_too_large(error):
    """
    Handle PDF files larger than MAX_FILE_SIZE.
    """

    return json_error(
        "The uploaded PDF is too large. "
        "Maximum allowed size is 20 MB.",
        413,
    )


# ---------------------------------------------------------------------------
# GENERAL ERROR HANDLER
# ---------------------------------------------------------------------------

@app.errorhandler(
    500
)
def internal_server_error(error):
    """
    Handle unexpected Flask errors.
    """

    app.logger.exception(
        "Internal server error."
    )

    return json_error(
        "An unexpected server error occurred.",
        500,
    )


# ---------------------------------------------------------------------------
# APPLICATION START
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )