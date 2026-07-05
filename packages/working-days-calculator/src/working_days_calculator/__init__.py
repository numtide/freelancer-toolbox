import sys

import pandas as pd


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <csv_file>")
        print(
            "Go to https://numtide.harvestapp.com/reports?kind=year and export the CSV for the year"
        )
        sys.exit(1)

    csv_file = sys.argv[1]
    df = pd.read_csv(csv_file, parse_dates=["Date"])
    working_days = len(df["Date"].unique())
    start = df["Date"].min()
    end = df["Date"].max()
    print(f"Working days: {working_days} from {start} to {end}")


if __name__ == "__main__":
    main()
