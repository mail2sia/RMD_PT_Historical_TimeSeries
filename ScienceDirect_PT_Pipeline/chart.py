import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.nonparametric.smoothers_lowess import lowess

# Load your PT output
df = pd.read_csv("collected_PT_NoM.csv")
df["date"] = pd.to_datetime(df["date"], errors="coerce")
df["year"] = df["date"].dt.year

df = df.dropna(subset=["year"])
df["year"] = df["year"].astype(int)

grouped = df.groupby(["year", "technology"])["NoM"].sum().reset_index()
pivot = grouped.pivot(index="year", columns="technology", values="NoM").fillna(0)
pivot = pivot.sort_index()

plt.figure(figsize=(14, 8))
for tech in pivot.columns:
    y = pd.to_numeric(pivot[tech], errors='coerce')
    x = pivot.index.values
    if (y > 0).sum() < 3:
        continue
    smoothed = lowess(y, x, frac=0.3, return_sorted=False)
    plt.plot(x, smoothed, label=tech)

plt.title("LOESS-Smoothed Mentions of Pertinent Technologies Over Time")
plt.xlabel("Year")
plt.ylabel("Total Mentions (Smoothed NoM)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.legend(title="Technology", bbox_to_anchor=(1.05, 1), loc="upper left")
plt.show()
