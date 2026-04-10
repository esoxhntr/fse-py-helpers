# fse-unbuilt-refresh

Standalone Python script that logs into the FSE web app, fetches the current list of airports with open/unbuilt FBO slots, and writes the cleaned ICAO list to a JSON file.

## What it does

1. Starts an FSE web session.
2. Logs in with `FSE_USERNAME` / `FSE_PASSWORD`.
3. Calls `https://server.fseconomy.net/rest/api2/map/fbos/open`.
4. Extracts unique ICAO codes.
5. Saves a JSON payload containing the timestamp, total count, and ICAO list.

## Requirements

- Python 3.11+
- `requests` and `python-dotenv` (installed via `requirements.txt`)
- `.env` populated with FSE credentials

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
FSE_USERNAME=your_fse_username
FSE_PASSWORD=your_fse_password
FSE_TIMEOUT=30
```

## Usage

Dry run (fetch + log sample ICAOs, no file output):

```powershell
python .\refresh_unbuilt_lots.py --dry-run --verbose
```

Write JSON (defaults to `unbuilt_lots.json` in the repo root):

```powershell
python .\refresh_unbuilt_lots.py --output data/unbuilt_lots.json --verbose
```

Optional arguments:

```text
--timeout <seconds>     HTTP timeout, defaults to FSE_TIMEOUT or 30
--output <path>         Destination JSON file, defaults to unbuilt_lots.json
--dry-run               Fetch and preview only, do not write a file
--verbose               Enable debug logging
```

The JSON structure looks like:

```json
{
  "generated_utc": "2024-04-09T03:31:57.123456+00:00",
  "count": 42,
  "icaos": ["KJFK", "CYTZ", "..."]
}
```

## Notes

- Each run overwrites the target JSON file.
- Because this uses the website login flow rather than a service-key XML feed, it is a little more fragile if FSE changes their web auth/session behavior.

## Security

Do not commit `.env` or real credentials.

## Credits

Thanks to Piero and the [FSE Planner Helpers](https://github.com/piero-la-lune/FSE-Planner-Helpers) project for the original inspiration and groundwork that informed this simplified JSON exporter.
