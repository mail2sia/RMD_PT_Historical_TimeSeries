import os, json, time, random, logging, re, hashlib, io, gzip
import urllib.parse as urlparse
import requests
from dateutil import parser as dateparser
from common.rate_limiter import DomainRateLimiter

# ---------- Config ----------
CONFIG: dict = {}
try:
    with open("project_config.json", "r", encoding="utf-8") as f:
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
    return cur

CONTACT_EMAIL  = cfg_get("contact","email", default=os.getenv("CONTACT_EMAIL","anonymous@example.com"))

def _ensure_str_path(val, default: str):
    # Accept plain strings, bytes or os.PathLike objects; otherwise fall back to default
    if isinstance(val, (str, bytes, os.PathLike)):
        try:
            return str(val)
        except Exception:
            return default
    return default

OUTPUT_DIR     = _ensure_str_path(cfg_get("output_dir", default="outputs"), "outputs")
CACHE_DIR      = os.path.join(OUTPUT_DIR, "cache")
LOG_LEVEL      = cfg_get("log_level", default="INFO")

# Safely parse START_YEAR and END_YEAR which may come as str/int/float or invalid types (dict/None)
def _safe_int(val, default):
    if isinstance(val, (int, float, str)):
        try:
            return int(val)
        except Exception:
            try:
                return int(str(val))
            except Exception:
                return default
    return default

START_YEAR     = _safe_int(cfg_get("start_year", default=2004), 2004)
END_YEAR       = _safe_int(cfg_get("end_year", default=2025), 2025)

# Safely parse max_workers which may come as str/int/float or invalid types (dict/None)
_val_max_workers = cfg_get("max_workers", default=8)
if isinstance(_val_max_workers, (int, float, str)):
    try:
        MAX_WORKERS = int(_val_max_workers)
    except Exception:
        try:
            MAX_WORKERS = int(str(_val_max_workers))
        except Exception:
            MAX_WORKERS = 8
else:
    MAX_WORKERS = 8
ENCODING       = cfg_get("runner","encoding", default="utf-8")
REFRESH        = os.getenv("REFRESH", "0") == "1"  # force re-fetch ignoring cache

# ---------- Polite HTTP ----------
_per_host = cfg_get("scraper","per_host_min_interval", default={}) or {}

# cfg_get may return a JSON string (from an env var) or incorrect types; ensure a dict[str, float]
if isinstance(_per_host, str):
    try:
        parsed = json.loads(_per_host)
        _per_host = parsed if isinstance(parsed, dict) else {}
    except Exception:
        _per_host = {}

# Normalize to dict[str, float], dropping invalid entries
clean_per_host: dict[str, float] = {}
if isinstance(_per_host, dict):
    for k, v in _per_host.items():
        try:
            clean_per_host[str(k)] = float(v)
        except Exception:
            # skip entries that cannot be converted to float
            continue

_per_host = clean_per_host or {}

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
