from sqlalchemy import select
from app.database import SessionLocal
from app import models

db = SessionLocal()

try:
    print("\n--- STUDENT GROUPS ---")
    groups = db.scalars(select(models.StudentGroup)).all()

    for group in groups:
        print(
            "ID:", group.id,
            "| Name:", group.group_name,
            "| Section:", group.section_identifier,
            "| Semester:", group.semester_id,
            "| Students:", group.student_count,
            "| Active:", group.is_active,
            "| Protected:", group.predefined_identity is not None,
        )

    print("\n--- COLLEGE TIME CONFIGURATIONS ---")
    configs = db.scalars(
        select(models.CollegeTimeConfiguration)
    ).all()

    for config in configs:
        print(
            "ID:", config.id,
            "| Active:", config.is_active,
            "| Academic hour:", config.academic_hour_minutes,
        )

    print("\n--- WORKING DAYS AND PERIODS ---")
    for config in configs:
        print("Configuration:", config.id)

        for day in config.working_days:
            print("Working day:", day.weekday)

        for block in config.time_blocks:
            print(
                block.sequence_number,
                block.block_type,
                block.period_number,
                block.label,
                block.start_time,
                block.end_time,
                "Lab-compatible:", block.is_lab_compatible,
            )

finally:
    db.close()