import { chromium } from 'playwright';
const b = await chromium.launch({ headless: true });
const p = await b.newPage({ viewport: { width: 1440, height: 1000 } });
await p.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
console.log('TITLE:', await p.title());
await p.screenshot({ path: '../docs/feature-test-screenshots/00-smoke-home.png', fullPage: true });
console.log('SMOKE OK');
await b.close();
