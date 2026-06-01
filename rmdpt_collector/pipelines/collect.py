import os, logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import time
from collections import defaultdict

from common import utils, matcher
from common.writer import CSVWriter

from sources import openalex, clinical_trials


# Canonical terms only: use keys (no synonyms) from uploaded search_terms.py
# This file is user-provided and kept as the source of truth.
from search_terms import DISEASE_SYNONYMS, PT_SYNONYMS  # (dicts)

logging.basicConfig(
    level=getattr(logging, str(utils.LOG_LEVEL).upper(), logging.INFO),
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("collection.log", mode="w", encoding="utf-8")]
)

TARGET_MONTHS = tuple(f"{y:04d}-{m:02d}" for y in range(utils.START_YEAR, utils.END_YEAR+1) for m in range(1,13))

# Toggle counting behavior: document-level counts (more stable) vs raw mention sums
USE_DOC_COUNTS = True        # if True, each document contributes 1 when it contains >=1 match
MENTION_CAP    = 3           # if USE_DOC_COUNTS is False, cap per-document NoM at this value

def _ingest_count(term: str, recs: list[dict], source_name: str, title_only: bool = False) -> list[dict]:
    """
    Normalize text, count NoM (whole-word, unicode-aware), drop NoM<=0,
    and dedup within-source by (date, doi_or_titlehash).
    """
    """
    Normalize text, count NoM across {canonical + synonyms} (unicode-aware, overlap-safe),
    month-normalize the date, drop NoM<=0, and dedup within-source by (date, doi_or_titlehash).
    """
    def _build_text(r: dict, title_only: bool) -> str:
        # Prefer title for news-like sources but include snippet/description if present.
        if title_only:
            parts = [r.get("title"), r.get("snippet"), r.get("description")]
        else:
            parts = [r.get("title"), r.get("abstract"), r.get("text"), r.get("body"), r.get("description"), r.get("snippet")]
        return " ".join([p for p in parts if p])[:200000]

    seen = set()
    out  = []
    # synonyms for this canonical term
    syns = DISEASE_SYNONYMS.get(term) or PT_SYNONYMS.get(term) or []
    for r in recs:
        # Normalize month
        date = utils.parse_month(r.get("date")) or utils.parse_month(r.get("published")) or utils.parse_month(r.get("pub_date"))
        if not date:
            continue
        title = r.get("title") or ""
        text  = _build_text(r, title_only=title_only)
        doi  = utils.normalize_doi(r.get("doi"))
        key  = (date, doi or utils.collapse_title(title))
        if key in seen:
            continue
        seen.add(key)
        # concept-level counting with synonyms, avoiding overlap double-counts
        nom = matcher.count_concept(term, syns, text)
        if nom <= 0:
            continue

        # Weighting: either count documents (1 per doc with >=1 match) or cap mentions per doc
        if USE_DOC_COUNTS:
            weight = 1
        else:
            try:
                weight = min(int(nom), int(MENTION_CAP))
            except Exception:
                weight = min(nom, MENTION_CAP)

        out.append({"date": date, "term": term, "NoM": weight, "doi": doi})
    return out

def _dedup_merge(precedence_buckets: list[tuple[str,list[dict]]]) -> list[dict]:
    """
    Deduplicate across sources with precedence. 
    Key: (date, term, doi_or_titlehash).
    """
    seen, merged = set(), []
    for _, bucket in precedence_buckets:
        for r in bucket:
            doi = r.get("doi")
            title = r.get("title", "")
            key = (r["date"], r["term"], doi or utils.collapse_title(title))
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    return merged

def _coverage_months(items: list[dict]) -> set[str]:
    return {it["date"] for it in items}



