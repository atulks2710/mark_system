"""
ANSORA Mark Processing System
Flask application and API routes.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
)
from werkzeug.utils import secure_filename

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
# FLASK APPLICATION AND CONFIGURATION
# ---------------------------------------------------------------------------

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
TEMP_DIR = STORAGE_DIR / "temp"

MAX_FILE_SIZE = 20 * 1024 * 1024
SESSION_EXPIRY_MINUTES = 60
ALLOWED_EXTENSIONS = {".pdf"}
ALLOWED_INTERNAL_SCALES = {"50", "75", "100"}

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Version 1 stores temporary processing sessions in memory.
jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    """Return True only for files with a PDF extension."""
    if not filename:
        return False
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def create_job(internal_mark_scale: int) -> str:
    """Create a new processing session and remember its assessment scale."""
    job_id = str(uuid.uuid4())

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
        "internal_mark_scale": internal_mark_scale,
        "branch": "COMPUTER SCIENCE & ENGINEERING",
        "semester": "",
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    """Return a processing session, or None if it does not exist."""
    return jobs.get(job_id)


def save_uploaded_file(uploaded_file, job_id: str, prefix: str) -> Path:
    """Save an uploaded PDF using a safe, session-specific filename."""
    original_filename = secure_filename(uploaded_file.filename or "")
    if not original_filename:
        raise ValueError("Invalid filename.")

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF files are allowed.")

    destination = TEMP_DIR / f"{job_id}_{prefix}_{original_filename}"
    uploaded_file.save(destination)
    return destination


def remove_file(path: str | Path | None) -> None:
    """Delete a temporary file without allowing cleanup errors to crash Flask."""
    if not path:
        return
    try:
        file_path = Path(path)
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except Exception:
        app.logger.warning("Could not remove temporary file: %s", path)


def remove_job_files(job: dict) -> None:
    """Delete the PDF files belonging to a session."""
    remove_file(job.get("internal_pdf"))
    remove_file(job.get("result_pdf"))


def cleanup_old_jobs() -> None:
    """Remove expired sessions and their temporary PDF files."""
    now = datetime.now()
    expired_ids = []

    for job_id, job in list(jobs.items()):
        created_at = job.get("created_at")
        if not created_at or now - created_at > timedelta(minutes=SESSION_EXPIRY_MINUTES):
            expired_ids.append(job_id)

    for job_id in expired_ids:
        job = jobs.pop(job_id, None)
        if job:
            remove_job_files(job)


def json_error(message: str, status_code: int = 400):
    """Return a consistent JSON error response."""
    return jsonify({"success": False, "error": message}), status_code


def get_request_value(name: str, default: str = "") -> str:
    """
    Read a value from either a regular form submission or a JSON request.
    The updated frontend sends JSON when changing course codes.
    """
    value = request.form.get(name)
    if value is None:
        payload = request.get_json(silent=True) or {}
        value = payload.get(name, default)
    return str(value if value is not None else default).strip()


def get_internal_scale(job: dict) -> int:
    """Return the stored internal assessment maximum mark."""
    try:
        scale = int(job.get("internal_mark_scale", 50))
    except (TypeError, ValueError):
        scale = 50

    if scale not in (50, 75, 100):
        raise ValueError("Invalid internal assessment scale stored in session.")
    return scale


def merge_session_marks(internal_marks: dict, grades: dict, course_code: str, job: dict):
    """
    Merge marks using the assessment maximum selected in Step 1.

    The matcher is being updated alongside this application. Parameter
    inspection keeps this route compatible with either internal_max_mark
    or internal_mark_scale as the matcher's scale argument.
    """
    scale = get_internal_scale(job)
    parameters = inspect.signature(merge_mark_data).parameters
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    kwargs = {}
    if "course_code" in parameters or accepts_kwargs:
        kwargs["course_code"] = course_code

    if "internal_max_mark" in parameters or accepts_kwargs:
        kwargs["internal_max_mark"] = scale
    elif "internal_mark_scale" in parameters:
        kwargs["internal_mark_scale"] = scale
    elif "assessment_scale" in parameters:
        kwargs["assessment_scale"] = scale

    return merge_mark_data(internal_marks, grades, **kwargs)


def make_frontend_summary(summary: dict, results: list, internal_marks: dict) -> dict:
    """
    Normalize summary names expected by the browser while preserving all
    fields returned by the summary service.
    """
    data = dict(summary or {})

    matched = data.get(
        "matched_students",
        data.get("matched", sum(1 for row in results if str(row.get("grade", "")).upper() not in {"NOT FOUND", ""})),
    )
    missing = data.get(
        "missing_students",
        data.get("missing_grades", data.get("missing", max(0, len(internal_marks) - int(matched or 0)))),
    )
    missing_reg_nos = data.get(
        "missing_reg_nos",
        data.get("missing_grade_reg_numbers", data.get("missing_reg_numbers", [])),
    )

    data["total_students"] = len(internal_marks)
    data["matched_students"] = int(matched or 0)
    data["missing_students"] = int(missing or 0)
    data["missing_reg_nos"] = list(missing_reg_nos or [])
    return data


def processing_response(job_id: str, course_code: str, results: list, summary: dict):
    """Create a standard result response for process and change-course routes."""
    job = jobs[job_id]
    frontend_summary = make_frontend_summary(
        summary,
        results,
        job.get("internal_marks", {}),
    )

    return jsonify({
        "success": True,
        "job_id": job_id,
        "course_code": course_code,
        "internal_mark_scale": get_internal_scale(job),
        "assessment_type": {
            50: "Regular Internal",
            75: "Laboratory",
            100: "Project",
        }[get_internal_scale(job)],
        "total_students": frontend_summary["total_students"],
        "matched_students": frontend_summary["matched_students"],
        "missing_grades": frontend_summary["missing_students"],
        "result_only_students": summary.get("result_only_students", 0),
        "missing_grade_reg_numbers": summary.get("missing_grade_reg_numbers", []),
        "result_only_reg_numbers": summary.get("result_only_reg_numbers", []),
        "summary": frontend_summary,
        "rows": results,
        "message": f"{course_code} grades processed successfully.",
    })


# ---------------------------------------------------------------------------
# HOME PAGE AND HEALTH CHECK
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health_check():
    return jsonify({
        "success": True,
        "message": "ANSORA Mark Processing System is running.",
    })


# ---------------------------------------------------------------------------
# STEP 1: UPLOAD INTERNAL PDF
# ---------------------------------------------------------------------------

@app.post("/api/upload-internal")
def upload_internal():
    cleanup_old_jobs()

    if "internal_pdf" not in request.files:
        return json_error("Please select the internal marks PDF.")

    uploaded_file = request.files["internal_pdf"]
    if not uploaded_file.filename:
        return json_error("No internal marks PDF was selected.")

    if not allowed_file(uploaded_file.filename):
        return json_error("Invalid file type. Please upload a PDF file.")

    scale_value = get_request_value("internal_mark_scale")
    if scale_value not in ALLOWED_INTERNAL_SCALES:
        return json_error(
            "Please select an assessment type: 50, 75 or 100 marks."
        )

    internal_mark_scale = int(scale_value)
    job_id = create_job(internal_mark_scale)
    job = jobs[job_id]

    try:
        internal_path = save_uploaded_file(uploaded_file, job_id, "internal")
        job["internal_pdf"] = str(internal_path)
        job["internal_filename"] = secure_filename(uploaded_file.filename)

        internal_marks = extract_internal_marks(internal_path)
        if not internal_marks:
            raise InternalPDFError("No student internal marks were found in the PDF.")

        job["internal_marks"] = internal_marks

        students = [
            {"reg_no": reg_no, "internal_mark": mark}
            for reg_no, mark in internal_marks.items()
        ]

        return jsonify({
            "success": True,
            "job_id": job_id,
            "student_count": len(students),
            "internal_mark_scale": internal_mark_scale,
            "assessment_type": {
                50: "Regular Internal",
                75: "Laboratory",
                100: "Project",
            }[internal_mark_scale],
            "students": students,
            "message": "Internal marks PDF processed successfully.",
        })

    except InternalPDFError as exc:
        remove_job_files(job)
        jobs.pop(job_id, None)
        return json_error(str(exc))

    except Exception as exc:
        remove_job_files(job)
        jobs.pop(job_id, None)
        app.logger.exception("Unexpected error while processing internal PDF.")
        return json_error(f"Unexpected error while processing PDF: {exc}", 500)


# ---------------------------------------------------------------------------
# GET EXTRACTED INTERNAL DATA
# ---------------------------------------------------------------------------

@app.get("/api/internal/<job_id>")
def get_internal_data(job_id: str):
    cleanup_old_jobs()
    job = get_job(job_id)

    if not job:
        return json_error("Processing session not found or expired.", 404)

    internal_marks = job.get("internal_marks", {})
    students = [
        {"reg_no": reg_no, "internal_mark": mark}
        for reg_no, mark in internal_marks.items()
    ]

    return jsonify({
        "success": True,
        "job_id": job_id,
        "student_count": len(students),
        "internal_mark_scale": get_internal_scale(job),
        "students": students,
    })


# ---------------------------------------------------------------------------
# OPTIONAL COURSE CODE SUGGESTIONS
# ---------------------------------------------------------------------------

@app.post("/api/course-codes")
def get_course_codes():
    if "result_pdf" not in request.files:
        return json_error("Please upload the result PDF.")

    uploaded_file = request.files["result_pdf"]
    if not uploaded_file.filename:
        return json_error("No result PDF was selected.")

    if not allowed_file(uploaded_file.filename):
        return json_error("Invalid file type. Please upload a PDF file.")

    temp_id = str(uuid.uuid4())
    temp_path = None

    try:
        temp_path = save_uploaded_file(uploaded_file, temp_id, "course-list")
        course_codes = extract_result_course_codes(temp_path)

        return jsonify({
            "success": True,
            "course_codes": course_codes,
        })

    except ResultPDFError as exc:
        return json_error(str(exc))

    except Exception as exc:
        app.logger.exception("Unexpected error while reading course codes.")
        return json_error(f"Unexpected error while reading result PDF: {exc}", 500)

    finally:
        if temp_path:
            remove_file(temp_path)


# ---------------------------------------------------------------------------
# STEP 2: PROCESS RESULT PDF
# ---------------------------------------------------------------------------

@app.post("/api/process-result")
def process_result():
    cleanup_old_jobs()

    job_id = get_request_value("job_id")
    course_code = get_request_value("course_code").upper()

    if not job_id:
        return json_error("Processing session ID is missing.")

    job = get_job(job_id)
    if not job:
        return json_error(
            "Processing session not found or expired. Please upload the internal marks PDF again.",
            404,
        )

    if not course_code:
        return json_error("Please enter the course code.")

    if "result_pdf" not in request.files:
        return json_error("Please select the result PDF.")

    uploaded_file = request.files["result_pdf"]
    if not uploaded_file.filename:
        return json_error("No result PDF was selected.")

    if not allowed_file(uploaded_file.filename):
        return json_error("Invalid file type. Please upload a PDF file.")

    result_path = None

    try:
        result_path = save_uploaded_file(uploaded_file, job_id, "result")

        old_result = job.get("result_pdf")
        if old_result and Path(old_result) != result_path:
            remove_file(old_result)

        job["result_pdf"] = str(result_path)
        job["result_filename"] = secure_filename(uploaded_file.filename)

        grades = extract_result_grades(result_path, course_code)
        internal_marks = job.get("internal_marks", {})

        if not internal_marks:
            return json_error(
                "No internal-mark data exists for this session. Please upload the internal marks PDF again."
            )

        results = merge_session_marks(internal_marks, grades, course_code, job)
        summary = create_processing_summary(internal_marks, grades)

        job["grades"] = grades
        job["course_code"] = course_code
        job["results"] = results
        job["summary"] = summary

        return processing_response(job_id, course_code, results, summary)

    except ResultPDFError as exc:
        return json_error(str(exc))

    except MatchingError as exc:
        return json_error(str(exc))

    except Exception as exc:
        app.logger.exception("Unexpected error while processing result PDF.")
        return json_error(f"Unexpected error while processing result PDF: {exc}", 500)


# ---------------------------------------------------------------------------
# REPROCESS STORED RESULT PDF WITH ANOTHER COURSE CODE
# ---------------------------------------------------------------------------

@app.post("/api/change-course")
def change_course():
    cleanup_old_jobs()

    # Accept both JSON (updated frontend) and form-encoded requests.
    job_id = get_request_value("job_id")
    course_code = get_request_value("course_code").upper()

    if not job_id:
        return json_error("Processing session ID is missing.")

    job = get_job(job_id)
    if not job:
        return json_error("Processing session not found or expired.", 404)

    if not course_code:
        return json_error("Please enter the new course code.")

    result_pdf = job.get("result_pdf")
    if not result_pdf:
        return json_error("No result PDF is stored in this session.")

    result_path = Path(result_pdf)
    if not result_path.exists():
        return json_error(
            "The stored result PDF is no longer available. Please upload it again."
        )

    try:
        grades = extract_result_grades(result_path, course_code)
        internal_marks = job.get("internal_marks", {})

        if not internal_marks:
            return json_error("Internal-mark data is missing.")

        results = merge_session_marks(internal_marks, grades, course_code, job)
        summary = create_processing_summary(internal_marks, grades)

        job["course_code"] = course_code
        job["grades"] = grades
        job["results"] = results
        job["summary"] = summary

        return processing_response(job_id, course_code, results, summary)

    except ResultPDFError as exc:
        return json_error(str(exc))

    except MatchingError as exc:
        return json_error(str(exc))

    except Exception as exc:
        app.logger.exception("Unexpected error while changing course.")
        return json_error(f"Unexpected error while reprocessing: {exc}", 500)


# ---------------------------------------------------------------------------
# GET CURRENT RESULTS
# ---------------------------------------------------------------------------

@app.get("/api/results/<job_id>")
def get_results(job_id: str):
    cleanup_old_jobs()
    job = get_job(job_id)

    if not job:
        return json_error("Processing session not found or expired.", 404)

    results = job.get("results", [])
    summary = make_frontend_summary(
        job.get("summary", {}),
        results,
        job.get("internal_marks", {}),
    )

    return jsonify({
        "success": True,
        "job_id": job_id,
        "course_code": job.get("course_code"),
        "internal_mark_scale": get_internal_scale(job),
        "total_students": len(results),
        "matched_students": summary["matched_students"],
        "missing_grades": summary["missing_students"],
        "result_only_students": job.get("summary", {}).get("result_only_students", 0),
        "missing_grade_reg_numbers": job.get("summary", {}).get("missing_grade_reg_numbers", []),
        "result_only_reg_numbers": job.get("summary", {}).get("result_only_reg_numbers", []),
        "summary": summary,
        "rows": results,
    })


# ---------------------------------------------------------------------------
# EXCEL EXPORT
# ---------------------------------------------------------------------------

@app.get("/api/export/<job_id>")
def export_excel(job_id: str):
    cleanup_old_jobs()
    job = get_job(job_id)

    if not job:
        return json_error("Processing session not found or expired.", 404)

    results = job.get("results", [])
    course_code = job.get("course_code")
    summary = job.get("summary", {})
    internal_mark_scale = get_internal_scale(job)

    if not results:
        return json_error("There are no processed results to export.")

    if not course_code:
        return json_error("Course code is missing. Please process the result again.")

    filename = make_excel_filename(course_code)
    output_path = TEMP_DIR / f"{job_id}_{filename}"

    try:
        # Only pass keyword arguments supported by the currently installed
        # exporter. This allows the exporter file to be updated in sequence.
        exporter_parameters = inspect.signature(generate_excel).parameters
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in exporter_parameters.values()
        )

        candidate_kwargs = {
            "results": results,
            "rows": results,
            "course_code": course_code,
            "output_path": output_path,
            "summary": summary,
            "branch": job.get("branch", "COMPUTER SCIENCE & ENGINEERING"),
            "semester": job.get("semester", ""),
            "internal_max_mark": internal_mark_scale,
            "internal_mark_scale": internal_mark_scale,
        }

        export_kwargs = {}
        if "results" in exporter_parameters:
            export_kwargs["results"] = results
        elif "rows" in exporter_parameters:
            export_kwargs["rows"] = results
        elif accepts_kwargs:
            export_kwargs["results"] = results

        for key in (
            "course_code",
            "output_path",
            "summary",
            "branch",
            "semester",
            "internal_max_mark",
            "internal_mark_scale",
        ):
            if key in exporter_parameters or accepts_kwargs:
                export_kwargs[key] = candidate_kwargs[key]

        generated_file = generate_excel(**export_kwargs)

        return send_file(
            generated_file,
            as_attachment=True,
            download_name=filename,
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    except ExcelExportError as exc:
        return json_error(str(exc))

    except Exception as exc:
        app.logger.exception("Unexpected error while generating Excel.")
        return json_error(f"Could not generate Excel file: {exc}", 500)


# ---------------------------------------------------------------------------
# DELETE / START NEW SESSION
# ---------------------------------------------------------------------------

@app.delete("/api/session/<job_id>")
def delete_session(job_id: str):
    job = jobs.pop(job_id, None)

    if not job:
        return json_error("Processing session not found.", 404)

    remove_job_files(job)

    return jsonify({
        "success": True,
        "message": "Processing session deleted.",
    })


# ---------------------------------------------------------------------------
# UPLOAD SIZE ERROR
# ---------------------------------------------------------------------------

@app.errorhandler(413)
def request_entity_too_large(error):
    return json_error(
        "The uploaded PDF is too large. Maximum allowed size is 20 MB.",
        413,
    )


# ---------------------------------------------------------------------------
# GENERAL SERVER ERROR
# ---------------------------------------------------------------------------

@app.errorhandler(500)
def internal_server_error(error):
    app.logger.exception("Internal server error.")
    return json_error("An unexpected server error occurred.", 500)


# ---------------------------------------------------------------------------
# LOCAL DEVELOPMENT ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
