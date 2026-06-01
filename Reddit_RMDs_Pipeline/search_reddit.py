import json
import os
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict
import time
import requests
from search_terms import DISEASE_SYNONYMS

SUBREDDITS = ["mentalhealth", "AskReddit", "depression", "psychology", "all"]
DEFAULT_START_DATE = "2004-01-01"
DEFAULT_END_DATE = "2026-02-28"
PROGRESS_FILE = "reddit_rmd_progress.json"
OUTPUT_FILE = "reddit_rmd_mentions.csv"


def generate_query_variants(term, synonyms):
    base_terms = [term] + list(synonyms or [])
    variants = []
    for t in base_terms:
        t_lower = t.strip().lower()
        variants.append(t_lower)
        if " disorder" not in t_lower:
            variants.append(f"{t_lower} disorder")
        if " syndrome" not in t_lower:
            variants.append(f"{t_lower} syndrome")
    return list({v for v in variants if v})


def _load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_progress(progress):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f)


def search_reddit_rmd_mentions_by_day(start_date=DEFAULT_START_DATE, end_date=DEFAULT_END_DATE):
    progress = _load_progress()

    # Load existing output so we only append new results
    existing_rows = {}  # {(date, disease): NoM}
    if os.path.exists(OUTPUT_FILE):
        try:
            df_existing = pd.read_csv(OUTPUT_FILE)
            for _, row in df_existing.iterrows():
                key = (str(row["date"]), str(row["disease"]))
                existing_rows[key] = existing_rows.get(key, 0) + int(row.get("NoM", 0))
        except Exception:
            pass

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    print("Using Arctic Shift for historical Reddit search (2004–2026)...")

    def arctic_shift_search(term, subreddit, after, before, limit=100, max_retries=5):
        url = "https://arctic-shift.photon-reddit.com/api/posts/search"
        params = {
            "query": term,
            "subreddit": subreddit,
            "after": after,
            "before": before,
            "limit": limit,
        }
        headers = {"User-Agent": "rmdpt-collector/1.0"}
        backoff = 10.0

        for attempt in range(1, max_retries + 1):
            response = None
            try:
                response = requests.get(url, params=params, headers=headers, timeout=30)
                if response.status_code == 429:
                    print(f"Arctic Shift 429 (rate limit). attempt={attempt}, sleeping {backoff}s")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                response.raise_for_status()
                return response.json().get("data", [])
            except requests.exceptions.HTTPError as exc:
                print(f"Arctic Shift HTTP error for '{term}' in r/{subreddit}: {exc}")
                if response is not None and response.status_code in (429, 502, 503, 504):
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return []
            except Exception as exc:
                print(f"Arctic Shift error for '{term}' in r/{subreddit}: {exc}")
                time.sleep(backoff)
                backoff *= 2
        return []

    def month_ranges(start_date_obj, end_date_obj):
        current = datetime(start_date_obj.year, start_date_obj.month, 1)
        while current.date() <= end_date_obj:
            if current.month == 12:
                next_month = datetime(current.year + 1, 1, 1)
            else:
                next_month = datetime(current.year, current.month + 1, 1)
            after = int(time.mktime(current.timetuple()))
            before = int(time.mktime((next_month - pd.Timedelta(seconds=1)).timetuple()))
            yield after, before, current.strftime("%Y-%m")
            current = next_month

    for disease_term, synonyms in DISEASE_SYNONYMS.items():
        terms = generate_query_variants(disease_term, synonyms)
        daily_counter = defaultdict(int)
        seen_submission_ids = set()

        for subreddit in SUBREDDITS:
            for term in terms:
                ck_key = f"{term}|{subreddit}"
                done_months = set(progress.get(ck_key, []))
                print(f"Searching '{term}' in r/{subreddit}...")
                try:
                    for after, before, month_str in month_ranges(start_dt, end_dt):
                        if month_str in done_months:
                            continue  # already fetched — skip

                        results = arctic_shift_search(term, subreddit, after, before, limit=100)
                        time.sleep(2.0)
                        for item in results:
                            sid = str(item.get("id", "")).strip()
                            if sid and sid in seen_submission_ids:
                                continue
                            created_date = datetime.fromtimestamp(item.get("created_utc", 0), tz=timezone.utc).date()
                            if created_date < start_dt or created_date > end_dt:
                                continue
                            content = f"{item.get('title', '')} {item.get('selftext', '')}".lower()
                            if any(keyword in content for keyword in terms):
                                if sid:
                                    seen_submission_ids.add(sid)
                                daily_counter[created_date.strftime("%Y-%m-%d")] += 1

                        # Mark this (term, subreddit, month) as done
                        if ck_key not in progress:
                            progress[ck_key] = []
                        if month_str not in progress[ck_key]:
                            progress[ck_key].append(month_str)
                        _save_progress(progress)

                except Exception as exc:
                    print(f"Error searching '{term}' in r/{subreddit}: {exc}")

        # Merge new counts into existing_rows
        for date, count in daily_counter.items():
            key = (date, disease_term)
            existing_rows[key] = existing_rows.get(key, 0) + count

    result_rows = [
        {"date": d, "NoM": n, "disease": t}
        for (d, t), n in existing_rows.items()
    ]
    df = pd.DataFrame(result_rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "NoM", "disease"])

    return df.sort_values(by=["disease", "date"]).reset_index(drop=True)


if __name__ == "__main__":
    df = search_reddit_rmd_mentions_by_day()
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved results to {OUTPUT_FILE}")
