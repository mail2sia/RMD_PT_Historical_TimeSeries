from __future__ import annotations

import argparse
from io import StringIO
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from entity_catalog_v2 import PT_CATALOG, RMD_CATALOG, normalize


DEFAULT_CONFIG = Path(__file__).with_name("data_collection_config.json")
DEFAULT_API_BASE = "https://sdmx.oecd.org/public/rest"


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def cfg_get(config: dict[str, Any], section: str, key: str, default: Any = None) -> Any:
    obj = config.get(section, {}) if isinstance(config, dict) else {}
    return obj.get(key, default) if isinstance(obj, dict) else default


def cfg_get_list(config: dict[str, Any], section: str, key: str) -> list[str]:
    value = cfg_get(config, section, key, [])
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def build_catalog_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in {**RMD_CATALOG, **PT_CATALOG}.items():
        lookup[normalize(canonical)] = canonical
        for alias in aliases:
            n = normalize(alias)
            if n and n not in lookup:
                lookup[n] = canonical
    return lookup


def parse_time_period(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None

    # Yearly values: 2021 -> 01-2021
    if len(text) == 4 and text.isdigit():
        return f"01-{text}"

    # Monthly values: 2021-07
    if len(text) == 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
        return f"{text[5:7]}-{text[:4]}"

    # Quarterly values: 2021-Q3
    if len(text) == 7 and text[4:6].upper() == "-Q" and text[:4].isdigit() and text[6].isdigit():
        q = int(text[6])
        month = 1 + (q - 1) * 3
        return f"{month:02d}-{text[:4]}"

    # OECD sometimes uses 2021-M07
    if len(text) == 8 and text[4:6].upper() == "-M" and text[:4].isdigit() and text[6:8].isdigit():
        return f"{text[6:8]}-{text[:4]}"

    return None


def pick_entity_column(columns: list[str]) -> str | None:
    preferred = [
        "INDICATOR",
        "SUBJECT",
        "MEASURE",
        "ACTIVITY",
        "HEALTH_PROFESSION",
        "VAR",
        "SERIES",
        "INDICATOR_LABEL",
        "SUBJECT_LABEL",
        "MEASURE_LABEL",
    ]
    colset = {c.upper(): c for c in columns}
    for key in preferred:
        if key in colset:
            return colset[key]

    for c in columns:
        up = c.upper()
        if up.endswith("_LABEL") and up not in {"REF_AREA_LABEL", "TIME_PERIOD_LABEL"}:
            return c

    return None


def build_oecd_url(base: str, dataset_spec: str, start_period: str, end_period: str, fmt: str) -> str:
    root = base.rstrip("/")
    return (
        f"{root}/data/{dataset_spec}/all"
        f"?startPeriod={start_period}&endPeriod={end_period}"
        f"&dimensionAtObservation=AllDimensions&format={fmt}"
    )


def fetch_oecd_csv(url: str, timeout: int = 60) -> pd.DataFrame:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))


