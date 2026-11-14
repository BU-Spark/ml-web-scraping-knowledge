"""Apply database/migrations/*.sql in order, each exactly once.

    python3 -m database.migrate            # apply pending migrations to DATABASE_URL
    python3 -m database.migrate --status   # list applied / pending, change nothing

Applied files are recorded in schema_migrations with a checksum. Each file runs in its own
transaction, so a failing migration leaves the database unchanged. Never edit an applied migration;
add a new numbered file instead. Get team approval before running against the shared Heroku database.
"""
import argparse
import hashlib
from pathlib import Path

from database.connection import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    sha256     text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)"""


def migration_files(directory=MIGRATIONS_DIR):
    return sorted(Path(directory).glob("[0-9][0-9][0-9]_*.sql"))


def applied(conn, create=True):
    if create:
        conn.execute(CREATE_TABLE)
    elif conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None:
        return {}
    return dict(conn.execute("SELECT filename, sha256 FROM schema_migrations").fetchall())


def migrate(conn, directory=MIGRATIONS_DIR, dry_run=False, log=print):
    """Apply pending migrations; return the list of filenames applied (or pending if dry_run)."""
    with conn.transaction():
        done = applied(conn, create=not dry_run)
    pending = []
    for path in migration_files(directory):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name in done:
            if done[path.name] != sha:
                raise RuntimeError(f"{path.name} was edited after it was applied; add a new migration instead")
            continue
        pending.append(path.name)
        if dry_run:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename, sha256) VALUES (%s, %s)", (path.name, sha))
        log(f"applied {path.name}")
    return pending


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="show pending migrations without applying")
    args = parser.parse_args()
    with connect(autocommit=True) as conn:
        names = migrate(conn, dry_run=args.status)
    if args.status:
        print("pending: " + (", ".join(names) if names else "none"))
    elif not names:
        print("up to date")


if __name__ == "__main__":
    main()
