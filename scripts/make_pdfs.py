"""Generate the synthetic PDF corpus (contracts + project briefs, English + Hebrew).

These are realistic business documents that pair with the SQLite data so the
hybrid questions have something to retrieve. Clause numbers (penalties, service
suspension), an SLA identifier ("SLA-2025"), and per-project Risk sections are all
deliberately present so the demo questions are answerable WITH citations.

Pages are not tracked here — the ingestion pipeline extracts real page numbers from
the rendered PDFs, so citations always point at the true page.
"""
from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]

FONT = "Body"
FONT_BOLD = "BodyBold"


def _register_fonts() -> None:
    regular = next((p for p in _FONT_CANDIDATES if os.path.exists(p)), None)
    bold = next((p for p in _BOLD_CANDIDATES if os.path.exists(p)), None)
    if regular:
        pdfmetrics.registerFont(TTFont(FONT, regular))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, bold or regular))
    else:  # last resort — built-in (no Hebrew glyphs, English still fine)
        globals()["FONT"] = "Helvetica"
        globals()["FONT_BOLD"] = "Helvetica-Bold"


def _styles():
    ss = getSampleStyleSheet()
    title = ParagraphStyle("DocTitle", parent=ss["Title"], fontName=FONT_BOLD, fontSize=18)
    heading = ParagraphStyle("Heading", parent=ss["Heading2"], fontName=FONT_BOLD, fontSize=12, spaceBefore=12)
    body = ParagraphStyle("BodyText2", parent=ss["BodyText"], fontName=FONT, fontSize=10.5, leading=15)
    body_rtl = ParagraphStyle("BodyRTL", parent=body, alignment=TA_RIGHT)
    heading_rtl = ParagraphStyle("HeadingRTL", parent=heading, alignment=TA_RIGHT)
    title_rtl = ParagraphStyle("TitleRTL", parent=title, alignment=TA_RIGHT)
    return dict(
        title=title, heading=heading, body=body,
        body_rtl=body_rtl, heading_rtl=heading_rtl, title_rtl=title_rtl,
    )


def _unescape(s: str) -> str:
    return (s.replace("&quot;", '"').replace("&amp;", "&")
             .replace("&lt;", "<").replace("&gt;", ">"))


