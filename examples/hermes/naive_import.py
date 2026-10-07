"""Deliberately naive parser used as the failure case in the demo."""

import csv
from pathlib import Path

with Path(__file__).with_name("invoice.csv").open() as f:
    rows = list(csv.DictReader(f))
print(sum(float(row["total_usd"]) for row in rows))
