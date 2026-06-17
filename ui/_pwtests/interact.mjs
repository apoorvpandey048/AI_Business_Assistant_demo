// Interactive checks: (1) count <table> elements in the answer for anomaly B,
// (2) click a citation chip and confirm a passage highlights.
import { chromium } from 'playwright';
const BASE = 'http://localhost:3000';
const SHOTS = '../docs/feature-test-screenshots';
const browser = await chromium.launch({ headless: true });

// ---- Anomaly B: count tables rendered in the answer card ----
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await ctx.addInitScript(() => { localStorage.removeItem('aba.role'); localStorage.removeItem('aba.cases'); });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.locator('textarea').first().fill('Show the family court case key dates and events as a table.');
  await page.getByRole('button', { name: /Ask/ }).first().click();
  await page.waitForFunction(() => /Routed to/i.test(document.body.innerText || ''), { timeout: 120000 });
  await page.waitForTimeout(1500);
  // The answer card is the Card containing "Answer" SectionTitle.
  const tableCount = await page.evaluate(() => {
    // find the answer region: the card with the "Answer" heading
    const cards = Array.from(document.querySelectorAll('div'));
    // simplest robust measure: count tables in the whole main, minus 0 (no other tables on chat)
    return document.querySelectorAll('main table').length;
  });
  console.log('ANOMALY-B: <table> count in main =', tableCount, '(expect 2 = inline + structured for one logical table)');
  await ctx.close();
}

// ---- Citation highlight: click first source chip, see if a passage gets highlighted ----
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await ctx.addInitScript(() => { localStorage.removeItem('aba.role'); localStorage.removeItem('aba.cases'); });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.locator('textarea').first().fill('What are the key allegations in the family court case?');
  await page.getByRole('button', { name: /Ask/ }).first().click();
  await page.waitForFunction(() => /Routed to/i.test(document.body.innerText || ''), { timeout: 120000 });
  await page.waitForTimeout(1200);
  // Click the first citation chip in the SOURCES area (button labelled e1/e2…)
  const chip = page.getByRole('button', { name: /^e\d+$/ }).first();
  const had = await chip.count();
  if (had) {
    await chip.click();
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${SHOTS}/17-citation-highlight.png`, fullPage: true });
    // detect a highlight ring class on an evidence item
    const highlighted = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('[class*="ring-indigo"],[class*="ring-2"],[class*="bg-indigo-50"]')).length;
    });
    console.log('CITATION-CLICK: chip clicked; highlight-ish elements =', highlighted);
  } else {
    console.log('CITATION-CLICK: no chip found');
  }
  await ctx.close();
}

await browser.close();
console.log('INTERACT DONE');
