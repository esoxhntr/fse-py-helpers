from __future__ import annotations

import argparse
import logging
import os
from typing import Iterable

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def get_env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def get_env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def get_engine(*, fast_executemany: bool = True) -> Engine:
    db_url = get_env_str("DB_URL")
    if not db_url:
        raise ValueError("DB_URL must be set.")

    return create_engine(db_url, future=True, fast_executemany=fast_executemany)


def execute_sql(engine: Engine, sql: str) -> None:
    with engine.begin() as conn:
        conn.execute(text(sql))


def execute_many(engine: Engine, sql: str, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(text(sql), rows)


def fetch_one(engine: Engine, sql: str) -> dict[str, object] | None:
    with engine.begin() as conn:
        row = conn.execute(text(sql)).mappings().first()
        return dict(row) if row else None


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )


def fetch_unbuilt_icaos(timeout: int) -> list[str]:
    username = get_env_str("FSE_USERNAME")
    password = get_env_str("FSE_PASSWORD")

    if not username or not password:
        raise ValueError("FSE_USERNAME and FSE_PASSWORD must be set.")

    base_url = "https://server.fseconomy.net/"
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    response = session.post(f"{base_url}index.jsp", timeout=timeout)
    response.raise_for_status()

    response = session.post(
        f"{base_url}userctl",
        data={
            "offset": "1",
            "user": username,
            "password": password,
            "event": "Agree & Log in",
            "basil": "",
        },
        timeout=timeout,
    )
    response.raise_for_status()

    response = session.get(f"{base_url}rest/api2/map/fbos/open", timeout=timeout)
    response.raise_for_status()

    payload = response.json()
    airports = payload.get("data", {}).get("airports", [])

    if not isinstance(airports, list):
        raise ValueError("Expected FSE payload.data.airports to be a list.")

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in airports:
        if not isinstance(item, dict):
            continue

        icao_raw = item.get("icao")
        if not isinstance(icao_raw, str):
            continue

        icao = icao_raw.strip().upper()
        if not icao:
            continue

        if icao not in seen:
            seen.add(icao)
            cleaned.append(icao)

    return cleaned


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def refresh_unbuilt_lots_table(engine: Engine, icaos: list[str], *, chunk_size: int = 1000) -> None:
    execute_sql(engine, "DELETE FROM dbo.unbuilt_lots")

    insert_sql = "INSERT INTO dbo.unbuilt_lots (icao) VALUES (:icao)"
    for batch in chunked(icaos, chunk_size):
        execute_many(engine, insert_sql, [{"icao": icao} for icao in batch])


def sync_refresh_state_unbuilt(engine: Engine) -> dict[str, int]:
    execute_sql(
        engine,
        """
        INSERT INTO dbo.fbo_refresh_state (icao)
        SELECT ul.icao
        FROM dbo.unbuilt_lots ul
        WHERE NOT EXISTS
        (
            SELECT 1
            FROM dbo.fbo_refresh_state rs
            WHERE rs.icao = ul.icao
        );
        """,
    )

    execute_sql(
        engine,
        """
        UPDATE rs
        SET
            reactivate_unbuilt_cleared = CASE
                WHEN rs.is_unbuilt_current = 1 AND ul.icao IS NULL THEN 1
                ELSE rs.reactivate_unbuilt_cleared
            END,
            last_unbuilt_cleared_utc = CASE
                WHEN rs.is_unbuilt_current = 1 AND ul.icao IS NULL THEN SYSUTCDATETIME()
                ELSE rs.last_unbuilt_cleared_utc
            END,
            reactivate_unbuilt_listed = CASE
                WHEN rs.is_unbuilt_current = 0 AND ul.icao IS NOT NULL THEN 1
                ELSE rs.reactivate_unbuilt_listed
            END,
            last_unbuilt_listed_utc = CASE
                WHEN rs.is_unbuilt_current = 0 AND ul.icao IS NOT NULL THEN SYSUTCDATETIME()
                ELSE rs.last_unbuilt_listed_utc
            END,
            last_reactivated_utc = CASE
                WHEN rs.is_unbuilt_current = 1 AND ul.icao IS NULL THEN SYSUTCDATETIME()
                WHEN rs.is_unbuilt_current = 0 AND ul.icao IS NOT NULL THEN SYSUTCDATETIME()
                ELSE rs.last_reactivated_utc
            END,
            reactivated_reason = CASE
                WHEN rs.is_unbuilt_current = 1 AND ul.icao IS NULL THEN 'UNBUILT_CLEARED'
                WHEN rs.is_unbuilt_current = 0 AND ul.icao IS NOT NULL THEN 'UNBUILT_LISTED'
                ELSE rs.reactivated_reason
            END,
            is_unbuilt_current = CASE WHEN ul.icao IS NOT NULL THEN 1 ELSE 0 END
        FROM dbo.fbo_refresh_state rs
        LEFT JOIN dbo.unbuilt_lots ul
            ON ul.icao = rs.icao;
        """,
    )

    current_unbuilt = (
        fetch_one(engine, "SELECT COUNT(1) AS cnt FROM dbo.fbo_refresh_state WHERE is_unbuilt_current = 1;")
        or {}
    ).get("cnt", 0)
    pending_unbuilt_cleared = (
        fetch_one(engine, "SELECT COUNT(1) AS cnt FROM dbo.fbo_refresh_state WHERE reactivate_unbuilt_cleared = 1;")
        or {}
    ).get("cnt", 0)
    pending_unbuilt_listed = (
        fetch_one(engine, "SELECT COUNT(1) AS cnt FROM dbo.fbo_refresh_state WHERE reactivate_unbuilt_listed = 1;")
        or {}
    ).get("cnt", 0)

    return {
        "current_unbuilt": int(current_unbuilt or 0),
        "pending_unbuilt_cleared": int(pending_unbuilt_cleared or 0),
        "pending_unbuilt_listed": int(pending_unbuilt_listed or 0),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh dbo.unbuilt_lots directly from FSE open FBO data."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=get_env_int("FSE_TIMEOUT", 30) or 30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Rows per INSERT batch.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    setup_logging(args.verbose)

    logging.info("Fetching unbuilt lots directly from FSE")
    icaos = fetch_unbuilt_icaos(args.timeout)
    logging.info("Fetched %d unique ICAO(s) from source", len(icaos))

    if args.dry_run:
        logging.info("Dry run only. Sample ICAOs: %s", icaos[:10])
        return

    engine = get_engine(fast_executemany=True)
    refresh_unbuilt_lots_table(engine, icaos, chunk_size=args.chunk_size)
    stats = sync_refresh_state_unbuilt(engine)
    logging.info(
        "Refreshed dbo.unbuilt_lots with %d ICAO(s); current_unbuilt=%d, pending_unbuilt_cleared=%d, pending_unbuilt_listed=%d",
        len(icaos),
        stats["current_unbuilt"],
        stats["pending_unbuilt_cleared"],
        stats["pending_unbuilt_listed"],
    )


if __name__ == "__main__":
    main()
