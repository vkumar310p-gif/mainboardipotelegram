import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.chittorgarh.com/"
INVESTORGAIN_GMP_URL = "https://www.investorgain.com/report/ipo-gmp-live/331/ipo/"
# Fallback pages; the scraper also discovers relevant links from the homepage.
FALLBACK_URLS = [
    "https://www.chittorgarh.com/ipo/ipo_dashboard.asp",
    "https://www.chittorgarh.com/report/ipo_subscription_status/1/mainboard/",
    "https://www.chittorgarh.com/report/ipo_grey_market/1/mainboard/",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; MainboardIPOReport/1.0; contact: personal-use)"
}
TIMEOUT = 25


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def get_html(url):
    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def discover_pages():
    """Discover likely dashboard, subscription and grey-market pages from site navigation."""
    pages = set(FALLBACK_URLS)
    try:
        soup = BeautifulSoup(get_html(BASE), "html.parser")
        for a in soup.select("a[href]"):
            href = urljoin(BASE, a.get("href", ""))
            text = clean(a.get_text(" ", strip=True)).lower()
            path = href.lower()
            if "chittorgarh.com" not in path:
                continue
            if any(word in (text + " " + path) for word in
                   ["mainboard ipo", "ipo dashboard", "ipo subscription", "grey market", "ipo grey", "gmp"]):
                pages.add(href.split("#")[0])
    except Exception as exc:
        print(f"Homepage discovery warning: {exc}", file=sys.stderr)
    return sorted(pages)


def parse_tables(url):
    """Return HTML tables as row dictionaries; handles ordinary server-rendered tables."""
    try:
        soup = BeautifulSoup(get_html(url), "html.parser")
    except Exception as exc:
        print(f"Could not fetch {url}: {exc}", file=sys.stderr)
        return []

    result = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if len(rows) < 2:
            continue

        # Use first row as headers, but skip tables without meaningful labels.
        headers = [clean(x).lower() for x in rows[0]]
        if not any(any(k in h for k in ["ipo", "company", "name", "gmp", "qib", "retail", "issue", "size", "subscription"]) for h in headers):
            continue

        records = []
        for row in rows[1:]:
            if not any(row):
                continue
            record = {}
            for i, header in enumerate(headers):
                if header:
                    record[header] = row[i] if i < len(row) else ""
            record["_source_url"] = url
            records.append(record)
        if records:
            result.extend(records)
    return result


def first_value(record, keys):
    for key, value in record.items():
        k = key.lower()
        if any(term in k for term in keys) and value and value not in {"-", "--", "N/A", "NA"}:
            return value
    return ""


def normalise_name(record):
    name = first_value(record, ["ipo name", "company name", "company", "ipo", "name"])
    if not name:
        # Fallback to the first non-empty cell that looks like a company label.
        for key, value in record.items():
            if not key.startswith("_") and value and len(value) > 3:
                name = value
                break
    name = re.sub(r"\b(ipo|limited|ltd\.?)\b", "", name, flags=re.I)
    return clean(name).lower()


def looks_mainboard(record):
    blob = " ".join(str(v) for k, v in record.items() if not k.startswith("_")).lower()
    # Keep records from mainboard-labelled pages, or rows explicitly marked mainboard.
    source = record.get("_source_url", "").lower()
    return ("mainboard" in source) or ("mainboard" in blob) or ("ipo" in blob)


def build_report():
    pages = discover_pages()
    all_records = []
    for url in pages:
        all_records.extend(parse_tables(url))

    # Merge rows by normalized company name. Only include rows with a plausible IPO/company name.
    merged = {}
    for record in all_records:
        name = normalise_name(record)
        if not name or len(name) < 3:
            continue
        if not looks_mainboard(record):
            continue
        key = name
        merged.setdefault(key, {"name": name.title(), "sources": set(), "raw": []})
        merged[key]["sources"].add(record.get("_source_url", ""))
        merged[key]["raw"].append(record)

    # Keep only rows that appear to contain IPO information, not general site tables.
    output = []
    for item in merged.values():
        rows = item["raw"]
        combined = {}
        for row in rows:
            combined.update(row)
        size = first_value(combined, ["issue size", "issue amount", "total issue", "size"])
        gmp = first_value(combined, ["gmp", "grey market", "grey-market"])
        qib = first_value(combined, ["qib", "qualified institutional"])
        retail = first_value(combined, ["retail"])
        total = first_value(combined, ["total", "overall", "subscription"])
        close_date = first_value(combined, ["close date", "closing date", "issue close", "close"])
        # Avoid sending unrelated tables from the homepage.
        if any([size, gmp, qib, retail, total]) or "ipo" in " ".join(item["sources"]).lower():
            output.append({
                "name": item["name"],
                "size": size or "N/A",
                "gmp": gmp or "N/A",
                "qib": qib or "N/A",
                "retail": retail or "N/A",
                "overall": total or "N/A",
                "close_date": close_date or "N/A",
                "sources": sorted(item["sources"]),
            })
    gmp_rows = fetch_investorgain_gmp()
    output = merge_gmp_into_rows(output, gmp_rows)
    if INVESTORGAIN_GMP_URL not in pages:
        pages.append(INVESTORGAIN_GMP_URL)
    return output, pages



