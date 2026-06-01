import logging
import time
import random
from typing import List, Dict

# Selenium for scraping
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..common import utils
from ..common.browser import get_driver # Use shared browser

# Use API to get IDs and metadata, then scrape the page for full text
API_BASE = "https://clinicaltrials.gov/api/query/study_fields"
STUDY_URL_BASE = "https://clinicaltrials.gov/study/"

# Fields to retrieve from the API
API_FIELDS = [
    "NCTId", "OfficialTitle", "BriefTitle", "BriefSummary",
    "StartDate", "PrimaryCompletionDate", "StudyFirstPostDate"
]

# --- Scraping Logic ---

def scrape_study_page_text(nct_id: str) -> str | None:
    """
    Given an NCT ID, scrapes the study page for all relevant text sections
    and combines them.
    """
    driver = get_driver()
    if not driver:
        return None # WebDriver failed to initialize

    url = f"{STUDY_URL_BASE}{nct_id}"
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "main-content"))
        )
        
        def get_text_by_id(elem_id: str) -> str:
            try:
                return driver.find_element(By.ID, elem_id).text
            except NoSuchElementException:
                return ""

        title = driver.find_element(By.CSS_SELECTOR, "h1.ct-header-title").text
        brief_summary = get_text_by_id("brief-summary")
        detailed_description = get_text_by_id("detailed-description")
        conditions = get_text_by_id("conditions")
        interventions = get_text_by_id("interventions")
        criteria = get_text_by_id("criteria")

        full_text = " ".join(filter(None, [
            title, brief_summary, detailed_description, 
            conditions, interventions, criteria
        ]))
        
        return full_text.strip()

    except TimeoutException:
        logging.warning(f"[ClinicalTrials] Timeout loading page for {nct_id} at {url}")
        return None
    except Exception as e:
        logging.error(f"[ClinicalTrials] Error scraping {nct_id}: {e}")
        return None

# --- Main Fetcher ---

def _pick_date(rec: dict) -> str | None:
    """Picks the best available date from a study record."""
    for k in ("StartDate", "PrimaryCompletionDate", "StudyFirstPostDate"):
        vals = rec.get(k) or []
        if isinstance(vals, list) and vals:
            m = utils.parse_month(date_str=vals[0])
            if m:
                return m
    return None

def fetch_clinical_trials(term: str, max_records_to_scrape: int = 100) -> list[dict]:
    """
    Fetches clinical trials for a term by getting IDs from the API, then scraping each page.
    """
    cached = utils.cache_load("clinicaltrials", term)
    if cached is not None:
        return cached

    params = {
        "expr": term,
        "fields": ",".join(API_FIELDS),
        "min_rnk": 1,
        "max_rnk": max_records_to_scrape,
        "fmt": "json"
    }
    try:
        resp = utils.http_get(API_BASE, params=params)
        data = resp.json()
        root = data.get("StudyFieldsResponse")
        if not root:
            logging.info(f"[ClinicalTrials] No API results for term '{term}'")
            utils.cache_save("clinicaltrials", term, [])
            return []
        studies = root.get("StudyFields", [])
        total_found = root.get("NStudiesFound", 0)
        logging.info(f"[ClinicalTrials] API found {total_found} studies for '{term}'. Scraping top {len(studies)}.")
    except Exception as e:
        logging.error(f"[ClinicalTrials] API call failed for term '{term}': {e}")
        return []

    out = []
    for i, study in enumerate(studies):
        nct_id = (study.get("NCTId") or [""])[0]
        if not nct_id:
            continue
        
        logging.debug(f"Scraping {nct_id} ({i+1}/{len(studies)} for term '{term}')...")
        
        full_text = scrape_study_page_text(nct_id)
        
        if full_text:
            date_month = _pick_date(study)
            if not date_month:
                continue

            official_title = (study.get("OfficialTitle") or [""])[0]
            brief_title = (study.get("BriefTitle") or [""])[0]
            title = official_title or brief_title
            
            brief_summary_text = (study.get("BriefSummary") or [""])[0]

            out.append({
                "title": title.strip(),
                "abstract": brief_summary_text.strip(),
                "text": full_text,
                "doi": None,
                "date": date_month
            })
        time.sleep(0.2 + random.random() * 0.2)

    utils.cache_save("clinicaltrials", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    # The clinicaltrials.gov API 'expr' doesn't have a reliable date filter.
    # Date filtering happens later in the main pipeline.
    return fetch_clinical_trials(term, max_records_to_scrape=100)
