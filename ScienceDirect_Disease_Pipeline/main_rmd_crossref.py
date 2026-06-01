import logging
import csv
import re
import time
import requests
import os
import json as _json_mod
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from bs4.element import Tag
from concurrent.futures import ThreadPoolExecutor, as_completed
from search_terms import ALL_DISEASE_TERMS as ALL_SEARCH_TERMS, TERM_TO_BASE

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

OUTPUT_FILE = "collected_RMD_CrossRef_NoM.csv"
NOP_OUTPUT_FILE = "collected_RMD_CrossRef_NoP.csv"
SKIPPED_FILE = "skipped_rmd_crossref.txt"
DOIS_FILE = "collected_rmd_crossref_dois.csv"
EXISTING_FILE = "collected_rmd_dois.csv"
MAX_WORKERS = 8
MAX_QUERY_RUNTIME_MINUTES = 180
MAX_METADATA_RUNTIME_MINUTES = 240
MAX_ARTICLES_TO_PROCESS = 20000
ENABLE_HTML_SCRAPE_FALLBACK = os.getenv("RMD_CROSSREF_SCRAPE_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "y"}
COLLECTION_START = datetime(2004, 1, 1)
COLLECTION_END = datetime(2026, 2, 28)

logging.basicConfig(filename="rmd_crossref_log.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# ==== LLM NoP extraction (inline from abstracts) ====
_DC_CONFIG = Path(__file__).resolve().parent.parent / "data_collection_config.json"
_GEMINI_URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

def _load_llm_keys():
    try:
        with open(_DC_CONFIG, encoding="utf-8") as f:
            cfg = _json_mod.load(f)
        return cfg.get("api_keys", {}).get("google_api_key", "").strip()
    except Exception:
        return ""

_GEMINI_KEY = _load_llm_keys()
_NOP_DOI_CACHE: dict = {}

_NOP_SYSTEM = """\
You are a strict epidemiological data extraction assistant.
Extract ONLY real-world patient counts — actual documented cases of people diagnosed with,
living with, affected by, died from, or treated for a rare mental disorder, as recorded
in clinical practice, patient registries, or real-world observational studies.

ACCEPT a count when the abstract contains ANY of these phrases:
  • "X patients were diagnosed with [condition]"
  • "X cases of [condition] were reported / identified / recorded"
  • "registry of X patients with [condition]"
  • "X individuals living with / affected by [condition]"
  • "X people received a diagnosis of [condition]"
  • "X patients treated for [condition]"
  • "X patients died from / died of / death due to [condition]"
  • "X deaths from / mortality from [condition]"
  • "X individuals suffered from [condition]"
  • "X people were affected by [condition]"
  • "X patients presented with [condition]"
  • "X cases identified / confirmed [condition]"

YEAR RULE — a year (YYYY) MUST appear somewhere in the abstract (it does NOT need to be
adjacent to the count phrase). If NO year appears anywhere -> return count=null.
If a month is also present anywhere (MM, Mon, or month name) use it; otherwise default to null.

REJECT — return count=null for:
  • Prospective trial/RCT enrollment ("we recruited/enrolled X patients for this study/trial")
  • Statistical rates or estimates (X per 100,000; X%; incidence of X)
  • Modelled, projected, or hypothetical counts
  • No year (YYYY) found anywhere in the abstract
  • Year found but falls outside Jan 2004 – Feb 2026

NOTE: ACCEPT retrospective counts — "X patients were identified/found/recorded/diagnosed
in hospital records/registry/cohort" — these are real-world patient counts.\
"""

_NOP_USER_TPL = """\
Abstract: {abstract}
Entities mentioned: {entities}

Step 1 — Find ONE real-world patient count in the abstract using any ACCEPT phrase above.
Step 2 — Scan the ENTIRE abstract for any year (YYYY) and optional month. The year does NOT \
need to be next to the count; use the most contextually relevant year found anywhere.
Step 3 — If no year exists anywhere in the abstract, set count=null.

Return ONLY valid JSON (no markdown fences):
{{"entity": "<entity from the list this count refers to, or 'general'>", \
"count": <integer — real patients only, or null if none found or no year in abstract>, \
"year": <4-digit year found anywhere in abstract, or null if absent>, \
"month": <1-12 if any month is mentioned anywhere in abstract, or null>, \
"unit": "patients", \
"notes": "<quote the patient count phrase; append the year/month found>"}}"""

def _llm_extract_nop(abstract: str, entities: list, doi: str) -> dict | None:
    """Extract NoP from a CrossRef article abstract using Gemini (no web search)."""
    if not entities or not abstract:
        return None
    if doi and doi in _NOP_DOI_CACHE:
        return _NOP_DOI_CACHE.get(doi)
    if not _GEMINI_KEY:
        logging.warning("google_api_key missing — NoP extraction skipped")
        return None

    entity_list = ", ".join(entities[:10])
    full_prompt = f"{_NOP_SYSTEM}\n\n{_NOP_USER_TPL.format(abstract=abstract[:2000], entities=entity_list)}"

    result = None
    for attempt in range(3):
        try:
            url = _GEMINI_URL_TPL.format(key=_GEMINI_KEY)
            body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 300,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            resp = requests.post(url, json=body, timeout=30)
            resp.raise_for_status()
            parts = resp.json()["candidates"][0]["content"]["parts"]
            text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
            text = "\n".join(text_parts).strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = _json_mod.loads(text)
            break
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            logging.warning(f"CrossRef Gemini NoP HTTP {code} for {doi}: {exc}")
            if code in {429, 503} and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            break
        except Exception as e:
            logging.warning(f"CrossRef Gemini NoP failed for {doi}: {e}")
            break

    if result and result.get("count") is None:
        result = None
    if doi:
        _NOP_DOI_CACHE[doi] = result
    return result

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

def query_crossref(term, year, rows=25):
    params = {
        "query.bibliographic": term,
        "filter": f"from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
        "rows": rows
    }
    try:
        print(f"🌐 CrossRef Query: {term} ({year})")
        response = requests.get("https://api.crossref.org/works", params=params, timeout=15)
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
                results.append({"doi": doi, "disease": term, "date": date, "country": country})
            return results
        else:
            logging.warning(f"CrossRef failed: {response.status_code}")
    except Exception as e:
        logging.error(f"CrossRef error: {e}")
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

def fetch_crossref_metadata(doi):
    try:
        url = f"https://api.crossref.org/works/{doi}"
        res = requests.get(url, timeout=20)
        if res.status_code == 200:
            item = res.json().get("message", {})
            title = normalize_text(" ".join(item.get("title", [])))
            abstract = normalize_text(item.get("abstract", ""))
            keywords = normalize_text(" ".join(item.get("subject", [])))
            pub_date = item.get("published-print", item.get("issued", {})).get("date-parts", [[]])[0]
            date = "-".join(map(str, pub_date)) if pub_date else ""

            # Optional scraping fallback can be enabled explicitly; disabled by default for resilience.
            if ENABLE_HTML_SCRAPE_FALLBACK and (not abstract or not keywords):
                try:
                    html_url = f"https://doi.org/{doi}"
                    page = requests.get(html_url, timeout=20)
                    soup = BeautifulSoup(page.text, 'html.parser')

                    if not abstract:
                        abs_tag = soup.find('meta', {'name': 'dc.Description'}) or soup.find('meta', {'name': 'description'})
                        if isinstance(abs_tag, Tag) and abs_tag.get('content'):
                            abstract = normalize_text(abs_tag['content'])

                    if not keywords:
                        kw_tag = soup.find('meta', {'name': 'keywords'})
                        if isinstance(kw_tag, Tag) and kw_tag.get('content'):
                            keywords = normalize_text(kw_tag['content'])
                except Exception as e:
                    logging.warning(f"⚠️ Scraping failed for DOI {doi}: {e}")

            return {
                "doi": doi,
                "date": date,
                "title": title,
                "abstract": abstract,
                "keywords": keywords,
                "full_text": ""
            }
    except Exception as e:
        logging.warning(f"⚠️ Metadata fetch failed for DOI {doi}: {e}")
    return {"doi": doi, "date": "", "title": "", "abstract": "", "keywords": "", "full_text": ""}

def process_article(article):
    doi = article["doi"]
    meta = fetch_crossref_metadata(doi)
    all_text = f"{meta['title']} {meta['abstract']} {meta['keywords']} {meta['full_text']}"
    mention_counts = count_mentions_by_term(all_text, ALL_SEARCH_TERMS)

    total_mentions = sum(mention_counts.values())
    country = article.get("country", "UN")

    nom_rows = []
    nop_rows = []

    if not is_within_collection_window(meta["date"]):
        return nom_rows, nop_rows

    for disease, count in mention_counts.items():
        nom_rows.append({
            "date": meta["date"],
            "NoM": count,
            "total_NoM": total_mentions,
            "disease": f"{disease}_{country}",
            "doi": meta["doi"]
        })

    # LLM NoP extraction from abstract
    if mention_counts and meta["abstract"]:
        nop_result = None  # NoP collected separately via nop_llm_collect.py
        if nop_result:
            try:
                nop_count = float(nop_result["count"]) if nop_result.get("count") is not None else None
                nop_year  = int(nop_result["year"])  if nop_result.get("year")  is not None else None
                nop_month = int(nop_result["month"]) if nop_result.get("month") is not None else 1
                if nop_count is not None and nop_count > 0 and nop_year is not None:
                    nop_date = f"{nop_month:02d}-{nop_year}"
                    if is_within_collection_window(nop_date):
                        entity = nop_result.get("entity", "general")
                        target = entity if entity in mention_counts else list(mention_counts.keys())[0]
                        nop_rows.append({
                            "date": nop_date,
                            "NoP": nop_count,
                            "disease": f"{target}_{country}",
                            "unit": nop_result.get("unit", "patients"),
                            "notes": nop_result.get("notes", ""),
                            "doi": meta["doi"]
                        })
            except (TypeError, ValueError):
                pass

    return nom_rows, nop_rows

def main():
    query_start = time.monotonic()

    with open(OUTPUT_FILE, "w", newline='', encoding="utf-8") as f_out, \
         open(NOP_OUTPUT_FILE, "w", newline='', encoding="utf-8") as f_nop, \
         open(SKIPPED_FILE, "w", encoding="utf-8") as f_skip, \
         open(DOIS_FILE, "w", newline='', encoding="utf-8") as f_dois:

        writer = csv.DictWriter(f_out, fieldnames=["date", "NoM", "total_NoM", "disease", "doi"])
        writer.writeheader()
        writer_nop = csv.DictWriter(f_nop, fieldnames=["date", "NoP", "disease", "unit", "notes", "doi"])
        writer_nop.writeheader()
        writer_dois = csv.DictWriter(f_dois, fieldnames=["doi", "disease", "date"])
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
                    writer_dois.writerow({"doi": entry["doi"], "disease": entry["disease"], "date": entry["date"]})

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
                nom_rows, nop_rows = future.result()
                if nom_rows:
                    for row in nom_rows:
                        writer.writerow(row)
                        print(f"✅ Saved: {row['doi']} → {row['disease']} (NoM: {row['NoM']}, Total: {row['total_NoM']})")
                    for row in nop_rows:
                        writer_nop.writerow(row)
                        print(f"  [NoP] {row['doi']} → {row['disease']} count={row['NoP']}")
                else:
                    doi = future_map[future]["doi"]
                    f_skip.write(f"{doi}\tNo matches found\n")

    print(f"📁 Completed. Results in: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
