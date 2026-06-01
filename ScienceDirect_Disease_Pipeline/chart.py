import pandas as pd
import matplotlib.pyplot as plt

# Load the data
df = pd.read_csv("Master_RMD_Merged.csv")

# Parse and extract year
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["year"] = df["date"].dt.year

# Clean out rows with missing year
df = df.dropna(subset=["year"])
df["year"] = df["year"].astype(int)

# Group by year and disease
df_grouped = df.groupby(["year", "disease"])["NoM"].sum().reset_index()

# Optional: filter out diseases with very low total mentions (uncomment to use)
# top_diseases = df_grouped.groupby("disease")["NoM"].sum()
# top_diseases = top_diseases[top_diseases > 10].index
# df_grouped = df_grouped[df_grouped["disease"].isin(top_diseases)]

# Pivot to create one column per disease
df_pivot = df_grouped.pivot(index="year", columns="disease", values="NoM").fillna(0)
df_pivot = df_pivot.sort_index()

# Plot the final chart
ax = df_pivot.plot(kind="line", marker="o", figsize=(14, 8))
plt.title("Number of Mentions per Rare Mental Disease Over Time")
plt.xlabel("Year")
plt.ylabel("Total Mentions (NoM)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.legend(title="Disease", bbox_to_anchor=(1.05, 1), loc="upper left")
plt.show()
