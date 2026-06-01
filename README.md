# RMD/PT Historical Time-Series Pipeline

Data collection and model-preparation workspace for Rare Mental Diseases (RMDs) and Pertinent Technologies (PTs). The repository contains source-specific collectors plus a checked-in monthly feature matrix at `data/data.csv` for downstream time-series forecasting.

The current checkout is a compact pipeline snapshot. It includes the main model matrix and collector code, but it does not include the larger normalization workspace described by some older notes, such as `data/scripts/`, `data/nodes.csv`, or `data/data_scorces/`.

## What This Repository Contains

- ScienceDirect and CrossRef collectors for RMD and PT article mention counts.
- PubMed-focused RMD collector with optional NoP extraction.
- OpenAlex and ClinicalTrials collector package under `rmdpt_collector/`.
- Reddit RMD and PT mention collectors.
- GNews/Google News collectors for news and funding signals.
- Patent mention processing scripts.
- OECD seed output under `OECD/processed/`.
- A prepared monthly model input matrix under `data/data.csv`.

## Core Concepts

| Term | Meaning |
| --- | --- |
| `RMD` | Rare mental disease entity. In the current checkout, RMD entities are represented by search-term modules and `RMD_*` columns in `data/data.csv`. |
| `PT` | Pertinent technology, treatment, intervention, or measurement entity represented by search-term modules and `PT_*` columns in `data/data.csv`. |
| `NoM` | Number of Mentions. A count of source mentions or source records for an entity in a time period. |
| `NoP` | Number of Patients. A real-world absolute human count extracted from a source. |
| `Month-Year` | Monthly time index used by the final model matrix, for example `Jan-04`. |

### NoP Definition

`NoP` means **Number of Patients**: an absolute real-world human count extracted from a source. Valid NoP values are counts of people diagnosed with, affected by, living with, documented as cases of, treated with a PT, or explicitly reported as dying from an RMD/PT-related condition.

NoP is not a mention count, publication count, percentage, rate, prevalence ratio, model estimate, or study score. If a source reports deaths or mortality as an absolute number of people, it can be stored as NoP, but the source note or unit should make that clear.

Do not treat sums across monthly model matrices as unique patient totals. Files such as `data/data.csv` are merged, filled, transformed, and prepared for forecasting.

## Repository Layout

```text
.
|-- data/
|   `-- data.csv                                  # Main checked-in model input matrix
|-- OECD/
|   `-- processed/oecd_pipeline_seed.csv          # OECD seed rows
|-- ScienceDirect_Disease_Pipeline/               # RMD ScienceDirect + CrossRef collector
|-- ScienceDirect_PT_Pipeline/                    # PT ScienceDirect + CrossRef collector
|-- rmdpt_collector/                              # OpenAlex + ClinicalTrials collector package
|-- rmdpt_collector_final_PubMed/                 # PubMed collector package
|-- Reddit_RMDs_Pipeline/                         # Reddit RMD mention collector
|-- Reddit_PTs_Pipeline/                          # Reddit PT mention collector
|-- News_Gnews_Pipeline/                          # GNews/Google News collector
|-- Funding/                                      # Funding-oriented GNews collector
|-- Patents/                                      # Patent mention processing
|-- nop_llm_collect.py                            # Gemini + search-grounded NoP collector
|-- oecd_import.py                                # OECD API import helper
|-- search_terms.py                               # Root RMD compatibility search terms
|-- search_terms_pt.py                            # Root PT compatibility search terms
|-- en_product1.json                              # Patent/product source data
|-- LICENSE
`-- README.md
```

## Current Checked-In Data

The current `data/data.csv` file has:

- 264 monthly rows.
- 190 columns.
- 48 `RMD_*_NoM` columns.
- 88 `PT_*_NoM` columns.
- 48 `RMD_*_NoP` columns.
- 5 external context columns for war, public holidays, and disaster features.

The main external seed file currently checked in is:

- `OECD/processed/oecd_pipeline_seed.csv`

Older README notes referenced additional source and normalized CSVs under `data/data_scorces/` and `data/scripts/`; those paths are not present in this checkout.

## Pipeline Overview

The project is organized as independent source collectors plus a prepared model matrix.

1. **Source collection**
   - `ScienceDirect_Disease_Pipeline/run_pipeline.py` runs the RMD ScienceDirect collector, then optional CrossRef fallback, and writes `Master_RMD_Merged.csv` in that folder.
   - `ScienceDirect_PT_Pipeline/run_pipeline.py` runs the PT ScienceDirect collector, then optional CrossRef fallback, and writes `Master_PT_Merged.csv` in that folder.
   - `rmdpt_collector_final_PubMed/rmdpt_collector/pipelines/collect.py` collects PubMed rows and can emit long, pivot, and NoP CSVs.
   - `rmdpt_collector/pipelines/collect.py` collects OpenAlex and ClinicalTrials rows into `outputs/rmdpt_timeseries.csv`.
   - `Reddit_RMDs_Pipeline/main.py` and `Reddit_PTs_Pipeline/main.py` collect Reddit mentions.
   - `News_Gnews_Pipeline/news_gnews.py` collects monthly news mentions from GNews and Google News HTML results.
   - `Funding/funding.py` collects funding-related news signals.
   - `Patents/patent.py` counts RMD/PT mentions in a patent CSV.

2. **Prepared data**
   - `data/data.csv` is the checked-in monthly feature matrix used by downstream forecasting work.
   - The current checkout does not include a reproducible end-to-end builder that regenerates `data/data.csv` from every raw source.

3. **Entity terms**
   - `search_terms.py` and `search_terms_pt.py` are root compatibility modules.
   - Several current scripts expect an `entity_catalog_v2.py` module that is not included in this checkout.
   - The older standalone collector under `rmdpt_collector/search_terms.py` contains embedded RMD and PT synonym dictionaries and does not depend on the missing root catalog.

## Setup

Use Python 3.9 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pandas numpy requests beautifulsoup4 python-dateutil tqdm holidays
```

