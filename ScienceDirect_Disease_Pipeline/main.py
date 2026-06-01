import logging
import csv
import re
import time
import requests
import os
import json as _json_mod
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from tqdm import tqdm

from search_terms import ALL_DISEASE_TERMS as ALL_SEARCH_TERMS, TERM_TO_BASE
from config_loader import get_next_api_key

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

# ==== Config ====
OUTPUT_FILE = "collected_Diseases_NoM.csv"
NOP_OUTPUT_FILE = "collected_Diseases_NoP.csv"
SKIPPED_FILE = "skipped_disease_dois.txt"
DOIS_FILE = "collected_disease_dois.csv"
MAX_WORKERS = 16
BATCH_SIZE = 10
INTERMEDIATE_SAVE_INTERVAL = 10
COLLECTION_START = datetime(2004, 1, 1)
COLLECTION_END = datetime(2026, 2, 28)

logging.basicConfig(filename="disease_article_retrieval_log.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# ==== LLM NoP extraction (inline from abstracts) ====
_DC_CONFIG = Path(__file__).resolve().parent.parent / "data_collection_config.json"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_GEMINI_URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

def _load_llm_keys():
    try:
        with open(_DC_CONFIG, encoding="utf-8") as f:
            cfg = _json_mod.load(f)
        keys = cfg.get("api_keys", {})
        return keys.get("openai_api_key", "").strip(), keys.get("google_api_key", "").strip()
    except Exception:
        return "", ""

_OPENAI_KEY, _GEMINI_KEY = _load_llm_keys()

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

_NOP_DOI_CACHE: dict = {}

def _llm_extract_nop(abstract: str, entities: list, doi: str) -> dict | None:
    """Extract NoP from a ScienceDirect article abstract using Gemini (no web search)."""
    if not entities or not abstract:
        return None
    if doi and doi in _NOP_DOI_CACHE:
        return _NOP_DOI_CACHE.get(doi)
    if not _GEMINI_KEY:
        logging.warning("google_api_key missing — NoP extraction skipped")
        return None

    entity_list = ", ".join(entities[:10])
    prompt = _NOP_USER_TPL.format(abstract=abstract[:2000], entities=entity_list)
    full_prompt = f"{_NOP_SYSTEM}\n\n{prompt}"

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
            logging.warning(f"Gemini NoP HTTP {code} for {doi}: {exc}")
            if code in {429, 503} and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            break
        except Exception as e:
            logging.warning(f"Gemini NoP failed for {doi}: {e}")
            break

    if result and result.get("count") is None:
        result = None
    if doi:
        _NOP_DOI_CACHE[doi] = result
    return result

# ==== Precompile regex patterns ====
TERM_TO_REGEX = {term: re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE) for term in ALL_SEARCH_TERMS}

# ==== Helper functions ====
def normalize_text(text):
    return re.sub(r"\s+", " ", text.strip().lower()) if isinstance(text, str) else ""

