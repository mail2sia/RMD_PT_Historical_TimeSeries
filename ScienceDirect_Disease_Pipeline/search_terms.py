import unicodedata
import sys
from pathlib import Path

# Ensure workspace root is importable when this pipeline is executed directly.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from entity_catalog_v2 import RMD_CATALOG


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

TERM_TO_BASE = {}
for base_term, synonyms in DISEASE_SYNONYMS.items():
    for variant in generate_variations(base_term):
        TERM_TO_BASE[normalize_term(variant)] = base_term
    for synonym in synonyms:
        for variant in generate_variations(synonym):
            TERM_TO_BASE[normalize_term(variant)] = base_term

ALL_DISEASE_TERMS = sorted(set(TERM_TO_BASE.keys()))
