/* =========================================================
   ANSORA MARK PROCESSING SYSTEM
   Frontend JavaScript
========================================================= */

"use strict";

/* =========================================================
   GLOBAL STATE
========================================================= */

const state = {
    jobId: null,
    internalFile: null,
    resultFile: null,
    internalStudents: [],
    resultRows: [],
    currentCourseCode: "",
    assessmentScale: null,
    courseSuggestions: []
};


/* =========================================================
   DOM HELPERS
========================================================= */

const $ = (id) => document.getElementById(id);


/* =========================================================
   DOM REFERENCES
========================================================= */

const internalPdf = $("internalPdf");
const resultPdf = $("resultPdf");

const internalMarkScale = $("internalMarkScale");
const selectedAssessmentLabel = $("selectedAssessmentLabel");
const assessmentHelp = $("assessmentHelp");

const internalDropZone = $("internalDropZone");
const resultDropZone = $("resultDropZone");

const internalBrowseButton = $("internalBrowseButton");
const resultBrowseButton = $("resultBrowseButton");

const internalSelectedFile = $("internalSelectedFile");
const resultSelectedFile = $("resultSelectedFile");

const internalFileName = $("internalFileName");
const internalFileSize = $("internalFileSize");

const resultFileName = $("resultFileName");
const resultFileSize = $("resultFileSize");

const removeInternalFile = $("removeInternalFile");
const removeResultFile = $("removeResultFile");

const uploadInternalButton = $("uploadInternalButton");
const processResultButton = $("processResultButton");

const courseCode = $("courseCode");
const processCourseLabel = $("processCourseLabel");

const changeCourseCode = $("changeCourseCode");
const changeCourseButton = $("changeCourseButton");

const resultSearch = $("resultSearch");
const gradeFilter = $("gradeFilter");

const resultsTableBody = $("resultsTableBody");
const resultTableHeadRow = $("resultTableHeadRow");
const dynamicGradeHeader = $("dynamicGradeHeader");
const universityMarkHeader = $("universityMarkHeader");

const exportButton = $("exportButton");
const startNewButton = $("startNewButton");

const messageBox = $("messageBox");
const messageIcon = $("messageIcon");
const messageTitle = $("messageTitle");
const messageText = $("messageText");
const messageClose = $("messageClose");

const loadingOverlay = $("loadingOverlay");
const loadingTitle = $("loadingTitle");
const loadingText = $("loadingText");

const internalResult = $("internalResult");
const internalResultText = $("internalResultText");
const studentCount = $("studentCount");
const previewCount = $("previewCount");
const internalPreviewBody = $("internalPreviewBody");

const resultSection = $("resultSection");
const resultsSection = $("resultsSection");

const resultTableTitle = $("resultTableTitle");
const resultRecordCount = $("resultRecordCount");

const summaryTotal = $("summaryTotal");
const summaryMatched = $("summaryMatched");
const summaryMissing = $("summaryMissing");
const summaryCourse = $("summaryCourse");

const mismatchPanel = $("mismatchPanel");
const mismatchCount = $("mismatchCount");
const missingStudentsList = $("missingStudentsList");

const emptySearchState = $("emptySearchState");

const courseSuggestionsSection = $("courseSuggestionsSection");
const courseSuggestions = $("courseSuggestions");
const suggestionLoading = $("suggestionLoading");

const workflowStep1 = $("workflowStep1");
const workflowStep2 = $("workflowStep2");
const workflowStep3 = $("workflowStep3");

const courseInputStatus = $("courseInputStatus");


/* =========================================================
   INITIALIZATION
========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    setupFileInputEvents();
    setupDropZones();
    setupButtonEvents();
    setupFormEvents();

    updateProcessCourseLabel();
    updateAssessmentUI();
    updateResultTableColumns();

});


/* =========================================================
   FILE INPUT EVENTS
========================================================= */

function setupFileInputEvents() {

    internalBrowseButton.addEventListener("click", (event) => {
        event.stopPropagation();
        internalPdf.click();
    });

    resultBrowseButton.addEventListener("click", (event) => {
        event.stopPropagation();
        resultPdf.click();
    });

    internalPdf.addEventListener("change", () => {
        if (internalPdf.files.length > 0) {
            handleInternalFile(internalPdf.files[0]);
        }
    });

    resultPdf.addEventListener("change", () => {
        if (resultPdf.files.length > 0) {
            handleResultFile(resultPdf.files[0]);
        }
    });

    removeInternalFile.addEventListener("click", clearInternalFile);

    removeResultFile.addEventListener("click", clearResultFile);

}