def normalize_date(date_str):
    if not date_str:
        return ""
    formats = ["%Y-%m-%d", "%Y-%m", "%Y"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%m-%Y")
        except ValueError:
            continue
    try:
        parts = date_str.split("-")
        if len(parts) == 3:
            return f"{parts[1]}-{parts[0]}"
        elif len(parts) == 2:
            return f"{parts[1]}-{parts[0]}"
        elif len(parts) == 1:
            return f"01-{parts[0]}"
    except Exception:
        pass
    return ""


def is_within_collection_window(date_mm_yyyy: str) -> bool:
    """Return True when normalized MM-YYYY date is inside Jan-2004..Feb-2026."""
    if not date_mm_yyyy:
        return False
    try:
        dt = datetime.strptime(date_mm_yyyy, "%m-%Y")
        return COLLECTION_START <= dt <= COLLECTION_END
    except ValueError:
        return False

def fetch_full_text(doi):
    url = f"https://api.elsevier.com/content/article/doi/{doi}"
    headers = {
        "X-ELS-APIKey": get_next_api_key(),
        "Accept": "application/json; charset=utf-8",
        "X-ELS-ResourceVersion": "full-text",
        "User-Agent": "ElsevierDiseaseMiningBot/1.0"
    }
    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code == 200:
            data = res.json().get("full-text-retrieval-response", {})
            core = data.get("coredata", {})
            return {
                "doi": doi,
                "date": normalize_date(core.get("prism:coverDate", "")),
                "title": normalize_text(core.get("dc:title", "")),
                "abstract": normalize_text(core.get("dc:description", "")),
                "keywords": normalize_text(core.get("authkeywords", ""))
            }
    except Exception as e:
        logging.warning(f"⚠️ Fetch failed for DOI {doi}: {e}")
    return {
        "doi": doi,
        "date": "",
        "title": "",
        "abstract": "",
        "keywords": ""
    }

def count_mentions_by_term(text):
    mentions = {}
    if not text:
        return mentions
    for term, regex in TERM_TO_REGEX.items():
        matches = regex.findall(text)
        if matches:
            base = TERM_TO_BASE.get(term)
            if base:
                mentions[base] = mentions.get(base, 0) + len(matches)
    return mentions

def process_article(article):
    doi = article["doi"]
    meta = fetch_full_text(doi)
    all_text = normalize_text(f"{meta['title']} {meta['abstract']} {meta['keywords']}")
    mention_counts = count_mentions_by_term(all_text)

    nom_rows = []
    nop_rows = []
    if not is_within_collection_window(meta["date"]):
        return nom_rows, nop_rows

    country = article.get("country", "UN")
    for disease, count in mention_counts.items():
        disease_with_country = f"{disease}_{country}"
        nom_rows.append({
            "date": meta["date"],
            "NoM": count,
            "disease": disease_with_country,
            "doi": meta["doi"]
        })

    # LLM NoP extraction from abstract
    if mention_counts and meta["abstract"]:
        time.sleep(4)  # ~15 RPM Gemini rate limit
        nop_result = _llm_extract_nop(meta["abstract"], list(mention_counts.keys()), doi)
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

def batch_articles(articles, batch_size):
    for i in range(0, len(articles), batch_size):
        yield articles[i:i + batch_size]

def process_batch(batch):
    results = []
    for article in batch:
        nom_rows, nop_rows = process_article(article)
        results.append((article.get("doi", ""), nom_rows, nop_rows))
    return results


def csv_has_payload(path: str) -> bool:
    """Return True when CSV exists and has at least one non-header data row."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            _ = f.readline()  # header
            for line in f:
                if line.strip():
                    return True
    except Exception:
        return False
    return False

# Country code mapping (ISO + common mappings)
COUNTRY_NAME_TO_CODE = {
    'united states': 'US', 'usa': 'US', 'united states of america': 'US',
    'china': 'CN', 'peoples republic of china': 'CN', 'people\'s republic of china': 'CN',
    'united kingdom': 'UK', 'great britain': 'UK', 'uk': 'UK',
    'germany': 'DE', 'japan': 'JP', 'france': 'FR', 'italy': 'IT', 'spain': 'ES',
    'canada': 'CA', 'australia': 'AU', 'brazil': 'BR', 'russia': 'RU', 'india': 'IN',
    'south korea': 'KR', 'korea': 'KR', 'republic of korea': 'KR',
    'netherlands': 'NL', 'switzerland': 'CH', 'sweden': 'SE', 'belgium': 'BE',
    'austria': 'AT', 'poland': 'PL', 'denmark': 'DK', 'norway': 'NO', 'finland': 'FI',
    'israel': 'IL', 'turkey': 'TR', 'mexico': 'MX', 'argentina': 'AR', 'chile': 'CL',
    'south africa': 'ZA', 'saudi arabia': 'SA', 'egypt': 'EG', 'iran': 'IR',
    'indonesia': 'ID', 'malaysia': 'MY', 'thailand': 'TH', 'singapore': 'SG',
    'philippines': 'PH', 'vietnam': 'VI', 'pakistan': 'PK', 'bangladesh': 'BD',
    'new zealand': 'NZ', 'ireland': 'IE', 'portugal': 'PT', 'greece': 'GR',
    'czech republic': 'CZ', 'hungary': 'HU', 'romania': 'RO', 'colombia': 'CO',
    'peru': 'PE', 'venezuela': 'VE', 'ecuador': 'EC', 'morocco': 'MA', 'algeria': 'DZ',
    'nigeria': 'NG', 'kenya': 'KE', 'ethiopia': 'ET', 'ukraine': 'UA'
}

def extract_country_from_affiliation(affiliation_data):
    """Extract country from Scopus affiliation data"""
    try:
        if isinstance(affiliation_data, dict):
            # Try various country fields
            for field in ['affiliation-country', 'affilcountry', 'country']:
                if field in affiliation_data:
                    country_name = str(affiliation_data[field]).strip().lower()
                    if not country_name or country_name == 'nan':
                        continue
                    # Map country name to code
                    if country_name in COUNTRY_NAME_TO_CODE:
                        return COUNTRY_NAME_TO_CODE[country_name]
                    # If already a 2-letter code
                    if len(country_name) == 2:
                        return country_name.upper()
                    # Try first 2 letters as fallback
                    if len(country_name) > 2:
                        return country_name[:2].upper()
    except Exception as e:
        logging.warning(f"⚠️ Error extracting country: {e}")
    return "UN"  # Unknown only when no metadata available

def search_scopus_articles(year):
    url = "https://api.elsevier.com/content/search/scopus"
    headers_template = {
        "Accept": "application/json; charset=utf-8",
        "User-Agent": "ElsevierDiseaseMiningBot/1.0"
    }

    results = []
    for term in ALL_SEARCH_TERMS:
        query = f'TITLE-ABS-KEY("{term}") AND PUBYEAR = {year}'
        params = {
            "query": query,
            "count": 25,
            "field": "doi,prism:coverDate,affiliation,affiliation.affiliation-country,affiliation.affilcountry"
        }

        headers = headers_template.copy()
        headers["X-ELS-APIKey"] = get_next_api_key()

        try:
            print(f"🔍 Scopus Query: {query}")
            res = requests.get(url, headers=headers, params=params, timeout=20)

            if res.status_code == 200:
                entries = res.json().get("search-results", {}).get("entry", [])
                for e in entries:
                    doi = e.get("prism:doi", "")
                    date = normalize_date(e.get("prism:coverDate", ""))
                    
                    # Extract country from affiliation(s)
                    country = "UN"  # unknown by default
                    
                    # Try affiliation array
                    if "affiliation" in e:
                        affiliations = e["affiliation"]
                        if isinstance(affiliations, list) and len(affiliations) > 0:
                            country = extract_country_from_affiliation(affiliations[0])
                        elif isinstance(affiliations, dict):
                            country = extract_country_from_affiliation(affiliations)
                    
                    if doi:
                        results.append({"doi": doi, "date": date, "country": country})
                time.sleep(0.3)
            else:
                logging.warning(f"❌ Scopus {res.status_code} — {query}")
        except Exception as e:
            logging.error(f"⚠️ Scopus request error for year {year}, term '{term}': {e}")
            time.sleep(5)
    return results

# ==== Main function ====
def main():
    # ── Load already-processed DOIs so re-runs skip them ──────────────────────
    processed_dois: set = set()
    if os.path.exists(DOIS_FILE) and os.path.getsize(DOIS_FILE) > 0:
        try:
            with open(DOIS_FILE, "r", encoding="utf-8") as _f:
                for row in csv.DictReader(_f):
                    if row.get("doi"):
                        processed_dois.add(row["doi"].strip())
            print(f"📋 {len(processed_dois)} DOIs already processed — will skip on this run.")
        except Exception as e:
            logging.warning(f"⚠️ Could not load existing DOIs: {e}")

    # ── Append to existing output files; write fresh only when they don't exist ─
    nom_new  = not (os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0)
    nop_new  = not csv_has_payload(NOP_OUTPUT_FILE)
    dois_new = not (os.path.exists(DOIS_FILE)       and os.path.getsize(DOIS_FILE)       > 0)

    with open(OUTPUT_FILE,     "w" if nom_new  else "a", newline='', encoding="utf-8") as f_out, \
         open(SKIPPED_FILE,    "a",                       encoding="utf-8") as f_skip, \
         open(DOIS_FILE,       "w" if dois_new else "a", newline='', encoding="utf-8") as f_dois, \
         open(NOP_OUTPUT_FILE, "w" if nop_new  else "a", newline='', encoding="utf-8") as f_nop:

        writer = csv.DictWriter(f_out, fieldnames=["date", "NoM", "disease", "doi"])
        if nom_new:
            writer.writeheader()
        writer_dois = csv.DictWriter(f_dois, fieldnames=["doi", "disease", "date"])
        if dois_new:
            writer_dois.writeheader()
        writer_nop = csv.DictWriter(f_nop, fieldnames=["date", "NoP", "disease", "unit", "notes", "doi"])
        if nop_new:
            writer_nop.writeheader()

        all_tasks = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for year in range(2004, 2027):
                future = executor.submit(search_scopus_articles, year)
                all_tasks.append(future)

            articles = []
            for future in all_tasks:
                try:
                    results = future.result(timeout=300)
                except FutureTimeoutError:
                    logging.warning("⚠️ Year search timed out after 300s, skipping year")
                    continue
                except Exception as exc:
                    logging.warning(f"⚠️ Year search failed: {exc}")
                    continue
                if results:
                    for doi_dict in results:
                        articles.append({"doi": doi_dict["doi"], "date": doi_dict["date"], "country": doi_dict.get("country", "UN")})
                        writer_dois.writerow({"doi": doi_dict["doi"], "disease": "unknown", "date": doi_dict["date"]})

        unique_articles = {a["doi"]: a for a in articles if a["doi"]}
        all_scopus_articles = list(unique_articles.values())

        # ── Build article sets by output target ───────────────────────────────
        nom_articles = [a for a in all_scopus_articles if a["doi"] not in processed_dois]
        skipped = len(all_scopus_articles) - len(nom_articles)
        print(f"🔄 {len(nom_articles)} new NoM articles to process ({skipped} already done, skipped).")

        # If NoP is empty but we already have a DOI history, backfill NoP by
        # reprocessing known DOIs instead of skipping all work.
        if nop_new and processed_dois:
            nop_article_map = {doi: {"doi": doi, "date": "", "country": "UN"} for doi in processed_dois}
            for a in all_scopus_articles:
                nop_article_map[a["doi"]] = a
            nop_articles = list(nop_article_map.values())
            print(f"🧩 NoP backfill mode: {len(nop_articles)} DOIs will be reprocessed for patient-count extraction.")
        else:
            nop_articles = nom_articles

        nom_doi_set = {a["doi"] for a in nom_articles}
        nop_doi_set = {a["doi"] for a in nop_articles}
        process_articles = nop_articles

        save_counter = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_batch = {
                executor.submit(process_batch, batch): batch
                for batch in batch_articles(process_articles, batch_size=BATCH_SIZE)
            }

            with tqdm(total=len(future_to_batch), desc="Collecting articles", unit="batch") as pbar:
                for future in as_completed(future_to_batch):
                    try:
                        all_rows = future.result(timeout=120)
                    except FutureTimeoutError:
                        logging.warning("⚠️ Article batch timed out after 120s, skipping batch")
                        pbar.update(1)
                        continue
                    except Exception as exc:
                        logging.warning(f"⚠️ Article batch failed: {exc}")
                        pbar.update(1)
                        continue
                    for article_doi, nom_rows, nop_rows in all_rows:
                        if article_doi in nom_doi_set:
                            if nom_rows:
                                for row in nom_rows:
                                    writer.writerow(row)
                                    print(f"✅ NoM: {row['doi']} → {row['disease']} ({row['NoM']})")
                            else:
                                f_skip.write(f"{article_doi or 'unknown'}\tNo matches found\n")

                        if article_doi in nop_doi_set:
                            for row in nop_rows:
                                writer_nop.writerow(row)
                                print(f"✅ NoP: {row['doi']} → {row['disease']} ({row['NoP']} {row['unit']})")
                    save_counter += 1
                    pbar.update(1)

                    if save_counter % INTERMEDIATE_SAVE_INTERVAL == 0:
                        f_out.flush()
                        f_dois.flush()
                        f_skip.flush()
                        f_nop.flush()
                        print(f"💾 Intermediate save after {save_counter} batches...")

    print(f"📁 Completed. Results in: {OUTPUT_FILE}")

# ==== Entry point ====
if __name__ == "__main__":
    main()