Install source-specific dependencies as needed:

```powershell
python -m pip install -r rmdpt_collector\requirements.txt
python -m pip install -r Reddit_PTs_Pipeline\requirements.txt
python -m pip install -r News_Gnews_Pipeline\requirements.txt
python -m pip install -r Patents\requirements.txt
```

The Reddit RMD pipeline uses the same local client pattern as the PT pipeline but does not currently include its own `requirements.txt`; install the Reddit PT requirements if Reddit dependencies are missing.

## Configuration and Secrets

Several collectors require API keys or service credentials. This checkout contains some hard-coded keys and local paths in collector scripts. Before publishing or sharing the repository:

- Move API keys, passwords, and tokens out of tracked files and into environment variables or an untracked local config.
- Rotate any credentials that were previously committed.
- Replace absolute local paths in scripts such as `Patents/patent.py` before running on another machine.
- Add local secret files, caches, virtual environments, generated outputs, and checkpoints to `.gitignore`.

Important current config notes:

- `ScienceDirect_Disease_Pipeline/config_loader.py` and `ScienceDirect_PT_Pipeline/config_loader.py` expect folder-local `config.json` files containing Elsevier API keys; those config files are not present in this checkout.
- `rmdpt_collector_final_PubMed/rmdpt_collector/common/config.py` expects `project_config.json` by default, but that file is not present in this checkout.
- `search_terms.py`, `search_terms_pt.py`, `oecd_import.py`, `nop_llm_collect.py`, and the PubMed package's compatibility search terms import `entity_catalog_v2`; provide that module locally or update those imports before running them.
- `News_Gnews_Pipeline/news_gnews.py` and `Funding/funding.py` contain GNews API key lists directly in code.

## Common Commands

Run commands from the repository root unless the command changes directory.

### Run ScienceDirect RMD Collection

Create `ScienceDirect_Disease_Pipeline/config.json` with Elsevier API keys before running.

```powershell
cd ScienceDirect_Disease_Pipeline
python run_pipeline.py
cd ..
```

Outputs are written in `ScienceDirect_Disease_Pipeline/`, including `Master_RMD_Merged.csv`.

### Run ScienceDirect PT Collection

Create `ScienceDirect_PT_Pipeline/config.json` with Elsevier API keys before running.

```powershell
cd ScienceDirect_PT_Pipeline
python run_pipeline.py
cd ..
```

