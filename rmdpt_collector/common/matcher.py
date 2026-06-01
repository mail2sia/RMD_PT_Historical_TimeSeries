import regex as rx  # better Unicode support than stdlib re
from common.utils import normalize_text_utf8_lower

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

def count_concept(canonical: str, variants: list[str], text: str | None) -> int:
    """
    Count mentions of a concept across {canonical + variants}, avoiding
    double-counting sub-phrases by masking spans matched by longer phrases.
    """
    if not text:
        return 0
    t = normalize_text_utf8_lower(text)
    # longest-first to prevent "anorexia" counting inside "anorexia nervosa"
    tokens = sorted({canonical.lower(), *(v.lower() for v in variants)}, key=len, reverse=True)
    total = 0
    for tok in tokens:
        key = f"rx::{tok}"
        pat = _cache.get(key)
        if pat is None:
            pat = rx.compile(rf"(?<![\p{{L}}\p{{N}}]){rx.escape(tok)}(?![\p{{L}}\p{{N}}])")
            _cache[key] = pat
        matches = list(pat.finditer(t))
        total += len(matches)
        if matches:
            # mask matched spans so shorter tokens won't recount the same text
            buf = list(t)
            for m in matches:
                buf[m.start():m.end()] = " " * (m.end() - m.start())
            t = "".join(buf)
    return total
