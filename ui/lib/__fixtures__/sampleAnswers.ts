// Local visual-testing fixtures for the Cases / viz sprint. Not imported by
// the app — kept so an integrator can eyeball the rendering against the
// locked AskResponse contract (ui/lib/types.ts).
import type { AskResponse } from "@/lib/types";

export const sampleTriage: AskResponse = {
  question: "Triage the active cases.",
  answer:
    "Three cases were reviewed. **Mohammed Ben** is on life support [e1]. " +
    "Sarah Cohen is stable and recovering [e2].\n\n" +
    "| Case | Status | Owner |\n| --- | --- | --- |\n" +
    "| Mohammed Ben | Critical [e1] | Dr. Levi |\n| Sarah Cohen | Stable [e2] | Dr. Adler |",
  insufficient: false,
  citations: [],
  trace: {
    question: "Triage the active cases.",
    languages: ["en"],
    notes: [],
    sql_executions: [],
    evidence: [],
    generation: {},
    llm_calls: [],
    timings: [],
    mode: "stub",
  },
  triage: {
    defined: true,
    legend: { red: "Life support", green: "Recovering", blue: "Routine follow-up" },
    note: "Buckets follow the clinic's own colour rules.",
    items: [
      { label: "Mohammed Ben", level: "red", summary: "On ventilator after hip fracture.", evidence_ids: ["e1"], rule: "ICU admission" },
      { label: "Sarah Cohen", level: "green", summary: "Discharged to rehab, improving.", evidence_ids: ["e2"], rule: null },
      { label: "David Katz", level: "blue", summary: "Annual checkup scheduled.", evidence_ids: [], rule: null },
    ],
  },
  timeline: [
    { date: "2026-01-12", title: "Admission", detail: "Mohammed Ben admitted with hip fracture.", evidence_ids: ["e1"] },
    { date: "2026-02-03", title: "Surgery", detail: "Hip replacement performed.", evidence_ids: ["e1"] },
    { date: "2026-03-20", title: "Discharge", detail: "Sarah Cohen discharged to rehab.", evidence_ids: ["e2"] },
  ],
  tables: [
    {
      title: "Medication schedule",
      columns: ["Drug", "Dose", "Frequency"],
      rows: [
        ["Enoxaparin", "40mg", "Daily [e1]"],
        ["Paracetamol", "500mg", "PRN"],
      ],
      evidence_ids: ["e1"],
    },
  ],
};

// Hebrew RTL fixture — confirms direction + citation ordering inside RTL text.
export const sampleHebrew: AskResponse = {
  question: "מה האבחנה של מוחמד בן?",
  answer: "האבחנה היא **דמנציה** ושבר בירך [e1]. המטופל מקבל טיפול תומך [e2].",
  insufficient: false,
  citations: [],
  trace: {
    question: "מה האבחנה?",
    languages: ["he"],
    notes: [],
    sql_executions: [],
    evidence: [],
    generation: {},
    llm_calls: [],
    timings: [],
    mode: "stub",
  },
  triage: {
    defined: true,
    legend: { red: "דחוף", green: "יציב", blue: "מעקב" },
    note: "",
    items: [
      { label: "מוחמד בן", level: "red", summary: "דמנציה ושבר בירך.", evidence_ids: ["e1"], rule: null },
    ],
  },
  timeline: [
    { date: "2026-01-12", title: "קבלה", detail: "מוחמד בן התקבל עם שבר בירך.", evidence_ids: ["e1"] },
  ],
  tables: [],
};
