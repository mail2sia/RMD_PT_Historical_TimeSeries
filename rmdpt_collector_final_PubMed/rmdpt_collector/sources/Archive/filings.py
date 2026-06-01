import logging
from common import utils

SEC_KEY = utils.cfg_get("SEC_API_KEY", default=None)
BASE = "https://api.sec-api.io"  # Query API via POST

def fetch_filings(term: str, cfg) -> list[dict]:
    cached = utils.cache_load("filings", term)
    if cached is not None: return cached
    out = []
    sec_key = cfg.env.get("SEC_API_KEY")
    if not sec_key:
        logging.warning("SEC_API_KEY not set; skipping filings.")
        utils.cache_save("filings", term, out)
        return out
    
    start_date = f"{cfg.start[:4]}-01-01"
    end_date = f"{cfg.end[:4]}-12-31"

    q = {
        "query": {
            "query_string": {
                "query": f"\"{term}\" AND filedAt:[{start_date} TO {end_date}]"
            }
        },
        "from": 0,
        "size": 100,
        "sort": [{"filedAt": {"order": "desc"}}]
    }
    hdr = {"Authorization": sec_key, "Content-Type":"application/json"}
    
    total = None
    while True:
        try:
            r = utils.http_post(BASE, headers=hdr, json_body=q)
            j = r.json()
        except Exception as e:
            logging.error(f"[Filings] API error for term '{term}': {e}")
            break

        if total is None:
            total = (j.get("total") or {}).get("value", 0)
            logging.info(f"[Filings] API found {total} results for '{term}'.")

        filings = j.get("filings", [])
        if not filings:
            break
        
        for f in filings:
            filed = f.get("filedAt")
            month = utils.parse_month(date_str=filed) if filed else None
            if not month: continue
            
            form_type = f.get('formType','')
            company_name = f.get('companyName','')
            title = f"SEC {form_type} filing by {company_name}".strip()
            
            # The link to the filing is more useful than a snippet
            link = f.get("linkToFilingDetails", "")
            text = f"{title}. URL: {link}"

            out.append({"title": title, "abstract": text, "text": text, "doi": None, "date": month})
        
        q["from"] += len(filings)
        if q["from"] >= total or len(filings) < q["size"]:
            break
            
    utils.cache_save("filings", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from SEC filings."""
    return fetch_filings(term, cfg)
