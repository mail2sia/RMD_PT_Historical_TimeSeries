import logging
import csv
import re
import time
import requests
import os
from datetime import datetime
from bs4 import BeautifulSoup, Tag
from concurrent.futures import ThreadPoolExecutor, as_completed
from search_terms_pt import ALL_PT_TERMS as ALL_SEARCH_TERMS, TERM_TO_BASE

# ==== Country Code Mapping ====
COUNTRY_MAPPING = {
    "united states": "US", "usa": "US", "china": "CN", "japan": "JP", "india": "IN",
    "germany": "DE", "france": "FR", "united kingdom": "UK", "canada": "CA", "australia": "AU",
    "brazil": "BR", "mexico": "MX", "russia": "RU", "south korea": "KR", "indonesia": "ID",
    "philippines": "PH", "thailand": "TH", "vietnam": "VI", "singapore": "SG", "malaysia": "MY",
    "pakistan": "PK", "bangladesh": "BD", "spain": "ES", "italy": "IT", "netherlands": "NL",
    "belgium": "BE", "switzerland": "CH", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "poland": "PL", "turkey": "TR", "iran": "IR", "egypt": "EG",
    "south africa": "ZA", "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
    "israel": "IL", "new zealand": "NZ", "greece": "GR", "austria": "AT", "portugal": "PT",
    "ireland": "IE", "cyprus": "CY", "romania": "RO", "bulgaria": "BG", "ukraine": "UA",
    "hungary": "HU", "czech": "CZ", "saudi arabia": "SA", "united arab emirates": "AE",
    "kuwait": "KU", "qatar": "QA", "morocco": "MA", "algeria": "DZ", "nigeria": "NG",
    "kenya": "KE", "ghana": "GH", "tanzania": "TA", "uganda": "UG", "ethiopia": "ET",
}

