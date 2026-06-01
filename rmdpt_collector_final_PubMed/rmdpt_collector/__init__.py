# rmdpt_collector/__init__.py
from __future__ import annotations
import sys as _sys

__all__ = ["__version__"]
__version__ = "1.0.0"

def _alias(modname: str, target: str) -> None:
    """
    Install a compatibility alias so imports like 'from common import utils'
    resolve to 'rmdpt_collector.common' when running as a package.
    """
    if modname not in _sys.modules:
        try:
            __import__(target)
            _sys.modules[modname] = _sys.modules[target]
        except Exception:
            pass

# Legacy aliases (safe no-ops if modules are missing)
_alias("common", "rmdpt_collector.common")
_alias("sources", "rmdpt_collector.sources")
_alias("pipelines", "rmdpt_collector.pipelines")
_alias("terms", "rmdpt_collector.terms")
