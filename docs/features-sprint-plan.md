# Features Sprint — Implementation Plan

**Status:** proposed → in progress
**Owner branch:** `feature/ux-cases-viz` (new, branched from `main`)
**Date:** 2026-06-15
**Scope of THIS sprint:** items **1, 2, 5** (Cases prompt, triage panels, rich rendering + settings/UI polish).
**Explicitly out of scope (separate efforts):**
- Items **6 & 7** (Hebrew parity + chunking/zero-loss) — owned by a *separate, concurrent chat* on branch `sprint-15-hebrew-parity`. We do **not** touch `app/ingestion/`, `app/llm/lang.py`, Hebrew eval sets, or RTL normalization.
- Item **3** (multi-user auth + isolation) — next sprint. Decided model: one org / a few users, Google sign-in + BYO API keys.
- Item **4** (CRM/QuickBooks/Excel APIs) — later sprint, still being scoped with the client.
- Arabic — deferred at user's request.

---

## 1. Coordination with the concurrent Hebrew chat

This is a **single shared checkout** on the live-server machine. The other chat is actively committing to `sprint-15-hebrew-parity`. To avoid collisions:

1. We branch **`feature/ux-cases-viz` from `main`** (NOT from the Hebrew branch), so we get a clean base without half-finished Hebrew work.
2. We avoid all files the Hebrew effort owns:
   - `app/ingestion/**` (pdf.py, normalize_rtl, detect_text_order)
   - `app/llm/lang.py` (language resolution/directives)
   - `tests/test_hebrew_*`, `scripts/eval_hebrew_retrieval.py`, `docs/hebrew-*`
3. The one genuinely shared file is `app/generation/generate.py` (system prompt). We touch it **additively** — we append a Cases-prompt block and a structured-output schema field; we do **not** modify the language directive, the grounding rules, or the negative-mention/grounding guards. If a merge conflict arises there, it will be a clean additive hunk.
4. We never run a live deploy/restart as part of this sprint without explicit say-so — the other chat may be mid-deploy.

**Risk if ignored:** double-deploy races, clobbering uncommitted Hebrew work, merge pain in `generate.py`. Mitigation above keeps our blast radius to new files + additive hunks.

---

## 2. How the two product features map to one mental model

Items 1 and 2 are **one coupled feature**, not two:

- **Item 1 — two prompts.** Today there is exactly one user prompt slot: the **Role / MVP prompt** (`role_instructions`, persisted as `aba.role`, applied on Save, capped 1500 chars, shapes tone/emphasis only — never overrides grounding). We add a **second, independent slot: the Cases prompt** (`case_instructions`, persisted as `aba.cases`). It is the *ruleset* that drives item 2.
- **Item 2 — blue/green/red panels.** Per the user's clarification, this is **NOT** fixed urgent/important/severe lanes. It is **user-defined triage**: the client asks about N entities (e.g. 10 patients), and her Cases prompt defines what each color means ("stable → blue, fever → green, life support → red"). The system classifies each entity into her three buckets **alongside** the normal grounded answer/reasoning/evidence — every classification is itself cited.

So the Cases prompt is the input; the triage panels are the output. They ship together.

---

## 3. The contract (Phase 0 — lock first, then fan out)

Everything hinges on the `AskRequest` / `AskResponse` shapes, because they are the single seam between backend and frontend (`app/models.py` ↔ `ui/lib/types.ts`). We lock these **before** any agent starts, so parallel work compiles against a frozen interface.

### 3.1 `AskRequest` (additive)
```python
class AskRequest(BaseModel):
    question: str
    developer_mode: bool = True
    scope: Literal["workspace", "all"] = "workspace"
    role_instructions: Optional[str] = None      # existing — Role/MVP prompt
    case_instructions: Optional[str] = None       # NEW — Cases prompt (triage ruleset)
```

### 3.2 New response models (additive to `app/models.py`)
```python
TriageLevel = Literal["red", "green", "blue"]

class TriageItem(BaseModel):
    """One classified entity in the triage view. Fully grounded: every item
    references the evidence ids that justify its bucket — same [eN] objects as
    the answer, so the panels are as traceable as the answer text."""
    label: str                       # entity name as it appears in evidence, e.g. "Mohammed Ben"
    level: TriageLevel               # red | green | blue — meaning defined by the Cases prompt
    summary: str                     # one-line grounded reason for the bucket
    evidence_ids: list[str] = Field(default_factory=list)   # [eN] that justify this
    rule: Optional[str] = None       # which Cases-prompt rule matched (model's own words)

class TriagePanel(BaseModel):
    """The triage view for one answer. `defined` is false when no Cases prompt was
    supplied (UI then hides the panels entirely). `legend` echoes what each color
    means per the user's Cases prompt, so the UI can label the columns truthfully."""
    defined: bool = False
    legend: dict[str, str] = Field(default_factory=dict)   # {"red": "...", "green": "...", "blue": "..."}
    items: list[TriageItem] = Field(default_factory=list)
    note: str = ""                   # e.g. "3 entities could not be classified from the evidence"

class TimelineEvent(BaseModel):
    """One dated, grounded event for the timeline visualization."""
    date: str                        # ISO-ish display string exactly as grounded in evidence
    title: str
    detail: str = ""
    evidence_ids: list[str] = Field(default_factory=list)

class AnswerTable(BaseModel):
    """A structured table extracted alongside the answer so the UI renders a real
    <table> instead of ASCII pipes-and-dashes."""
    title: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
```

