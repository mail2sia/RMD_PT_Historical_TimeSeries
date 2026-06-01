import logging
import time
import random
from ..common import utils
from ..common.browser import get_driver

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE    = "https://api.elsevier.com/content/search/sciencedirect"

def _scrape_sciencedirect_page(url: str) -> str | None:
    """
    Given a ScienceDirect URL, scrapes the page for the full article text.
    """
    driver = get_driver()
    if not driver:
        return None

    try:
        driver.get(url)
        # Wait for the main article body to be present
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "body"))
        )
        
        # Extract text from the abstract and the main body
        title_text = driver.find_element(By.CSS_SELECTOR, "span.title-text").text
        abstract_text = ""
        try:
            abstract_text = driver.find_element(By.CSS_SELECTOR, "div.abstract.author-highlights").text
        except Exception:
            pass # Highlights may not exist
            
        body_text = driver.find_element(By.ID, "body").text
        
        full_text = " ".join(filter(None, [title_text, abstract_text, body_text]))
        return full_text.strip()

    except TimeoutException:
        logging.warning(f"[Elsevier] Timeout loading page for {url}")
        return None
    except Exception as e:
        # This can happen for various reasons, e.g., article requires login, page structure is different
        logging.debug(f"[Elsevier] Could not scrape {url}: {e}")
        return None

def fetch_elsevier(term: str, cfg, max_records_to_scrape: int = 50) -> list[dict]:
    cached = utils.cache_load("elsevier", term)
    if cached is not None: return cached
    
    out = []
    api_keys = cfg.env.get("ELSEVIER_API_KEY", [])
    if not api_keys:
        logging.warning("Elsevier API keys not configured; skipping.")
        utils.cache_save("elsevier", term, out); return out

    hdr = {"X-ELS-APIKey": random.choice(api_keys), "Accept":"application/json"}
    inst_token = cfg.env.get("ELSEVIER_INST_TOKEN")
    if inst_token: hdr["X-ELS-Insttoken"] = inst_token
    
    # Query for metadata from the API
    q  = f"TITLE-ABS-KEY({term}) AND PUBYEAR > 2003 AND PUBYEAR < 2026"
    par = {"query": q, "count": max_records_to_scrape, "start": 0} # Limit API results to what we will scrape
    
    try:
        r = utils.http_get(BASE, headers=hdr, params=par)
        j = r.json()
        total = int((j.get("search-results", {}) or {}).get("opensearch:totalResults", "0"))
        logging.info(f"[Elsevier] API found {total} results for '{term}'. Scraping top {max_records_to_scrape}.")
        entries = (j.get("search-results", {}) or {}).get("entry", []) or []
    except Exception as e:
        logging.error(f"[Elsevier] API call failed for term '{term}': {e}")
        return []

    if not entries:
        utils.cache_save("elsevier", term, out)
        return out

    for i, e in enumerate(entries):
        title = e.get("dc:title","")
        abstract = e.get("dc:description","") or ""
        doi = utils.normalize_doi(e.get("prism:doi"))
        pub = e.get("prism:coverDate") or e.get("prism:coverDisplayDate")
        month = utils.parse_month(date_str=pub) if pub else None
        if not month:
            y = (e.get("prism:coverDate") or "")[:4]; month = utils.parse_month(year=y, month=1) if y else None
        if not month: continue

        # Get the URL to scrape
        article_url = e.get("prism:url")
        if not article_url:
            continue

        logging.debug(f"Scraping {doi} ({i+1}/{len(entries)} for term '{term}')...")
        full_text = _scrape_sciencedirect_page(article_url)

        if full_text:
            out.append({
                "title": title, 
                "abstract": abstract, 
                "text": full_text, 
                "doi": doi, 
                "date": month
            })
        else:
            # Fallback to API data if scraping fails
            text = f"{title} {abstract}".strip()
            out.append({"title": title, "abstract": abstract, "text": text, "doi": doi, "date": month})

        time.sleep(0.5 + random.random() * 0.5) # Be polite

    utils.cache_save("elsevier", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from Elsevier using API search and page scraping."""
    # Date filtering is done by the API query (PUBYEAR)
    return fetch_elsevier(term, cfg)