/* =========================================================
   DROP ZONES
========================================================= */

function setupDropZones() {

    configureDropZone(internalDropZone, handleInternalFile);
    configureDropZone(resultDropZone, handleResultFile);

}


function configureDropZone(zone, onFile) {

    zone.addEventListener("click", (event) => {

        if (
            event.target.closest("button") ||
            event.target.closest("input")
        ) {
            return;
        }

        const input =
            zone === internalDropZone
                ? internalPdf
                : resultPdf;

        input.click();

    });

    zone.addEventListener("dragenter", (event) => {
        event.preventDefault();
        zone.classList.add("dragging");
    });

    zone.addEventListener("dragover", (event) => {
        event.preventDefault();
        zone.classList.add("dragging");
    });

    zone.addEventListener("dragleave", (event) => {
        event.preventDefault();

        if (!zone.contains(event.relatedTarget)) {
            zone.classList.remove("dragging");
        }
    });

    zone.addEventListener("drop", (event) => {

        event.preventDefault();
        zone.classList.remove("dragging");

        const files = event.dataTransfer.files;

        if (!files || files.length === 0) {
            return;
        }

        onFile(files[0]);

    });

}


/* =========================================================
   BUTTON EVENTS
========================================================= */

function setupButtonEvents() {

    uploadInternalButton.addEventListener(
        "click",
        uploadInternalPdf
    );

    processResultButton.addEventListener(
        "click",
        processResultPdf
    );

    changeCourseButton.addEventListener(
        "click",
        changeCourse
    );

    exportButton.addEventListener(
        "click",
        handleExport
    );

    startNewButton.addEventListener(
        "click",
        resetEverything
    );

    messageClose.addEventListener(
        "click",
        hideMessage
    );

}


/* =========================================================
   FORM EVENTS
========================================================= */

function setupFormEvents() {

    internalMarkScale.addEventListener("change", () => {

        state.assessmentScale =
            Number(internalMarkScale.value) || null;

        updateAssessmentUI();

    });


    courseCode.addEventListener("input", () => {

        courseCode.value = normalizeCourseCode(
            courseCode.value
        );

        updateProcessCourseLabel();
        updateCourseInputStatus();

    });


    courseCode.addEventListener("keydown", (event) => {

        if (event.key === "Enter") {
            event.preventDefault();
            processResultPdf();
        }

    });


    changeCourseCode.addEventListener("input", () => {

        changeCourseCode.value = normalizeCourseCode(
            changeCourseCode.value
        );

    });


    changeCourseCode.addEventListener("keydown", (event) => {

        if (event.key === "Enter") {
            event.preventDefault();
            changeCourse();
        }

    });


    resultSearch.addEventListener(
        "input",
        renderFilteredResults
    );


    gradeFilter.addEventListener(
        "change",
        renderFilteredResults
    );

}


/* =========================================================
   FILE VALIDATION
========================================================= */

function validatePdf(file) {

    if (!file) {
        return {
            valid: false,
            message: "Please select a PDF file."
        };
    }

    const isPdf =
        file.type === "application/pdf" ||
        file.name.toLowerCase().endsWith(".pdf");

    if (!isPdf) {
        return {
            valid: false,
            message: "Only PDF files are allowed."
        };
    }

    const maxBytes = 20 * 1024 * 1024;

    if (file.size > maxBytes) {
        return {
            valid: false,
            message: "The PDF must be smaller than 20 MB."
        };
    }

    return { valid: true };

}


/* =========================================================
   INTERNAL FILE
========================================================= */

function handleInternalFile(file) {

    const validation = validatePdf(file);

    if (!validation.valid) {

        showMessage(
            "Invalid File",
            validation.message,
            "error"
        );

        return;
    }

    state.internalFile = file;

    internalFileName.textContent = file.name;
    internalFileSize.textContent = formatFileSize(file.size);

    internalSelectedFile.classList.remove("hidden");

    updateAssessmentUI();
    hideMessage();

}


function clearInternalFile() {

    state.internalFile = null;
    internalPdf.value = "";

    internalSelectedFile.classList.add("hidden");

    updateAssessmentUI();

}


