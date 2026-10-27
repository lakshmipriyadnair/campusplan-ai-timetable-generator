# S5 data-entry schema and migration proposal

## Status

The additive schema, API resources, and isolated migration tests are prepared. No existing database was opened or migrated. The administrator must separately approve any migration against the normal local database.

## Data design

| Table | Purpose and important fields | Relationships and safeguards |
|---|---|---|
| `shared_subject_requirements` | One common S5 subject requirement: `semester_id`, `subject_id`, weekly lecture/tutorial/practical hours, optional session durations. Hour fields are nullable and have no zero defaults. | References existing semester and subject records. Unique semester+subject prevents conflicting duplicate hour records. API accepts only CSE S5. Existing `semester_subjects` rows are untouched and are not merged. |
| `section_teacher_assignments` | `requirement_id`, `student_group_id`, `faculty_id`. | References a common requirement, protected S5-A/S5-B group, and existing faculty record. Unique requirement+group+faculty blocks duplicate links while allowing different teachers for the two sections and one teacher on multiple subjects. API checks that the group and requirement belong to the same S5 semester. |
| `college_time_configurations` | Version number and active flag. No times are seeded. | Version is unique; a partial unique index permits at most one active version. |
| `college_working_days` | Configuration and weekday number (Monday=0 through Sunday=6). | Unique configuration+weekday; weekday constrained to 0–6. |
| `college_time_blocks` | Configuration, sequence, type (teaching/break/lunch), optional positive period number, optional label, start/end times, lab-compatible flag. | Unique sequence and period numbers per configuration; end must be after start; only teaching blocks can be lab-compatible. Periods use positive integers, so no Period Z is created. |
| `room_capabilities` | Room, administrator-entered equipment/capability name, kind, optional positive quantity. | References existing room; one capability name per room. |
| `room_availability_profiles` | One profile per room and an explicit completeness/confirmation flag. | References existing room; unique room profile. A missing or unconfirmed profile remains unknown. |
| `room_availability_windows` | Profile, weekday, start/end times, and available/unavailable state. | References the profile; weekday and time ordering are constrained. |

Existing `Subject`, `Faculty`, `Room`, `StudentGroup`, `SemesterSubject`, `FacultySubject`, and Excel-import resources remain in place. Existing room type and capacity fields are reused. The explicit group configuration example now includes the confirmed S5-A and S5-B identities and counts; its academic-year value remains a placeholder and is not applied.

## Migration mechanism

Alembic is added as the migration tool. Revision `20261021_01` is a baseline marker; `20261021_02` creates only the eight new tables and their indexes. Revision `20261021_03` adds nullable weekly lecture, tutorial, and practical session counts to shared requirements. Neither upgrade copies, updates, or deletes existing academic data. Downgrades remove the newly-added structures and any data entered into them, so they must not be used after records have been entered unless deleting those additions is intended.

The explicit runner is `python -m app.migrate --database-url <SQLAlchemy URL>`. It has no default database URL, refuses to create a missing SQLite file, checks for the expected existing academic tables and columns, and stops if it finds partial/unversioned scheduling tables or an unsupported migration version. It stamps the baseline only after successful preflight, then runs the additive revision.

Startup behavior is guarded:

- New development databases must be explicitly initialized with `python -m app.initialize_database --database-url <new-sqlite-url>`; the command refuses any existing file.
- Application startup requires an existing versioned database with all expected tables and columns. It does not call `create_all` or repair missing schema objects.
- A missing or incorrectly configured SQLite path is rejected before connection, so startup cannot create a replacement empty database.
- A recognized but older revision also stops for an explicit migration.

The actual local database remains unversioned until a separately approved migration is run. If it predates the protected-group marker table, this migration runner will refuse it and a reviewed prior migration will be needed first.

## Data migration risks and limits

- No existing hours are copied into the shared requirements. In particular, stored zero defaults are not considered confirmed.
- If legacy per-group S5 subject rows exist for a subject, the new shared requirement endpoint refuses a competing row until an administrator reviews the legacy records. If a shared requirement exists first, the legacy CRUD/import paths refuse new per-group S5 hour copies for that subject. Existing legacy rows remain untouched and visible.
- No existing teacher links are moved; S5-A/B assignments must be entered against the new shared requirement records.
- No subject names, teacher names, room identifiers, availability, timetable periods, or equipment are seeded.
- The S5 group configuration example does not run automatically and still requires the correct existing academic year.
- The current API has no server-side authentication. This local prototype must not be exposed publicly.

## Isolated verification

The migration test creates a disposable SQLite database with only the legacy tables, upgrades it through the explicit migration runner, verifies old table names remain, and runs the upgrade again to confirm it is repeatable. Separate temporary databases test new-database startup and rejection of silent startup changes.

No production or existing local database is used by the test suite.
