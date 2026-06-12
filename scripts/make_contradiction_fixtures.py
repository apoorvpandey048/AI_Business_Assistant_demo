"""Generate the synthetic CONTRADICTION corpus (Trust & Evaluation Sprint, WS6).

Two fixture sets land in data/eval/contradictions/:

1. CONTRA_Amendment_2026.pdf — an "amendment" document that deliberately
   CONTRADICTS the bundled sample database (data/business.db):
   - invoice INV-1187: paid in full 2026-06-01     (DB: status=overdue)
   - contract ACM-MSA-2025: expires 2027-08-20     (DB: end_date=2026-08-20)
   - early-termination penalty: 20%                (ACME_MSA_2025.pdf: 15%)
   - invoice INV-1201 amount: $19,500              (DB: amount_usd=18000)
   Upload this PDF next to the sample corpus and the conflict detector MUST fire.

2. vortex.db + VORTEX_Agreement.pdf — a self-contained customer ("Vortex
   Analytics", invoice INV-9001) whose database and contract disagree on payment
   status (paid/unpaid), expiry (2028-03-15 / 2027-03-15), penalty (10% / 15%),
   amount ($18,000 / $18,500) and account status (active / suspended). Used by
   detector unit tests and live evaluation sessions.

The corpus is synthetic and entity-disjoint from real customers; entities were
chosen so nothing collides with the sample data except where a collision IS the
test (INV-1187 / INV-1201 / ACM-MSA-2025).

Usage: .venv/bin/python scripts/make_contradiction_fixtures.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "eval" / "contradictions"

from scripts.make_pdfs import _build, _register_fonts  # noqa: E402  (same renderer)
import scripts.make_pdfs as make_pdfs                  # noqa: E402


def amendment_sections():
    return [
        ("1. Purpose of this Amendment", [
            "This Amendment records updated commercial terms and updated invoice payment "
            "status for overdue invoices under the Master Services Agreement with "
            "Acme Corporation (reference ACM-MSA-2025).",
        ]),
        ("2. Payment Status Updates", [
            "Payment update: invoice INV-1187 was paid in full on 2026-06-01.",
            "Correction: the total amount of invoice INV-1201 is $19,500, not the amount "
            "previously recorded.",
        ]),
        ("3. Term Extension", [
            "The parties agree to extend the term: the Agreement ACM-MSA-2025 now expires "
            "on 2027-08-20.",
        ]),
        ("4. Revised Termination Penalty", [
            "The early termination penalty under ACM-MSA-2025 is revised to 20% of the "
            "remaining contract value.",
        ]),
    ]


def vortex_sections():
    return [
        ("1. Parties and Purpose", [
            "This Master Services Agreement (reference VTX-MSA-2026) is entered into "
            "between Northwind Solutions Ltd. (\"Provider\") and Vortex Analytics "
            "(\"Customer\") for managed data analytics services.",
        ]),
        ("2. Term", [
            "The Agreement VTX-MSA-2026 expires on 2027-03-15 and does not renew "
            "automatically.",
        ]),
        ("3. Fees and Invoicing", [
            "Invoice INV-9001 in the amount of $18,500 remains unpaid as of June 2026.",
        ]),
        ("4. Termination and Penalties", [
            "Early termination by the Customer incurs a penalty equal to 15% of the "
            "remaining contract value under VTX-MSA-2026.",
        ]),
        ("5. Account Standing", [
            "Following repeated non-payment, the account of Vortex Analytics is "
            "suspended until all outstanding amounts are settled.",
        ]),
    ]


def make_vortex_db(path: Path) -> None:
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE crm_customers (
            id INTEGER PRIMARY KEY, name TEXT, status TEXT, country TEXT
        );
        CREATE TABLE crm_contracts (
            id INTEGER PRIMARY KEY, contract_ref TEXT, customer TEXT,
            end_date TEXT, penalty_pct REAL, value_usd REAL, status TEXT
        );
        CREATE TABLE crm_invoices (
            id INTEGER PRIMARY KEY, invoice_ref TEXT, customer TEXT,
            amount_usd REAL, status TEXT, due_date TEXT
        );
        INSERT INTO crm_customers VALUES (1, 'Vortex Analytics', 'active', 'USA');
        INSERT INTO crm_contracts VALUES
            (1, 'VTX-MSA-2026', 'Vortex Analytics', '2028-03-15', 10.0, 150000.0, 'active');
        INSERT INTO crm_invoices VALUES
            (1, 'INV-9001', 'Vortex Analytics', 18000.0, 'paid', '2026-04-30');
        """
    )
    con.commit()
    con.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _register_fonts()
    make_pdfs.PDF_DIR = OUT  # render into the contradiction corpus, not data/pdfs
    _build("CONTRA_Amendment_2026.pdf",
           "Amendment No. 1 — Master Services Agreement (Acme Corporation)",
           amendment_sections())
    _build("VORTEX_Agreement.pdf",
           "Master Services Agreement — Vortex Analytics",
           vortex_sections())
    make_vortex_db(OUT / "vortex.db")
    print(f"Wrote contradiction fixtures to {OUT}")


if __name__ == "__main__":
    main()
