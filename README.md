# Alaska Airlines Award Flight Scraper

Automatically search for Alaska Airlines award flight availability and get notified of deals.

## Features

- 🔍 Search multiple routes in parallel
- 🔥 Highlight deals below your threshold
- 📅 Filter by date range
- ⏰ Scheduled daily searches via GitHub Actions

## Local Usage

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the script
python alaska.py
```

## GitHub Actions Setup

This repo includes a GitHub Actions workflow that runs daily at 8 AM UTC.

### Quick Setup

1. Create a new GitHub repository
2. Push this code to the repository:
   ```bash
   cd /Users/mahaojun/scripts
   git init
   git add .
   git commit -m "Initial commit: Alaska award flight scraper"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/alaska-awards.git
   git push -u origin main
   ```

3. Go to your repo on GitHub → **Actions** tab
4. Click **"I understand my workflows, go ahead and enable them"**
5. The workflow will run automatically daily, or click **"Run workflow"** to trigger manually

### View Results

- Go to **Actions** → click on a workflow run
- **Artifacts**: Download JSON/PNG results
- **Logs**: See deals summary in the "Display results summary" step

## Configuration

Edit `alaska.py` to modify searches in the `main()` function:

```python
searches = [
    {
        "origin": "BA3",
        "destination": "TPE",
        "outbound_date": "2026-03-10",
        "date_range_start": "2026-03-09",
        "date_range_end": "2026-03-16",
        "highlight_below": 175,
        "adults": 2,
    },
    # Add more routes here...
]
```

## Schedule

Edit `.github/workflows/alaska.yml` to change the schedule:

```yaml
schedule:
  - cron: '0 8 * * *'  # Daily at 8 AM UTC
```

[Cron syntax reference](https://crontab.guru/)
