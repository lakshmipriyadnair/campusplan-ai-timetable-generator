import sqlite3
from pathlib import Path

db_path = Path('data/college_timetable_fresh.db')
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== ACTIVITY ROOM REQUIREMENTS ===")
c.execute("""
SELECT arr.id, ssr.id as req_id, s.subject_code, arr.activity_type, arr.room_type
FROM activity_room_requirements arr
JOIN shared_subject_requirements ssr ON ssr.id = arr.requirement_id
JOIN subjects s ON s.id = ssr.subject_id
""")
for r in c.fetchall():
    print(f"  id={r['id']} req={r['req_id']} subj={r['subject_code']} act={r['activity_type']} room_type={r['room_type']}")

print("\n=== FACULTY SCHEDULING PROFILES ===")
c.execute("""
SELECT fsp.id, f.faculty_name, fsp.is_confirmed, fsp.max_daily_minutes, fsp.max_weekly_minutes
FROM faculty_scheduling_profiles fsp
JOIN faculty f ON f.id = fsp.faculty_id
""")
profiles = c.fetchall()
print(f"  Total profiles: {len(profiles)}")
for r in profiles:
    print(f"  fac={r['faculty_name']} confirmed={r['is_confirmed']} daily_max={r['max_daily_minutes']} weekly_max={r['max_weekly_minutes']}")

print("\n=== FACULTY AVAILABILITY WINDOWS ===")
c.execute("""
SELECT f.faculty_name, faw.weekday, faw.start_time, faw.end_time, faw.availability
FROM faculty_availability_windows faw
JOIN faculty_scheduling_profiles fsp ON fsp.id = faw.profile_id
JOIN faculty f ON f.id = fsp.faculty_id
""")
rows = c.fetchall()
print(f"  Total windows: {len(rows)}")
for r in rows:
    print(f"  {r['faculty_name']} weekday={r['weekday']} {r['start_time']}-{r['end_time']} {r['availability']}")

print("\n=== ROOMS ===")
c.execute("SELECT id, room_name, room_type, capacity, is_active FROM rooms")
rooms = c.fetchall()
print(f"  Total rooms: {len(rooms)}")
for r in rooms:
    print(f"  id={r['id']} name={r['room_name']} type={r['room_type']} cap={r['capacity']} active={r['is_active']}")

print("\n=== ROOM AVAILABILITY PROFILES ===")
c.execute("""
SELECT r.room_name, rap.is_confirmed, rap.id as profile_id
FROM room_availability_profiles rap
JOIN rooms r ON r.id = rap.room_id
""")
rap_rows = c.fetchall()
print(f"  Total room profiles: {len(rap_rows)}")
for r in rap_rows:
    print(f"  {r['room_name']} confirmed={r['is_confirmed']} profile_id={r['profile_id']}")

print("\n=== ROOM AVAILABILITY WINDOWS ===")
c.execute("""
SELECT r.room_name, raw.weekday, raw.start_time, raw.end_time, raw.availability
FROM room_availability_windows raw
JOIN room_availability_profiles rap ON rap.id = raw.profile_id
JOIN rooms r ON r.id = rap.room_id
""")
rows = c.fetchall()
print(f"  Total room windows: {len(rows)}")
for r in rows:
    print(f"  {r['room_name']} weekday={r['weekday']} {r['start_time']}-{r['end_time']} {r['availability']}")

print("\n=== COLLEGE TIME CONFIGURATION ===")
c.execute("SELECT id, version, is_active, academic_hour_minutes FROM college_time_configurations")
for r in c.fetchall():
    print(f"  id={r['id']} version={r['version']} active={r['is_active']} acad_hr_min={r['academic_hour_minutes']}")

print("\n=== COLLEGE WORKING DAYS ===")
c.execute("SELECT configuration_id, weekday FROM college_working_days ORDER BY weekday")
days_names = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
for r in c.fetchall():
    print(f"  config={r['configuration_id']} weekday={r['weekday']}({days_names[r['weekday']]})")

print("\n=== COLLEGE TIME BLOCKS ===")
c.execute("SELECT id, configuration_id, sequence_number, block_type, period_number, label, start_time, end_time, is_lab_compatible FROM college_time_blocks ORDER BY sequence_number")
for r in c.fetchall():
    print(f"  seq={r['sequence_number']} type={r['block_type']} period={r['period_number']} {r['start_time']}-{r['end_time']} lab={r['is_lab_compatible']} label={r['label']}")

conn.close()
