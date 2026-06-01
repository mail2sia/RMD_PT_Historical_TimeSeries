# main_pt.py
from search_reddit import search_reddit_pt_mentions_by_day


def main():
    df = search_reddit_pt_mentions_by_day()
    df.to_csv("reddit_pt_mentions.csv", index=False)
    print("✅ Saved to reddit_pt_mentions.csv")

if __name__ == "__main__":
    main()
