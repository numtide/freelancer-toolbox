import csv
import sys
from datetime import date
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <csv_file>")
        print(
            "Go to https://numtide.harvestapp.com/reports?kind=year and export the CSV for the year"
        )
        sys.exit(1)

    csv_file = Path(sys.argv[1])
    with csv_file.open(newline="") as f:
        dates = {date.fromisoformat(row["Date"]) for row in csv.DictReader(f)}

    if not dates:
        print("No entries found in CSV")
        sys.exit(1)

    print(f"Working days: {len(dates)} from {min(dates)} to {max(dates)}")


if __name__ == "__main__":
    main()
