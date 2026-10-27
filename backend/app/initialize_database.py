"""Explicitly create a new local development database at a fresh SQLite path."""

import argparse

from app.database import initialize_new_database, make_engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        required=True,
        help="A new SQLite path that does not already exist; existing files are never replaced.",
    )
    args = parser.parse_args()
    engine = make_engine(args.database_url)
    try:
        initialize_new_database(engine)
    finally:
        engine.dispose()
    print("New development database initialized.")


if __name__ == "__main__":
    main()