def _build(filename: str, title: str, sections: list[tuple[str, list[str]]],
           rtl: bool = False, sidecar: bool = False) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    st = _styles()
    doc = SimpleDocTemplate(
        str(PDF_DIR / filename), pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title=title,
    )
    flow = [Paragraph(title, st["title_rtl" if rtl else "title"]), Spacer(1, 14)]
    for heading, paras in sections:
        flow.append(Paragraph(heading, st["heading_rtl" if rtl else "heading"]))
        for p in paras:
            flow.append(Paragraph(p, st["body_rtl" if rtl else "body"]))
            flow.append(Spacer(1, 4))
        flow.append(Spacer(1, 6))
    doc.build(flow)

    # For RTL documents, also emit a clean logical-order text layer. PDF extractors
    # jumble RTL numbers across lines; a production pipeline would use a Hebrew-aware
    # parser/OCR to produce exactly this. Ingestion prefers the sidecar when present.
    if sidecar:
        lines = [_unescape(title), ""]
        for heading, paras in sections:
            lines.append(_unescape(heading))
            lines.extend(_unescape(p) for p in paras)
            lines.append("")
        (PDF_DIR / filename).with_suffix(".txt").write_text(
            "\n".join(lines), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# English contracts
# ---------------------------------------------------------------------------
def contract(ref: str, customer: str, suspend_days: int, penalty_pct: int, late_fee: str):
    return [
        ("1. Parties and Purpose", [
            f"This Master Services Agreement (the &quot;Agreement&quot;, reference {ref}) is entered into between "
            f"Northwind Solutions Ltd. (&quot;Provider&quot;) and {customer} (&quot;Customer&quot;) for the provision of "
            "managed logistics and data services.",
        ]),
        ("2. Term and Renewal", [
            "The initial term commences on the Effective Date and continues for twenty-four (24) months unless "
            "terminated earlier in accordance with this Agreement. Renewal is automatic for successive twelve (12) "
            "month periods unless either party provides sixty (60) days written notice.",
        ]),
        ("3. Fees and Invoicing", [
            "Customer shall pay all undisputed invoices within thirty (30) days of the invoice date. "
            f"Overdue amounts accrue interest and a late payment fee of {late_fee}.",
        ]),
        ("4. Service Levels (SLA-2025)", [
            "Provider shall meet the service levels defined in schedule SLA-2025, including 99.5% monthly uptime "
            "and a four (4) hour response time for priority incidents. Service credits apply for breaches of SLA-2025.",
        ]),
        ("5. Service Suspension", [
            f"Provider may suspend the Services, in whole or in part, if any undisputed invoice remains unpaid for more "
            f"than {suspend_days} days after its due date. Provider shall give Customer five (5) business days written "
            "notice prior to suspension. Services will be restored within two (2) business days of full payment of "
            "outstanding amounts.",
        ]),
        ("6. Termination and Penalties", [
            f"Either party may terminate for material breach not cured within thirty (30) days. If Customer terminates "
            f"for convenience before the end of the term, Customer shall pay an early termination penalty equal to "
            f"{penalty_pct}% of the remaining contract value. Penalties are in addition to any unpaid fees.",
        ]),
        ("7. Confidentiality and Data", [
            "Each party shall protect the other's confidential information and process personal data in accordance "
            "with applicable law and the Data Processing Addendum attached to this Agreement.",
        ]),
    ]


def project_brief(name: str, customer: str, risks: list[str], mitigations: list[str]):
    return [
        ("1. Overview", [
            f"Project {name} delivers a managed implementation for {customer}, covering onboarding, data migration, "
            "and integration with the Customer's existing systems.",
        ]),
        ("2. Scope", [
            "In scope: discovery, environment setup, data migration, two integration endpoints, user training, and "
            "thirty (30) days of hypercare. Out of scope: custom hardware procurement and third-party license costs.",
        ]),
        ("3. Timeline", [
            "The project runs across four phases — Discovery, Build, Migrate, and Stabilize — with go-live targeted "
            "at the end of Phase 3 and a stabilization window in Phase 4.",
        ]),
        ("4. Risks", [f"R{i+1}. {r}" for i, r in enumerate(risks)]),
        ("5. Mitigations", [f"M{i+1}. {m}" for i, m in enumerate(mitigations)]),
    ]


# ---------------------------------------------------------------------------
# Hebrew contract (logical-order Hebrew; glyphs via DejaVuSans, UI renders RTL)
# ---------------------------------------------------------------------------
def hebrew_contract():
    return [
        ("‎1. הצדדים ומטרת ההסכם", [
            "הסכם שירותים זה (להלן: &quot;ההסכם&quot;, מספר אסמכתא TVR-MSA-2025) נכרת בין נורת'ווינד פתרונות בע&quot;מ "
            "(&quot;נותן השירות&quot;) לבין תבור מערכות בע&quot;מ (&quot;הלקוח&quot;) לאספקת שירותי לוגיסטיקה וניהול נתונים.",
        ]),
        ("‎2. תקופת ההתקשרות", [
            "תקופת ההתקשרות הראשונית הינה עשרים וארבעה (24) חודשים ותתחדש מאליה לתקופות נוספות אלא אם נמסרה הודעה "
            "מוקדמת בכתב של שישים (60) יום.",
        ]),
        ("‎3. תשלומים וחשבוניות", [
            "הלקוח ישלם כל חשבונית שאינה שנויה במחלוקת בתוך שלושים (30) יום ממועד הוצאתה. על סכומים באיחור ייווסף "
            "קנס פיגורים בשיעור 1.5% לחודש.",
        ]),
        ("‎4. רמת השירות (SLA-2025)", [
            "נותן השירות יעמוד ברמות השירות המוגדרות בנספח SLA-2025, לרבות זמינות חודשית של 99.5% וזמן תגובה של "
            "ארבע (4) שעות לתקלות בעדיפות גבוהה.",
        ]),
        ("‎5. השעיית שירות", [
            "נותן השירות רשאי להשעות את השירותים אם חשבונית שאינה שנויה במחלוקת לא שולמה במשך למעלה מארבעים וחמישה "
            "(45) יום ממועד הפירעון, ובכפוף להודעה מוקדמת של חמישה (5) ימי עסקים. השירות יחודש בתוך שני (2) ימי עסקים "
            "ממועד התשלום המלא.",
        ]),
        ("‎6. סיום ההסכם וקנסות", [
            "במקרה של סיום ההסכם על ידי הלקוח מטעמי נוחות לפני תום התקופה, ישלם הלקוח קנס יציאה בשיעור 12% מיתרת "
            "שווי ההסכם, בנוסף לכל סכום שטרם שולם.",
        ]),
    ]


def main() -> None:
    _register_fonts()

    _build("ACME_MSA_2025.pdf", "Master Services Agreement — Acme Corporation",
           contract("ACM-MSA-2025", "Acme Corporation", suspend_days=30, penalty_pct=15, late_fee="1.5% per month"))

    _build("GLOBEX_Service_Agreement.pdf", "Service Agreement — Globex Industries",
           contract("GLX-SA-2025", "Globex Industries", suspend_days=45, penalty_pct=10, late_fee="2.0% per month"))

    _build("INITECH_Agreement.pdf", "Master Services Agreement — Initech LLC",
           contract("INI-MSA-2024", "Initech LLC", suspend_days=30, penalty_pct=12, late_fee="1.5% per month"))

    _build("UMBRELLA_Agreement.pdf", "Service Agreement — Umbrella Group",
           contract("UMB-SA-2025", "Umbrella Group", suspend_days=60, penalty_pct=20, late_fee="1.0% per month"))

    _build("STARK_Agreement.pdf", "Master Services Agreement — Stark Industries",
           contract("STK-MSA-2025", "Stark Industries", suspend_days=30, penalty_pct=15, late_fee="1.5% per month"))

    _build("TAVOR_Contract_HE.pdf", "‎הסכם שירותים — תבור מערכות בע\"מ",
           hebrew_contract(), rtl=True, sidecar=True)

    _build("PRJ_ATLAS_Brief.pdf", "Project Atlas — Implementation Brief (Acme Corporation)",
           project_brief(
               "Atlas", "Acme Corporation",
               risks=[
                   "Schedule risk: the data migration depends on a legacy export that has slipped twice; a further "
                   "delay would push go-live beyond the contractual milestone.",
                   "Vendor dependency: a third-party customs API is on the critical path and has no contractual SLA "
                   "with us.",
                   "Data quality risk: roughly 8% of legacy shipment records are missing destination codes and require "
                   "manual remediation.",
               ],
               mitigations=[
                   "Negotiate a fixed export window with the legacy vendor and add a fallback manual export.",
                   "Add a circuit-breaker and cache around the customs API; escalate an SLA addendum.",
                   "Run an automated data-quality sweep before migration and triage exceptions.",
               ]))

    _build("PRJ_ORION_Brief.pdf", "Project Orion — Implementation Brief (Globex Industries)",
           project_brief(
               "Orion", "Globex Industries",
               risks=[
                   "Budget risk: integration scope grew after discovery; current burn trends 12% over the approved "
                   "budget.",
                   "Integration risk: the Customer's ERP is mid-upgrade, so the target API contract may change during "
                   "the build phase.",
                   "Resourcing risk: a key integration engineer is shared with another account and only 50% allocated.",
               ],
               mitigations=[
                   "Re-baseline scope with a change request and a prioritized cut-list.",
                   "Pin to the current ERP API version and add a compatibility shim for the upgrade.",
                   "Secure a backfill engineer and document the integration to reduce bus-factor.",
               ]))

    _build("PRJ_NOVA_Brief.pdf", "Project Nova — Implementation Brief (Stark Industries)",
           project_brief(
               "Nova", "Stark Industries",
               risks=[
                   "Regulatory risk: the solution processes regulated trade data and must pass a compliance review "
                   "before go-live; the review slot is not yet booked.",
                   "Security risk: a penetration test is required by the Customer and has a four-week lead time.",
                   "Adoption risk: end-user training has low sign-up so far, threatening post-go-live adoption.",
               ],
               mitigations=[
                   "Book the compliance review now and prepare the evidence pack in parallel.",
                   "Schedule the penetration test at the start of the Build phase.",
                   "Add manager-nominated training cohorts and a short enablement series.",
               ]))

    print(f"Wrote {len(list(PDF_DIR.glob('*.pdf')))} PDFs to {PDF_DIR}")


if __name__ == "__main__":
    main()
