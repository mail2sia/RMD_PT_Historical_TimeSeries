<!-- python -m rmdpt_collector.pipelines.collect `
  --config project_config.json `
  --terms-file terms\search_terms.py `
  --start-year 2004 --end-year 2025 `
  --sources openalex,crossref,pubmed,springer,elsevier,clinical_trials,google_news,news_gnews,reddit,filings `
  --out outputs\collected_RMD_NoM.csv `
  --pivot-out outputs\pivot_RMD_NoM.csv `
  --resume --verbose --log-level INFO


# 2) (Strongly recommended) set your OpenAlex email
#    You can also put this into your environment permanently.
$env:OPENALEX_EMAIL = "your.email@org.com" -->