/* =========================================================
   RESULT FILE
========================================================= */

function handleResultFile(file) {

    const validation = validatePdf(file);

    if (!validation.valid) {

        showMessage(
            "Invalid File",
            validation.message,
            "error"
        );

        return;
    }

    state.resultFile = file;

    resultFileName.textContent = file.name;
    resultFileSize.textContent = formatFileSize(file.size);

    resultSelectedFile.classList.remove("hidden");

    hideMessage();

    loadCourseSuggestions();

}


function clearResultFile() {

    state.resultFile = null;
    resultPdf.value = "";

    resultSelectedFile.classList.add("hidden");
    courseSuggestionsSection.classList.add("hidden");

    courseSuggestions.innerHTML = "";
    state.courseSuggestions = [];

}


/* =========================================================
   ASSESSMENT TYPE
========================================================= */

function getAssessmentLabel(scale = state.assessmentScale) {

    const value = Number(scale);

    if (value === 50) {
        return "50 Marks – Regular Internal";
    }

    if (value === 75) {
        return "75 Marks – Laboratory";
    }

    if (value === 100) {
        return "100 Marks – Project";
    }

    return "—";

}


function updateAssessmentUI() {

    const scale = Number(
        internalMarkScale.value ||
        state.assessmentScale ||
        0
    );

    // CO1–CO8 calculations are no longer required.
    // Only University Mark will be calculated for every assessment type.

    if (scale === 50) {

        assessmentHelp.textContent =
            "Regular internal assessment: Only University Mark will be calculated.";

    } else if (scale === 75) {

        assessmentHelp.textContent =
            "Laboratory assessment: Only University Mark will be calculated.";

    } else if (scale === 100) {

        assessmentHelp.textContent =
            "Project assessment: Only University Mark will be calculated.";

    } else {

        assessmentHelp.textContent =
            "Select an assessment type. University Mark will be calculated for all assessment types.";

    }

    // Display selected assessment type.
    if (selectedAssessmentLabel) {

        selectedAssessmentLabel.textContent =
            getAssessmentLabel(scale);

    }

    // Enable upload only when PDF and assessment type are selected.
    uploadInternalButton.disabled =
        Boolean(state.jobId) ||
        !state.internalFile ||
        !scale;

}


/* =========================================================
   INTERNAL PDF UPLOAD
========================================================= */

async function uploadInternalPdf() {

    if (!internalMarkScale.value) {

        showMessage(
            "Assessment Type Required",
            "Please select 50, 75 or 100 marks before uploading the internal PDF.",
            "error"
        );

        internalMarkScale.focus();
        return;

    }

    if (!state.internalFile) {

        showMessage(
            "Internal PDF Required",
            "Please select the internal marks PDF first.",
            "error"
        );

        return;

    }

    const validation = validatePdf(state.internalFile);

    if (!validation.valid) {

        showMessage(
            "Invalid File",
            validation.message,
            "error"
        );

        return;

    }

    const formData = new FormData();

    formData.append(
        "internal_pdf",
        state.internalFile
    );

    state.assessmentScale = Number(internalMarkScale.value);

    formData.append(
        "internal_mark_scale",
        String(state.assessmentScale)
    );

    setLoading(
        true,
        "Reading Internal Marks",
        "Extracting registration numbers and internal marks from the PDF..."
    );

    uploadInternalButton.disabled = true;

    try {

        const response = await fetch(
            "/api/upload-internal",
            {
                method: "POST",
                body: formData
            }
        );

        const data = await parseJsonResponse(response);

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Unable to process the internal PDF."
            );
        }

        state.jobId = data.job_id;

        state.assessmentScale = Number(
            data.internal_mark_scale ??
            data.assessment_scale ??
            internalMarkScale.value
        );

        internalMarkScale.disabled = true;

        updateAssessmentUI();

        state.internalStudents =
            Array.isArray(data.students)
                ? data.students
                : [];

        renderInternalPreview();

        const count = Number(
            data.student_count ||
            state.internalStudents.length ||
            0
        );

        studentCount.textContent = count.toString();
        previewCount.textContent = `${count} records`;

        internalResultText.textContent =
            `${count} students were extracted successfully.`;

        internalResult.classList.remove("hidden");
        resultSection.classList.remove("hidden");

        markWorkflowStepComplete(workflowStep1);
        activateWorkflowStep(workflowStep2);

        showMessage(
            "Internal PDF Processed",
            `${count} students and their internal marks were extracted successfully.`,
            "success"
        );

        resultSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    } catch (error) {

        console.error(error);

        showMessage(
            "Processing Failed",
            error.message ||
            "Something went wrong while processing the internal PDF.",
            "error"
        );

        uploadInternalButton.disabled = false;

    } finally {

        setLoading(false);

    }

}


