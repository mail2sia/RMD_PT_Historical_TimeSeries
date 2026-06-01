import regex as rx  # better Unicode support than stdlib re
def normalize_text_utf8_lower(text):
    return text.lower()

_cache = {}

def count_term(term: str, text: str | None) -> int:
    if not text: return 0
    # normalize text lower; we match term lower too
    t = normalize_text_utf8_lower(text)
    key = f"rx::{term}"
    pat = _cache.get(key)
    if pat is None:
        # Word boundary over Unicode letters/digits (exclude underscores and punctuation)
        # (?<![\p{L}\p{N}])  term  (?![\p{L}\p{N}])
        pat = rx.compile(rf"(?<![\p{{L}}\p{{N}}]){rx.escape(term.lower())}(?![\p{{L}}\p{{N}}])")
        _cache[key] = pat
    return len(pat.findall(t))
