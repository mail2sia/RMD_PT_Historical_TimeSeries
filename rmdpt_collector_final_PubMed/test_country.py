from rmdpt_collector.sources.pubmed import fetch_pubmed
import json

results = fetch_pubmed('Reactive Attachment')
print(f'Found {len(results)} results')
if results:
    print('\nFirst 5 results with country codes:')
    for i, r in enumerate(results[:5]):
        country = r.get("country_code") or "None"
        nom = r.get("total_NoM")
        print(f'{i+1}. country={country}, NoM={nom}')
