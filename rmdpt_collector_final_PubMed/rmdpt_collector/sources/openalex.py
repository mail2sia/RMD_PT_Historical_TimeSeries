import logging
import os
import requests

try:
    from ..common import utils
except ImportError:
    import importlib

    try:
        utils = importlib.import_module("rmdpt_collector.common.utils")
    except Exception:
        utils = importlib.import_module("common.utils")

BASE = "https://api.openalex.org/works"
OPENALEX_API_KEY = (
    (utils.cfg_get("OPENALEX_API_KEY", default="") or "").strip()
    or (os.getenv("OPENALEX_API_KEY", "") or "").strip()
)
OPENALEX_PER_PAGE = 100  # OpenAlex documented maximum; keeps call budget efficient.

def _reconstruct(inv_idx: dict | None) -> str:
    if not inv_idx: return ""
    max_pos = 0
    for pos in inv_idx.values():
        if pos: max_pos = max(max_pos, max(pos))
    words = [""] * (max_pos + 1)
    for w, poss in inv_idx.items():
        for p in poss:
            if 0 <= p < len(words): words[p] = w
    return " ".join(words).strip()

def _via_http(term: str, start: str = "2004-01-01", end: str = "2026-02-28") -> list[dict]:
    out = []
    params = {
        "search": term,
        "filter": f"from_publication_date:{start},to_publication_date:{end}",
        "per-page": OPENALEX_PER_PAGE,
        "cursor": "*",
        "mailto": utils.CONTACT_EMAIL,
        "select": "id,doi,display_name,publication_date,publication_year,abstract_inverted_index"
    }
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY

    page = 1
    total_cost_usd = 0.0
    while True:
        try:
            resp = utils.http_get(BASE, params=params)
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                logging.warning(
                    "[OpenAlex] 429 rate-limited for term '%s' on page %s. "
                    "Returning %s records collected so far for this term.",
                    term,
                    page,
                    len(out),
                )
                break
            raise

        j = resp.json()
        meta = j.get("meta", {}) or {}
        total_cost_usd += float(meta.get("cost_usd") or 0.0)

        if page == 1:
            total_count = int(meta.get("count") or 0)
            est_pages = (total_count + OPENALEX_PER_PAGE - 1) // OPENALEX_PER_PAGE if total_count else 0
            first_call_cost = float(meta.get("cost_usd") or 0.0)
            est_total_cost = est_pages * first_call_cost
            logging.info(
                f"[OpenAlex] {term} total={total_count} est_pages={est_pages} "
                f"first_call_cost=${first_call_cost:.6f} est_total_cost=${est_total_cost:.4f}"
            )

            remaining = resp.headers.get("X-RateLimit-Remaining")
            if remaining:
                logging.info(f"[OpenAlex] X-RateLimit-Remaining={remaining}")

        for w in j.get("results", []) or []:
            title = (w.get("display_name") or "").strip()
            abstract = _reconstruct(w.get("abstract_inverted_index"))
            doi = utils.normalize_doi((w.get("ids") or {}).get("doi") or w.get("doi"))
            date = w.get("publication_date")
            year = w.get("publication_year")
            month = utils.parse_month(date_str=date) if date else (utils.parse_month(year=year, month=1) if year else None)
            if not month: continue
            out.append({"title": title, "abstract": abstract, "text": f"{title} {abstract}".strip(), "doi": doi, "date": month})
        nxt = j.get("meta", {}).get("next_cursor")
        if not nxt: break
        params["cursor"] = nxt
        page += 1

    if page >= 1:
        logging.info(f"[OpenAlex] {term} pages={page} total_cost_usd=${total_cost_usd:.4f}")
    return out

def _via_openalexapi(term: str, start: str = "2004-01-01", end: str = "2026-02-28") -> list[dict]:
    try:
        import openalexapi as oax
    except Exception as e:
        logging.warning(f"OpenAlexAPI not available: {e}; using HTTP.")
        return _via_http(term, start=start, end=end)
    try:
        # Attempt common constructors
        ctor = getattr(oax, "OpenAlexAPI", None) or getattr(oax, "Client", None) or getattr(oax, "OpenAlex", None)
        if ctor is None: 
            logging.warning("OpenAlexAPI ctor not found; using HTTP.")
            return _via_http(term, start=start, end=end)
        # Try the most common constructor signatures across OpenAlex wrappers.
        try:
            client = ctor(utils.CONTACT_EMAIL)
        except TypeError:
            client = ctor()
        # Try common getters
        getter = None
        for name in ("getEntities","works","searchWorks","search"):
            if hasattr(client, name):
                getter = getattr(client, name); break
        if getter is None:
            logging.warning("OpenAlexAPI getter not found; using HTTP.")
            return _via_http(term, start=start, end=end)
        filt = {"from_publication_date": start, "to_publication_date": end}
        try:
            entities = getter("works", search=term, filter=filt, per_page=OPENALEX_PER_PAGE, cursor="*")
        except TypeError:
            entities = getter(entityType="works", search=term, filter=filt, per_page=OPENALEX_PER_PAGE, cursor="*")
        out = []
        for w in entities:
            title = (w.get("display_name") or w.get("title") or "").strip()
            abstract = _reconstruct(w.get("abstract_inverted_index"))
            doi = utils.normalize_doi((w.get("ids") or {}).get("doi") or w.get("doi"))
            date = w.get("publication_date")
            year = w.get("publication_year")
            month = utils.parse_month(date_str=date) if date else (utils.parse_month(year=year, month=1) if year else None)
            if not month: continue
            out.append({"title": title, "abstract": abstract, "text": f"{title} {abstract}".strip(), "doi": doi, "date": month})
        return out
    except Exception as e:
        logging.warning(f"OpenAlexAPI runtime error: {e}; using HTTP.")
        return _via_http(term, start=start, end=end)

def fetch_openalex(term: str, start: str = "2004-01-01", end: str = "2026-02-28") -> list[dict]:
    # per-source cache
    cache_term = f"{term}::{start}::{end}"
    cached = utils.cache_load("openalex", cache_term)
    if cached is not None: return cached
    data = _via_openalexapi(term, start=start, end=end)
    utils.cache_save("openalex", cache_term, data)
    return data

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from OpenAlex."""
    return fetch_openalex(term, start=start, end=end)
