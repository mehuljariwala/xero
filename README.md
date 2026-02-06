# Xero Report Automation

Automate Xero report generation and export using Playwright browser automation.

## Setup

### 1. Install Dependencies

```bash
pip install -e .
playwright install chromium
```

### 2. Export Your Xero Cookies

1. Log into Xero in your browser
2. Use a browser extension like "Cookie-Editor" to export cookies as JSON
3. Save the exported JSON to `cookies.json` in the project root

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

## Usage

### Basic Usage

```bash
# Generate report with defaults (End of last month, Excel format)
python -m src.main

# Or use the CLI command (after pip install -e .)
xero-report generate
```

### Options

```bash
python -m src.main generate \
  --period "End of last month" \
  --format excel \
  --output-dir ./reports \
  --cookies ./cookies.json \
  --headless
```

### Debug Mode

Run in headed mode with verbose logging:

```bash
python -m src.main generate --debug
```

### Available Periods

- `Today`
- `End of last month`
- `End of last quarter`
- `End of last financial year`

### Available Formats

- `excel`
- `pdf`
- `google_sheets`

## Troubleshooting

### Session Expired

If you see "Session expired" error, your cookies have expired. Re-export them from your browser after logging into Xero.

### Selectors Not Working

The UI selectors in `src/browser/selectors.py` may need updating if Xero changes their UI. Run in debug mode (`--debug`) to see the browser and inspect elements.

## Project Structure

```
xero-report-automation/
├── src/
│   ├── main.py              # CLI entry point
│   ├── browser/
│   │   ├── xero_client.py   # Core automation
│   │   └── selectors.py     # UI selectors
│   ├── config/
│   │   └── settings.py      # Configuration
│   ├── models/
│   │   └── report_params.py # Data models
│   └── utils/
│       ├── cookie_loader.py # Cookie handling
│       ├── file_handler.py  # Download management
│       └── logger.py        # Logging setup
├── downloads/               # Default output directory
├── cookies.json             # Your exported cookies
├── .env                     # Configuration
└── pyproject.toml           # Project dependencies
```