def _fetch_all_for_term(term: str):
    # 1) Primary OpenAlex (cached)
    oa_raw = openalex.fetch_openalex(term)
    oa     = _ingest_count(term, oa_raw, "OpenAlex", title_only=False)
    covered = _coverage_months(oa)
    logging.info(f"[{term}] OpenAlex items={len(oa)} covered_months={len(covered)}")

    # 2) Additional local source: ClinicalTrials
    ct = []
    try:
        ct = _ingest_count(term, clinical_trials.fetch_clinical_trials(term), "ClinicalTrials")
    except Exception as e:
        logging.error(f"[{term}] ClinicalTrials error: {e}")

    # 3) Merge with precedence: OpenAlex first, then ClinicalTrials, then Filings
    buckets = [
        ("OpenAlex", oa),
        ("ClinicalTrials", ct),
    ]
    merged = _dedup_merge(buckets)
    return merged

def main():
    terms = list(DISEASE_SYNONYMS.keys()) + list(PT_SYNONYMS.keys())
    os.makedirs(utils.OUTPUT_DIR, exist_ok=True)
    out_csv = os.path.join(utils.OUTPUT_DIR, "rmdpt_timeseries.csv")
    csv = CSVWriter(out_csv, header=["date", "term", "NoM", "doi"])
    # optional audit file with source attribution (non-breaking)
    out_csv_attr = os.path.join(utils.OUTPUT_DIR, "rmdpt_timeseries_attributed.csv")
    csv_attr = CSVWriter(out_csv_attr, header=["date", "term", "NoM", "doi"])

    # Market outputs removed from main; collector focuses on core sources only.

    # Time-boxed executor loop to remain responsive and cancellable.
    FUTURE_TIMEOUT_S = 10.0       # how long as_completed waits before we re-check
    TASK_HARD_DEADLINE = 180.0    # per-task hard walltime (seconds)

    logging.info(f"Processing {len(terms)} canonical terms (2004-01..{utils.END_YEAR}-12)")
    with ThreadPoolExecutor(max_workers=utils.MAX_WORKERS) as ex:
        # submit all terms (we keep mapping for bookkeeping)
        inflight = {}
        it = iter(terms)
        # prime queue with a small burst
        for _ in range(min(utils.MAX_WORKERS * 2, len(terms))):
            try:
                t = next(it)
            except StopIteration:
                break
            fut = ex.submit(_fetch_all_for_term, t)
            inflight[fut] = (time.time(), t)

        done_ct = 0
        try:
            while inflight:
                # iterate over futures that finish within FUTURE_TIMEOUT_S
                try:
                    for f in as_completed(list(inflight.keys()), timeout=FUTURE_TIMEOUT_S):
                        start_ts, term = inflight.pop(f)
                        try:
                            items = f.result()
                            if items is None:
                                items = []
                            # sort for stable output
                            items.sort(key=lambda r: (r["date"], r["term"], -r["NoM"]))
                            csv.write_rows([(r["date"], r["term"], r["NoM"], r.get("doi", "")) for r in items])
                            csv_attr.write_rows([(r["date"], r["term"], r["NoM"], r.get("doi", "")) for r in items])
                            got = _coverage_months(items)
                            missing = [m for m in TARGET_MONTHS if m not in got]
                            logging.info(f"[{term}] written={len(items)} months_covered={len(got)} missing={len(missing)}")
                        except Exception as e:
                            logging.error(f"[{term}] crashed: {e}")
                        done_ct += 1

                        # top up queue with next term, if any
                        try:
                            t = next(it)
                            fut = ex.submit(_fetch_all_for_term, t)
                            inflight[fut] = (time.time(), t)
                        except StopIteration:
                            pass

                    # enforce hard deadlines on straggling tasks
                    now = time.time()
                    for fut, (st, t) in list(inflight.items()):
                        if now - st > TASK_HARD_DEADLINE:
                            cancelled = fut.cancel()
                            logging.warning(f"[CANCEL] {t} exceeded {TASK_HARD_DEADLINE}s (cancelled={cancelled})")
                            inflight.pop(fut, None)

                except TimeoutError:
                    # no completed futures in this window; loop back to re-check deadlines/top-ups
                    continue
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt received — attempting graceful shutdown...")
            # best-effort immediate flush of current writers (they're flushed on write)
            raise

    csv.close()
    csv_attr.close()
    logging.info(f"ALL DONE -> {out_csv}")

if __name__ == "__main__":
    main()