/* =========================================================
   COURSE CODE SUGGESTIONS
========================================================= */

async function loadCourseSuggestions() {

    if (!state.resultFile) {
        return;
    }

    const formData = new FormData();

    formData.append(
        "result_pdf",
        state.resultFile
    );

    courseSuggestionsSection.classList.remove("hidden");

    suggestionLoading.textContent = "Checking PDF...";

    try {

        const response = await fetch(
            "/api/course-codes",
            {
                method: "POST",
                body: formData
            }
        );

        const data = await parseJsonResponse(response);

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Unable to read course codes."
            );
        }

        let codes = [];

        if (Array.isArray(data.course_codes)) {
            codes = data.course_codes;
        } else if (Array.isArray(data.courses)) {
            codes = data.courses;
        } else if (Array.isArray(data)) {
            codes = data;
        }

        state.courseSuggestions = codes
            .map(normalizeCourseCode)
            .filter(Boolean);

        renderCourseSuggestions();

        suggestionLoading.textContent =
            state.courseSuggestions.length > 0
                ? `${state.courseSuggestions.length} found`
                : "No codes found";

    } catch (error) {

        console.error("Course suggestion error:", error);

        courseSuggestions.innerHTML = "";

        suggestionLoading.textContent =
            "Could not read codes";

    }

}


/* =========================================================
   RENDER COURSE SUGGESTIONS
========================================================= */

function renderCourseSuggestions() {

    courseSuggestions.innerHTML = "";

    state.courseSuggestions.forEach((code) => {

        const button = document.createElement("button");

        button.type = "button";
        button.className = "course-chip";
        button.textContent = code;

        button.addEventListener("click", () => {

            courseCode.value = code;

            updateProcessCourseLabel();
            updateCourseInputStatus();

            courseCode.focus();

        });

        courseSuggestions.appendChild(button);

    });

}


/* =========================================================
   PROCESS RESULT PDF
========================================================= */

async function processResultPdf() {

    if (!state.jobId) {

        showMessage(
            "Internal PDF Not Ready",
            "Please upload and process the internal marks PDF first.",
            "error"
        );

        return;

    }

    const enteredCourse =
        normalizeCourseCode(courseCode.value);

    if (!enteredCourse) {

        showMessage(
            "Course Code Required",
            "Please manually enter a course code such as CST309.",
            "error"
        );

        courseCode.focus();
        return;

    }

    if (!/^[A-Z]{2,6}\d{3}$/i.test(enteredCourse)) {

        showMessage(
            "Invalid Course Code",
            "Please enter a valid course code, for example CST309.",
            "error"
        );

        courseCode.focus();
        return;

    }

    if (!state.resultFile) {

        showMessage(
            "Result PDF Required",
            "Please select the result PDF before processing.",
            "error"
        );

        return;

    }

    const formData = new FormData();

    formData.append("job_id", state.jobId);
    formData.append("course_code", enteredCourse);
    formData.append("result_pdf", state.resultFile);

    setLoading(
        true,
        `Processing ${enteredCourse}`,
        "Reading the result PDF and matching student grades..."
    );

    processResultButton.disabled = true;

    try {

        const response = await fetch(
            "/api/process-result",
            {
                method: "POST",
                body: formData
            }
        );

        const data = await parseJsonResponse(response);

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Unable to process the result PDF."
            );
        }

        state.currentCourseCode =
            normalizeCourseCode(
                data.course_code || enteredCourse
            );

        state.assessmentScale = Number(
            data.internal_mark_scale ||
            state.assessmentScale
        );

        state.resultRows =
            Array.isArray(data.rows)
                ? data.rows
                : [];

        renderResults(data.summary);

        markWorkflowStepComplete(workflowStep2);
        activateWorkflowStep(workflowStep3);

        showResultsSection();

        showMessage(
            "Results Processed",
            `${state.resultRows.length} student records have been processed for ${state.currentCourseCode}.`,
            "success"
        );

    } catch (error) {

        console.error(error);

        showMessage(
            "Result Processing Failed",
            error.message ||
            "Something went wrong while processing the result PDF.",
            "error"
        );

    } finally {

        processResultButton.disabled = false;
        setLoading(false);

    }

}


