import logging
import time
import random
from ..common import utils
from ..common.browser import get_driver

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

API_KEY = utils.cfg_get("SPRINGER_API_KEY", default=None)
BASE = "https://api.springernature.com/metadata/json"

def _scrape_springer_page(url: str) -> str | None:
    """
    Given a Springer Link URL, scrapes the page for the full article text.
    """
    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(url)
        # Wait for the main article content to appear
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.c-article"))
        )
        
        # The main article element seems to contain all the relevant text
        article_element = driver.find_element(By.CSS_SELECTOR, "article.c-article")
        full_text = article_element.text
        
        return full_text.strip()

    except TimeoutException:
        logging.warning(f"[Springer] Timeout loading page for {url}")
        return None
    except Exception as e:
        logging.debug(f"[Springer] Could not scrape {url}: {e}")
        return None

def fetch_springer(term: str, cfg, max_records_to_scrape: int = 50) -> list[dict]:
    cached = utils.cache_load("springer", term)
    if cached is not None: return cached
    
    out = []
    api_key = cfg.env.get("SPRINGER_API_KEY")
    if not api_key:
        logging.warning("Springer API key not set; skipping.")
        utils.cache_save("springer", term, out)
        return out

    # API query to get metadata
    p = {"q": f'keyword:"{term}" AND (year:2004-2025)', "api_key": api_key, "s": 1, "p": max_records_to_scrape}
    
    try:
        r = utils.http_get(BASE, params=p)
        j = r.json()
        total = int((j.get("result") or [{}])[0].get("total", "0"))
        logging.info(f"[Springer] API found {total} results for '{term}'. Scraping top {max_records_to_scrape}.")
        recs = j.get("records", []) or []
    except Exception as e:
        logging.error(f"[Springer] API call failed for term '{term}': {e}")
        return []

    if not recs:
        utils.cache_save("springer", term, out)
        return out

    for i, rec in enumerate(recs):
        title = rec.get("title","")
        abstract = rec.get("abstract","") or ""
        doi = utils.normalize_doi(rec.get("doi"))
        pub = rec.get("publicationDate") or rec.get("publicationYear")
        month = utils.parse_month(date_str=pub) if pub else None
        if not month: continue

        # Get URL for scraping. The API provides a list of URLs.
        api_urls = rec.get("url", [])
        article_url = None
        if api_urls:
            # The first URL is usually the customer-facing one
            article_url = api_urls[0].get('value')

        if not article_url:
            continue

        logging.debug(f"Scraping {doi} ({i+1}/{len(recs)} for term '{term}')...")
        full_text = _scrape_springer_page(article_url)

        if full_text:
            out.append({"title": title, "abstract": abstract, "text": full_text, "doi": doi, "date": month})
        else:
            # Fallback to API data if scraping fails
            text = f"{title} {abstract}".strip()
            out.append({"title": title, "abstract": abstract, "text": text, "doi": doi, "date": month})

        time.sleep(0.5 + random.random() * 0.5) # Be polite

    utils.cache_save("springer", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from Springer using API search and page scraping."""
    # Date filtering is done by the API query
    return fetch_springer(term, cfg)
