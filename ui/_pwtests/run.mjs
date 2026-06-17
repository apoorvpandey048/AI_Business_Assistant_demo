// Feature-test harness — drives the real UI at localhost:3000 with Playwright.
// Sets the two prompts via localStorage (aba.role / aba.cases) exactly as the app does,
// types the question, clicks Ask, waits for the answer card, captures a full-page
// screenshot + the raw /ask JSON for the report. Temporary test tooling, not feature code.
import { chromium } from 'playwright';

const BASE = 'http://localhost:3000';
const SHOTS = '../docs/feature-test-screenshots';
const JSONDIR = `${SHOTS}/_json`;
import { mkdirSync, writeFileSync } from 'fs';
mkdirSync(JSONDIR, { recursive: true });

// Scenario list: {id, file, role, cases, question, settingsShot?}
// role/cases are the SAVED localStorage values (undefined = not set / cleared).
const SCENARIOS = [
  { id: '03', file: '03-nursing-table-triage.png',
    cases: 'medical history will be given choose red,green,blue based on importance and severity',
    question: 'List each patient and their primary diagnosis as a table.' },

  { id: '04', file: '04-nursing-triage-severity.png',
    cases: 'Triage patients: red = critical or life-threatening conditions; green = needs monitoring; blue = stable.',
    question: 'Describe each patient in the nursing home and triage them by severity.' },

  { id: '05', file: '05-nursing-timeline.png',
    question: 'Give a timeline of the care events for the patients in the nursing home.' },

  { id: '06', file: '06-family-role-lawyer.png',
    role: 'Act as a family-law attorney reviewing this case file.',
    question: 'Summarize the family court case.' },

  { id: '07', file: '07-carters-timeline.png',
    question: 'Give a chronological timeline of what happened in the Carters story.' },

  { id: '08', file: '08-family-triage-people.png',
    cases: 'Triage the people: red = poses risk or central to dispute; green = needs follow-up; blue = peripheral.',
    question: 'Triage the people involved in the family court case.' },

  { id: '09', file: '09-hebrew-diagnosis.png',
    question: 'מה האבחנה של מוחמד בן?' },

  { id: '10', file: '10-crosslang-he-persona.png',
    role: 'Answer in Hebrew. ענה בעברית.',
    question: 'What is the diagnosis of the patient Mohammad Ben?' },

  { id: '11', file: '11-out-of-scope-decline.png',
    cases: 'red = urgent; green = normal; blue = low priority',
    question: 'What is the capital of France?' },

  { id: '12a', file: '12a-role-off.png',
    question: 'What are the main risks in the family court case?' },
  { id: '12b', file: '12b-role-on.png',
    role: 'Act as a risk-assessment compliance officer. Be terse and list risks.',
    question: 'What are the main risks in the family court case?' },

  { id: '13', file: '13-cases-off-no-triage.png',
    question: 'Describe each patient in the nursing home.' },

  { id: '14', file: '14-two-pdf-span.png',
    question: 'Compare the people in the family court case with the patients in the nursing home — are any the same person?' },

  { id: '15', file: '15-table-no-cases.png',
    question: 'Show the family court case key dates and events as a table.' },

  { id: '16', file: '16-markdown-bold-list.png',
    question: 'What are the key allegations in the family court case? Use a bulleted list and bold the most important one.' },
];

function pad(s, n) { return (s + ' '.repeat(n)).slice(0, n); }

async function seedStorage(ctx, role, cases) {
  // Set localStorage before app JS reads it: use an init script applied to every page.
  await ctx.addInitScript(([r, c]) => {
    try {
      if (r) localStorage.setItem('aba.role', r); else localStorage.removeItem('aba.role');
      if (c) localStorage.setItem('aba.cases', c); else localStorage.removeItem('aba.cases');
    } catch (e) {}
  }, [role || '', cases || '']);
}

async function runOne(browser, sc) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await seedStorage(ctx, sc.role, sc.cases);
  const page = await ctx.newPage();

  // capture the /ask response JSON for evidence
  let captured = null;
  page.on('response', async (resp) => {
    try {
      const u = resp.url();
      if (u.endsWith('/api/ask') || u.endsWith('/ask')) {
        captured = await resp.json().catch(() => null);
      }
    } catch (e) {}
  });

  await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });
  // wait for engine connect to clear
  await page.waitForTimeout(800);

  // type the question into the chat textarea
  const ta = page.locator('textarea').first();
  await ta.click();
  await ta.fill(sc.question);
  // click Ask
  await page.getByRole('button', { name: /Ask/ }).first().click();

  // wait for the answer card (the "Answer" section title) OR an error card.
  try {
    await page.waitForFunction(() => {
      const t = document.body.innerText || '';
      return /Routed to/i.test(t) || /Could not reach the engine/i.test(t);
    }, { timeout: 120000 });
  } catch (e) { /* fall through, screenshot whatever is there */ }
  // settle: triage/timeline/tables render after answer
  await page.waitForTimeout(1500);

  await page.screenshot({ path: `${SHOTS}/${sc.file}`, fullPage: true });
  if (captured) writeFileSync(`${JSONDIR}/${sc.id}.json`, JSON.stringify(captured, null, 2));

  // quick verdict signals
  const sig = captured ? {
    route: captured.trace?.route?.route,
    conf: captured.trace?.route?.confidence,
    insufficient: captured.insufficient,
    cites: (captured.citations || []).length,
    triageDefined: captured.triage?.defined,
    triageItems: (captured.triage?.items || []).length,
    tables: (captured.tables || []).length,
    timeline: (captured.timeline || []).length,
    answerHasPipeTable: /\n\s*\|?[-: ]*\|[-: |]*\n/.test(captured.answer || '') || /\|.*\|/.test((captured.answer||'').split('\n')[0]||''),
    answerLen: (captured.answer || '').length,
  } : { error: 'no /ask json captured' };

  console.log(`[${pad(sc.id,4)}] ${pad(sc.file,34)} ` +
    `route=${pad(String(sig.route),6)} conf=${pad(String(sig.conf),5)} insuf=${pad(String(sig.insufficient),5)} ` +
    `cites=${pad(String(sig.cites),2)} triage=${pad(String(sig.triageDefined)+'/'+sig.triageItems,7)} ` +
    `tbl=${pad(String(sig.tables),2)} tl=${pad(String(sig.timeline),2)} pipe=${sig.answerHasPipeTable}`);

  await ctx.close();
  return { sc, sig };
}

const only = process.argv[2]; // optional: run a single scenario id
const browser = await chromium.launch({ headless: true });
const results = [];
for (const sc of SCENARIOS) {
  if (only && sc.id !== only) continue;
  try {
    results.push(await runOne(browser, sc));
  } catch (e) {
    console.log(`[${sc.id}] ERROR: ${e.message}`);
  }
}
await browser.close();
writeFileSync(`${JSONDIR}/_signals.json`, JSON.stringify(results.map(r => ({ id: r.sc.id, file: r.sc.file, ...r.sig })), null, 2));
console.log('DONE', results.length, 'scenarios');