/* =========================================================
   CHANGE COURSE CODE
========================================================= */

async function changeCourse() {

    if (!state.jobId) {

        showMessage(
            "Session Not Ready",
            "Please process an internal PDF first.",
            "error"
        );

        return;

    }

    const newCourse =
        normalizeCourseCode(changeCourseCode.value);

    if (!newCourse) {

        showMessage(
            "Course Code Required",
            "Enter the new course code, for example CST305.",
            "error"
        );

        changeCourseCode.focus();
        return;

    }

    if (!/^[A-Z]{2,6}\d{3}$/i.test(newCourse)) {

        showMessage(
            "Invalid Course Code",
            "Please enter a valid course code.",
            "error"
        );

        changeCourseCode.focus();
        return;

    }

    setLoading(
        true,
        `Changing Course to ${newCourse}`,
        "Reusing the stored result PDF and matching the new course..."
    );

    changeCourseButton.disabled = true;

    try {

        const response = await fetch(
            "/api/change-course",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    job_id: state.jobId,
                    course_code: newCourse
                })
            }
        );

        const data = await parseJsonResponse(response);

        if (!response.ok) {
            throw new Error(
                data.error ||
                "Unable to change the course."
            );
        }

        state.currentCourseCode =
            normalizeCourseCode(
                data.course_code || newCourse
            );

        state.assessmentScale = Number(
            data.internal_mark_scale ||
            state.assessmentScale
        );

        state.resultRows =
            Array.isArray(data.rows)
                ? data.rows
                : [];

        renderResults(data.summary);

        changeCourseCode.value = "";

        showMessage(
            "Course Changed",
            `Results are now displayed for ${state.currentCourseCode}.`,
            "success"
        );

    } catch (error) {

        console.error(error);

        showMessage(
            "Course Change Failed",
            error.message ||
            "Unable to process the new course code.",
            "error"
        );

    } finally {

        changeCourseButton.disabled = false;
        setLoading(false);

    }

}


/* =========================================================
   INTERNAL STUDENT PREVIEW
========================================================= */

function renderInternalPreview() {

    internalPreviewBody.innerHTML = "";

    const previewStudents =
        state.internalStudents.slice(0, 12);

    previewStudents.forEach((student, index) => {

        const row = document.createElement("tr");

        const regNo =
            student.reg_no ??
            student.registration_number ??
            student.registration_no ??
            "";

        const mark =
            student.internal_mark ??
            student.mark ??
            "";

        row.innerHTML = `
            <td>${escapeHtml(index + 1)}</td>
            <td>${escapeHtml(regNo)}</td>
            <td class="mark-value">${escapeHtml(mark)}</td>
        `;

        internalPreviewBody.appendChild(row);

    });

}


/* =========================================================
   RENDER RESULTS
========================================================= */

function renderResults(summary) {

    const course =
        state.currentCourseCode || "—";

    dynamicGradeHeader.textContent =
        `${course} Grade`;

    resultTableTitle.textContent =
        `${course} Results`;

    summaryCourse.textContent = course;

    updateResultTableColumns();

    if (summary) {

        summaryTotal.textContent =
            formatInteger(
                summary.total_students ??
                state.resultRows.length
            );

        summaryMatched.textContent =
            formatInteger(
                summary.matched_students ??
                summary.matched ??
                countMatchedRows()
            );

        summaryMissing.textContent =
            formatInteger(
                summary.missing_students ??
                summary.missing ??
                countMissingRows()
            );

    } else {

        summaryTotal.textContent =
            formatInteger(state.resultRows.length);

        summaryMatched.textContent =
            formatInteger(countMatchedRows());

        summaryMissing.textContent =
            formatInteger(countMissingRows());

    }

    renderFilteredResults();
    renderMissingStudents(summary);

    if (state.jobId) {
        exportButton.href =
            `/api/export/${encodeURIComponent(state.jobId)}`;
    }

}


/* =========================================================
   DYNAMIC TABLE COLUMNS
========================================================= */