OUTPUT_FILE = "collected_PT_CrossRef_NoM.csv"
SKIPPED_FILE = "skipped_pt_crossref.txt"
DOIS_FILE = "collected_pt_crossref_dois.csv"
EXISTING_FILE = "collected_pt_dois.csv"
MAX_WORKERS = 2  # Reduced to avoid rate limiting
MAX_QUERY_RUNTIME_MINUTES = 180
MAX_METADATA_RUNTIME_MINUTES = 240
MAX_ARTICLES_TO_PROCESS = 20000
ENABLE_HTML_SCRAPE_FALLBACK = os.getenv("PT_CROSSREF_SCRAPE_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "y"}
COLLECTION_START = datetime(2004, 1, 1)
COLLECTION_END = datetime(2026, 2, 28)

logging.basicConfig(filename="pt_crossref_log.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Load existing DOIs to avoid duplication
existing_dois = set()
if os.path.exists(EXISTING_FILE):
    with open(EXISTING_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = row.get("doi", "").lower().strip()
            if doi:
                existing_dois.add(doi)

def normalize_text(text):
    return re.sub(r"\s+", " ", text.strip().lower()) if isinstance(text, str) else ""


def is_within_collection_window(date_value: str) -> bool:
    """Accept YYYY, YYYY-MM, or YYYY-MM-DD and enforce Jan-2004..Feb-2026."""
    if not date_value:
        return False
    raw = str(date_value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return COLLECTION_START <= dt <= COLLECTION_END
        except ValueError:
            continue
    return False

def query_crossref(term, year, rows=25, max_retries=3):
    params = {
        "query.bibliographic": term,
        "filter": f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
        "rows": rows
    }
    
    for attempt in range(max_retries):
        try:
            print(f"🌐 CrossRef Query: {term} ({year})")
            time.sleep(1)  # Rate limiting delay
            response = requests.get("https://api.crossref.org/works", params=params, timeout=15)
            
            if response.status_code == 429:
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                logging.warning(f"Rate limited. Waiting {wait_time}s before retry {attempt+1}/{max_retries}")
                time.sleep(wait_time)
                continue
                
            if response.status_code == 200:
                items = response.json().get("message", {}).get("items", [])
                results = []
                for item in items:
                    doi = item.get("DOI", "")
                    if not doi or doi.lower().strip() in existing_dois:
                        continue
                    pub_date = item.get("published-print", item.get("issued", {})).get("date-parts", [[year]])[0]
                    date = "-".join(map(str, pub_date)) if pub_date else f"{year}"
                    if not is_within_collection_window(date):
                        continue
                    # Extract country from funder metadata
                    country = "UN"  # Unknown by default
                    funder_info = item.get("funder", [])
                    if isinstance(funder_info, list) and len(funder_info) > 0:
                        funder_country = funder_info[0].get("country", "")
                        if funder_country and funder_country.strip():
                            country = funder_country.upper()[:2]
                    results.append({"doi": doi, "technology": term, "date": date, "country": country})
                return results
            else:
                logging.warning(f"CrossRef failed: {response.status_code}")
                
        except Exception as e:
            logging.error(f"CrossRef error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                
    return []

def count_mentions_by_term(text, terms):
    mentions = {}
    text = text.lower()
    for term in terms:
        matches = re.findall(r'\b' + re.escape(term) + r'\b', text or "", re.IGNORECASE)
        if matches:
            base = TERM_TO_BASE.get(term)
            if base:
                mentions[base] = mentions.get(base, 0) + len(matches)
    return mentions

def fetch_crossref_metadata(doi, max_retries=3):
    for attempt in range(max_retries):
        try:
            time.sleep(0.5)  # Rate limiting delay
            url = f"https://api.crossref.org/works/{doi}"
            res = requests.get(url, timeout=20)
            
            if res.status_code == 429:
                wait_time = (2 ** attempt) * 5
                logging.warning(f"Rate limited fetching {doi}. Waiting {wait_time}s")
                time.sleep(wait_time)
                continue
                
            if res.status_code == 200:
                item = res.json().get("message", {})
                title = normalize_text(" ".join(item.get("title", [])))
                abstract = normalize_text(item.get("abstract", ""))
                keywords = normalize_text(" ".join(item.get("subject", [])))
                pub_date = item.get("published-print", item.get("issued", {})).get("date-parts", [[]])[0]
                date = "-".join(map(str, pub_date)) if pub_date else ""

                # Optional scraping fallback can be enabled explicitly; disabled by default for resilience.
                if ENABLE_HTML_SCRAPE_FALLBACK and (not abstract or not keywords or not title):
                    try:
                        html_url = f"https://doi.org/{doi}"
                        page = requests.get(html_url, timeout=20)
                        soup = BeautifulSoup(page.text, 'html.parser')

                        if not title:
                            title_tag = soup.find('meta', {'name': 'dc.Title'}) or soup.find('title')
                            if title_tag:
                                if isinstance(title_tag, Tag):
                                    content = title_tag.get('content', None)
                                    if not content:
                                        content = title_tag.get_text()
                                else:
                                    content = title_tag.get_text() if hasattr(title_tag, 'get_text') else str(title_tag)
                                title = normalize_text(content)

                        if not abstract:
                            abs_tag = soup.find('meta', {'name': 'dc.Description'}) or soup.find('meta', {'name': 'description'})
                            if abs_tag and isinstance(abs_tag, Tag):
                                abstract = normalize_text(abs_tag.get('content', ''))

                        if not keywords:
                            kw_tag = soup.find('meta', {'name': 'keywords'})
                            if kw_tag and isinstance(kw_tag, Tag):
                                content = kw_tag.get('content', '') or kw_tag.get_text()
                                keywords = normalize_text(content)

                    except Exception as e:
                        logging.warning(f"⚠️ Scraping failed for DOI {doi}: {e}")

                return {
                    "doi": doi,
                    "date": date,
                    "title": title,
                    "abstract": abstract,
                    "keywords": keywords
                }
            else:
                logging.warning(f"⚠️ Metadata fetch failed for DOI {doi}: HTTP {res.status_code}")
                
        except Exception as e:
            logging.warning(f"⚠️ Metadata fetch error for DOI {doi} (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                
    return {"doi": doi, "date": "", "title": "", "abstract": "", "keywords": ""}

def process_article(article):
    doi = article["doi"]
    meta = fetch_crossref_metadata(doi)
    all_text = f"{meta['title']} {meta['abstract']} {meta['keywords']}"
    mention_counts = count_mentions_by_term(all_text, ALL_SEARCH_TERMS)

    # Calculate total mentions across all technologies
    total_mentions = sum(mention_counts.values())
    
    rows = []
    if not is_within_collection_window(meta["date"]):
        return rows

    for tech, count in mention_counts.items():
        # Extract country from article metadata
        country = article.get("country", "UN")
        tech_with_country = f"{tech}_{country}"
        rows.append({
            "date": meta["date"],
            "NoM": count,
            "total_NoM": total_mentions,
            "technology": tech_with_country,
            "doi": meta["doi"]
        })
    return rows

def main():
    query_start = time.monotonic()

    with open(OUTPUT_FILE, "w", newline='', encoding="utf-8") as f_out, \
         open(SKIPPED_FILE, "w", encoding="utf-8") as f_skip, \
         open(DOIS_FILE, "w", newline='', encoding="utf-8") as f_dois:

        writer = csv.DictWriter(f_out, fieldnames=["date", "NoM", "total_NoM", "technology", "doi"])
        writer.writeheader()
        writer_dois = csv.DictWriter(f_dois, fieldnames=["doi", "technology", "date"])
        writer_dois.writeheader()

        articles = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for year in range(2004, 2027):
                for term in ALL_SEARCH_TERMS:
                    futures.append(executor.submit(query_crossref, term, year))

            for future in as_completed(futures):
                if (time.monotonic() - query_start) > (MAX_QUERY_RUNTIME_MINUTES * 60):
                    logging.warning(
                        f"Query phase runtime exceeded {MAX_QUERY_RUNTIME_MINUTES} minutes. "
                        "Stopping Crossref query collection early."
                    )
                    for pending in futures:
                        pending.cancel()
                    break
                results = future.result()
                for entry in results:
                    articles.append(entry)
                    writer_dois.writerow({"doi": entry["doi"], "technology": entry["technology"], "date": entry["date"]})

        unique_articles = {a["doi"]: a for a in articles if a["doi"]}
        if len(unique_articles) > MAX_ARTICLES_TO_PROCESS:
            logging.warning(
                f"Article cap reached ({MAX_ARTICLES_TO_PROCESS}). "
                f"Trimming from {len(unique_articles)} unique DOIs."
            )
            trimmed_items = list(unique_articles.items())[:MAX_ARTICLES_TO_PROCESS]
            unique_articles = dict(trimmed_items)

        print(f"🔄 Found total unique articles: {len(unique_articles)}")

        metadata_start = time.monotonic()
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(process_article, a): a
                for a in unique_articles.values()
            }

            for future in as_completed(future_map):
                if (time.monotonic() - metadata_start) > (MAX_METADATA_RUNTIME_MINUTES * 60):
                    logging.warning(
                        f"Metadata phase runtime exceeded {MAX_METADATA_RUNTIME_MINUTES} minutes. "
                        "Stopping DOI processing early."
                    )
                    for pending in future_map:
                        pending.cancel()
                    break
                rows = future.result()
                if rows:
                    for row in rows:
                        writer.writerow(row)
                        print(f"✅ Saved: {row['doi']} → {row['technology']} (NoM: {row['NoM']}, Total: {row['total_NoM']})")
                else:
                    doi = future_map[future]["doi"]
                    f_skip.write(f"{doi}\tNo matches found\n")

    print(f"📁 Completed. Results in: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
