import logging, xml.etree.ElementTree as ET, re
import importlib.util
import json as _json_mod
import requests as _requests_mod
from pathlib import Path
from ..common import utils

# ==== LLM NoP extraction (inline from abstracts) ====
_DC_CONFIG = Path(__file__).resolve().parent.parent.parent.parent / "data_collection_config.json"
_GEMINI_URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"

def _load_llm_keys_pubmed():
    try:
        with open(_DC_CONFIG, encoding="utf-8") as f:
            cfg = _json_mod.load(f)
        keys = cfg.get("api_keys", {})
        return keys.get("google_api_key", "").strip()
    except Exception:
        return ""

_PM_GEMINI_KEY = _load_llm_keys_pubmed()

_PM_NOP_SYSTEM = """\
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

_PM_NOP_USER_TPL = """\
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

_PM_NOP_CACHE: dict = {}

def _pubmed_llm_extract_nop(abstract: str, entities: list, doi: str) -> dict | None:
    """Extract NoP from a PubMed article abstract using Gemini (no web search)."""
    if not abstract or not entities:
        return None
    cache_key = doi or abstract[:50]
    if cache_key in _PM_NOP_CACHE:
        return _PM_NOP_CACHE.get(cache_key)
    if not _PM_GEMINI_KEY:
        logging.warning("google_api_key missing — PubMed NoP extraction skipped")
        return None

    prompt = _PM_NOP_USER_TPL.format(abstract=abstract[:2000], entities=", ".join(entities[:10]))
    full_prompt = f"{_PM_NOP_SYSTEM}\n\n{prompt}"
    result = None
    import time as _time
    for attempt in range(3):
        try:
            url = _GEMINI_URL_TPL.format(key=_PM_GEMINI_KEY)
            body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "maxOutputTokens": 300,
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            resp = _requests_mod.post(url, json=body, timeout=30)
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
        except _requests_mod.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            logging.warning(f"PubMed Gemini NoP HTTP {code} for {doi}: {exc}")
            if code in {429, 503} and attempt < 2:
                _time.sleep(30 * (attempt + 1))
                continue
            break
        except Exception as e:
            logging.warning(f"PubMed Gemini NoP failed for {doi}: {e}")
            break

    if result and result.get("count") is None:
        result = None
    _PM_NOP_CACHE[cache_key] = result
    return result

# Load search terms for NoM counting without static imports (avoids Pylance missing-import warnings)
def _load_terms_module(module_path: Path, module_name: str):
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    return None

disease_dir = Path(__file__).parent.parent.parent.parent / "ScienceDirect_Disease_Pipeline"
pt_dir = Path(__file__).parent.parent.parent.parent / "ScienceDirect_PT_Pipeline"

disease_mod = _load_terms_module(disease_dir / "search_terms.py", "rmd_terms")
pt_mod = _load_terms_module(pt_dir / "search_terms_pt.py", "pt_terms")

ALL_DISEASE_TERMS = getattr(disease_mod, "ALL_DISEASE_TERMS", []) if disease_mod else []
DISEASE_TERM_TO_BASE = getattr(disease_mod, "TERM_TO_BASE", {}) if disease_mod else {}

ALL_PT_TERMS = getattr(pt_mod, "ALL_PT_TERMS", []) if pt_mod else []
PT_TERM_TO_BASE = getattr(pt_mod, "TERM_TO_BASE", {}) if pt_mod else {}

SEARCH_TERMS_AVAILABLE = bool(ALL_DISEASE_TERMS or ALL_PT_TERMS)
if not SEARCH_TERMS_AVAILABLE:
    logging.warning("Search terms not available for NoM counting")

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
NCBI_API_KEY = utils.cfg_get("NCBI_API_KEY", default=None)