### 3.3 `AskResponse` (additive)
```python
class AskResponse(BaseModel):
    question: str
    answer: str
    insufficient: bool = False
    citations: list[Evidence] = Field(default_factory=list)
    trace: Trace
    # NEW — all optional, all grounded, all default-empty so existing behavior is unchanged:
    triage: Optional[TriagePanel] = None        # populated only when case_instructions given
    timeline: list[TimelineEvent] = Field(default_factory=list)
    tables: list[AnswerTable] = Field(default_factory=list)
```

**Design rule:** every new field is **optional / empty by default**. An answer with no Cases prompt, no dates, and no tabular data is byte-identical to today. This keeps the trust/eval batteries green and means the Hebrew branch's answers are unaffected.

### 3.4 `ui/lib/types.ts` — mirror the above exactly (TriageLevel, TriageItem, TriagePanel, TimelineEvent, AnswerTable, extended AskResponse).

---

## 4. Backend generation design (item 2 logic + tables/timeline)

All in `app/generation/` and threaded through `orchestrator.ask` → `engine.ask` → `routes.ask`.

### 4.1 Threading the Cases prompt
`case_instructions` flows the same path `role_instructions` already does:
`routes.ask` → `engine.ask(..., case_instructions=)` → `orchestrator.ask(..., case_instructions=)` → new `triage_classify(...)` call.

### 4.2 Triage classification (`app/generation/triage.py`, new)
- Runs **only when `case_instructions` is non-empty**. Otherwise returns `TriagePanel(defined=False)` and the UI hides panels.
- One additional structured LLM call **after** the grounded answer is produced, fed: the question, the Cases prompt (sanitized, capped like role at 1500 chars), and the **same evidence block** used for the answer.
- Forced JSON schema → list of `TriageItem`. The model must put each entity into red/green/blue per the user's rules and cite the `evidence_ids` that justify it.
- **Grounding guard:** any `TriageItem` whose `evidence_ids` are empty or reference ids not in the evidence set is dropped (logged in `note`). No ungrounded triage rows — same discipline as the answer's citation check.
- **Offline / fallback:** deterministic path returns `defined=True` with `items=[]` and a `note` that triage needs a live model, OR a trivial keyword bucket if the Cases prompt is simple — TBD by the backend agent, but must never fabricate. Trust battery must stay green.

### 4.3 Tables (`app/generation/structured.py`, new)
- Two parts: (a) extend the answer schema with an optional `tables` array the model can fill when the answer is naturally tabular; (b) a deterministic post-pass that detects an **ASCII table already emitted in `answer`** (pipes/dashes) and lifts it into an `AnswerTable`, so even offline/cached answers render as real tables.
- Tables are grounded via `evidence_ids` where the model provides them; the ASCII-lift path inherits the answer's citations.

### 4.4 Timeline
- When the question asks for a timeline/sequence/"what happened when", a structured extraction call (or deterministic date-scan over evidence) produces `TimelineEvent[]`, each carrying the `evidence_ids` it came from.
- Detection: question contains timeline/chronology/sequence cues OR the Cases/answer context implies ordering. Conservative — empty list when not applicable, so non-timeline answers are unchanged.

### 4.5 Non-negotiables (inherited from existing trust design)
- Triage rows, timeline events, and tables are **grounded and cited** or they do not appear.
- `generation_acceptable` / language enforcement is **not** modified (Hebrew branch owns it). Triage/timeline text inherits the answer's target language by passing the same `target_language` into their prompts.
- New LLM calls are logged in `trace.llm_calls` and counted in cost, exactly like generation.

---

## 5. Frontend design (items 2 + 5)

### 5.1 Triage panels (`ui/components/TriagePanel.tsx`, new)
- Three columns, color-coded red/green/blue, rendered **above or beside** the answer card in `AnswerPanel.tsx` when `resp.triage?.defined`.
- Column headers show the user's own legend text ("Life support", "Fever", "Stable") — never hardcoded labels.
- Each card: entity label, one-line summary, clickable `[eN]` chips reusing the existing `useCiteHighlight` / `CitationChips` machinery so clicking scrolls to the same evidence panel. Full RTL support via existing `isRTL`/`bidiPlaintext`.
- Hidden entirely when `triage` is absent or `defined=false`.

