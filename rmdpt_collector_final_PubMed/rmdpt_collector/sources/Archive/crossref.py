import logging
from ..common import utils
import re
from typing import List, Dict, Any

BASE = "https://api.crossref.org/works"

# --- helpers ---
_TAG = re.compile(r"<[^>]+>")

def re_strip_tags(s: str) -> str:
    return _TAG.sub(" ", s or "")

# ---------------------------------------------------------------------------
# Robust Crossref fetcher handling occasional malformed / unexpected payload
# shapes where 'message' may be a list (observed) or missing. Adds retries and
# ability to respect dynamic start/end date passed from pipeline.
# ---------------------------------------------------------------------------

def fetch_crossref(term: str, start: str, end: str, max_rows: int = 1000, max_retries: int = 3) -> list[dict]:
    cached = utils.cache_load("crossref", term)
    if cached is not None:
        return cached

    out: List[Dict[str, Any]] = []
    rows = max_rows
    offset = 0
    total: int | None = None
    attempt = 0

    # Crossref uses filter parameters; ensure inclusive dates (YYYY-MM-DD)
    filt = f"from-pub-date:{start},until-pub-date:{end}"

    while True:
        params = {
            "query.bibliographic": term,
            "filter": filt,
            "rows": rows,
            "offset": offset
        }
        resp = utils.http_get(BASE, params=params)
        try:
            j = resp.json()
        except Exception as e:
            logging.warning(f"[Crossref] {term} JSON decode error at offset={offset}: {e}")
            if attempt < max_retries:
                attempt += 1
                rows = max(100, rows // 2)  # shrink page size
                continue
            break

        # If top-level is a list, treat concatenated list of blocks
        if isinstance(j, list):
            logging.warning(f"[Crossref] {term} unexpected top-level list at offset={offset}; treating as terminal batch")
            extracted: List[Dict[str, Any]] = []
            for blk in j:
                if isinstance(blk, dict):
                    msg_blk = blk.get("message")
                    if isinstance(msg_blk, dict):
                        its = msg_blk.get("items")
                        if isinstance(its, list):
                            extracted.extend(its)
            if not extracted:
                break
            items: List[Dict[str, Any]] = extracted
            if total is None:
                total = len(out) + len(items)
        else:
            msg = j.get("message")
            # Observed case: message is list rather than dict
            if isinstance(msg, list):
                logging.warning(f"[Crossref] {term} 'message' list at offset={offset}; attempting to combine")
                extracted2: List[Dict[str, Any]] = []
                for m in msg:
                    if isinstance(m, dict):
                        its2 = m.get("items")
                        if isinstance(its2, list):
                            extracted2.extend(its2)
                if not extracted2:
                    if attempt < max_retries:
                        attempt += 1; rows = max(100, rows // 2); continue
                    break
                items = extracted2
                if total is None:
                    total = len(items)
            elif isinstance(msg, dict):
                if total is None:
                    total = msg.get("total-results", 0) or 0
                    logging.info(f"[Crossref] {term} total={total}")
                its3 = msg.get("items")
                if its3 is None:
                    items = []
                elif isinstance(its3, list):
                    items = its3
                else:
                    logging.warning(f"[Crossref] {term} 'items' not list at offset={offset}; aborting")
                    break
            else:
                logging.warning(f"[Crossref] {term} unexpected 'message' type={type(msg)} at offset={offset}; aborting")
                break

        if not items:
            break

        for it in items:
            if not isinstance(it, dict):
                continue
            title_list = it.get("title") or [""]
            if isinstance(title_list, list):
                title = title_list[0] if title_list else ""
            else:
                title = str(title_list)
            abstract = it.get("abstract") or ""
            if abstract:
                abstract = re_strip_tags(abstract)
            doi = utils.normalize_doi(it.get("DOI"))

            def _dp(node: Dict[str, Any] | None):
                if not isinstance(node, dict):
                    return None
                dp = node.get("date-parts")
                if isinstance(dp, list) and dp and dp[0]:
                    y = dp[0][0]
                    m = dp[0][1] if len(dp[0]) > 1 else 1
                    return utils.parse_month(year=y, month=m)
                return None

            month = (_dp(it.get("published-print")) or _dp(it.get("published-online")) or _dp(it.get("issued")))
            if not month:
                pub = it.get("published")
                if isinstance(pub, dict):
                    dps = pub.get("date-parts")
                    if isinstance(dps, list) and dps and dps[0] and dps[0][0]:
                        month = utils.parse_month(year=dps[0][0], month=1)
            if not month:
                continue
            text = f"{title} {abstract}".strip()
            out.append({"title": title, "abstract": abstract, "text": text, "doi": doi, "date": month})

        offset += len(items)
        if total is not None and offset >= total:
            break
        if len(items) < rows:
            break

    utils.cache_save("crossref", term, out)
    return out


def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    return fetch_crossref(term, start=start, end=end)
