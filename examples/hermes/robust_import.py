"""Parser for this fixture's documented format; not a universal CSV parser."""

import csv
from decimal import Decimal
from pathlib import Path

with Path(__file__).with_name("invoice.csv").open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
    assert reader.fieldnames == ["invoice_id", "total_usd"], "Unexpected invoice schema"
    rows = list(reader)
    total = sum((Decimal(row["total_usd"]) for row in rows), Decimal("0"))
assert len(rows) == 3 and total == Decimal("125.50")
print(f"PASS: imported {len(rows)} invoices; total USD {total:.2f}")
