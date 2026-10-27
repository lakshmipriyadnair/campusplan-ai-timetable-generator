# AI College Timetable Generator

A local prototype for maintaining academic data, generating S5-A/S5-B timetable alternatives with OR-Tools CP-SAT, and approving/publishing an official version.

## Prerequisites

- Python 3.12 or newer
- Node.js 20.19+ or 22.12+ (Node.js 24 is suitable)
- npm (included with Node.js)

The backend uses FastAPI, SQLAlchemy, Pydantic, Alembic, and openpyxl. The frontend uses React, TypeScript, Vite, and Tailwind CSS. Git is optional.

## Start the application

Use two PowerShell terminals opened in the project folder.

### Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

If `backend/.venv` already exists, activate it instead of creating it again. If the Python launcher `py -3.12` is unavailable, use `python -m venv .venv`.

The API runs at `http://127.0.0.1:8000`; interactive API documentation is at `http://127.0.0.1:8000/docs`. Check the health endpoint at `http://127.0.0.1:8000/health`, or run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response: `status: ok`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The frontend talks to `http://127.0.0.1:8000/api/v1` by default. To use another API base URL, set `VITE_API_BASE_URL` before starting Vite.

## Administrator data entry

The dashboard loads current records from the API. Its sections let you:

- Create and review departments, academic years, semesters, and ordinary student groups.
- Add, view, edit, deactivate, and delete faculty, rooms, and subjects. Deleting records that are still referenced is rejected by the backend.
- Connect subjects with student groups, enter weekly lecture/tutorial/practical hours and session lengths, and assign faculty to those subject records.
- Review protected predefined groups. Their identity, semester, and student count are read-only in ordinary forms and are protected by the backend.

Start with the academic structure (department, academic year, and semester) before adding groups or semester-subject records. The application does not insert sample faculty, rooms, subjects, or timetable data.

This prototype has no login or server-side user authorization. Administrator Mode is a navigation label, not a security boundary. Do not expose the local prototype publicly or enter sensitive personal information.

## Timetable viewer

The Timetables section provides semester selection for CSE S1, S3, S5, and S7. For S5, it fetches and displays only the currently published immutable snapshot, using the college-time configuration captured with that version. Approved but unpublished snapshots and generated previews do not appear in the official viewer.

The current backend has no timetable-result model or read endpoint, so the weekly grid shows “No timetable published for this semester yet.” It also displays saved subject requirements and faculty assignments when the academic-data API has them. Two-period laboratory sessions are represented by one continuous display block when timetable-result data becomes available. No timetable sessions are fabricated.

## Excel templates and imports

Open **Excel import**, select a data type, then download its `.xlsx` template. Fill in the exact column names and upload the completed workbook. The backend parses and validates it, then shows the proposed rows and any row-level errors. **Confirm and import** is enabled only when every row passes validation. It asks for confirmation and revalidates the same file before saving.

Supported templates:

- **Faculty:** `faculty_name`, `faculty_code`, `email` (leave email blank if not known).
- **Rooms and laboratories:** `room_name`, `room_type` (`classroom`, `laboratory`, or `other`), `capacity`.
- **Subjects:** `subject_code`, `subject_name`.
- **Subject and group assignments:** uses existing numeric `semester_id`, `student_group_id`, and `subject_id`, plus the weekly hour and optional session-minute columns shown in the template. Use the IDs returned by the API or shown in `/docs`; IDs must refer to existing records, and the group must belong to that semester.
- **Protected group configuration:** `group_code`, `semester_number`, `academic_year_name`, `group_name`, `student_count`. This uses the same explicit configuration rules as the protected-group configuration command. It creates or verifies protected groups and cannot edit or delete them. Only confirmed group data should be entered; no additional groups are preloaded.

Only `.xlsx` workbooks up to 5 MB are accepted. Keep all template column names unchanged. Existing faculty codes/emails, room names, subject codes, assignments, and repeated rows are rejected rather than overwritten. A workbook is validated in full before writes; normal imports are committed together or not at all. Each file imports one data type. Preview is read-only. If academic records change between preview and apply, the import is validated again and may be rejected without saving.

## Database and safety

### S5 data entry and schema migration

