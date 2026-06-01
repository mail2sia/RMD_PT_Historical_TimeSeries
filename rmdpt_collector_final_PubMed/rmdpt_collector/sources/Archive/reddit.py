import logging, datetime, requests
from common import utils

P_SUB = "https://api.pushshift.io/reddit/search/submission/"
P_COM = "https://api.pushshift.io/reddit/search/comment/"

def _windowed_fetch(url, q, after_ts, before_ts, size=100):
    out, offset = [], 0
    while True:
        params = {"q": q, "after": after_ts, "before": before_ts, "size": size, "offset": offset}
        try:
            utils._http_limiter.wait("api.pushshift.io")
            r = requests.get(url, params=params, timeout=30)
        except Exception as e:
            logging.error(f"[Reddit] {url} offset={offset} error={e}")
            break
        if r.status_code != 200: break
        data = r.json()
        items = data.get("data", []) or []
        if not items: break
        out.extend(items)
        offset += len(items)
        if len(items) < size: break
    return out

def fetch_reddit(term: str) -> list[dict]:
    cached = utils.cache_load("reddit", term)
    if cached is not None: return cached
    out = []
    after  = int(datetime.datetime(utils.START_YEAR,1,1).timestamp())
    before = int(datetime.datetime(utils.END_YEAR,12,31,23,59,59).timestamp())
    subs = _windowed_fetch(P_SUB, term, after, before, size=100)
    for s in subs:
        title = (s.get("title") or "")
        selftext = (s.get("selftext") or "")
        ts = s.get("created_utc")
        if not ts: continue
        month = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m")
        text = f"{title} {selftext}".strip()
        out.append({"title": title, "abstract": selftext, "text": text, "doi": None, "date": month})
    # include comments as available
    coms = _windowed_fetch(P_COM, term, after, before, size=100)
    for c in coms:
        body = (c.get("body") or "")
        link_title = (c.get("link_title") or "")
        ts = c.get("created_utc")
        if not ts: continue
        month = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m")
        text = f"{link_title} {body}".strip()
        out.append({"title": link_title, "abstract": body, "text": text, "doi": None, "date": month})
    utils.cache_save("reddit", term, out)
    logging.info(f"[Reddit] {term} posts+comments={len(out)}")
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from Reddit."""
    return fetch_reddit(term)
