import logging
from common import utils

BASE = "https://api.openalex.org/works"

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

def _via_http(term: str) -> list[dict]:
    out = []
    params = {
        "search": term,
        "filter": "from_publication_date:2004-01-01,to_publication_date:2025-12-31",
        "per-page": 200,
        "cursor": "*",
        "mailto": utils.CONTACT_EMAIL,
        "select": "id,doi,display_name,publication_date,publication_year,abstract_inverted_index"
    }
    page = 1
    while True:
        resp = utils.http_get(BASE, params=params)
        j = resp.json()
        if page == 1:
            logging.info(f"[OpenAlex] {term} total={j.get('meta',{}).get('count')}")
        for w in j.get("results", []) or []:
            title = (w.get("display_name") or "").strip()
            abstract = _reconstruct(w.get("abstract_inverted_index"))
            doi = utils.normalize_doi((w.get("ids") or {}).get("doi") or w.get("doi"))
            date = w.get("publication_date")
            year = w.get("publication_year")
            # Prefer exact publication_date when available. If only a year is present,
            # map year-only records to mid-year (June) to avoid artificial January spikes.
            if date:
                month = utils.parse_month(date_str=date)
            elif year:
                month = utils.parse_month(year=year, month=6)
            else:
                month = None
            if not month: continue
            out.append({"title": title, "abstract": abstract, "text": f"{title} {abstract}".strip(), "doi": doi, "date": month})
        nxt = j.get("meta", {}).get("next_cursor")
        if not nxt: break
        params["cursor"] = nxt
        page += 1
    return out

# We always use the HTTP endpoint; omit optional openalexapi dependency

def fetch_openalex(term: str) -> list[dict]:
    # per-source cache
    cached = utils.cache_load("openalex", term)
    if cached is not None: return cached
    data = _via_http(term)
    utils.cache_save("openalex", term, data)
    return data
