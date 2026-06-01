import subprocess
import pandas as pd
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

def run_script(script_name, required=True):
    print(f"\n🚀 Running: {script_name}")
    result = subprocess.run([sys.executable, script_name], cwd=HERE)
    if result.returncode != 0:
        print(f"❌ Failed: {script_name}")
        if required:
            sys.exit(1)
        print(f"⚠️ Continuing without optional step: {script_name}")

# Step 1: Run main.py (Scopus)
run_script("main.py")

# Step 2: Run CrossRef fallback (optional resilience step)
run_script("main_rmd_crossref.py", required=False)

# Step 3: Merge both outputs
scopus_file = os.path.join(HERE, "collected_Diseases_NoM.csv")
crossref_file = os.path.join(HERE, "collected_RMD_CrossRef_NoM.csv")
merged_file = os.path.join(HERE, "Master_RMD_Merged.csv")

df_scopus = pd.read_csv(scopus_file) if os.path.exists(scopus_file) else pd.DataFrame()
df_crossref = pd.read_csv(crossref_file) if os.path.exists(crossref_file) else pd.DataFrame()

# Combine and deduplicate
df_all = pd.concat([df_scopus, df_crossref], ignore_index=True)
df_all.drop_duplicates(subset=["doi", "disease"], keep="first", inplace=True)

# Optional: sort by date
if "date" in df_all.columns:
    df_all["date"] = pd.to_datetime(df_all["date"], errors="coerce")
    df_all = df_all.sort_values("date")

# Save final merged output
df_all.to_csv(merged_file, index=False)
print(f"\n✅ Merged dataset saved as: {merged_file}")
