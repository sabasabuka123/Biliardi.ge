const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('owner dashboard renders hostile API fields as text and refreshes safely', async () => {
  const dom = new JSDOM(fs.readFileSync(path.join(__dirname, '../public/index.html'), 'utf8'), { runScripts: 'outside-only' });
  try {
    const { window } = dom;
    const payload = '<img src=x onerror="window.xss=true"><svg onload="window.xss=true"></svg>';
    let rows = [{ hall_name: payload, table_number: payload, customer_name: payload, customer_email: payload,
      start_time: '2030-01-01T10:00:00Z', end_time: '2030-01-01T11:00:00Z', total_price: payload, payment_status: payload }];
    window.fetch = async () => ({ json: async () => ({ reservations: rows }) });
    window.eval(fs.readFileSync(path.join(__dirname, '../public/app.js'), 'utf8'));
    await window.loadOwnerReservations();
    const owner = window.document.getElementById('ownerReservations');
    assert.equal(owner.querySelectorAll('img,svg,script,[onerror],[onload]').length, 0);
    assert.ok(owner.textContent.includes(`კლიენტი: ${payload} (${payload})`));
    assert.equal(owner.querySelector('strong').textContent, payload);
    rows = [];
    await window.loadOwnerReservations();
    assert.equal(owner.querySelectorAll('.res').length, 0);
    assert.equal(owner.querySelector('p.muted').textContent, 'ჯავშნები არ არის.');
  } finally { dom.window.close(); }
});