Use the **S5 curriculum** screen to create one shared weekly-requirement record per S5 subject, then add teacher assignments independently for S5-A and S5-B. Blank shared-hour fields remain unconfirmed and are not converted to zero. The **College times** screen stores a versioned working-day and period configuration; no official times are prefilled. Room equipment/capabilities and availability profiles can be entered under **Rooms & labs**.

The additive schema revisions `20261021_04` (solver inputs) and `20261021_05` (approval snapshots and publication history) are required for the solver and approval workflow. They have not been applied to any working database by this task. After separately approving a migration and making a backup, run the explicit migration command from `backend` with the exact database URL: `python -m app.migrate --database-url sqlite:///data/college_timetable_fresh.db`. The runner has no default URL, refuses a missing SQLite file, validates each supported starting version, and does not copy or alter academic records. It upgrades through both revisions when starting at `20261021_03`.

Startup is read-only with respect to schema structure. It requires an existing SQLite file with the expected schema version, required tables, and required columns. It never runs `create_all` or repairs an incomplete schema. If the database path is missing or incorrect, startup stops without creating a replacement file.

The default local SQLite path configured by the current source is `backend/data/college_timetable_fresh.db`. To explicitly initialize a brand-new development database, first choose a new filename that does not exist, then run this command from the `backend` directory:

```powershell
python -m app.initialize_database --database-url sqlite:///data/college_timetable_dev.db
```

The initializer refuses to use an existing file. It creates the parent folder only as part of this explicit command, then creates and versions the schema. To run the app against that development database, set the same URL before starting the backend:

```powershell
$env:TIMETABLE_DATABASE_URL = "sqlite:///data/college_timetable_dev.db"
python -m uvicorn app.main:app --reload
```

Never use the initializer to handle an existing database. Startup does not seed, reset, or delete data. A missing, unversioned, outdated, incomplete, or incorrectly configured database stops with an explicit error and is left unchanged.

To use another SQLite database, set `TIMETABLE_DATABASE_URL` before starting the backend. Tests use a separate temporary SQLite database per test and do not use the default application database.

The timetable viewer supports CSE S1, S3, S5, and S7. The S5 scheduling scope is S5-A and S5-B, with 72 students each. No subjects, weekly hours, teacher names, room identifiers, equipment, official times, or timetable entries are preloaded.

### Generate, approve, and publish

1. Complete confirmed S5 subject hours, session counts/durations, section-specific teacher assignments, teacher availability/workload, room requirements/availability, and college times.
2. Open **Generate options**, choose the academic year, and request three or four alternatives. The CP-SAT solver checks both groups together. Results are transient previews and never modify an official timetable.
3. Select a validated alternative and choose **Approve selected alternative**. Confirm in the dialog. The backend revalidates the submitted placements against the latest saved data and stores an immutable snapshot.
4. In **Approval and publication**, choose **Publish this version** and confirm separately. Publication switches one current pointer atomically and appends history; older snapshots remain intact.
5. Open **Timetables** to see only the published S5 version. If none has been published, the viewer shows an empty state.

API endpoints: `POST /api/v1/timetables/generate`, `POST /api/v1/timetables/approve`, `GET /api/v1/timetables/approved?academic_year_id=...`, `POST /api/v1/timetables/{snapshot_id}/publish`, `GET /api/v1/timetables/official?academic_year_id=...`, and `GET /api/v1/timetables/publication-history?academic_year_id=...`.

## Tests and production build

Backend tests:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests -q
```

Frontend form validation tests and production build:

```powershell
cd frontend
npm test
npm run build
```

## Project structure

```text
frontend/src/               React administrator dashboard and API client
backend/app/                FastAPI routes, validation, CRUD, models, and Excel import
backend/tests/              Isolated API and import tests
backend/config/             Explicit predefined-group configuration example
```

## Current limitations

- The local prototype still has no login or server-side administrator authorization. Approval and publication actions require explicit confirmation but are not protected from a caller who can reach the API; do not expose this app publicly until server-side authentication and authorization are added.
- Approval snapshots and publication history are immutable/append-only in SQLite. Timetable editing and rollback are not implemented; to switch the official timetable, publish another approved version.
- Excel imports handle one template type per workbook. Subject assignments reference numeric API IDs.
- Predefined group import is an explicit administrator action and does not infer missing CSE group data.
- The interface is a local prototype. Hidden or visible frontend controls do not provide security.
