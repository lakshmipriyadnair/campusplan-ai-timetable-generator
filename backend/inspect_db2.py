import sqlite3
from pathlib import Path

db_path = Path('data/college_timetable_fresh.db')
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== STUDENT GROUPS ===")
c.execute("SELECT sg.id, sg.group_name, sg.semester_id, sg.student_count, sg.is_active, psg.group_code FROM student_groups sg LEFT JOIN predefined_student_groups psg ON psg.student_group_id = sg.id")
for r in c.fetchall():
    print(f"  id={r['id']} name={r['group_name']} semester={r['semester_id']} students={r['student_count']} active={r['is_active']} predefined_code={r['group_code']}")

print("\n=== SHARED SUBJECT REQUIREMENTS ===")
c.execute("""
SELECT ssr.id, s.subject_code, s.subject_name, 
       ssr.weekly_lecture_hours, ssr.weekly_tutorial_hours, ssr.weekly_practical_hours,
       ssr.weekly_lecture_sessions, ssr.weekly_tutorial_sessions, ssr.weekly_practical_sessions,
       ssr.lecture_session_minutes, ssr.tutorial_session_minutes, ssr.practical_session_minutes,
       ssr.semester_id
FROM shared_subject_requirements ssr
JOIN subjects s ON s.id = ssr.subject_id
ORDER BY ssr.id
""")
for r in c.fetchall():
    print(f"  req_id={r['id']} subj={r['subject_code']} '{r['subject_name'][:25]}' sem={r['semester_id']}")
    print(f"    lec: hours={r['weekly_lecture_hours']} sess={r['weekly_lecture_sessions']} mins={r['lecture_session_minutes']}")
    print(f"    tut: hours={r['weekly_tutorial_hours']} sess={r['weekly_tutorial_sessions']} mins={r['tutorial_session_minutes']}")
    print(f"    prac: hours={r['weekly_practical_hours']} sess={r['weekly_practical_sessions']} mins={r['practical_session_minutes']}")

print("\n=== SECTION TEACHER ASSIGNMENTS (all) ===")
c.execute("SELECT * FROM section_teacher_assignments")
rows = c.fetchall()
print(f"  Total: {len(rows)}")
for r in rows:
    print(f"  {dict(r)}")

print("\n=== ACTIVITY ROOM REQUIREMENTS ===")
c.execute("""
SELECT arr.id, ssr.id as req_id, s.subject_code, arr.activity_type, arr.room_type
FROM activity_room_requirements arr
JOIN shared_subject_requirements ssr ON ssr.id = arr.requirement_id
JOIN subjects s ON s.id = ssr.subject_id
""")
for r in c.fetchall():
    print(f"  id={r['id']} req={r['req_id']} subj={r['subject_code']} {r['activity_type']}→{r['room_type']}")

print("\n=== FACULTY ===")
c.execute("SELECT id, faculty_name, faculty_code, is_active FROM faculty")
for r in c.fetchall():
    print(f"  id={r['id']} name={r['faculty_name']} code={r['faculty_code']} active={r['is_active']}")

print("\n=== FACULTY SCHEDULING PROFILES ===")
c.execute("""
SELECT fsp.id, f.faculty_name, fsp.is_confirmed, fsp.max_daily_minutes, fsp.max_weekly_minutes
FROM faculty_scheduling_profiles fsp
JOIN faculty f ON f.id = fsp.faculty_id
""")
profiles = c.fetchall()
for r in profiles:
    print(f"  fac={r['faculty_name']} confirmed={r['is_confirmed']} daily_max={r['max_daily_minutes']} weekly_max={r['max_weekly_minutes']}")

print("\n=== FACULTY AVAILABILITY WINDOWS ===")
c.execute("""
SELECT f.faculty_name, faw.weekday, faw.start_time, faw.end_time, faw.availability
FROM faculty_availability_windows faw
JOIN faculty_scheduling_profiles fsp ON fsp.id = faw.profile_id
JOIN faculty f ON f.id = fsp.faculty_id
""")
for r in c.fetchall():
    print(f"  {r['faculty_name']} weekday={r['weekday']} {r['start_time']}-{r['end_time']} {r['availability']}")

print("\n=== ROOMS ===")
c.execute("SELECT id, room_name, room_type, capacity, is_active FROM rooms")
for r in c.fetchall():
    print(f"  id={r['id']} name={r['room_name']} type={r['room_type']} cap={r['capacity']} active={r['is_active']}")

print("\n=== ROOM AVAILABILITY PROFILES ===")
c.execute("""
SELECT r.room_name, rap.is_confirmed
FROM room_availability_profiles rap
JOIN rooms r ON r.id = rap.room_id
""")
for r in c.fetchall():
    print(f"  {r['room_name']} confirmed={r['is_confirmed']}")

print("\n=== COLLEGE TIME CONFIGURATION ===")
c.execute("SELECT id, version, is_active, academic_hour_minutes FROM college_time_configurations")
for r in c.fetchall():
    print(f"  id={r['id']} version={r['version']} active={r['is_active']} academic_hour_min={r['academic_hour_minutes']}")

print("\n=== COLLEGE WORKING DAYS ===")
c.execute("SELECT configuration_id, weekday FROM college_working_days ORDER BY weekday")
for r in c.fetchall():
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    print(f"  config={r['configuration_id']} weekday={r['weekday']}({days[r['weekday']]})")

print("\n=== COLLEGE TIME BLOCKS ===")
c.execute("SELECT id, configuration_id, sequence_number, block_type, period_number, label, start_time, end_time, is_lab_compatible FROM college_time_blocks ORDER BY sequence_number")
for r in c.fetchall():
    print(f"  seq={r['sequence_number']} type={r['block_type']} period={r['period_number']} {r['start_time']}-{r['end_time']} lab_compat={r['is_lab_compatible']} label={r['label']}")

conn.close()
