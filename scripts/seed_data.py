"""Generate the synthetic business SQLite database.

Schema: customers, contracts, invoices, projects, payments.
Dates are anchored to the demo date (2026-06-08) so "expiring in 90 days" and
"overdue" are always live and reproducible. Rows are aligned with the PDF corpus
(scripts/make_pdfs.py) so the hybrid questions resolve cleanly end-to-end.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "business.db"

TODAY = "2026-06-08"  # demo anchor

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT,
    country TEXT,
    contact_email TEXT
);
CREATE TABLE contracts (
    id INTEGER PRIMARY KEY,
    contract_ref TEXT UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    title TEXT,
    pdf_file TEXT,           -- links a contract row to its source PDF (enables agentic hybrid)
    start_date TEXT,
    end_date TEXT,
    value_usd REAL,
    status TEXT,             -- active | expired | terminated
    sla_ref TEXT
);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    invoice_ref TEXT UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    contract_id INTEGER REFERENCES contracts(id),
    issue_date TEXT,
    due_date TEXT,
    amount_usd REAL,
    status TEXT              -- paid | pending | overdue
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    project_ref TEXT UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    name TEXT,
    status TEXT,             -- active | completed | on_hold
    start_date TEXT,
    target_end_date TEXT,
    doc_file TEXT            -- links a project to its brief PDF
);
CREATE TABLE payments (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER REFERENCES invoices(id),
    paid_date TEXT,
    amount_usd REAL
);
"""

CUSTOMERS = [
    (1, "Acme Corporation", "Logistics", "USA", "ap@acme.example"),
    (2, "Globex Industries", "Manufacturing", "USA", "billing@globex.example"),
    (3, "Initech LLC", "Software", "USA", "accounts@initech.example"),
    (4, "Umbrella Group", "Pharmaceuticals", "UK", "finance@umbrella.example"),
    (5, "Stark Industries", "Aerospace", "USA", "ar@stark.example"),
    (6, "Tavor Systems", "Technology", "Israel", "finance@tavor.example"),
]

# id, ref, customer_id, title, pdf_file, start, end, value, status, sla
CONTRACTS = [
    (1, "ACM-MSA-2025", 1, "Master Services Agreement", "ACME_MSA_2025.pdf",
     "2024-08-20", "2026-08-20", 480000, "active", "SLA-2025"),
    (2, "GLX-SA-2025", 2, "Service Agreement", "GLOBEX_Service_Agreement.pdf",
     "2024-07-10", "2026-07-10", 360000, "active", "SLA-2025"),
    (3, "INI-MSA-2024", 3, "Master Services Agreement", "INITECH_Agreement.pdf",
     "2025-03-01", "2027-03-01", 250000, "active", "SLA-2025"),
    (4, "UMB-SA-2025", 4, "Service Agreement", "UMBRELLA_Agreement.pdf",
     "2024-12-15", "2026-12-15", 300000, "active", "SLA-2025"),
    (5, "STK-MSA-2025", 5, "Master Services Agreement", "STARK_Agreement.pdf",
     "2024-06-29", "2026-06-29", 540000, "active", "SLA-2025"),
    (6, "TVR-MSA-2025", 6, "Service Agreement (Hebrew)", "TAVOR_Contract_HE.pdf",
     "2024-09-01", "2026-09-01", 220000, "active", "SLA-2025"),
]

# id, ref, customer_id, contract_id, issue, due, amount, status
INVOICES = [
    # overdue
    (1, "INV-1187", 1, 1, "2026-04-20", "2026-05-20", 42000, "overdue"),
    (2, "INV-1201", 1, 1, "2026-05-01", "2026-05-31", 18000, "overdue"),
    (3, "INV-1190", 2, 2, "2026-04-25", "2026-05-25", 30000, "overdue"),
    (4, "INV-1175", 3, 3, "2026-04-10", "2026-05-10", 15000, "overdue"),
    # pending
    (5, "INV-1240", 1, 1, "2026-06-01", "2026-07-01", 40000, "pending"),
    (6, "INV-1230", 5, 5, "2026-05-20", "2026-06-19", 45000, "pending"),
    (7, "INV-1228", 4, 4, "2026-05-15", "2026-06-14", 25000, "pending"),
    (8, "INV-1235", 6, 6, "2026-05-22", "2026-06-21", 18000, "pending"),
    # paid
    (9, "INV-1100", 2, 2, "2026-02-10", "2026-03-12", 30000, "paid"),
    (10, "INV-1090", 1, 1, "2026-01-20", "2026-02-19", 40000, "paid"),
    (11, "INV-1110", 3, 3, "2026-02-15", "2026-03-17", 15000, "paid"),
    (12, "INV-1120", 5, 5, "2026-03-01", "2026-03-31", 45000, "paid"),
]

# id, ref, customer_id, name, status, start, target_end, doc
PROJECTS = [
    (1, "PRJ-ATLAS", 1, "Atlas", "active", "2026-02-01", "2026-08-15", "PRJ_ATLAS_Brief.pdf"),
    (2, "PRJ-ORION", 2, "Orion", "active", "2026-03-01", "2026-09-30", "PRJ_ORION_Brief.pdf"),
    (3, "PRJ-NOVA", 5, "Nova", "active", "2026-04-01", "2026-10-31", "PRJ_NOVA_Brief.pdf"),
    (4, "PRJ-HELIOS", 3, "Helios", "completed", "2025-09-01", "2026-02-28", None),
    (5, "PRJ-ZEPHYR", 4, "Zephyr", "on_hold", "2026-01-15", "2026-07-31", None),
]

# id, invoice_id, paid_date, amount
PAYMENTS = [
    (1, 9, "2026-03-05", 30000),
    (2, 10, "2026-02-10", 40000),
    (3, 11, "2026-03-10", 15000),
    (4, 12, "2026-03-28", 45000),
]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", CUSTOMERS)
    con.executemany("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?)", CONTRACTS)
    con.executemany("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?)", INVOICES)
    con.executemany("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?)", PROJECTS)
    con.executemany("INSERT INTO payments VALUES (?,?,?,?)", PAYMENTS)
    con.commit()
    counts = {
        t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("customers", "contracts", "invoices", "projects", "payments")
    }
    con.close()
    print(f"Wrote {DB_PATH} (anchor date {TODAY}): {counts}")


if __name__ == "__main__":
    main()
