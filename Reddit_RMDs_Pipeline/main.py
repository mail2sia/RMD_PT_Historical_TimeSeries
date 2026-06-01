from search_reddit import search_reddit_rmd_mentions_by_day


def main():
    df = search_reddit_rmd_mentions_by_day()
    df.to_csv("reddit_rmd_mentions.csv", index=False)
    print("Saved to reddit_rmd_mentions.csv")


if __name__ == "__main__":
    main()