# Country code mapping (ISO and auto-generated codes)
COUNTRY_CODES = {
    "united states": "US", "usa": "US", "u.s.": "US", "u.s.a": "US",
    "china": "CN", "chinese": "CN",
    "japan": "JP", "japanese": "JP",
    "germany": "DE", "german": "DE",
    "france": "FR", "french": "FR",
    "united kingdom": "UK", "britain": "UK", "british": "UK", "england": "UK",
    "canada": "CA", "canadian": "CA",
    "australia": "AU", "australian": "AU",
    "india": "IN", "indian": "IN",
    "brazil": "BR", "brazilian": "BR",
    "mexico": "MX", "mexican": "MX",
    "south korea": "KR", "korea": "KR",
    "russia": "RU", "russian": "RU",
    "italy": "IT", "italian": "IT",
    "spain": "ES", "spanish": "ES",
    "netherlands": "NL", "dutch": "NL",
    "switzerland": "CH", "swiss": "CH",
    "sweden": "SE", "swedish": "SE",
    "norway": "NO", "norwegian": "NO",
    "denmark": "DK", "danish": "DK",
    "finland": "FI", "finnish": "FI",
    "israel": "IL", "israeli": "IL",
    "singapore": "SG", "singaporean": "SG",
    "thailand": "TH", "thai": "TH",
    "indonesia": "ID", "indonesian": "ID",
    "philippines": "PH", "philippine": "PH",
    "vietnam": "VI", "vietnamese": "VI",
    "argentina": "AR", "argentinian": "AR",
    "chile": "CL", "chilean": "CL",
    "colombia": "CO", "colombian": "CO",
    "peru": "PE", "peruvian": "PE",
    "egypt": "EG", "egyptian": "EG",
    "south africa": "ZA", "south african": "ZA",
    "nigeria": "NG", "nigerian": "NG",
    "kenya": "KE", "kenyan": "KE",
    "turkey": "TR", "turkish": "TR",
    "iran": "IR", "iranian": "IR",
    "saudi arabia": "SA", "saudi": "SA",
    "belgium": "BE", "belgian": "BE",
    "austria": "AT", "austrian": "AT",
    "portugal": "PT", "portuguese": "PT",
    "greece": "GR", "greek": "GR",
    "poland": "PL", "polish": "PL",
    "czech": "CZ", "czechoslovakia": "CZ",
    "hungary": "HU", "hungarian": "HU",
    "romania": "RO", "romanian": "RO",
    "bulgaria": "BG", "bulgarian": "BG",
    "ukraine": "UA", "ukrainian": "UA",
    "new zealand": "NZ", "new zealander": "NZ",
    "ireland": "IE", "irish": "IE",
    "pakistan": "PK", "pakistani": "PK",
    "bangladesh": "BD", "bangladeshi": "BD",
    "thailand": "TH", "thai": "TH",
    "malaysia": "MY", "malaysian": "MY",
}

def extract_country_code(affiliation_text: str) -> str:
    """Extract country code from affiliation text."""
    if not affiliation_text:
        return "UN"
    
    affiliation_lower = affiliation_text.lower()
    
    # Try exact matches first
    for country, code in COUNTRY_CODES.items():
        if country in affiliation_lower:
            return code
    
    # Try common country name patterns
    patterns = [
        (r'\b(USA|US)\b', 'US'),
        (r'\b(UK|Britain|England)\b', 'UK'),
        (r'\bCanada\b', 'CA'),
        (r'\bAustralia\b', 'AU'),
    ]
    for pattern, code in patterns:
        if re.search(pattern, affiliation_text, re.IGNORECASE):
            return code
    
    return "UN"