Outputs are written in `ScienceDirect_PT_Pipeline/`, including `Master_PT_Merged.csv`.

### Run PubMed Collection

This collector expects a config file at `rmdpt_collector_final_PubMed/rmdpt_collector/project_config.json` unless `--config` points somewhere else. It also expects the missing root `entity_catalog_v2.py` module through the compatibility search-term imports.

```powershell
cd rmdpt_collector_final_PubMed
python -m rmdpt_collector.pipelines.collect `
  --terms-file rmdpt_collector\search_terms.py `
  --start-year 2004 `
  --end-year 2026 `
  --sources pubmed `
  --out rmdpt_collector\outputs\pubmed_long.csv `
  --pivot-out rmdpt_collector\outputs\pubmed_pivot.csv `
  --nop-out rmdpt_collector\outputs\pubmed_nop.csv `
  --resume `
  --log-level INFO
cd ..
```

### Run OpenAlex and ClinicalTrials Collection

```powershell
cd rmdpt_collector
python pipelines\collect.py
cd ..
```

This writes collector outputs under `rmdpt_collector/outputs/` using defaults from `rmdpt_collector/common/utils.py`.

### Run Reddit Collectors

```powershell
cd Reddit_RMDs_Pipeline
python main.py
cd ..

cd Reddit_PTs_Pipeline
python main.py
cd ..
```

Expected local outputs:

- `Reddit_RMDs_Pipeline/reddit_rmd_mentions.csv`
- `Reddit_PTs_Pipeline/reddit_pt_mentions.csv`

### Run News and Funding Collectors

```powershell
cd News_Gnews_Pipeline
python news_gnews.py
cd ..

cd Funding
python funding.py
cd ..
```

### Run Patent Mention Processing

Update the input and output paths at the top of `Patents/patent.py` first; the checked-in script currently points to an absolute path under `C:/Users/Ahsan/Downloads/`.

```powershell
cd Patents
python patent.py
cd ..
```

### Run OECD Import

`oecd_import.py` requires the missing `entity_catalog_v2.py` module and uses `data_collection_config.json` by default. If no OECD dataset specs are configured, it writes an empty seed file.

```powershell
python oecd_import.py --output OECD\processed\oecd_pipeline_seed.csv --keep-unmatched
```

### Run Gemini NoP Collection

`nop_llm_collect.py` requires `entity_catalog_v2.py` plus a Gemini API key/configuration. It writes seed and audit outputs under `outputs/` by default.

```powershell
python nop_llm_collect.py --max-entities 5
```

## Data Quality and Reproducibility Notes

- `data/data.csv` is currently the only checked-in final model matrix.
- Source collectors can change results when APIs, search pages, credentials, rate limits, or caches change.
- Several scripts emit generated CSVs into their local folders; those generated files are not all tracked.
- The current checkout does not include the older normalization scripts that were previously documented as `data/scripts/build_rmd_dataset.py`, `data/scripts/build_pt_dataset.py`, or `data/scripts/validate_pt_inventory.py`.
- Keep logs, skipped DOI files, checkpoints, and generated raw outputs when auditing a collection run.

## Publishing Checklist

Before making this repository public:

- Remove or rotate committed API keys, passwords, and tokens.
- Add or verify `.gitignore` entries for credentials, caches, virtual environments, outputs, and checkpoints.
- Replace absolute local paths with relative paths or CLI arguments.
- Confirm redistribution rights for large raw source files and generated CSVs.
- Restore any missing local modules needed for reproducibility, especially `entity_catalog_v2.py` and collector config files.
- Add citation information for upstream data sources used in papers or reports.

## License

MIT License

## Citation

If you use this repository, please cite it as:

```bibtex
@software{br_mtgnn_2026,
  title  = {Long-horizon Forecasting for Rare Mental Health via the Co-evolution of Disorders and Technologies in Multisource Temporal Graphs},
  author = {Ahsan, Shakil Ibne and Yoo, Paul D. and Han, Dongwoon and Damiani, Ernesto},
  year   = {2026},
  url    = {https://github.com/yourusername/BR_MTGNN}
}
```
This repository includes an MIT `LICENSE` file.
