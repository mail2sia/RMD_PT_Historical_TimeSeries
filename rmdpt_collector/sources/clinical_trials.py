"""ClinicalTrials.gov v2 JSON-backed source for the collector.

This module queries the v2 endpoint and returns records compatible with the pipeline.
Counting (NoM) should be done by the pipeline's matcher on the returned `text` field;
we provide `text` built from the flattened whole record to meet the "whole-site text" requirement.
"""
from __future__ import annotations
import logging, time
from typing import Any, Dict, List, Optional
import requests
from common import utils

log = logging.getLogger("ClinicalTrialsV2")
BASE_SEARCH = "https://clinicaltrials.gov/api/v2/studies"
METADATA_CACHE_SOURCE = "clinicaltrials_meta"
METADATA_CACHE_TERM = "metadata"
_METADATA: dict | None = None


def _http_get_json(url: str, params: Dict[str, Any] | None = None, retries: int = 4, backoff: float = 1.5) -> Optional[Dict[str, Any]]:
    for attempt in range(retries):
        try:
            hdrs = {"Accept": "application/json"}
            resp = requests.get(url, params=params, headers=hdrs, timeout=30)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if resp.ok and "application/json" in ctype:
                return resp.json()
            log.warning("ClinicalTrialsV2 unexpected response (%s): %s", ctype or resp.status_code, resp.text[:200])
        except Exception as e:
            log.warning("ClinicalTrialsV2 fetch error: %s", e)
        time.sleep(backoff ** attempt)
    return None


def _flatten_strings(obj: Any, out: List[str], max_len: int = 512, max_total: int = 2_000_000) -> None:
    """Recursively collect short string fragments from an object.

    Stops when total collected chars exceed max_total to avoid memory blowups.
    """
    if len("".join(out)) > max_total:
        return
    if obj is None:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if s:
            out.append(s[:max_len])
        return
    if isinstance(obj, (int, float, bool)):
        out.append(str(obj))
        return
    if isinstance(obj, list):
        for it in obj:
            _flatten_strings(it, out, max_len, max_total)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_strings(v, out, max_len, max_total)
        return


def _compose_whole_record_text(study: Dict[str, Any]) -> str:
    # If metadata is available, prefer extracting listed metadata fields (less noise)
    global _METADATA
    parts: List[str] = []
    try:
        if _METADATA is None:
            # attempt to fetch metadata from API (no persistent cache here)
            md = _http_get_json(f"{BASE_SEARCH}/metadata")
            if md:
                _METADATA = md
        fields = []
        if isinstance(_METADATA, dict):
            # metadata may include a 'fields' list; each field can have a 'path' or 'id'
            for f in (_METADATA.get("fields") or []):
                p = None
                if isinstance(f, dict):
                    p = f.get("path") or f.get("id")
                elif isinstance(f, str):
                    p = f
                if p:
                    fields.append(p)
        # helper to deep-get by dot-path
        def _deep_path_get(obj: Any, path: str):
            cur = obj
            for seg in path.split("."):
                if cur is None:
                    return None
                if isinstance(cur, dict) and seg in cur:
                    cur = cur[seg]
                else:
                    return None
            return cur

        if fields:
            for p in fields:
                val = _deep_path_get(study, p)
                if val is None:
                    continue
                # collect strings safely
                _flatten_strings(val, parts)
            if parts:
                return utils.normalize_text_utf8_lower(" ".join(parts))
    except Exception:
        # fallback to full recursive flattening on any error
        pass
    _flatten_strings(study, parts)
    return utils.normalize_text_utf8_lower(" ".join(parts))


def _enrich_study_detail_if_needed(study: Dict[str, Any]) -> Dict[str, Any]:
    """If key fields (nctId or dates) are missing, try fetching full study detail via /studies/{nctId}.

    Returns the (possibly enriched) study dict.
    """
    try:
        nct = _pick_nct_id(study)
        # if no nct or the record already contains rich protocolSection, skip
        if not nct:
            return study
        sec = study.get("protocolSection") or {}
        status = (sec.get("statusModule") or {})
        # if structured dates missing, fetch detail
        has_date = False
        for key in ("startDateStruct", "primaryCompletionDateStruct", "completionDateStruct", "startDate", "primaryCompletionDate", "completionDate"):
            if status.get(key):
                has_date = True; break
        if has_date:
            return study
        # fetch detail
        detail = _http_get_json(f"{BASE_SEARCH}/{nct}")
        if detail and isinstance(detail, dict):
            # the detail payload may include protocolSection at top-level or under 'protocolSection'
            # prefer the detailed protocolSection if present
            if detail.get("protocolSection"):
                return detail
            # sometimes the API wraps study object under 'study' or similar; attempt to find studies
            studies_list = detail.get("studies")
            if isinstance(studies_list, list) and studies_list:
                return studies_list[0]
        return study
    except Exception:
        return study


