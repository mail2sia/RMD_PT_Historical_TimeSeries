# rmdpt_collector/common/config.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
import json, os, pathlib

@dataclass
class Config:
    start: str
    end: str
    outputs: Dict[str, str]
    throttle: Dict[str, float]
    sources: List[str]
    google_news: Dict[str, int]
    elsevier: Dict[str, Any]
    reddit: Dict[str, Any]
    env: Dict[str, str]

def load_config(path: str | None) -> Config:
    p = pathlib.Path(path or "project_config.json")
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = raw.get("outputs", {})
    throttle = raw.get("throttle", {
        "min_sleep_s": 1.0, "max_sleep_s": 2.0,
        "max_retries": 6, "backoff_base": 1.8, "backoff_jitter": 0.25
    })
    # Load from JSON, with fallback to environment variables
    elsevier_keys = raw.get("ELSEVIER_API_KEY", os.getenv("ELSEVIER_API_KEY", ""))
    if isinstance(elsevier_keys, str) and elsevier_keys:
        elsevier_keys = [k.strip() for k in elsevier_keys.split(',')]
    elif not isinstance(elsevier_keys, list):
        elsevier_keys = []

    gnews_keys = raw.get("GNEWS_API_KEYS", os.getenv("GNEWS_API_KEYS", ""))
    if isinstance(gnews_keys, str) and gnews_keys:
        gnews_keys = [k.strip() for k in gnews_keys.split(',')]
    elif not isinstance(gnews_keys, list):
        gnews_keys = []

    env = {
        "OPENALEX_EMAIL": raw.get("OPENALEX_MAILTO", "sahsan03@student.bbk.ac.uk"),
        "SPRINGER_API_KEY": raw.get("SPRINGER_API_KEY", os.getenv("SPRINGER_API_KEY", "")),
        "ELSEVIER_API_KEY": elsevier_keys,
        "GNEWS_API_KEYS": gnews_keys,
        "REDDIT_CLIENT_ID": raw.get("REDDIT_CLIENT_ID", os.getenv("REDDIT_CLIENT_ID", "")),
        "REDDIT_CLIENT_SECRET": raw.get("REDDIT_CLIENT_SECRET", os.getenv("REDDIT_CLIENT_SECRET", "")),
        "REDDIT_USERNAME": raw.get("REDDIT_USERNAME", os.getenv("REDDIT_USERNAME", "")),
        "REDDIT_PASSWORD": raw.get("REDDIT_PASSWORD", os.getenv("REDDIT_PASSWORD", "")),
        "REDDIT_USER_AGENT": raw.get("REDDIT_USER_AGENT", os.getenv("REDDIT_USER_AGENT", "")),
        "NCBI_API_KEY": raw.get("NCBI_API_KEY", os.getenv("NCBI_API_KEY", "")),
        "SEC_API_KEY": raw.get("SEC_API_KEY", os.getenv("SEC_API_KEY", "")),
        "CROSSREF_MAILTO": raw.get("CROSSREF_MAILTO", "sahsan03@student.bbk.ac.uk"),
    }
    return Config(
        start=raw.get("date_range", {}).get("start", "2004-01-01"),
        end=raw.get("date_range", {}).get("end", "2025-12-31"),
        outputs={
            "rmd_csv": out.get("rmd_csv", "outputs/collected_RMD_NoM.csv"),
            "pivot_csv": out.get("pivot_csv", "outputs/pivot_RMD_NoM.csv"),
            "audit_json": out.get("audit_json", "outputs/audit.json"),
            "audit_html": out.get("audit_html", "outputs/audit.html"),
            "checkpoints_dir": out.get("checkpoints_dir", "outputs/checkpoints"),
            "logs_dir": out.get("logs_dir", "outputs/logs"),
        },
        throttle=throttle,
        sources=raw.get("sources", []),
        google_news=raw.get("google_news", {"max_pages": 5}),
        elsevier=raw.get("elsevier", {"use": True}),
        reddit=raw.get("reddit", {"use_comments": False}),
        env=env
    )
