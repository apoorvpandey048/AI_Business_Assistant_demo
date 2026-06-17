// Captures Settings-tab screenshots for the two-independent-prompts feature.
import { chromium } from 'playwright';
const BASE = 'http://localhost:3000';
const SHOTS = '../docs/feature-test-screenshots';

const browser = await chromium.launch({ headless: true });

// 01 — settings empty (no prompts)
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await ctx.addInitScript(() => { localStorage.removeItem('aba.role'); localStorage.removeItem('aba.cases'); });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.getByRole('button', { name: /Settings/ }).first().click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${SHOTS}/01-settings-empty.png`, fullPage: true });
  console.log('01 settings-empty done');
  await ctx.close();
}

// 02 — type both prompts, Save both, capture active state
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await ctx.addInitScript(() => { localStorage.removeItem('aba.role'); localStorage.removeItem('aba.cases'); });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.getByRole('button', { name: /Settings/ }).first().click();
  await page.waitForTimeout(400);

  // Analysis mode textarea is the first textarea; Case rules is the second.
  const tas = page.locator('textarea');
  await tas.nth(0).fill('Act as a compliance auditor reviewing these records.');
  await page.getByRole('button', { name: /^Save/ }).nth(0).click();
  await page.waitForTimeout(400);
  await tas.nth(1).fill('medical history will be given choose red,green,blue based on importance and severity');
  await page.getByRole('button', { name: /^Save/ }).nth(1).click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${SHOTS}/02-settings-saved-both.png`, fullPage: true });

  // verify persisted
  const ls = await page.evaluate(() => ({ role: localStorage.getItem('aba.role'), cases: localStorage.getItem('aba.cases') }));
  console.log('02 persisted:', JSON.stringify(ls));
  await ctx.close();
}

await browser.close();
console.log('SETTINGS DONE');
