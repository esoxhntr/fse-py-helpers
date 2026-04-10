from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv


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


def write_json(icaos: list[str], output_path: str) -> None:
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "count": len(icaos),
        "icaos": icaos,
    }
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch open FBO ICAOs from FSE and write them to JSON."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=get_env_int("FSE_TIMEOUT", 30) or 30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        default="unbuilt_lots.json",
        help="Path to the JSON file to create.",
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

    write_json(icaos, args.output)
    logging.info("Wrote %d ICAO(s) to %s", len(icaos), args.output)


if __name__ == "__main__":
    main()
