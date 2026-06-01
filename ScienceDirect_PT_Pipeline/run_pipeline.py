import subprocess
import pandas as pd
import os
import sys

def run_script(script_name, required=True):
    print(f"🚀 Running: {script_name}")
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"❌ Failed: {script_name}")
        if required:
            sys.exit(1)
        print(f"⚠️ Continuing without optional step: {script_name}")

# Step 1: Run Scopus/Elsevier pipeline
run_script("main.py")

# Step 2: Run CrossRef fallback pipeline (optional resilience step)
run_script("main_pt_crossref.py", required=False)

# Step 3: Merge both outputs
scopus_file = "collected_PT_NoM.csv"
crossref_file = "collected_PT_CrossRef_NoM.csv"
merged_file = "Master_PT_Merged.csv"

df_scopus = pd.read_csv(scopus_file) if os.path.exists(scopus_file) else pd.DataFrame()
df_crossref = pd.read_csv(crossref_file) if os.path.exists(crossref_file) else pd.DataFrame()

# Combine, deduplicate
df_all = pd.concat([df_scopus, df_crossref], ignore_index=True)
df_all.drop_duplicates(subset=["doi", "technology"], keep="first", inplace=True)

# Sort by date if available
if "date" in df_all.columns:
    df_all["date"] = pd.to_datetime(df_all["date"], errors="coerce")
    df_all = df_all.sort_values("date")

# Save output
df_all.to_csv(merged_file, index=False)
print(f"✅ Merged dataset saved as: {merged_file}")
