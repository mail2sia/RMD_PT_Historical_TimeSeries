"""
NoP (Number of Patients) Collector — Gemini + Google Search Grounding
========================================================================
Collects real-world patient counts (affected / died) for every RMD entity
in RMD_CATALOG using Gemini with Google Search grounding (no Tavily needed).

Output
------
  outputs/nop_llm_seed.csv    — pipeline seed (date, disease, number of patients, …)
  outputs/nop_llm_meta.csv    — raw LLM extractions for auditing
  outputs/cache/nop/          — per-entity JSON cache (TTL from config)
  outputs/checkpoints/nop_checkpoint.json — resume support
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except AttributeError:
    pass
from typing import Any

import pandas as pd
import requests

from entity_catalog_v2 import RMD_CATALOG

DEFAULT_CONFIG = Path(__file__).with_name("data_collection_config.json")
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "outputs" / "cache" / "nop"
CHECKPOINT_PATH = ROOT / "outputs" / "checkpoints" / "nop_checkpoint.json"
SEED_OUTPUT = ROOT / "outputs" / "nop_llm_seed.csv"
META_OUTPUT = ROOT / "outputs" / "nop_llm_meta.csv"

SEED_COLS = ["date", "disease", "number of patients", "references", "notes", "Metric_Type", "Source_File"]
META_COLS = ["entity", "entity_type", "query", "year", "month", "count", "unit", "source_url", "confidence", "notes_llm", "llm_provider", "ts"]

GEMINI_URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cfg(config: dict, section: str, key: str, default: Any = None) -> Any:
    obj = config.get(section, {}) if isinstance(config, dict) else {}
    return obj.get(key, default) if isinstance(obj, dict) else default


# ─────────────────────────────────────────────────────────────────────────────
# Disk cache
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(entity: str, entity_type: str) -> str:
    raw = f"{entity_type}::{entity}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    slug = entity.replace(" ", "_")[:40]
    return f"{slug}-{digest}.json"


def _cache_load(key: str, ttl_hours: int) -> Any:
    path = CACHE_DIR / key
    if not path.exists():
        return None
    if ttl_hours > 0:
        age = time.time() - path.stat().st_mtime
        if age > ttl_hours * 3600:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cache_save(key: str, data: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / key
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint
# ─────────────────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict[str, Any]:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False),
        encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gemini with Google Search grounding
# ─────────────────────────────────────────────────────────────────────────────

_SEARCH_PROMPT_TPL = """\
Search the web for real-world patient count statistics for "{entity}" (rare mental disorder).

Find ONLY absolute patient counts — people who are:
  - Diagnosed with / affected by {entity}
  - Died from / mortality due to {entity}
  - Living with / suffering from {entity}
  - Documented cases / registry counts of {entity}

Return at most 5 distinct year data points (2004-2026), one entry per year.

Return ONLY valid JSON (no markdown fences). Keep "notes" under 80 chars:
{{"data_points":[{{"year":<int>,"month":<int|null>,"count":<int>,"unit":"<short label>","source_url":"<url>","confidence":"<high|medium|low>","notes":"<short quote>"}}]}}

