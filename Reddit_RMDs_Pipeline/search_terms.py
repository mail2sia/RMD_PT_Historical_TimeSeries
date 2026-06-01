from entity_catalog_v2 import RMD_CATALOG


DISEASE_SYNONYMS = {
    canonical: [alias for alias in aliases if alias != canonical]
    for canonical, aliases in RMD_CATALOG.items()
}