function updateResultTableColumns() {

    if (!resultTableHeadRow || !universityMarkHeader) {
        return;
    }

    // Remove CO headers before rebuilding the table.
    resultTableHeadRow
        .querySelectorAll("[data-co-header]")
        .forEach(header => header.remove());

    // University Mark is displayed for every assessment type.
    universityMarkHeader.hidden = false;

    // CO1–CO8 are only displayed for regular internal assessments.
    if (usesCOColumns()) {

        for (let co = 1; co <= 8; co++) {

            const header = document.createElement("th");

            header.textContent = `CO${co}`;
            header.dataset.coHeader = String(co);

            resultTableHeadRow.appendChild(header);

        }

    }

}


function usesCOColumns() {

    return false;

}


/* =========================================================
   FILTER AND SEARCH RESULTS
========================================================= */

function renderFilteredResults() {

    const query =
        resultSearch.value.trim().toLowerCase();

    const selectedGrade =
        gradeFilter.value;

    const filtered = state.resultRows.filter((row) => {

        const regNo = String(
            row.reg_no ??
            row.registration_number ??
            ""
        ).toLowerCase();

        const grade = normalizeGrade(row.grade);

        const gradeMatches =
            selectedGrade === "ALL" ||
            grade === selectedGrade.toUpperCase();

        const queryMatches =
            !query ||
            regNo.includes(query) ||
            grade.toLowerCase().includes(query);

        return gradeMatches && queryMatches;

    });

    resultsTableBody.innerHTML = "";

    filtered.forEach((row, index) => {

        const tr = document.createElement("tr");

        const regNo =
            row.reg_no ??
            row.registration_number ??
            "";

        const internalMark =
            row.internal_mark ??
            row.mark ??
            "";

        const grade = normalizeGrade(row.grade);

        const universityMark = getFirstDefined(
            row.university_mark,
            row.universityMark,
            row.university_mark_value
        );

        let cells = `
            <td>${escapeHtml(index + 1)}</td>

            <td>
                <strong>${escapeHtml(regNo)}</strong>
            </td>

            <td class="mark-value">
                ${escapeHtml(internalMark)}
            </td>

            <td>
                ${createGradeBadge(grade)}
            </td>

            <td class="mark-value">
                ${escapeHtml(displayCellValue(universityMark, grade))}
            </td>
        `;

        // Add CO1–CO8 only for 50-mark assessments.
        if (usesCOColumns()) {

            for (let co = 1; co <= 8; co++) {

                const coValue = getFirstDefined(
                    row[`co${co}`],
                    row[`co_${co}`],
                    row[`CO${co}`]
                );

                cells += `
                    <td class="mark-value co-value">
                        ${escapeHtml(displayCellValue(coValue, grade))}
                    </td>
                `;

            }

        }

        tr.innerHTML = cells;

        resultsTableBody.appendChild(tr);

    });

    resultRecordCount.textContent =
        `${filtered.length} of ${state.resultRows.length} records`;

    const tableScroll =
        document.querySelector(".table-scroll.large");

    if (filtered.length === 0) {

        emptySearchState.classList.remove("hidden");
        tableScroll?.classList.add("hidden");

    } else {

        emptySearchState.classList.add("hidden");
        tableScroll?.classList.remove("hidden");

    }

}


/* =========================================================
   TABLE VALUE HELPERS
========================================================= */

function getFirstDefined(...values) {

    return values.find(
        value => value !== undefined && value !== null
    );

}


function displayCellValue(value, grade) {

    // Do not show derived marks for missing or absent grades.
    if (
        grade === "Not Found" ||
        grade === "Absent"
    ) {
        return "";
    }

    return value === undefined || value === null
        ? ""
        : value;

}


/* =========================================================
   MISSING STUDENTS
========================================================= */

function renderMissingStudents(summary) {

    let missing = [];

    if (
        summary &&
        Array.isArray(summary.missing_reg_nos)
    ) {

        missing = summary.missing_reg_nos;

    } else {

        missing = state.resultRows
            .filter(row =>
                normalizeGrade(row.grade) === "Not Found"
            )
            .map(row =>
                row.reg_no ??
                row.registration_number ??
                ""
            );

    }

    mismatchCount.textContent =
        missing.length.toString();

    missingStudentsList.innerHTML = "";

    missing.forEach((regNo) => {

        const item = document.createElement("span");

        item.className = "missing-student";
        item.textContent = regNo;

        missingStudentsList.appendChild(item);

    });

    if (missing.length > 0) {
        mismatchPanel.classList.remove("hidden");
    } else {
        mismatchPanel.classList.add("hidden");
    }

}


