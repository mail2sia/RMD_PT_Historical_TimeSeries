import unicodedata
from entity_catalog_v2 import RMD_CATALOG, PT_CATALOG, RMD_TO_PT, PT_TO_RMD


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
    return [t, f"{t} disease", f"{t} disorder", f"{t} syndrome"]


DISEASE_SYNONYMS = {
    canonical: [alias for alias in aliases if alias != canonical]
    for canonical, aliases in RMD_CATALOG.items()
}

PT_SYNONYMS = {
    canonical: [alias for alias in aliases if alias != canonical]
    for canonical, aliases in PT_CATALOG.items()
}

# Disease-only compatibility exports (used by several existing pipelines)
TERM_TO_BASE = {}
for base_term, synonyms in DISEASE_SYNONYMS.items():
    for variant in generate_variations(base_term):
        TERM_TO_BASE[normalize_term(variant)] = base_term
    for synonym in synonyms:
        for variant in generate_variations(synonym):
            TERM_TO_BASE[normalize_term(variant)] = base_term

ALL_DISEASE_TERMS = sorted(set(TERM_TO_BASE.keys()))

# Additional v2 exports
RMD_CATALOG_V2 = RMD_CATALOG
PT_CATALOG_V2 = PT_CATALOG
RMD_TO_PT_V2 = RMD_TO_PT
PT_TO_RMD_V2 = PT_TO_RMD
