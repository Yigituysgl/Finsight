"""Download the pinned 10-K filings in filings.toml from SEC EDGAR.

    python src/fetch_filings.py             fetch every pinned filing (cached in data/edgar/)
    python src/fetch_filings.py --list KO   show a ticker's recent 10-K filings, to pin one
    python src/fetch_filings.py --verify    check the pins against EDGAR's filing index
"""
import argparse
import sys
import time
import tomllib

import requests

from config import EDGAR_DIR, FILINGS_CONFIG, SEC_USER_AGENT

TICKERS_URL     = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL     = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

# Income-statement rows each filing pins for the risk scorer's scale context.
SCALE_LINE_FIELDS = {"revenue": "revenue_line", "operating_income": "operating_income_line",
                     "net_income": "net_income_line"}

# SEC allows at most 10 requests per second; stay well below that.
MIN_INTERVAL = 0.2
MAX_ATTEMPTS = 3


class EdgarClient:
    def __init__(self, user_agent):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent":      user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self._last_request = 0.0

    def get(self, url):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = self._last_request + MIN_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

            response = self.session.get(url, timeout=30)
            if response.status_code in (429, 503) and attempt < MAX_ATTEMPTS:
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response


def filing_url(filing):
    return ARCHIVE_URL.format(
        cik=int(filing["cik"]),
        accession=filing["accession"].replace("-", ""),
        document=filing["primary_document"],
    )


def cache_path(filing):
    return EDGAR_DIR / filing["ticker"] / filing["accession"] / filing["primary_document"]


def load_filings():
    if not FILINGS_CONFIG.exists():
        sys.exit(f"{FILINGS_CONFIG.name} not found; pin filings first (see --list).")
    with open(FILINGS_CONFIG, "rb") as f:
        filings = tomllib.load(f)["filing"]
    # Only original annual reports: amendments (10-K/A) and variants are rejected.
    for filing in filings:
        if filing["form"] != "10-K":
            sys.exit(f"{filing['ticker']}: form {filing['form']!r} is not allowed; only '10-K'.")
        missing = [field for field in SCALE_LINE_FIELDS.values() if not filing.get(field)]
        if missing:
            sys.exit(f"{filing['ticker']}: {', '.join(missing)} not pinned in {FILINGS_CONFIG.name}.")
    return filings


def recent_10ks(client, cik, limit=5):
    recent = client.get(SUBMISSIONS_URL.format(cik=int(cik))).json()["filings"]["recent"]
    rows = zip(recent["form"], recent["accessionNumber"], recent["filingDate"],
               recent["reportDate"], recent["primaryDocument"])
    return [
        {"accession": acc, "filing_date": filed, "period_end": period, "primary_document": doc}
        for form, acc, filed, period, doc in rows if form == "10-K"
    ][:limit]


def lookup_cik(client, ticker):
    for entry in client.get(TICKERS_URL).json().values():
        if entry["ticker"].upper() == ticker.upper():
            return entry["cik_str"], entry["title"]
    sys.exit(f"Ticker {ticker} not found in EDGAR's ticker list.")


def list_filings(client, ticker):
    cik, title = lookup_cik(client, ticker)
    print(f"{ticker.upper()}  {title}  CIK {cik}")
    for f in recent_10ks(client, cik):
        print(f"  {f['accession']}  filed {f['filing_date']}  period {f['period_end']}  "
              f"{f['primary_document']}")


def verify_filings(client, filings):
    ok = True
    for filing in filings:
        known = {f["accession"]: f for f in recent_10ks(client, filing["cik"], limit=20)}
        match = known.get(filing["accession"])
        problems = []
        if match is None:
            problems.append("accession not among recent 10-K filings")
        else:
            if match["period_end"] != filing["period_end"]:
                problems.append(f"period_end is {match['period_end']}")
            if match["primary_document"] != filing["primary_document"]:
                problems.append(f"primary_document is {match['primary_document']}")
        ok &= not problems
        print(f"  {filing['ticker']:5} {filing['accession']}  "
              f"{'OK' if not problems else 'MISMATCH: ' + '; '.join(problems)}")
    return ok


def fetch_filings(client, filings):
    for filing in filings:
        path = cache_path(filing)
        if path.exists():
            print(f"  {filing['ticker']:5} cached      {path.relative_to(EDGAR_DIR)}")
            continue
        content = client.get(filing_url(filing)).content
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"  {filing['ticker']:5} downloaded  {path.relative_to(EDGAR_DIR)}  "
              f"({len(content):,} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Fetch pinned 10-K filings from SEC EDGAR.")
    parser.add_argument("--list", metavar="TICKER", help="show recent 10-K filings for a ticker")
    parser.add_argument("--verify", action="store_true", help="check pins against EDGAR")
    args = parser.parse_args()

    if not SEC_USER_AGENT or "@" not in SEC_USER_AGENT:
        sys.exit("SEC_USER_AGENT must be set in .env with a contact email, "
                 "e.g. 'FinSight you@example.com'. See .env.example.")
    client = EdgarClient(SEC_USER_AGENT)

    if args.list:
        list_filings(client, args.list)
    elif args.verify:
        sys.exit(0 if verify_filings(client, load_filings()) else 1)
    else:
        fetch_filings(client, load_filings())


if __name__ == "__main__":
    main()
