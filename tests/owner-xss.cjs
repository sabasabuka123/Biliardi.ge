const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(fs.readFileSync(path.join(__dirname, '../public/index.html'), 'utf8'));
    const payload = '<img src=x onerror="window.xss=true"><svg onload="window.xss=true"></svg>';
    await page.evaluate((payload) => {
      window.xss = false;
      window.rows = [{ hall_name: payload, table_number: payload, customer_name: payload,
        customer_email: payload, start_time: '2030-01-01T10:00:00Z', end_time: '2030-01-01T11:00:00Z',
        total_price: payload, payment_status: payload }];
      window.fetch = async () => ({ json: async () => ({ reservations: window.rows }) });
    }, payload);
    await page.addScriptTag({ path: path.join(__dirname, '../public/app.js') });
    await page.evaluate(() => loadOwnerReservations());
    const owner = page.locator('#ownerReservations');
    assert.equal(await owner.locator('img, svg, script, [onerror], [onload]').count(), 0);
    assert.equal(await page.evaluate(() => window.xss), false);
    assert.ok((await owner.textContent()).includes(`კლიენტი: ${payload} (${payload})`));
    assert.equal(await owner.locator('strong').textContent(), payload);
    await page.evaluate(() => { window.rows = []; return loadOwnerReservations(); });
    assert.equal(await owner.locator('.res').count(), 0);
    assert.equal(await owner.locator('p.muted').textContent(), 'ჯავშნები არ არის.');
    console.log('PASS: Chromium owner dashboard treats all API fields as text; no injected DOM or script execution; refresh/empty state works.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