def fetch_investorgain_gmp():
    """Fetch GMP, IPO size and update timestamp from InvestorGain's live GMP page."""
    records = []
    try:
        soup = BeautifulSoup(get_html(INVESTORGAIN_GMP_URL), "html.parser")
    except Exception as exc:
        print(f"InvestorGain GMP fetch warning: {exc}", file=sys.stderr)
        return records

    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        if len(rows) < 2:
            continue
        headers = [x.lower() for x in rows[0]]
        if not any("gmp" in h for h in headers) or not any("updated" in h for h in headers):
            continue

        def col_index(terms):
            for i, header in enumerate(headers):
                if any(term in header for term in terms):
                    return i
            return None

        name_i = col_index(["name", "ipo"])
        gmp_i = col_index(["gmp"])
        size_i = col_index(["ipo size", "size"])
        updated_i = col_index(["updated"])
        for row in rows[1:]:
            def at(i):
                return row[i] if i is not None and i < len(row) else ""
            name = at(name_i)
            if not name or re.search(r'\bSME\b|BSE SME|NSE SME', name, re.I):
                continue
            if "ipo" not in name.lower():
                continue
            records.append({
                "name": clean(re.sub(r'\s+[UOCL]\s*$', '', name)),
                "gmp": at(gmp_i) or "N/A",
                "size": at(size_i) or "N/A",
                "gmp_updated": at(updated_i) or "N/A",
                "source_url": INVESTORGAIN_GMP_URL,
            })
        if records:
            break
    return records


def merge_gmp_into_rows(rows, gmp_rows):
    def key(name):
        name = re.sub(r'\b(ipo|limited|ltd\.?|india)\b', ' ', name, flags=re.I)
        return re.sub(r'[^a-z0-9]', '', name.lower())

    lookup = {key(item["name"]): item for item in gmp_rows}
    for row in rows:
        row_key = key(row["name"])
        match = lookup.get(row_key)
        if not match:
            candidates = [g for g in gmp_rows if row_key and
                          (row_key in key(g["name"]) or key(g["name"]) in row_key)]
            match = candidates[0] if len(candidates) == 1 else None
        if match:
            row["gmp"] = match["gmp"]
            row["gmp_updated"] = match["gmp_updated"]
            row["gmp_source"] = match["source_url"]
        else:
            row["gmp"] = "N/A"
            row["gmp_updated"] = "N/A"
            row["gmp_source"] = INVESTORGAIN_GMP_URL
    return rows


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as environment variables.")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def format_report(rows, pages):
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
    lines = [f"📊 DAILY MAINBOARD IPO REPORT", f"🕓 As checked: {now}", ""]
    if not rows:
        lines += [
            "⚠️ The scraper could not confidently extract IPO rows from the current page layout.",
            "No figures have been guessed. Please check the source links below or inspect the GitHub Actions log.",
            "",
        ]
    else:
        # Telegram messages are limited; split into chunks if many IPOs are returned.
        for idx, row in enumerate(rows[:25], start=1):
            lines += [
                f"{idx}. {row['name']}",
                f"IPO size: {row['size']}",
                f"Current GMP: {row['gmp']} (InvestorGain updated: {row.get('gmp_updated', 'N/A')})",
                f"QIB: {row['qib']} | Retail: {row['retail']} | Overall: {row['overall']}",
                f"Closing date: {row['close_date']}",
                "",
            ]
    lines += ["🔗 Sources checked:"]
    for url in pages[:12]:
        lines.append(url)
    lines += [
        "",
        "Note: GMP is unofficial and may change quickly. N/A means the value was not reliably found."
    ]
    message = "\n".join(lines)
    # Telegram sendMessage limit is 4096 characters.
    return [message[i:i+3900] for i in range(0, len(message), 3900)]


def main():
    rows, pages = build_report()
    messages = format_report(rows, pages)
    for message in messages:
        send_telegram(message)
    print(f"Sent {len(messages)} Telegram message(s); parsed {len(rows)} candidate IPO rows from {len(pages)} pages.")


if __name__ == "__main__":
    main()
