# rmdpt_collector/pipelines/collect.py
from __future__ import annotations
import argparse, logging, os, pathlib, sys
from pathlib import Path
from typing import Any, Dict, List

# Default config path resolved relative to this file so the script works
# regardless of the current working directory.
_DEFAULT_CONFIG = str(Path(__file__).resolve().parent.parent / "project_config.json")

# Ensure the project root is in the Python path
_collector_root = str(Path(__file__).resolve().parent.parent)
_package_parent = str(Path(__file__).resolve().parent.parent.parent)
_workspace_root = str(Path(__file__).resolve().parent.parent.parent.parent)
for _p in (_collector_root, _package_parent, _workspace_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from ..common.config import load_config, Config
    from ..common.session import Session
    from ..common.utils import (
        build_lexicon, total_nom, norm_text,
        parse_best_date, ym, normalize_doi, title_hash,
        load_json, save_json, write_rows_csv, build_pivot,
        write_audit, dedup_rows, REQUIRED_SCHEMA
    )
    from ..sources import pubmed
except ImportError:
    # Script execution fallback: python pipelines/collect.py
    import importlib

    _config_mod = importlib.import_module("rmdpt_collector.common.config")
    _session_mod = importlib.import_module("rmdpt_collector.common.session")
    _utils_mod = importlib.import_module("rmdpt_collector.common.utils")
    _sources_mod = importlib.import_module("rmdpt_collector.sources")

    load_config = _config_mod.load_config
    Config = _config_mod.Config
    Session = _session_mod.Session

    build_lexicon = _utils_mod.build_lexicon
    total_nom = _utils_mod.total_nom
    norm_text = _utils_mod.norm_text
    parse_best_date = _utils_mod.parse_best_date
    ym = _utils_mod.ym
    normalize_doi = _utils_mod.normalize_doi
    title_hash = _utils_mod.title_hash
    load_json = _utils_mod.load_json
    save_json = _utils_mod.save_json
    write_rows_csv = _utils_mod.write_rows_csv
    build_pivot = _utils_mod.build_pivot
    write_audit = _utils_mod.write_audit
    dedup_rows = _utils_mod.dedup_rows
    REQUIRED_SCHEMA = _utils_mod.REQUIRED_SCHEMA

    pubmed = _sources_mod.pubmed

log = logging.getLogger("collect")

def _setup_logging(level: str, logs_dir: str):
    os.makedirs(logs_dir, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt)

def _read_terms(terms_file: str) -> List[str]:
    mod_path = pathlib.Path(terms_file).resolve()
    if not mod_path.exists():
        raise FileNotFoundError(f"Terms file not found: {mod_path}")
    import importlib.util
    spec = importlib.util.spec_from_file_location("user_terms", str(mod_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load terms module: {mod_path}")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    terms = list(getattr(m, "ALL_DISEASE_TERMS"))
    if not terms:
        raise RuntimeError("ALL_DISEASE_TERMS is empty. Provide your 106 canonical terms.")
    return list(dict.fromkeys(terms))

def _collect_for_term(source_name: str, term: str, cfg: Any, session: Any, resume: bool) -> List[Dict]:
    fn = {
        "pubmed": pubmed.collect,
    }.get(source_name)
    if not fn:
        log.warning("Unknown source %s; skipping", source_name)
        return []
    if source_name == "elsevier" and not cfg.env.get("ELSEVIER_API_KEY"):
        log.info("Elsevier skipped (no API key).")
        return []
    ck_dir = os.path.join(cfg.outputs["checkpoints_dir"], source_name)
    os.makedirs(ck_dir, exist_ok=True)
    ck_path = os.path.join(ck_dir, f"{norm_text(term).replace(' ', '_')}.json")
    ck = load_json(ck_path) if resume else {}
    try:
        result: Any = fn(term=term, start=cfg.start, end=cfg.end, session=session, cfg=cfg, checkpoint=ck)
    except Exception as exc:
        log.exception("Source '%s' failed for term '%s': %s", source_name, term, exc)
        return []
    if isinstance(result, dict) and "rows" in result and "checkpoint" in result:
        save_json(ck_path, result["checkpoint"])
        rows = result["rows"]
    else:
        save_json(ck_path, ck)
        rows = result
    if not isinstance(rows, list):
        log.warning("Source %s returned non-list data for term '%s'; ignored.", source_name, term)
        return []
    return rows

def _apply_nom_and_pk(rows: List[Dict], term: str, pat) -> List[Dict]:
    out = []
    for r in rows:
        title = r.get("title", "")
        abstract = r.get("abstract", "")
        fulltext = r.get("fulltext", "")
        keywords_text = r.get("keywords_text", "")
        topics_text = r.get("topics_text", "")
        concepts_text = r.get("concepts_text", "")
        text = " ".join([title, abstract, fulltext, keywords_text, topics_text, concepts_text])
        nom = total_nom(text, pat) if text.strip() else total_nom(title, pat)
        if nom <= 0:
            continue
        doi = normalize_doi(r.get("doi", ""))
        pk = doi if doi else title_hash(title)
        date = r.get("date", "")
        if not date:
            continue
        # Get total_NoM from row if available (from pubmed.py), otherwise use nom
        total_nom_value = r.get("total_NoM", nom)
        # Get country code from source; default to UN (Unknown) when missing
        country_code = r.get("country_code") or "UN"
        # Create terms_country_code field
        terms_country_code = f"{term}_{country_code}"
        out.append({
            "date": date, "NoM": int(total_nom_value), "terms_country_code": terms_country_code
        })
    return out

def main():
    ap = argparse.ArgumentParser(description="RMDPT Collector Orchestrator")
    ap.add_argument("--config", default=_DEFAULT_CONFIG)
    ap.add_argument("--terms-file", required=True)
    ap.add_argument("--start-year", type=int, required=True)
    ap.add_argument("--end-year", type=int, required=True)
    ap.add_argument("--sources", required=True,
                    help="Comma-separated list of enabled sources (pubmed)")
    ap.add_argument("--out", required=True, help="Output long CSV path")
    ap.add_argument("--pivot-out", required=True, help="Pivot CSV path")
    ap.add_argument("--nop-out", default="", help="Output NoP CSV path (optional)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()

    cfg = load_config(args.config)
    cfg.start = f"{args.start_year:04d}-01-01"
    cfg.end = f"{args.end_year:04d}-12-31"
    _setup_logging(args.log_level, cfg.outputs["logs_dir"])

    terms = _read_terms(args.terms_file)
    pats = build_lexicon(terms)

    polite_email = (cfg.env.get("OPENALEX_EMAIL") or "").strip()
    headers = {
        "User-Agent": f"RMDPTCollector/1.0"
                      + (f" (mailto:{polite_email})" if polite_email else " (contact:unknown)"),
        "Accept": "application/json,text/html;q=0.9",
    }
    session = Session(throttle=cfg.throttle, headers=headers)

    srcs = [s.strip() for s in args.sources.split(",") if s.strip()]
    srcs = [s for s in srcs if s.lower() != "openalex"]
    if not srcs:
        srcs = ["pubmed"]
    # NoP collection window: Jan 2004 – Feb 2026
    from datetime import datetime as _DT
    _NOP_WIN_START = _DT(2004, 1, 1)
    _NOP_WIN_END   = _DT(2026, 2, 28)

    def _nop_in_window(date_mm_yyyy: str) -> bool:
        try:
            return _NOP_WIN_START <= _DT.strptime(date_mm_yyyy, "%m-%Y") <= _NOP_WIN_END
        except ValueError:
            return False

    all_rows: List[Dict] = []
    all_nop_rows: List[Dict] = []
    per_source_count: Dict[str, int] = {}

    for term in terms:
        pat = pats[term]
        for s in srcs:
            log.info("[%s] %s", term, s)
            rows = _collect_for_term(s, term, cfg, session, resume=args.resume)
            per_source_count[s] = per_source_count.get(s, 0) + len(rows or [])
            cooked = _apply_nom_and_pk(rows or [], term, pat)
            all_rows.extend(cooked)
            # Collect NoP rows — real-world patient counts extracted by LLM
            # Only saved when both count AND year were stated in the abstract
            for r in (rows or []):
                nop_count = r.get("nop_count")
                nop_date = r.get("nop_date", "")
                # Skip if either count or year is missing
                if nop_count is None or not nop_date:
                    continue
                try:
                    nop_val = float(nop_count)
                except (TypeError, ValueError):
                    continue
                if nop_val <= 0:
                    continue
                if not _nop_in_window(nop_date):
                    continue
                country_code = r.get("country_code") or "UN"
                nop_entity = r.get("nop_entity", "") or term
                entity_with_country = f"{nop_entity}_{country_code}"
                doi = normalize_doi(r.get("doi", ""))
                all_nop_rows.append({
                    "date": nop_date,
                    "NoP": nop_val,
                    "disease": entity_with_country,
                    "unit": r.get("nop_unit", "patients"),
                    "notes": r.get("nop_notes", ""),
                    "doi": doi,
                })

    deduped = dedup_rows(all_rows)
    write_rows_csv(args.out, deduped)
    build_pivot(args.out, args.pivot_out, terms, cfg.start, cfg.end)

    # Write NoP CSV if requested and there are results
    if args.nop_out and all_nop_rows:
        import csv as _csv_mod, os as _os_mod
        _os_mod.makedirs(_os_mod.path.dirname(_os_mod.path.abspath(args.nop_out)), exist_ok=True)
        with open(args.nop_out, "w", newline="", encoding="utf-8") as _f:
            _w = _csv_mod.DictWriter(_f, fieldnames=["date", "NoP", "disease", "unit", "notes", "doi"])
            _w.writeheader()
            _w.writerows(all_nop_rows)
        log.info("NoP CSV written: %s (%d rows)", args.nop_out, len(all_nop_rows))
    audit = {
        "sources": srcs,
        "per_source_raw": per_source_count,
        "rows_after_nom_and_dedup": len(deduped),
        "long_csv": args.out,
        "pivot_csv": args.pivot_out,
        "date_range": {"start": cfg.start, "end": cfg.end},
        "terms": len(terms)
    }
    write_audit(cfg.outputs["audit_json"], cfg.outputs["audit_html"], audit)
    log.info("DONE.")

if __name__ == "__main__":
    main()