def count_mentions(text: str) -> int:
    """Count total mentions of all RMD and PT terms in text."""
    if not SEARCH_TERMS_AVAILABLE or not text:
        return 0
    
    text_lower = text.lower()
    total_mentions = 0
    counted_bases = set()
    
    # Count disease mentions
    for term in ALL_DISEASE_TERMS:
        matches = re.findall(r'\b' + re.escape(term.lower()) + r'\b', text_lower)
        if matches:
            base = DISEASE_TERM_TO_BASE.get(term)
            if base and base not in counted_bases:
                total_mentions += len(matches)
                counted_bases.add(base)
    
    # Count PT mentions
    for term in ALL_PT_TERMS:
        matches = re.findall(r'\b' + re.escape(term.lower()) + r'\b', text_lower)
        if matches:
            base = PT_TERM_TO_BASE.get(term)
            if base and base not in counted_bases:
                total_mentions += len(matches)
                counted_bases.add(base)
    
    return total_mentions

MAX_RESULTS_PER_TERM = 5000

MAX_NOP_CALLS_PER_TERM = 50  # cap Gemini calls per term

# Pre-filter: only call Gemini if abstract likely contains a real patient count
_NOP_PREFILTER = re.compile(
    r'\b(\d[\d,]*)\s*(?:patients?|cases?|individuals?|persons?|people|subjects?|deaths?)'
    r'|(?:patients?|cases?|individuals?|persons?|people|subjects?|deaths?)\s*(?:were|was|have|had|of)\b',
    re.IGNORECASE
)

def _abstract_likely_has_nop(abstract: str) -> bool:
    """Quick regex check before calling Gemini — avoids unnecessary API calls."""
    return bool(_NOP_PREFILTER.search(abstract))

