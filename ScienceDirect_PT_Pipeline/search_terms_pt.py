import unicodedata
from entity_catalog_v2 import PT_CATALOG


def normalize_term(term: str) -> str:
    return (
        unicodedata.normalize("NFKD", str(term))
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace("'", " ")
        .replace("-", " ")
        .lower()
        .strip()
    )


def _compact_spaces(term: str) -> str:
    return " ".join(str(term).split())


def generate_variations(term: str):
    t = _compact_spaces(term)
    return [t, f"{t} technology", f"{t} tool", f"{t} system"]


PT_SYNONYMS = {
    canonical: [alias for alias in aliases if alias != canonical]
    for canonical, aliases in PT_CATALOG.items()
}

TERM_TO_BASE = {}
for pt, synonyms in PT_SYNONYMS.items():
    for variant in generate_variations(pt):
        TERM_TO_BASE[normalize_term(variant)] = pt
    for synonym in synonyms:
        for variant in generate_variations(synonym):
            TERM_TO_BASE[normalize_term(variant)] = pt

ALL_PT_TERMS = sorted(set(TERM_TO_BASE.keys()))
