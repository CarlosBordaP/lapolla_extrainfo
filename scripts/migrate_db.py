#!/usr/bin/env python3
"""Database migration script.

Copies all data from the local SQLite database (polla_dev.db)
to a target database (SQLite, MySQL, etc.) specified by TARGET_DB_URL.
"""

from __future__ import annotations

import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure the app folder is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import Base, Match, MatchFile, PageVisit, Participant, Prediction


def main() -> None:
    target_db_url = os.environ.get("TARGET_DB_URL")
    if not target_db_url:
        print("Error: TARGET_DB_URL environment variable is not set.", file=sys.stderr)
        print("Usage:", file=sys.stderr)
        print("  TARGET_DB_URL='mysql+pymysql://user:pass@host/db' python scripts/migrate_db.py", file=sys.stderr)
        print("  TARGET_DB_URL='sqlite:///./polla_target.db' python scripts/migrate_db.py", file=sys.stderr)
        sys.exit(1)

    source_db_url = "sqlite:///./polla_dev.db"

    print(f"Connecting to source SQLite: {source_db_url}")
    source_engine = create_engine(source_db_url, future=True)

    print(f"Connecting to target database: {target_db_url}")
    target_engine = create_engine(target_db_url, future=True)

    print("Creating tables in target database if they do not exist...")
    Base.metadata.create_all(bind=target_engine)

    # Order of migration is critical to satisfy ForeignKey constraints:
    # 1. Participant (no dependencies)
    # 2. Match (no dependencies)
    # 3. MatchFile (depends on Match via optional match_id)
    # 4. PageVisit (no DB-level constraints, but related to username)
    # 5. Prediction (depends on Match and Participant)
    models_to_migrate = [
        Participant,
        Match,
        MatchFile,
        PageVisit,
        Prediction,
    ]

    def copy_instance(instance):
        cls = instance.__class__
        mapper = instance._sa_instance_state.mapper
        data = {}
        for column in mapper.columns:
            data[column.key] = getattr(instance, column.key)
        return cls(**data)

    with Session(source_engine) as source_session, Session(target_engine) as target_session:
        # Check if target database already has data
        has_data = False
        for model in models_to_migrate:
            if target_session.query(model).count() > 0:
                has_data = True
                break

        if has_data:
            force = os.environ.get("FORCE_MIGRATE") == "1"
            if not force:
                print("\nWARNING: The target database already contains data in one or more tables.", file=sys.stderr)
                print("To prevent overwriting or duplicate key errors, the script has paused.", file=sys.stderr)
                print("If you want to clear the target tables and FORCE the migration, run with FORCE_MIGRATE=1:", file=sys.stderr)
                print("  FORCE_MIGRATE=1 TARGET_DB_URL='...' python scripts/migrate_db.py", file=sys.stderr)
                sys.exit(1)
            else:
                print("\nFORCE_MIGRATE=1 detected: Clearing target database tables in reverse order to prevent foreign key violations...")
                for model in reversed(models_to_migrate):
                    count = target_session.query(model).count()
                    if count > 0:
                        print(f"  Deleting {count} records from target '{model.__tablename__}'...")
                        target_session.query(model).delete()
                target_session.commit()
                print("Target database cleared successfully.\n")

        # Start migrating tables in forward order
        for model in models_to_migrate:
            table_name = model.__tablename__
            print(f"Migrating table '{table_name}'...")

            # Query all rows from source database
            rows = source_session.query(model).all()
            if not rows:
                print(f"  No data found in source for '{table_name}'. Skipping.")
                continue

            print(f"  Found {len(rows)} records in source. Transferring...")

            # Add copy of each row to the target session
            copied_count = 0
            for row in rows:
                new_row = copy_instance(row)
                target_session.add(new_row)
                copied_count += 1

            try:
                target_session.commit()
                print(f"  Successfully migrated {copied_count} records to '{table_name}'.")
            except Exception as e:
                target_session.rollback()
                print(f"  Error committing migration for table '{table_name}': {e}", file=sys.stderr)
                sys.exit(1)

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    main()
