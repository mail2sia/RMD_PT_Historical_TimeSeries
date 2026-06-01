"""Canonical search-term exports backed by root entity_catalog_v2.

This module exists for backward compatibility with pipelines that import
rmdpt_collector.search_terms directly.
"""

from pathlib import Path
import sys
import importlib.util

# Ensure workspace root (data_collection/) is importable from this nested package.
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_root_search_terms = _load_module(ROOT_DIR / "search_terms.py", "_root_search_terms")
_root_search_terms_pt = _load_module(ROOT_DIR / "search_terms_pt.py", "_root_search_terms_pt")

ALL_DISEASE_TERMS = _root_search_terms.ALL_DISEASE_TERMS
DISEASE_TERM_TO_BASE = _root_search_terms.TERM_TO_BASE
DISEASE_SYNONYMS = _root_search_terms.DISEASE_SYNONYMS

ALL_PT_TERMS = _root_search_terms_pt.ALL_PT_TERMS
PT_TERM_TO_BASE = _root_search_terms_pt.TERM_TO_BASE
PT_SYNONYMS = _root_search_terms_pt.PT_SYNONYMS

# Backward-compatible aliases expected by some collectors.
TERM_TO_CANONICAL_DISEASES = DISEASE_TERM_TO_BASE
TERM_TO_CANONICAL_PT = PT_TERM_TO_BASE
