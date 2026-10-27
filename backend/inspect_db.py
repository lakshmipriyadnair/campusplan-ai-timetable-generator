import sqlite3
from pathlib import Path

db_path = Path('data/college_timetable_fresh.db')
print(f'DB path: {db_path.resolve()}')
print(f'DB size: {db_path.stat().st_size} bytes')

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [t[0] for t in cursor.fetchall()]
print(f'Tables ({len(tables)}): {tables}')

if 'alembic_version' in tables:
    cursor.execute('SELECT * FROM alembic_version')
    print(f'alembic version: {cursor.fetchall()}')

if 'shared_subject_requirements' in tables:
    cursor.execute('SELECT * FROM shared_subject_requirements')
    print('shared_subject_requirements:', cursor.fetchall())

if 'section_teacher_assignments' in tables:
    cursor.execute('SELECT * FROM section_teacher_assignments')
    print('section_teacher_assignments:', cursor.fetchall())

if 'faculty' in tables:
    cursor.execute('SELECT id, faculty_name, faculty_code, is_active FROM faculty')
    rows = cursor.fetchall()
    print(f'faculty ({len(rows)}):')
    for r in rows:
        print(f'  {r}')

if 'subjects' in tables:
    cursor.execute('SELECT id, subject_code, subject_name FROM subjects')
    rows = cursor.fetchall()
    print(f'subjects ({len(rows)}):')
    for r in rows:
        print(f'  {r}')

if 'semesters' in tables:
    cursor.execute('SELECT id, semester_number, name, department_id, academic_year_id FROM semesters')
    rows = cursor.fetchall()
    print(f'semesters ({len(rows)}):')
    for r in rows:
        print(f'  {r}')

if 'student_groups' in tables:
    cursor.execute('SELECT id, group_name, semester_id, student_count FROM student_groups')
    rows = cursor.fetchall()
    print(f'student_groups ({len(rows)}):')
    for r in rows:
        print(f'  {r}')

conn.close()