def fetch_pubmed(term: str) -> list[dict]:
    cached = utils.cache_load("pubmed", term)
    if cached is not None: return cached
    out = []
    q = f'"{term}"[Title/Abstract] AND 2004:2026[PDAT]'
    params = {"db":"pubmed","term":q,"usehistory":"y","retmax":0}
    if NCBI_API_KEY: params["api_key"] = NCBI_API_KEY
    sr = utils.http_get(ESEARCH, params=params)
    root = ET.fromstring(sr.text)
    count = int((root.findtext(".//Count") or "0"))
    if count == 0:
        utils.cache_save("pubmed", term, out)
        return out
    if count > MAX_RESULTS_PER_TERM:
        logging.warning(f"[PubMed] Skipping '{term}': {count} results exceeds cap of {MAX_RESULTS_PER_TERM}")
        utils.cache_save("pubmed", term, out)
        return out
    # Re-fetch with usehistory to get QueryKey/WebEnv for batch download
    params["retmax"] = 100000
    sr = utils.http_get(ESEARCH, params=params)
    root = ET.fromstring(sr.text)
    qk = root.findtext(".//QueryKey"); we = root.findtext(".//WebEnv")
    logging.info(f"[PubMed] {term} total={count}")
    bs = 500
    nop_call_count = 0  # track Gemini calls for this term
    for start in range(0, count, bs):
        fp = {"db":"pubmed","retstart":start,"retmax":bs,"query_key":qk,"WebEnv":we,"rettype":"medline","retmode":"xml"}
        if NCBI_API_KEY: fp["api_key"] = NCBI_API_KEY
        fr = utils.http_get(EFETCH, params=fp)
        R = ET.fromstring(fr.text)
        for art in R.findall(".//PubmedArticle"):
            title = art.findtext(".//ArticleTitle") or ""
            abstr_parts = [a.text or "" for a in art.findall(".//AbstractText")]
            abstract = " ".join(abstr_parts).strip()
            # Extract keywords
            keywords_parts = [kw.text or "" for kw in art.findall(".//Keyword")]
            keywords = " ".join(keywords_parts).strip()
            # Extract country from author affiliations - try multiple paths
            country_code = None
            # Try Author/Affiliation path
            for author in art.findall(".//Author"):
                aff_elem = author.find(".//Affiliation")
                if aff_elem is not None and aff_elem.text:
                    country_code = extract_country_code(aff_elem.text)
                    if country_code:
                        break
            # Try AuthorList/Author path
            if not country_code:
                for author in art.findall(".//AuthorList/Author"):
                    aff_elem = author.find(".//Affiliation")
                    if aff_elem is not None and aff_elem.text:
                        country_code = extract_country_code(aff_elem.text)
                        if country_code:
                            break
            # Try article-level affiliation
            if not country_code:
                aff_elem = art.find(".//Affiliation")
                if aff_elem is not None and aff_elem.text:
                    country_code = extract_country_code(aff_elem.text)
            # Try PublicationTypeList or other author elements
            if not country_code:
                for elem in art.findall(".//Affiliation"):
                    if elem.text:
                        country_code = extract_country_code(elem.text)
                        if country_code:
                            break
            
            doi = None
            for idn in art.findall(".//ArticleId"):
                if (idn.get("IdType") or "").lower() == "doi":
                    doi = utils.normalize_doi(idn.text); break
            # dates
            month = None
            ad = art.find(".//ArticleDate")
            if ad is not None:
                month = utils.parse_month(year=ad.findtext("Year"), month=ad.findtext("Month"))
            if not month:
                pub = art.find(".//JournalIssue/PubDate")
                if pub is not None:
                    y = pub.findtext("Year")
                    mt = pub.findtext("Month")
                    mm = _month_to_int(mt)
                    month = utils.parse_month(year=y, month=mm)
            if not month:
                y2 = art.findtext(".//JournalIssue/PubDate/Year")
                if y2: month = utils.parse_month(year=y2, month=1)
            if not month: continue
            # Only search in title, abstract, and keywords (not full text)
            text = f"{title} {abstract} {keywords}".strip()
            nom_count = count_mentions(text)
            # LLM NoP extraction from abstract
            nop_count = None
            nop_date = None
            nop_unit = ""
            nop_entity = ""
            nop_notes = ""
            if abstract and nom_count > 0:
                _matched_terms = []
                for t in ALL_DISEASE_TERMS + ALL_PT_TERMS:
                    if re.search(r'\b' + re.escape(t.lower()) + r'\b', text.lower()):
                        base = DISEASE_TERM_TO_BASE.get(t) or PT_TERM_TO_BASE.get(t)
                        if base and base not in _matched_terms:
                            _matched_terms.append(base)
                if nop_call_count >= MAX_NOP_CALLS_PER_TERM or not _abstract_likely_has_nop(abstract):
                    nop_result = None
                else:
                    import time as _time_mod; _time_mod.sleep(30)  # ~2 RPM Gemini free tier
                    nop_call_count += 1
                    nop_result = _pubmed_llm_extract_nop(abstract, _matched_terms, doi or "")
                if nop_result:
                    try:
                        _c = nop_result.get("count")
                        _y = nop_result.get("year")
                        _m = nop_result.get("month")
                        # Only save when both count AND year are explicitly stated
                        if _c is not None and _y is not None:
                            nop_count  = float(_c)
                            nop_month_val = int(_m) if _m is not None else 1
                            nop_date   = f"{nop_month_val:02d}-{int(_y)}"
                            nop_unit   = nop_result.get("unit", "patients")
                            nop_entity = nop_result.get("entity", "")
                            nop_notes  = nop_result.get("notes", "")
                    except (TypeError, ValueError):
                        nop_count = None
            out.append({"title": title, "abstract": abstract, "keywords": keywords, "doi": doi, "date": month, "country_code": country_code, "total_NoM": nom_count, "nop_count": nop_count, "nop_date": nop_date, "nop_unit": nop_unit, "nop_entity": nop_entity, "nop_notes": nop_notes})
    utils.cache_save("pubmed", term, out)
    return out

def collect(term: str, start: str, end: str, session, cfg, checkpoint: dict) -> list[dict]:
    """Collect data for a term from PubMed."""
    return fetch_pubmed(term)

import calendar
def _month_to_int(s: str | None):
    if not s: return 1
    s = s.strip()
    try: return int(s)
    except: pass
    try: return list(calendar.month_abbr).index(s[:3].title())
    except: return 1
