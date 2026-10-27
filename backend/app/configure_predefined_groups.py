"""Run an explicit, create-only predefined-group configuration file."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from app.database import SessionLocal, engine, initialize_schema
from app.predefined_groups import PredefinedGroupsFile, configure_predefined_groups


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify protected CSE student groups from a JSON file."
    )
    parser.add_argument("config", type=Path, help="Path to a predefined-groups JSON file")
    args = parser.parse_args()

    try:
        configuration = PredefinedGroupsFile.model_validate_json(
            args.config.read_text(encoding="utf-8")
        )
        initialize_schema(engine)
        with SessionLocal() as session:
            groups = configure_predefined_groups(session, configuration.groups)
    except (OSError, ValidationError, ValueError) as error:
        parser.error(str(error))

    print(f"Verified {len(groups)} configured predefined group(s).")
    print("Running the same file again will not create duplicates or overwrite group data.")


if __name__ == "__main__":
    main()