/* =========================================================
   GRADE BADGE
========================================================= */

function createGradeBadge(grade) {

    const normalized = normalizeGrade(grade);

    let className = "grade-not-found";

    if (normalized === "S") {

        className = "grade-s";

    } else if (normalized === "A+") {

        className = "grade-a-plus";

    } else if (normalized === "A") {

        className = "grade-a";

    } else if (normalized === "B+") {

        className = "grade-b-plus";

    } else if (normalized === "B") {

        className = "grade-b";

    } else if (normalized === "C+") {

        className = "grade-c-plus";

    } else if (normalized === "C") {

        className = "grade-c";

    } else if (normalized === "D") {

        className = "grade-d";

    } else if (normalized === "P") {

        className = "grade-p";

    } else if (
        normalized === "F" ||
        normalized === "FE"
    ) {

        className = "grade-f";

    } else if (normalized === "Absent") {

        className = "grade-absent";

    }

    return `
        <span class="grade-badge ${className}">
            ${escapeHtml(normalized)}
        </span>
    `;

}


/* =========================================================
   COUNT HELPERS
========================================================= */

function countMatchedRows() {

    return state.resultRows.filter(row => {

        const grade = normalizeGrade(row.grade);

        return (
            grade !== "Not Found" &&
            grade !== "Absent"
        );

    }).length;

}


function countMissingRows() {

    return state.resultRows.filter(row =>
        normalizeGrade(row.grade) === "Not Found"
    ).length;

}


/* =========================================================
   EXPORT
========================================================= */

function handleExport(event) {

    if (!state.jobId) {

        event.preventDefault();

        showMessage(
            "Nothing to Export",
            "Please process a result PDF first.",
            "error"
        );

        return;

    }

    exportButton.href =
        `/api/export/${encodeURIComponent(state.jobId)}`;

}


/* =========================================================
   WORKFLOW
========================================================= */

function markWorkflowStepComplete(step) {

    step.classList.remove("active");
    step.classList.add("completed");

    const number =
        step.querySelector(".workflow-number");

    if (number) {
        number.textContent = "✓";
    }

}


function activateWorkflowStep(step) {

    document
        .querySelectorAll(".workflow-step")
        .forEach(item => {
            item.classList.remove("active");
        });

    step.classList.add("active");

}


function showResultsSection() {

    resultsSection.classList.remove("hidden");

    setTimeout(() => {

        resultsSection.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    }, 80);

}


/* =========================================================
   COURSE DISPLAY
========================================================= */

function updateProcessCourseLabel() {

    const value =
        normalizeCourseCode(courseCode.value);

    processCourseLabel.textContent =
        value || "—";

}


function updateCourseInputStatus() {

    const value =
        normalizeCourseCode(courseCode.value);

    if (value) {

        courseInputStatus.textContent = "Ready";

        courseInputStatus.style.background =
            "var(--green-light)";

        courseInputStatus.style.color =
            "var(--green)";

    } else {

        courseInputStatus.textContent = "Manual";

        courseInputStatus.style.background =
            "var(--blue-light)";

        courseInputStatus.style.color =
            "var(--blue-dark)";

    }

}


/* =========================================================
   LOADING OVERLAY
========================================================= */

function setLoading(
    visible,
    title = "Processing...",
    text = "Please wait..."
) {

    if (!visible) {

        loadingOverlay.classList.add("hidden");
        return;

    }

    loadingTitle.textContent = title;
    loadingText.textContent = text;

    loadingOverlay.classList.remove("hidden");

}


/* =========================================================
   MESSAGE BOX
========================================================= */

function showMessage(
    title,
    text,
    type = "success"
) {

    messageTitle.textContent = title;
    messageText.textContent = text;

    messageBox.classList.remove(
        "hidden",
        "success",
        "error",
        "warning"
    );

    messageBox.classList.add(type);

    if (type === "success") {

        messageIcon.textContent = "✓";

    } else if (type === "warning") {

        messageIcon.textContent = "!";

    } else {

        messageIcon.textContent = "×";

    }

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });

}


function hideMessage() {

    messageBox.classList.add("hidden");

}


/* =========================================================
   RESET EVERYTHING
========================================================= */

