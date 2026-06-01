import os, json, time, random, logging, re, hashlib, io, gzip
import urllib.parse as urlparse
from pathlib import Path
import requests
from dateutil import parser as dateparser
from .rate_limiter import DomainRateLimiter

# Resolve paths relative to this file's location so the collector works
# regardless of the current working directory.
_MODULE_DIR = Path(__file__).resolve().parent.parent  # rmdpt_collector/
_lexicon_cache = {}

def build_lexicon(terms: list[str]) -> dict[str, re.Pattern]:
    """Build a lexicon of compiled regex patterns for term matching."""
    pats = {}
    for term in terms:
        key = f"lexicon::{term}"
        pat = _lexicon_cache.get(key)
        if pat is None:
            # Word boundary over Unicode letters/digits (exclude underscores and punctuation)
            pat = re.compile(rf"(?<![\w]){re.escape(term.lower())}(?![\w])")
            _lexicon_cache[key] = pat
        pats[term] = pat
    return pats

def total_nom(text: str | None, pat: re.Pattern) -> int:
    """Count total number of matches for a pattern in text."""
    if not text or not pat:
        return 0
    # normalize text lower
    t = normalize_text_utf8_lower(text)
    return len(pat.findall(t))

# ---------- Config ----------
CONFIG: dict = {}
_config_json_path = _MODULE_DIR / "project_config.json"
try:
    with open(_config_json_path, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    CONFIG = {}

def cfg_get(*path, default=None):
    cur = CONFIG
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            # allow ENV fallbacks like CONTACT__EMAIL
            env_key = "__".join(path).upper()
            return os.getenv(env_key, default)
        cur = cur[p]
    if isinstance(cur, dict):
        return default
    return cur

def cfg_get_int(*path, default: int) -> int:
    """Fetch a config value and coerce to int with a safe fallback."""
    val = cfg_get(*path, default=default)
    # Explicit narrowing for static type checkers
    if val is None:
        return int(default)
    if isinstance(val, bool):  # bool is subclass of int; preserve behavior
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, (str, bytes)):
        s = val.decode() if isinstance(val, bytes) else val
        s = s.strip()
        if not s:
            return int(default)
        try:
            return int(s)
        except ValueError:
            return int(default)
    # Unsupported type
    return int(default)

CONTACT_EMAIL  = cfg_get("contact","email", default=os.getenv("CONTACT_EMAIL","anonymous@example.com"))
_output_dir_rel = str(cfg_get("output_dir", default="outputs"))
# Resolve output/cache directories relative to the rmdpt_collector package root
# so they are stable regardless of working directory.
OUTPUT_DIR     = str(_MODULE_DIR / _output_dir_rel)
CACHE_DIR      = os.path.join(OUTPUT_DIR, "cache")
LOG_LEVEL      = str(cfg_get("log_level", default="INFO"))
START_YEAR     = cfg_get_int("start_year", default=2004)
END_YEAR       = cfg_get_int("end_year", default=2025)
MAX_WORKERS    = cfg_get_int("max_workers", default=8)
ENCODING       = cfg_get("runner","encoding", default="utf-8")
REFRESH        = os.getenv("REFRESH", "0") == "1"  # force re-fetch ignoring cache

# ---------- Polite HTTP ----------
def _coerce_per_host_intervals(val) -> dict[str, float]:
    if not isinstance(val, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in val.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out

_per_host: dict[str, float] = _coerce_per_host_intervals(cfg_get("scraper","per_host_min_interval", default={}))
_http_limiter = DomainRateLimiter(per_host_min_interval=_per_host, default_min=1.0, default_max=2.0)

def http_get(url, headers=None, params=None, timeout=30, retries=5):
    domain = urlparse.urlparse(url).netloc
    attempt, backoff = 0, 1.0
    while True:
        _http_limiter.wait(domain)
        try:
            hdrs = dict(headers or {})
            hdrs.setdefault("User-Agent", f"RMDPT-Collector/1.0 (+mailto:{CONTACT_EMAIL})")
            resp = requests.get(url, headers=hdrs, params=params, timeout=timeout)
        except Exception as e:
            attempt += 1
            if attempt > retries: raise
            time.sleep(backoff + random.random()*0.5); backoff *= 2
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            attempt += 1
            if attempt > retries: resp.raise_for_status()
            time.sleep(backoff + random.random()*0.5); backoff *= 2
            continue
        return resp

def http_post(url, headers=None, json_body=None, timeout=30, retries=5):
    domain = urlparse.urlparse(url).netloc
    attempt, backoff = 0, 1.0
    while True:
        _http_limiter.wait(domain)
        try:
            hdrs = dict(headers or {})
            hdrs.setdefault("User-Agent", f"RMDPT-Collector/1.0 (+mailto:{CONTACT_EMAIL})")
            resp = requests.post(url, headers=hdrs, json=json_body, timeout=timeout)
        except Exception as e:
            attempt += 1
            if attempt > retries: raise
            time.sleep(backoff + random.random()*0.5); backoff *= 2
            continue
        if resp.status_code in (429, 500, 502, 503, 504):
            attempt += 1
            if attempt > retries: resp.raise_for_status()
            time.sleep(backoff + random.random()*0.5); backoff *= 2
            continue
        return resp

# ---------- Dates / IDs ----------
def parse_month(date_str=None, year=None, month=None):
    try:
        if date_str:
            dt = dateparser.parse(date_str, default=dateparser.parse("2000-01-01"))
            return f"{dt.year:04d}-{dt.month:02d}"
        if year:
            m = int(month) if month else 1
            return f"{int(year):04d}-{m:02d}"
    except Exception:
        return None
    return None

_DOI_CLEAN = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", re.I)
def normalize_doi(doi: str | None):
    if not doi: return None
    s = _DOI_CLEAN.sub("", doi.strip()).strip().strip("/").lower()
    return s or None

def collapse_title(title: str) -> str:
    return "".join(ch.lower() for ch in (title or "") if ch.isalnum())

def normalize_text_utf8_lower(s: str | None) -> str:
    if not s: return ""
    return (s.encode("utf-8","ignore").decode("utf-8")).lower()

# ---------- Cache helpers ----------
def _term_slug(term: str) -> str:
    h = hashlib.sha1(term.encode("utf-8")).hexdigest()[:10]
    safe = "".join(ch for ch in term if ch.isalnum() or ch in ("-","_")).strip("_-")[:50]
    return f"{safe}-{h}" if safe else h

def cache_path(source: str, term: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    p = os.path.join(CACHE_DIR, source)
    os.makedirs(p, exist_ok=True)
    return os.path.join(p, f"{_term_slug(term)}.jsonl.gz")

def cache_load(source: str, term: str) -> list[dict] | None:
    if REFRESH: return None
    path = cache_path(source, term)
    if not os.path.exists(path): return None
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except: pass
    return out

def cache_save(source: str, term: str, records: list[dict]):
    path = cache_path(source, term)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False)+"\n")