### 5.2 Rich answer rendering (`ui/components/AnswerBody.tsx`, new — wraps/extends `CitedText`)
- **Tables:** render `resp.tables` as real, styled `<table>` elements (Tailwind, `scroll-thin`, sticky header). Also upgrade inline markdown tables in the answer text if present.
- **Markdown:** the answer is currently plain text. We add **minimal, safe** markdown rendering (bold, lists, tables) while **preserving `[eN]` citation markers** — the `[e\d+]` splitter runs first, then light markdown on the non-citation spans. No raw HTML injection (XSS-safe; we render via a tiny allowlisted renderer or a vetted lib).
- **Timeline (`ui/components/Timeline.tsx`, new):** vertical, visually distinct timeline (date rail + event cards), each event citing its `[eN]`. Renders only when `resp.timeline.length > 0`.

### 5.3 Settings + UI polish (item 5)
- **Two-prompt UI in `Settings.tsx`:** the existing "Analysis mode" card stays (Role/MVP). Add a **second card: "Case rules"** — same draft/save/clear pattern, persisted as `aba.cases`, with a helpful placeholder showing the patient-triage example. Both are threaded into `ask()`.
- **Simplify settings:** group into clear sections ("How it answers" = Role + Cases; "Engine & provider" = existing read-only + provider; "Workspace" = sources + reset). Keep it scannable, plain language, no jargon dumps.
- `ui/lib/api.ts` `ask()` gains a `caseInstructions?` arg → `case_instructions` in the body.
- `ui/app/page.tsx` adds `cases` state + `aba.cases` localStorage (mirror of `role`), passes to `ask()` and `Settings`.

### 5.4 Accessibility / quality
- Color is never the only signal — each triage column has a text label + icon (color-blind safe).
- Tables get proper `<th scope>`; timeline is a semantic ordered list under the hood.

---

## 6. Execution plan (agent roles)

**Phase 0 — contract lock (I do this solo, no parallelism):**
- Create branch `feature/ux-cases-viz` from `main`.
- Edit `app/models.py` (new models + extended request/response) and `ui/lib/types.ts` (mirror). Commit. This is the frozen interface.

**Phase 1 — fan out 3 agents (parallel, non-overlapping file sets):**
- **Agent A — Backend generation.** Owns `app/generation/triage.py`, `app/generation/structured.py` (new), the additive hunk in `app/generation/generate.py`, threading through `orchestrator.py`/`engine.py`/`routes.py`, and new `tests/test_triage.py` + `tests/test_structured_output.py`. Must keep eval/trust green.
- **Agent B — Frontend visualization.** Owns `TriagePanel.tsx`, `Timeline.tsx`, `AnswerBody.tsx`, table rendering, and the `AnswerPanel.tsx` integration. Compiles against the locked `types.ts`. Uses mock `AskResponse` fixtures until backend lands.
- **Agent C — Frontend prompts + settings polish.** Owns the two-prompt UI in `Settings.tsx`, `ui/lib/api.ts` `ask()` change, `ui/app/page.tsx` state wiring (`aba.cases`), and settings reorganization. Coordinates with B only via `page.tsx` (B touches `AnswerPanel`, C touches `page`/`Settings` — disjoint).

Agents A/B/C have disjoint file sets except `page.tsx` (C only) and `AnswerPanel.tsx` (B only) — no shared files, so no merge conflicts within the sprint.

**Phase 2 — integration + verification (I do this solo):**
- Wire C's `page.tsx` to pass real triage/timeline/tables into B's `AnswerPanel`.
- `cd ui && npm run build` (typecheck + build must pass).
- `pytest` (full suite — must stay green, incl. existing 270+ tests).
- `python scripts/eval.py`, `python scripts/eval_qa.py`, `python scripts/eval_trust.py` — must hold at current scores (eval 9/9, eval_qa 25/25, trust ≥ current).
- Manual smoke: a Cases-prompt question producing 3 buckets; a timeline question; a tabular question.
- **No deploy/restart** without explicit user approval (Hebrew chat may be mid-deploy).

---

## 7. Verification checklist (definition of done for this sprint)

- [ ] `AskResponse` with no Cases prompt / no dates / no tables is byte-identical to pre-sprint output (regression-safe).
- [ ] Cases prompt drives 3 color buckets; every triage row is grounded + cited; ungrounded rows dropped.
- [ ] Tables render as real HTML tables (both model-emitted and ASCII-lifted).
- [ ] Timeline renders for chronology questions, each event cited.
- [ ] Two independent prompts (Role + Cases) persist separately and apply on Save.
- [ ] Settings is simpler and clearer; color is never the only signal.
- [ ] `npm run build` clean; `pytest` green; eval 9/9, eval_qa 25/25, trust ≥ current.
- [ ] No files owned by the Hebrew effort were modified.
- [ ] No production restart performed without explicit approval.

---

## 8. Open questions / assumptions (proceeding on these unless corrected)

- **Triage colors fixed to red/green/blue** (3 buckets) — matches her description. If she wants N buckets later, `TriageLevel` widens; not now.
- **Cases prompt persisted per-browser** like Role (not server-side) — consistent with current persona model; revisits when multi-user auth lands.
- **Timeline trigger is heuristic** (question cues + presence of dated evidence). Erring toward *not* showing it rather than showing a weak one.
- **Markdown rendering is minimal + allowlisted** (no arbitrary HTML) for XSS safety.
