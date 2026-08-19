# Clay Leads Scraper

Playwright tool used with freelance Clay enrichment: open Clay in a stealth browser, sign up, then look at CSV batches in a local leads folder.

Default folders match the original machine:

- Source CSVs: `D:\LEADS CSV`
- Output: `D:\LEADS\archieved leads`

Override those with `LEADS_SOURCE_DIR` and `LEADS_OUTPUT_DIR`.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Fill `.env` (or set the same variables in your shell). Never commit API keys.

Convert Excel dumps into the Clay source folder:

```bash
python csv_to_leads_folder.py "D:\LEADS" "D:\LEADS CSV"
python clay_scraper.py
```

The browser stays visible (`headless=False`). After Clay email verification, press Enter in the terminal.

This copy lists pending CSVs in the leads folder. The Clay table-import step after signup was unfinished in the original file.