def _pick_year_month_from_study(study: Dict[str, Any]) -> Optional[str]:
    # Prefer structured dates in protocolSection.statusModule. For year-only strings,
    # map them to mid-year (June) to avoid piling everything on January.
    try:
        sec = study.get("protocolSection", {})
        status = sec.get("statusModule", {})

        # try structured date objects first (they may include 'date' or 'dateTime')
        for path in ("startDateStruct", "primaryCompletionDateStruct", "completionDateStruct"):
            d = status.get(path, {})
            if isinstance(d, dict):
                val = d.get("date") or d.get("dateTime")
                if val:
                    m = utils.parse_month(date_str=val)
                    if m:
                        return m

        # fallbacks: flat startDate / primaryCompletionDate / completionDate
        for key in ("startDate", "primaryCompletionDate", "completionDate"):
            v = status.get(key)
            if not v:
                continue
            # try parsing full date (may include month/day)
            m = utils.parse_month(date_str=v)
            if m:
                return m
            # if parse failed but a 4-digit year is present, map to mid-year
            try:
                y = int(str(v).strip()[:4])
                return utils.parse_month(year=y, month=6)
            except Exception:
                pass
    except Exception:
        pass
    return None


def _pick_nct_id(study: Dict[str, Any]) -> str:
    try:
        sec = study.get("protocolSection", {})
        ident = sec.get("identificationModule", {})
        nct = ident.get("nctId")
        if isinstance(nct, list):
            return nct[0] if nct else ""
        return str(nct or "")
    except Exception:
        return ""


def _extract_start_end_dates(study: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return (start_raw, end_raw, start_month, end_month).

    Tries structured fields first then flat fields.
    """
    try:
        sec = study.get("protocolSection") or {}
        status = sec.get("statusModule") or {}
        # start
        start_raw = None
        for k in ("startDateStruct", "startDate"):
            v = status.get(k)
            if isinstance(v, dict):
                start_raw = v.get("date") or v.get("dateTime") or None
            elif v:
                start_raw = v
            if start_raw:
                break
        # end (primaryCompletionDate preferred)
        end_raw = None
        for k in ("primaryCompletionDateStruct", "completionDateStruct", "primaryCompletionDate", "completionDate"):
            v = status.get(k)
            if isinstance(v, dict):
                end_raw = v.get("date") or v.get("dateTime") or None
            elif v:
                end_raw = v
            if end_raw:
                break
        start_month = utils.parse_month(date_str=start_raw) if start_raw else None
        end_month = utils.parse_month(date_str=end_raw) if end_raw else None
        return start_raw, end_raw, start_month, end_month
    except Exception:
        return None, None, None, None


def _search_v2_all(term: str, page_size: int = 100, max_pages: int = 200) -> List[Dict[str, Any]]:
    """Run a cursor-based search over the v2 JSON API, returning list of study JSON objects."""
    out: List[Dict[str, Any]] = []
    params = {"query.term": term, "pageSize": page_size, "countTotal": "true"}
    url = BASE_SEARCH
    for _ in range(max_pages):
        data = _http_get_json(url, params=params)
        if not data:
            break
        studies = data.get("studies") or []
        if not studies:
            break
        out.extend(studies)
        next_url = data.get("nextPageUrl")
        next_token = data.get("nextPageToken")
        if next_url:
            url = next_url
            params = {}
        elif next_token:
            params["pageToken"] = next_token
        else:
            break
        time.sleep(0.3)
    return out


def fetch_clinical_trials(term: str) -> List[Dict[str, Any]]:
    """Fetch studies matching `term` and return pipeline-compatible rows.

    Each returned dict contains: date (YYYY-MM), title, abstract, text (whole-record), doi (nct id or url)
    """
    cached = utils.cache_load("clinicaltrials", term)
    if cached is not None:
        return cached
    rows: List[Dict[str, Any]] = []
    studies = _search_v2_all(term)
    log.info("[ClinicalTrialsV2] %s studies=%d", term, len(studies))
    for st in studies:
        # try to enrich with per-record detail if key fields are missing
        st = _enrich_study_detail_if_needed(st)
        # Extract publication month
        ym = _pick_year_month_from_study(st)
        if not ym:
            continue
        # enforce global START_YEAR..END_YEAR window
        try:
            year = int(str(ym).split("-")[0])
        except Exception:
            continue
        if year < utils.START_YEAR or year > utils.END_YEAR:
            continue

        # Build whole-record text for robust NoM counting
        full_text = _compose_whole_record_text(st)
        # Ensure term appears somewhere — pipeline will re-count with whole-word matcher
        if term.lower() not in (full_text or ""):
            continue

        # Extract title / brief summary for nicer records
        sec = st.get("protocolSection", {})
        ident = sec.get("identificationModule", {})
        desc = sec.get("descriptionModule", {})
        title = "".join(ident.get("briefTitle") if ident.get("briefTitle") else []) if isinstance(ident.get("briefTitle"), list) else (ident.get("briefTitle") or "")
        if not title:
            # fallback: other identification fields
            title = str(ident.get("officialTitle") or "")
        # brief summary
        brief = desc.get("briefSummary")
        if isinstance(brief, dict):
            # some responses include {'textBlock': '...'}
            brief_text = brief.get("briefSummary") or brief.get("textBlock") or ""
        else:
            brief_text = brief or ""

        nct = _pick_nct_id(st)
        doi = nct or ""
        start_raw, end_raw, start_month, end_month = _extract_start_end_dates(st)

        rows.append({
            "date": ym,
            "title": (title or "").strip(),
            "abstract": (brief_text or "").strip(),
            "text": f"{title} {brief_text} {full_text}".strip(),
            "doi": doi or None,
            "start_raw": start_raw,
            "end_raw": end_raw,
            "start_month": start_month,
            "end_month": end_month,
        })

    utils.cache_save("clinicaltrials", term, rows)
    return rows
