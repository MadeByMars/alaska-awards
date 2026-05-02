# Alaska Airlines Award Flight Scraper

Automatically search for Alaska Airlines award flight availability and get notified of deals via email.

## Features

- 🔍 Search multiple routes in parallel
- 🔥 Highlight deals below your mileage threshold
- 📅 Filter by date range
- ⏰ Scheduled searches every 10 minutes via GitHub Actions
- 📧 Email notifications when deals are found

## Current Routes

| Search | Route | Date Range | Deal Threshold |
|--------|-------|------------|----------------|
| Partner Premium | PPT → BA3 | Sep 12, 2026 | < 50k miles |
| Partner Business | PPT → BA3 | Sep 12, 2026 | < 80k miles |

## Local Usage

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the script
python alaska.py
```

Results are saved to the `results/` directory.
Each search now writes separate raw and parsed files so multiple cabin searches on the same route do not overwrite each other.

## GitHub Actions Setup

The workflow runs every 10 minutes and sends an email when deals are found.

### 1. Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"**

### 2. Set Up Email Notifications

1. Create a Gmail App Password:
   - Go to https://myaccount.google.com/apppasswords
   - Generate a new app password for "Mail"

2. Add secrets to your repo:
   - Go to **Settings** → **Secrets and variables** → **Actions**
   - Add `EMAIL_USERNAME`: your Gmail address
   - Add `EMAIL_PASSWORD`: the 16-character app password

### 3. Run the Workflow

- **Manual**: Actions → "Alaska Award Flight Search" → "Run workflow"
- **Automatic**: Runs every 10 minutes

### View Results

- **Logs**: Actions → click workflow run → "Display results and check for deals"
- **Email**: Sent automatically when deals are found

## Configuration

### Modify Routes

Edit `alaska.py` to modify searches in the `main()` function:

```python
searches = [
    {
        "origin": "PPT",
        "destination": "BA3",
        "outbound_date": "2026-09-12",
        "date_range_start": "2026-09-12",
        "date_range_end": "2026-09-12",
        "highlight_below": 50,  # Alert if below this mileage
        "adults": 2,
        "fare_type": FARE_TYPES["partner_premium"],
        "search_name": "Partner Premium",
    },
    {
        "origin": "PPT",
        "destination": "BA3",
        "outbound_date": "2026-09-12",
        "date_range_start": "2026-09-12",
        "date_range_end": "2026-09-12",
        "highlight_below": 80,  # Alert if below this mileage
        "adults": 2,
        "fare_type": FARE_TYPES["partner_business"],
        "search_name": "Partner Business",
    },
    # Add more routes...
]
```

Available fare types:

- `FARE_TYPES["lowest"]` → `Lowest+price+available`
- `FARE_TYPES["partner_premium"]` → `Partner+Premium`
- `FARE_TYPES["partner_business"]` → `Partner+Business`

### Change Schedule

Edit `.github/workflows/alaska.yml`:

```yaml
schedule:
  - cron: '*/10 * * * *'  # Every 10 minutes
```

[Cron syntax reference](https://crontab.guru/)

## Project Structure

```
.
├── alaska.py                      # Main scraper script
├── requirements.txt               # Python dependencies
├── .gitignore                     # Ignore results/ directory
├── .github/
│   ├── workflows/
│   │   └── alaska.yml             # GitHub Actions workflow
│   └── scripts/
│       └── summarize.py           # Results summary script
└── results/                       # Output directory (gitignored)
    ├── alaska_*_raw.json          # Raw API responses, one file per search
    └── alaska_*_parsed.json       # Parsed flight data, one file per search
```