# ---------- Additional utility functions ----------
def norm_text(text: str) -> str:
    """Normalize text for processing."""
    if not text:
        return ""
    return text.lower().strip()

def parse_best_date(date_str: str) -> str | None:
    """Parse date string and return best date format."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        return dt.strftime("%Y-%m-%d")
    except:
        return None

def ym(date_str: str) -> str | None:
    """Extract year-month from date string."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        return dt.strftime("%Y-%m")
    except:
        return None

def title_hash(title: str) -> str:
    """Generate hash for title."""
    if not title:
        return ""
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:16]

def load_json(path: str) -> dict:
    """Load JSON from file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(path: str, data: dict):
    """Save data as JSON to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def write_rows_csv(path: str, rows: list[dict]):
    """Write rows to CSV file."""
    if not rows:
        return
    import csv
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

def build_pivot(csv_path: str, pivot_path: str, terms: list[str], start_date: str, end_date: str):
    """Build monthly wide pivot from long CSV.

    Expected long schema contains: date, NoM, terms_country_code.
    Produces a CSV with one row per month and one column per terms_country_code.
    """
    import csv
    from collections import defaultdict
    from datetime import datetime

    def _parse_month(value: str) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        # Accept YYYY-MM, YYYY-MM-DD, and common date-like strings.
        if len(value) >= 7 and value[4] == "-" and value[7:8] in {"", "-"}:
            try:
                return f"{int(value[0:4]):04d}-{int(value[5:7]):02d}"
            except Exception:
                return None
        try:
            dt = dateparser.parse(value)
            return dt.strftime("%Y-%m") if dt else None
        except Exception:
            return None

    def _month_range(start_ym: str, end_ym: str) -> list[str]:
        sy, sm = map(int, start_ym.split("-"))
        ey, em = map(int, end_ym.split("-"))
        cur = datetime(sy, sm, 1)
        end = datetime(ey, em, 1)
        out: list[str] = []
        while cur <= end:
            out.append(cur.strftime("%Y-%m"))
            if cur.month == 12:
                cur = datetime(cur.year + 1, 1, 1)
            else:
                cur = datetime(cur.year, cur.month + 1, 1)
        return out

    if not os.path.exists(csv_path):
        return

    start_ym = _parse_month(start_date)
    end_ym = _parse_month(end_date)
    if not start_ym or not end_ym:
        return

    months = _month_range(start_ym, end_ym)
    agg: dict[tuple[str, str], int] = defaultdict(int)
    seen_columns: set[str] = set()

    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            month = _parse_month(row.get("date", ""))
            col = (row.get("terms_country_code") or "").strip()
            if not month or not col:
                continue
            if month < start_ym or month > end_ym:
                continue
            try:
                value = int(float(row.get("NoM", 0) or 0))
            except Exception:
                value = 0
            agg[(month, col)] += value
            seen_columns.add(col)

    # Add baseline UN columns for configured terms to keep a stable schema.
    for term in terms:
        seen_columns.add(f"{term}_UN")

    columns = sorted(seen_columns)
    os.makedirs(os.path.dirname(pivot_path), exist_ok=True)
    with open(pivot_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", *columns])
        for month in months:
            writer.writerow([month, *[agg.get((month, c), 0) for c in columns]])

def write_audit(audit_json_path: str, audit_html_path: str, audit_data: dict):
    """Write audit information."""
    save_json(audit_json_path, audit_data)
    # HTML version would be generated here
    pass

def dedup_rows(rows: list[dict]) -> list[dict]:
    """Deduplicate rows based on some key."""
    seen = set()
    deduped = []
    for row in rows:
        key = (row.get("date", ""), row.get("doi", ""), row.get("title", ""))
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped

# Schema constant
REQUIRED_SCHEMA = {
    "date": str,
    "NoM": int,
    "disease": str,
    "doi": str,
    "source": str,
    "pk": str,
    "title": str
}
