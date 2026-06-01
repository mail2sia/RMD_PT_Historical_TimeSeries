# RMD/PT Data Pipeline Notes

This workspace contains the collected RMD/PT source data and the prepared model input files under `data/`.

## NoP Definition

`NoP` means **Number of Patients**: an absolute real-world human count extracted from a source. Valid NoP values are counts of people diagnosed with, affected by, living with, documented as cases of, or explicitly reported as dying from an RMD/PT-related condition.

NoP is not a mention count, publication count, percentage, rate, prevalence ratio, model estimate, or study score. If a source reports deaths or mortality as an absolute number of people, it can be stored as NoP, but the source note/unit must make that clear. In the currently unit-tagged local source files, the unit is `patients`.

## Current NoP Inventory

These counts are from the existing checked-in CSVs. No dataset regeneration is required for them.

| File | Meaning | Nonzero NoP rows | Entity coverage | Sum of raw NoP values |
| --- | --- | ---: | ---: | ---: |
| `data/data_scorces/collected_RMD_NoP.csv` | ScienceDirect RMD NoP source rows | 135 | 37 RMDs | 1,549,549 |
| `data/data_scorces/collected_RMD_CrossRef_NoP.csv` | CrossRef RMD NoP source rows | 0 | 0 RMDs | 0 |
| `data/data_scorces/nop_llm_seed_RMD.csv` | LLM/web-seeded RMD NoP rows | 95 | 36 RMDs | 6,542,437 |
| `data/data_scorces/pubmed_nop_RMD.csv` | PubMed RMD NoP source rows | 1,039 | 31 RMDs | 92,435,985 |
| `data/rmd_dataset_from_sources_all.csv` | Deduplicated RMD NoP rows used for RMD pivoting | 701 | 47 RMDs | 9,493,370 |
| `data/data_scorces/collected_PT_NoP.csv` | PT NoP source rows | 51 | 25 PTs | 179,321 |

The final model input `data/data.csv` contains:

- 48 `RMD_*_NoM` columns
- 48 `RMD_*_NoP` columns
- 89 `PT_*_NoM` columns in the current file, including the previously identified bad PT-prefixed `Chronic Traumatic Encephalopathy` column
- 0 valid `PT_*_NoP` model columns

For manuscript reporting, describe NoP as **real absolute patient/death counts** and report the RMD NoP source/pivot coverage separately from the modeled monthly feature matrix. Do not treat the sum of `data/data.csv` NoP columns as the number of unique patients; that matrix is monthly, merged, filled, and prepared for forecasting.

## PT Count Guard

The pipeline now guards against RMD labels leaking into PT builds:

- `data/scripts/build_pt_dataset.py` rejects exact RMD aliases during PT resolution.
- RMD-only source CSVs are skipped when building PT datasets.
- `data/scripts/validate_pt_inventory.py` validates the final PT inventory without modifying any data.

Run this read-only check after manual data edits:

```powershell
python data\scripts\validate_pt_inventory.py --data-csv data\data.csv --nodes-csv data\nodes.csv --expected-pt-count 88
```

Expected current behavior: the validator reports 88 valid PTs and flags `Chronic Traumatic Encephalopathy` if it is still present as a `PT_` column.

