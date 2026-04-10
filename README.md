# fse-unbuilt-refresh

Standalone Python script that logs into the FSE web app, fetches the current list of airports with open/unbuilt FBO slots, refreshes `dbo.unbuilt_lots`, and updates the related state flags in `dbo.fbo_refresh_state`.

This repo was split out from a larger ETL project. The original script depended on shared `fse_core` helpers; this version is self-contained and ready for a small public repo.

## What it does

1. Starts an FSE web session.
2. Logs in with `FSE_USERNAME` / `FSE_PASSWORD`.
3. Calls `https://server.fseconomy.net/rest/api2/map/fbos/open`.
4. Extracts unique ICAO codes.
5. Rebuilds `dbo.unbuilt_lots`.
6. Updates `dbo.fbo_refresh_state` so your downstream reactivation logic keeps working.

## Requirements

- Python 3.11+
- SQL Server-accessible database containing:
  - `dbo.unbuilt_lots`
  - `dbo.fbo_refresh_state`
- SQLAlchemy-compatible `DB_URL`
- SQL Server ODBC driver installed if you are using `pyodbc`

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` with your real values.

## Example `.env`

```env
DB_URL=mssql+pyodbc://USER:PASSWORD@SERVER/DATABASE?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
FSE_USERNAME=your_fse_username
FSE_PASSWORD=your_fse_password
FSE_TIMEOUT=30
```

## Usage

Dry run:

```powershell
python .\refresh_unbuilt_lots.py --dry-run --verbose
```

Real run:

```powershell
python .\refresh_unbuilt_lots.py --verbose
```

Optional arguments:

```text
--timeout <seconds>     HTTP timeout, defaults to FSE_TIMEOUT or 30
--chunk-size <rows>     Insert batch size, default 1000
--dry-run               Fetch and preview only, do not write to SQL
--verbose               Enable debug logging
```

## Notes

- This version no longer downloads or writes a JSON file. It fetches directly from FSE and writes straight to SQL.
- `dbo.unbuilt_lots` is fully rebuilt on each run.
- `dbo.fbo_refresh_state` is still updated with the same current-state / reactivation behavior.
- Because this uses the website login flow rather than a service-key XML feed, it is a little more fragile if FSE changes their web auth/session behavior.

## Minimal table expectations

This script assumes:

- `dbo.unbuilt_lots` has at least:
  - `icao`
- `dbo.fbo_refresh_state` has at least:
  - `icao`
  - `is_unbuilt_current`
  - `reactivate_unbuilt_cleared`
  - `last_unbuilt_cleared_utc`
  - `reactivate_unbuilt_listed`
  - `last_unbuilt_listed_utc`
  - `last_reactivated_utc`
  - `reactivated_reason`

## Security

Do not commit `.env` or real credentials.
