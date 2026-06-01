import logging, datetime
from ..common import utils

BASE = "https://gnews.io/api/v4/search"

def fetch_gnews_api(term: str, cfg) -> list[dict]:
    cached = utils.cache_load("gnews_api", term)
    if cached is not None: return cached
    out = []
    keys = cfg.env.get("GNEWS_API_KEYS", [])
    if not keys:
        logging.warning("GNews API keys not configured; skipping.")
        utils.cache_save("gnews_api", term, out)
        return out
    
    key_idx = 0

    def _get_key():
        nonlocal key_idx
        if not keys: return None
        # Cycle through keys
        key = keys[key_idx]
        key_idx = (key_idx + 1) % len(keys)
        return key

    # The API has date filters, but we'll iterate by year for simplicity,
    # as the API can be unreliable with wide date ranges.
    for y in range(int(cfg.start[:4]), int(cfg.end[:4]) + 1):
        f = datetime.date(y,1,1).strftime("%Y-%m-%d")
        t = datetime.date(y,12,31).strftime("%Y-%m-%d")
        for page in range(1, 11): # API is limited to 10 pages
            key = _get_key()
            if not key: break
            par = {"q": f"\"{term}\"", "from": f, "to": t, "lang": "en", "max": 100, "page": page, "token": key}
            try:
                r = utils.http_get(BASE, params=par)
                j = r.json()
            except Exception as e:
                logging.error(f"[GNews] API error for term '{term}' (year {y}, page {page}): {e}")
                break # Stop trying for this year
            
            arts = j.get("articles", []) or []
            if not arts:
                break # No more articles for this year
            
            for a in arts:
                title = (a.get("title") or "").strip()
                # Basic filter: ensure the term is at least in the title
                if not title or term.lower() not in title.lower():
                    continue
                
                m = utils.parse_month(date_str=a.get("publishedAt")) or f"{y:04d}-01"
                out.append({"title": title, "abstract": "", "text": title, "doi": None, "date": m})
        
        logging.info(f"[GNews] '{term}' year {y}: collected {len(out)} articles so far.")
    
    utils.cache_save("gnews_api", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from GNews API."""
    return fetch_gnews_api(term, cfg)
