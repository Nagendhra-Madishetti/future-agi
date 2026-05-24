#!/usr/bin/env python3
"""
apply_schema.py — Idempotent ClickHouse schema runner.

Reads files from schema/*.sql in lexical order, applies each, records the
content sha256 + applied_at in the `schema_versions` table inside whichever
database --ch-database points at (default: `default`). Re-runs are no-ops
unless a file's content has drifted (then we error out unless --force).

Schema files use UNQUALIFIED table names (`spans`, not `default.spans`) so
that --ch-database is the single switch for choosing a dev / test / prod
database without editing SQL.

Design decisions (DECISIONS.md #004):
    • Append-only: schema files are never deleted or edited after apply.
    • Hash-tracked: drift = file changed after apply = manual decision required.
    • DDL is statement-by-statement (CH doesn't have multi-statement transactions).
    • Each file is split on `;\n` and each statement is sent individually so we
      get precise error locations.
    • Empty / comment-only statements are skipped.
    • XML config files (001_storage_policy.xml, _local_overrides.xml) are NOT
      handled here — they're loaded by the CH server at boot via volume mount.

Usage:
    apply_schema.py --schema-dir schema --ch-host 127.0.0.1 --ch-http-port 19001
    apply_schema.py --status                                  # show applied versions
    apply_schema.py --force --files 002_spans_v2.sql ...      # bypass hash check

Exit codes:
    0   success or no-op
    1   user error (bad flags, file missing)
    2   drift detected without --force
    3   CH error during apply
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import clickhouse_connect          # HTTP — easier to debug than native here
import structlog


# ──────────────────────────────────────────────────────────────────────────────
# Logging — structured, machine-parseable, never print()
# ──────────────────────────────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger("apply_schema")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--schema-dir", type=Path, default=Path(__file__).parent.parent / "schema",
                   help="Directory containing *.sql files")
    p.add_argument("--ch-host", default="127.0.0.1")
    p.add_argument("--ch-http-port", type=int, default=19001)
    p.add_argument("--ch-user", default="default")
    p.add_argument("--ch-password", default=os.environ.get("CH_PASSWORD", ""))
    p.add_argument("--ch-database", default="default")
    p.add_argument("--status", action="store_true", help="Show applied versions, exit")
    p.add_argument("--force", action="store_true",
                   help="Apply even if hash drift detected (requires DECISIONS.md justification)")
    p.add_argument("--files", nargs="+", default=None,
                   help="Apply only these files (relative to --schema-dir). Default: all *.sql in order.")
    return p


# ──────────────────────────────────────────────────────────────────────────────
# DDL helpers
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SchemaFile:
    path: Path
    sha256: str

    @classmethod
    def from_path(cls, p: Path) -> "SchemaFile":
        return cls(path=p, sha256=hashlib.sha256(p.read_bytes()).hexdigest())


def split_statements(sql: str) -> list[str]:
    """
    Split a SQL file into individual statements.

    We split on `;` followed by a newline, then strip + filter empties. This is
    simpler than a full SQL parser and works for our schema files (no
    semicolons inside string literals or comments today). If a file ever
    needs a semicolon in a string, wrap the affected statement in its own file.
    """
    parts = sql.split(";\n")
    out = []
    for part in parts:
        stripped = "\n".join(
            line for line in part.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ).strip()
        if stripped:
            out.append(stripped + ";")
    return out


def ensure_versions_table(client) -> None:
    """Create schema_versions if it doesn't exist. Bootstrap; not tracked itself.

    Uses unqualified table name so it lands in the connection's current database
    (set via --ch-database). Schema files use the same convention so dev / test /
    prod can use whichever DB they need without editing SQL.
    """
    client.command("""
        CREATE TABLE IF NOT EXISTS schema_versions (
            filename   String,
            sha256     FixedString(64),
            applied_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC'),
            applied_by String DEFAULT '',
            notes      String DEFAULT ''
        ) ENGINE = MergeTree ORDER BY (filename, applied_at)
    """)


def fetch_applied(client) -> dict[str, str]:
    """Return {filename: sha256_of_most_recent_apply}.

    NOTE: CH `FixedString(64)` round-trips as Python `bytes` via clickhouse-connect.
    Decode to str so comparisons against `hashlib.sha256(...).hexdigest()` work.
    The cast also handles the case where CH ever returns str directly (no-op).
    """
    rows = client.query("""
        SELECT filename, argMax(sha256, applied_at) AS sha256
        FROM   schema_versions
        GROUP  BY filename
    """).result_rows
    out: dict[str, str] = {}
    for fn, sha in rows:
        if isinstance(sha, bytes):
            sha = sha.decode("ascii")
        out[fn] = sha
    return out


def discover_files(schema_dir: Path, only: Iterable[str] | None) -> list[SchemaFile]:
    if only:
        files = [schema_dir / name for name in only]
        missing = [p for p in files if not p.exists()]
        if missing:
            log.error("missing_files", missing=[str(m) for m in missing])
            sys.exit(1)
    else:
        files = sorted(p for p in schema_dir.glob("*.sql") if not p.name.startswith("_"))
    return [SchemaFile.from_path(p) for p in files]


def apply_file(client, sf: SchemaFile, applied_by: str) -> int:
    """Apply one file. Returns the number of statements executed."""
    sql = sf.path.read_text()
    statements = split_statements(sql)
    log.info("apply_file_begin", file=sf.path.name, sha256=sf.sha256[:12], statements=len(statements))
    for i, stmt in enumerate(statements, 1):
        first_line = stmt.splitlines()[0][:80]
        log.info("apply_statement", file=sf.path.name, n=i, of=len(statements), preview=first_line)
        try:
            client.command(stmt)
        except Exception as e:
            log.error("statement_failed",
                      file=sf.path.name, n=i,
                      statement_preview=stmt[:500],
                      err=str(e))
            raise
    # Record successful apply
    client.insert(
        "schema_versions",
        [[sf.path.name, sf.sha256, applied_by, ""]],
        column_names=["filename", "sha256", "applied_by", "notes"],
    )
    log.info("apply_file_complete", file=sf.path.name, statements=len(statements))
    return len(statements)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    log.info("connect", host=args.ch_host, port=args.ch_http_port, database=args.ch_database)
    client = clickhouse_connect.get_client(
        host=args.ch_host,
        port=args.ch_http_port,
        username=args.ch_user,
        password=args.ch_password,
        database=args.ch_database,
        # Sane request settings for DDL
        send_receive_timeout=120,
    )

    # Always make sure the versions table exists.
    ensure_versions_table(client)

    if args.status:
        applied = fetch_applied(client)
        if not applied:
            log.info("status_empty")
        for fn, sha in sorted(applied.items()):
            log.info("status_applied", file=fn, sha256=sha[:12])
        return 0

    files = discover_files(args.schema_dir, args.files)
    if not files:
        log.warning("no_schema_files", dir=str(args.schema_dir))
        return 0

    applied = fetch_applied(client)

    user = os.environ.get("FI_MIGRATION_USER", os.environ.get("USER", "unknown"))

    # Walk files in their (already lexically sorted) order from discover_files.
    # Decide per-file: skip / apply-as-new / drifted. With --force, drifted files
    # are queued IN PLACE so the final to_apply list is still in lexical order
    # (codex P2: appending drifted at the end caused 002 to run after 005).
    drift = []
    to_apply: list[SchemaFile] = []
    for sf in files:
        prior_sha = applied.get(sf.path.name)
        if prior_sha is None:
            to_apply.append(sf)
        elif prior_sha != sf.sha256:
            drift.append((sf, prior_sha))
            if args.force:
                to_apply.append(sf)
        else:
            log.info("skip_already_applied", file=sf.path.name, sha256=sf.sha256[:12])

    if drift and not args.force:
        for sf, prior in drift:
            log.error("drift_detected",
                      file=sf.path.name,
                      prior_sha=prior[:12],
                      current_sha=sf.sha256[:12],
                      hint="rerun with --force after writing a DECISIONS.md entry justifying the schema edit")
        return 2

    if not to_apply:
        log.info("nothing_to_apply")
        return 0

    total_stmts = 0
    t0 = time.time()
    for sf in to_apply:
        try:
            total_stmts += apply_file(client, sf, user)
        except Exception as e:
            log.error("apply_aborted", file=sf.path.name, err=str(e))
            return 3
    log.info("apply_complete",
             files=len(to_apply),
             statements=total_stmts,
             elapsed_sec=round(time.time() - t0, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