async function resetEverything() {

    const oldJobId = state.jobId;

    try {

        if (oldJobId) {

            await fetch(
                `/api/session/${encodeURIComponent(oldJobId)}`,
                {
                    method: "DELETE"
                }
            );

        }

    } catch (error) {

        console.warn(
            "Could not delete server session:",
            error
        );

    }

    state.jobId = null;

    state.internalFile = null;
    state.resultFile = null;

    state.internalStudents = [];
    state.resultRows = [];

    state.currentCourseCode = "";
    state.assessmentScale = null;
    state.courseSuggestions = [];

    internalPdf.value = "";
    resultPdf.value = "";

    internalMarkScale.value = "";
    internalMarkScale.disabled = false;

    courseCode.value = "";
    changeCourseCode.value = "";

    resultSearch.value = "";
    gradeFilter.value = "ALL";

    internalSelectedFile.classList.add("hidden");
    resultSelectedFile.classList.add("hidden");

    internalResult.classList.add("hidden");
    resultSection.classList.add("hidden");
    resultsSection.classList.add("hidden");

    courseSuggestionsSection.classList.add("hidden");
    mismatchPanel.classList.add("hidden");
    emptySearchState.classList.add("hidden");

    internalPreviewBody.innerHTML = "";
    resultsTableBody.innerHTML = "";
    missingStudentsList.innerHTML = "";
    courseSuggestions.innerHTML = "";

    studentCount.textContent = "0";
    previewCount.textContent = "0 records";
    selectedAssessmentLabel.textContent = "—";

    summaryTotal.textContent = "0";
    summaryMatched.textContent = "0";
    summaryMissing.textContent = "0";
    summaryCourse.textContent = "—";

    processCourseLabel.textContent = "—";
    resultRecordCount.textContent = "0 records";

    dynamicGradeHeader.textContent = "Course Grade";
    resultTableTitle.textContent = "Results";

    uploadInternalButton.disabled = false;
    processResultButton.disabled = false;
    changeCourseButton.disabled = false;

    workflowStep1.classList.remove("completed");
    workflowStep2.classList.remove("completed");
    workflowStep3.classList.remove("completed");

    workflowStep1.classList.add("active");
    workflowStep2.classList.remove("active");
    workflowStep3.classList.remove("active");

    const firstNumber =
        workflowStep1.querySelector(".workflow-number");

    const secondNumber =
        workflowStep2.querySelector(".workflow-number");

    const thirdNumber =
        workflowStep3.querySelector(".workflow-number");

    if (firstNumber) firstNumber.textContent = "1";
    if (secondNumber) secondNumber.textContent = "2";
    if (thirdNumber) thirdNumber.textContent = "3";

    updateAssessmentUI();
    updateResultTableColumns();
    updateCourseInputStatus();

    hideMessage();

    window.scrollTo({
        top: 0,
        behavior: "smooth"
    });

}


/* =========================================================
   FETCH HELPERS
========================================================= */

async function parseJsonResponse(response) {

    const contentType =
        response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        return response.json();
    }

    const text = await response.text();

    return {
        error:
            text ||
            "The server returned an unexpected response."
    };

}


/* =========================================================
   DATA HELPERS
========================================================= */

function normalizeCourseCode(value) {

    return String(value ?? "")
        .toUpperCase()
        .replace(/\s+/g, "")
        .trim();

}


function normalizeGrade(value) {

    const grade = String(
        value ?? "Not Found"
    ).trim();

    if (!grade) {
        return "Not Found";
    }

    const upper = grade.toUpperCase();

    if (upper === "NOT FOUND") {
        return "Not Found";
    }

    if (upper === "ABSENT") {
        return "Absent";
    }

    return upper;

}


function formatFileSize(bytes) {

    if (!bytes) {
        return "0 KB";
    }

    if (bytes < 1024) {
        return `${bytes} B`;
    }

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(
        bytes / (1024 * 1024)
    ).toFixed(2)} MB`;

}


function formatInteger(value) {

    const number = Number(value || 0);

    return number.toLocaleString("en-IN");

}


/* =========================================================
   HTML ESCAPING
========================================================= */

function escapeHtml(value) {

    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");

}


/* =========================================================
   PAGE EXIT WARNING
========================================================= */

window.addEventListener("beforeunload", (event) => {

    if (
        state.jobId &&
        state.resultRows.length === 0
    ) {

        event.preventDefault();
        event.returnValue = "";

    }

});