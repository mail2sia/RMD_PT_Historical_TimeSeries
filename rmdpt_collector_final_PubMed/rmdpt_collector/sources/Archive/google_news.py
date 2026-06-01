import logging
from bs4 import BeautifulSoup
from common import utils

BASE = "https://www.google.com/search"

def fetch_google_news(term: str) -> list[dict]:
    cached = utils.cache_load("google_news_html", term)
    if cached is not None: return cached
    out = []
    hdr = {"User-Agent": "Mozilla/5.0 (compatible; RMDPT-Collector/1.0)"}
    for y in range(utils.START_YEAR, utils.END_YEAR+1):
        params = {
            "q": f"\"{term}\"",
            "tbm": "nws",
            "tbs": f"cdr:1,cd_min:1/1/{y},cd_max:12/31/{y}"
        }
        try:
            r = utils.http_get(BASE, headers=hdr, params=params)
        except Exception as e:
            logging.error(f"[GoogleNews] {term} year={y} error={e}")
            continue
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.find_all("a"):
            title = (a.get_text() or "").strip()
            if not title or term.lower() not in title.lower():  # title-only matching
                continue
            # date is hard in HTML; fallback to loop year if not detected
            date_span = a.find_next("span", {"class": "xQ82C e8fRJf"})
            m = utils.parse_month(date_str=date_span.get_text()) if date_span else f"{y:04d}-01"
            out.append({"title": title, "abstract": "", "text": title, "doi": None, "date": m})
        logging.info(f"[GoogleNews] {term} {y}: cum={len(out)}")
    utils.cache_save("google_news_html", term, out)
    return out
