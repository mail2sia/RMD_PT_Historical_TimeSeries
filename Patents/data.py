import pandas as pd
import glob
import os

# ==== CONFIG ====
folder_path = 'C:/Users/Ahsan/Downloads/RMDs-and-PTs-main/Patents/manual_search/'
output_file = 'merged_cleaned_patents.csv'

# ==== STEP 1: Read all CSV files ====
all_files = glob.glob(os.path.join(folder_path, '*.csv'))

df_list = []

for filename in all_files:
    print(f"Reading file: {filename}")
    try:
        # First try reading as MultiIndex
        df = pd.read_csv(filename, header=[0,1])
        # Flatten columns
        df.columns = df.columns.map(lambda x: x[0] if x[0] == x[1] else f"{x[0]}_{x[1]}")
    except pd.errors.ParserError:
        # If not MultiIndex, fallback to normal
        df = pd.read_csv(filename)
    
    # Important: Reset index if needed
    df = df.reset_index()

    # Try to find the correct id/title structure
    if not 'id' in df.columns:
        possible_id_columns = [col for col in df.columns if 'id' in col.lower()]
        if possible_id_columns:
            df.rename(columns={possible_id_columns[0]: 'id'}, inplace=True)
        else:
            print(f"⚠️ Warning: No ID found in file {filename}, skipping.")
            continue

    df_list.append(df)

# ==== STEP 2: Merge ====
print("Merging all files together...")
merged_df = pd.concat(df_list, ignore_index=True)

# ==== STEP 3: Check and Deduplicate ====
print(f"Total rows before deduplication: {len(merged_df)}")

if 'id' not in merged_df.columns:
    raise ValueError("❌ Error: 'id' column still missing after trying to fix columns!")

# Drop duplicate IDs
merged_df = merged_df.drop_duplicates(subset=['id'], keep='first')

print(f"Total rows after removing duplicate IDs: {len(merged_df)}")

# ==== STEP 4: Save the result ====
merged_df.to_csv(output_file, index=False)
print(f"✅ Final cleaned file saved: {output_file}")