def convert_oecd_to_seed(
    base_url: str,
    dataset_specs: list[str],
    start_period: str,
    end_period: str,
    metric_type: str,
    keep_unmatched: bool,
) -> pd.DataFrame:
    lookup = build_catalog_lookup()
    out_rows: list[dict[str, Any]] = []

    for dataset_spec in dataset_specs:
        url = build_oecd_url(base_url, dataset_spec, start_period, end_period, fmt="csvfilewithlabels")
        try:
            df = fetch_oecd_csv(url)
        except Exception as exc:
            print(f"WARNING: OECD fetch failed for {dataset_spec}: {exc}")
            continue

        if df.empty:
            continue

        time_col = "TIME_PERIOD" if "TIME_PERIOD" in df.columns else ("TIME" if "TIME" in df.columns else None)
        value_col = "OBS_VALUE" if "OBS_VALUE" in df.columns else None
        if not time_col:
            for c in df.columns:
                if c.upper().startswith("TIME"):
                    time_col = c
                    break
        if not value_col:
            for c in df.columns:
                if c.upper() in {"VALUE", "OBS_VALUE", "OBS"}:
                    value_col = c
                    break

        entity_col = pick_entity_column(list(df.columns))
        if not time_col or not value_col:
            print(f"WARNING: Missing time/value columns in {dataset_spec}, skipped.")
            continue

        work = df.copy()
        work["MM-YYYY"] = work[time_col].apply(parse_time_period)
        work["Signal_Value"] = pd.to_numeric(work[value_col], errors="coerce")
        work = work.dropna(subset=["MM-YYYY", "Signal_Value"])
        if work.empty:
            continue

        for _, row in work.iterrows():
            raw_entity = str(row.get(entity_col, "OECD_Health_Indicator")).strip() if entity_col else "OECD_Health_Indicator"
            canonical = lookup.get(normalize(raw_entity))
            if canonical is None and not keep_unmatched:
                continue
            entity_name = canonical or raw_entity

            out_rows.append(
                {
                    "date": str(row["MM-YYYY"]),
                    "disease": entity_name,
                    "number of patients": float(row["Signal_Value"]),
                    "references": url,
                    "notes": f"Imported from OECD API dataset {dataset_spec}",
                    "Metric_Type": metric_type,
                    "Source_File": f"OECD_{dataset_spec}",
                }
            )

    if not out_rows:
        return pd.DataFrame(columns=["date", "disease", "number of patients", "references", "notes", "Metric_Type", "Source_File"])

    out = pd.DataFrame(out_rows)
    out = out.groupby(
        ["date", "disease", "references", "notes", "Metric_Type", "Source_File"],
        as_index=False,
    )["number of patients"].sum()
    if isinstance(out, pd.Series):
        out = out.to_frame(name="number of patients").reset_index()
    out["_sort_key"] = out["date"].astype(str) + "|" + out["disease"].astype(str)
    out = out.sort_values(by="_sort_key").drop(columns=["_sort_key"]).reset_index(drop=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OECD Data Explorer datasets via API and convert to pipeline seed format.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to data_collection_config.json")
    parser.add_argument("--output", default="OECD/processed/oecd_pipeline_seed.csv", help="Output seed CSV path")
    parser.add_argument("--metric-type", default="NoP", choices=["NoM", "NoP"], help="Metric type for produced rows")
    parser.add_argument("--keep-unmatched", action="store_true", help="Keep entities not mapped to local RMD/PT catalog")
    args = parser.parse_args()

    config = load_config(Path(args.config).resolve())
    base_url = str(cfg_get(config, "api_bases", "oecd_api_base", DEFAULT_API_BASE)).strip() or DEFAULT_API_BASE
    dataset_specs = cfg_get_list(config, "api_files", "oecd_dataset_specs")
    start_period = str(cfg_get(config, "runtime", "oecd_start_period", "2004")).strip() or "2004"
    end_period = str(cfg_get(config, "runtime", "oecd_end_period", "2026")).strip() or "2026"

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    empty_cols = ["date", "disease", "number of patients", "references", "notes", "Metric_Type", "Source_File"]

    if not dataset_specs:
        pd.DataFrame(columns=empty_cols).to_csv(output_path, index=False)
        print("WARNING: No OECD dataset specs configured; wrote empty OECD seed file.")
        print(f"Saved: {output_path}")
        print("Rows: 0 | Entities: 0")
        return

    out = convert_oecd_to_seed(
        base_url=base_url,
        dataset_specs=dataset_specs,
        start_period=start_period,
        end_period=end_period,
        metric_type=args.metric_type,
        keep_unmatched=args.keep_unmatched,
    )

    out.to_csv(output_path, index=False)

    print(f"Saved: {output_path}")
    print(f"Rows: {len(out)} | Entities: {out['disease'].nunique() if not out.empty else 0}")


if __name__ == "__main__":
    main()