REJECT: rates/percentages, study enrollment, modelled counts, data outside 2004-2026.
If nothing valid found: {{"data_points":[]}}
"""


def _extract_partial_json(text: str) -> dict | None:
    """Try to salvage complete data_point objects from truncated JSON."""
    import re
    # Find all complete {...} objects inside "data_points"
    objects = re.findall(r'\{[^{}]*"year"\s*:\s*\d{4}[^{}]*\}', text)
    valid = []
    for obj in objects:
        # Only keep if it has year + count — skip incomplete objects
        if '"count"' not in obj:
            continue
        try:
            valid.append(json.loads(obj))
        except json.JSONDecodeError:
            pass
    if valid:
        return {"data_points": valid}
    return None


def _call_gemini_search(entity: str, gemini_key: str, gemini_model: str, timeout: int) -> dict | None:
    """Call Gemini with Google Search grounding to find real patient counts."""
    prompt = _SEARCH_PROMPT_TPL.format(entity=entity)
    url = GEMINI_URL_TPL.format(model=gemini_model, key=gemini_key)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096},
    }
    for attempt in range(3):
        try:
            resp = requests.post(url, json=body, timeout=timeout)
            resp.raise_for_status()
            raw = resp.json()
            # Check finish reason for truncation
            finish = raw.get("candidates", [{}])[0].get("finishReason", "")
            parts = raw["candidates"][0]["content"]["parts"]
            text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
            text = "\n".join(text_parts).strip()
            # Strip markdown fences
            if "```" in text:
                fenced = text.split("```")
                for seg in fenced[1::2]:
                    seg = seg.lstrip("json").strip()
                    if seg:
                        text = seg
                        break
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                if finish == "MAX_TOKENS":
                    print(f"    [gemini] response truncated for '{entity}', trying partial recovery")
                    recovered = _extract_partial_json(text)
                    if recovered:
                        return recovered
                print(f"    [gemini] JSON parse error for '{entity}' (finish={finish})")
                return None
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            print(f"    [gemini] HTTP {code} for '{entity}': {exc}")
            if code in {429, 503} and attempt < 2:
                time.sleep(30 * (attempt + 1) + random.random())
                continue
            return None
        except Exception as exc:
            print(f"    [gemini] Error for '{entity}': {type(exc).__name__}: {exc}")
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-entity pipeline
# ─────────────────────────────────────────────────────────────────────────────

_NOP_WIN_START = 2004
_NOP_WIN_END_YEAR, _NOP_WIN_END_MONTH = 2026, 2


def _in_window(year: int, month: int | None) -> bool:
    if year < _NOP_WIN_START:
        return False
    if year > _NOP_WIN_END_YEAR:
        return False
    if year == _NOP_WIN_END_YEAR and (month or 1) > _NOP_WIN_END_MONTH:
        return False
    return True


def process_entity(
    entity: str,
    etype: str,
    config: dict,
    ttl_hours: int,
) -> list[dict]:
    """Full pipeline for one entity. Returns list of meta row dicts (one per data point)."""
    cache_key = _cache_key(entity, etype)
    cached = _cache_load(cache_key, ttl_hours)
    if cached is not None:
        print(f"    [cache] {entity} ({len(cached)} points)")
        return cached

    gemini_key = str(cfg(config, "api_keys", "google_api_key", "")).strip()
    gemini_model = str(cfg(config, "runtime", "llm_gemini_model", "gemini-2.5-flash")).strip()
    timeout = int(cfg(config, "runtime", "http_timeout_seconds", 60) or 60)

    if not gemini_key:
        print(f"  WARNING: google_api_key missing, skipping {entity}")
        return []

    # Single Gemini call with Google Search grounding
    parsed = _call_gemini_search(entity, gemini_key, gemini_model, timeout)

    if parsed is None:
        print(f"  WARNING: Gemini search failed for '{entity}'")
        return []

    data_points = parsed.get("data_points", [])
    if not isinstance(data_points, list):
        return []

    ts = datetime.now().isoformat(timespec="seconds")
    meta_rows = []
    seen_year_month: set[tuple] = set()

    for dp in data_points:
        year = dp.get("year")
        month = dp.get("month")
        count = dp.get("count")

        # Validate year, count, window
        if year is None or count is None:
            continue
        try:
            year = int(year)
            count = float(count)
            month = int(month) if month is not None else None
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        if not _in_window(year, month):
            continue

        # Dedup within this entity's result set
        ym_key = (year, month)
        if ym_key in seen_year_month:
            continue
        seen_year_month.add(ym_key)

        meta_rows.append({
            "entity": entity,
            "entity_type": etype,
            "query": entity,
            "year": year,
            "month": month,
            "count": count,
            "unit": dp.get("unit", ""),
            "source_url": dp.get("source_url", ""),
            "confidence": dp.get("confidence", "low"),
            "notes_llm": dp.get("notes", ""),
            "llm_provider": "gemini-search",
            "ts": ts,
        })

    _cache_save(cache_key, meta_rows)
    return meta_rows


# ─────────────────────────────────────────────────────────────────────────────
# Conversion to seed format
# ─────────────────────────────────────────────────────────────────────────────

def meta_to_seed(meta_row: dict) -> dict | None:
    count_f = float(meta_row["count"])
    year_int = int(meta_row["year"])
    month_int = int(meta_row["month"]) if meta_row.get("month") else 1

    unit = str(meta_row.get("unit", "")).lower()
    metric_type = "NoP_Rate" if ("per 100" in unit or "rate" in unit or "%" in unit) else "NoP"

    source_url = str(meta_row.get("source_url", "")).strip() or ""

    return {
        "date": f"{month_int:02d}-{year_int}",
        "disease": meta_row["entity"],
        "number of patients": count_f,
        "references": source_url,
        "notes": (
            f"LLM-web ({meta_row['llm_provider']}): "
            f"{meta_row.get('notes_llm', '')} [{unit}]"
        )[:250],
        "Metric_Type": metric_type,
        "Source_File": "NOP_LLM_GEMINI_SEARCH",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Collect NoP data for RMD entities via Gemini + Google Search grounding.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--seed-output", default=str(SEED_OUTPUT))
    parser.add_argument("--meta-output", default=str(META_OUTPUT))
    parser.add_argument("--max-entities", type=int, default=0,
                        help="Stop after N entities (0 = all, useful for testing)")
    parser.add_argument("--reset-checkpoint", action="store_true",
                        help="Ignore existing checkpoint and re-process all entities")
    parser.add_argument("--sleep", type=float, default=1.5,
                        help="Seconds to sleep between API calls (default 1.5)")
    args = parser.parse_args()

    config = load_config(Path(args.config).resolve())
    ttl_hours = int(cfg(config, "runtime", "disk_cache_ttl_hours", 336) or 336)

    # Build entity list — RMDs only
    entities: list[tuple[str, str]] = [(e, "RMD") for e in RMD_CATALOG.keys()]

    if args.max_entities > 0:
        entities = entities[: args.max_entities]

    total = len(entities)
    print(f"[NOP_LLM] Processing {total} RMD entities")

    # Load checkpoint
    checkpoint = load_checkpoint() if not args.reset_checkpoint else {}
    done_set: set[str] = set(checkpoint.get("done", []))
    remaining = [(e, t) for e, t in entities if f"{t}::{e}" not in done_set]
    print(f"[NOP_LLM] {len(done_set)} already done, {len(remaining)} remaining")

    # Load existing outputs
    seed_path = Path(args.seed_output)
    meta_path = Path(args.meta_output)
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    existing_seed = (
        pd.read_csv(seed_path).to_dict(orient="records")
        if seed_path.exists() and seed_path.stat().st_size > 0
        else []
    )
    existing_meta = (
        pd.read_csv(meta_path).to_dict(orient="records")
        if meta_path.exists() and meta_path.stat().st_size > 0
        else []
    )

    new_seed: list[dict] = []
    new_meta: list[dict] = []

    for idx, (entity, etype) in enumerate(remaining, 1):
        print(f"  [{idx}/{len(remaining)}] {etype} | {entity}")
        meta_rows = process_entity(entity=entity, etype=etype, config=config, ttl_hours=ttl_hours)

        if meta_rows:
            for meta_row in meta_rows:
                new_meta.append(meta_row)
                seed_row = meta_to_seed(meta_row)
                if seed_row is not None:
                    new_seed.append(seed_row)
            print(f"    -> {len(meta_rows)} data point(s) extracted")
        else:
            print(f"    -> no valid data points found")

        done_set.add(f"{etype}::{entity}")
        save_checkpoint(done_set)

        # Checkpoint-write outputs incrementally every 10 entities
        if idx % 10 == 0 or idx == len(remaining):
            all_meta = existing_meta + new_meta
            all_seed = existing_seed + new_seed
            # Dedup meta by (entity, entity_type, year, month)
            meta_df = pd.DataFrame(all_meta, columns=META_COLS).drop_duplicates(
                subset=["entity", "entity_type", "year", "month"]
            )
            meta_df.to_csv(meta_path, index=False)
            seed_df = pd.DataFrame(all_seed, columns=SEED_COLS)
            if not seed_df.empty:
                # Dedup seed: keep highest count for same (date, disease, Source_File)
                seed_df = (
                    seed_df.groupby(
                        ["date", "disease", "Metric_Type", "Source_File"],
                        as_index=False,
                    )
                    .agg({"number of patients": "max", "references": "first", "notes": "first"})
                    .sort_values(["disease", "date"])
                    .reset_index(drop=True)
                )
            seed_df.to_csv(seed_path, index=False)
            print(f"    [saved] seed={len(seed_df)} rows, meta={len(meta_df)} rows")

        time.sleep(args.sleep)

    # Final save
    all_meta = existing_meta + new_meta
    all_seed = existing_seed + new_seed
    meta_df = pd.DataFrame(all_meta, columns=META_COLS).drop_duplicates(
        subset=["entity", "entity_type", "year", "month"]
    )
    seed_df = pd.DataFrame(all_seed, columns=SEED_COLS)
    if not seed_df.empty:
        seed_df = (
            seed_df.groupby(
                ["date", "disease", "Metric_Type", "Source_File"],
                as_index=False,
            )
            .agg({"number of patients": "max", "references": "first", "notes": "first"})
            .sort_values(["disease", "date"])
            .reset_index(drop=True)
        )

    meta_df.to_csv(meta_path, index=False)
    seed_df.to_csv(seed_path, index=False)

    print(f"\n[NOP_LLM] Complete.")
    print(f"  Seed rows : {len(seed_df)}")
    print(f"  Meta rows : {len(meta_df)}")
    print(f"  Seed path : {seed_path}")
    print(f"  Meta path : {meta_path}")


if __name__ == "__main__":
    main()
