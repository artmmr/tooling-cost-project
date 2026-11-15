// Landing page, quick price, hand-off to the detailed analysis, report, AI summary (mocked) and themes.
// Real Chromium and real FastAPI; the AI summary endpoint is intercepted, so no paid calls are made.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const frontend = path.join(root, '..', 'frontend');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  const socket = net.createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const server = spawn(process.env.PYTHON || 'python3', ['-c',
    'import os,uvicorn;from app.main import app;from fastapi.staticfiles import StaticFiles;app.mount("/",StaticFiles(directory=os.environ["TEST_FRONTEND"],html=True));uvicorn.run(app,host="127.0.0.1",port=int(os.environ["TEST_PORT"]),log_level="error")'],
    {cwd: root, env: {...process.env, TEST_PORT: String(port), TEST_FRONTEND: frontend, OPENAI_API_KEY: '', FX_ECB_URL: 'file://' + path.join(__dirname, 'fixtures', 'ecb_sample.xml')}, stdio: ['ignore', 'pipe', 'pipe']});
  let serverErrors = '', browser, passed = 0;
  server.stderr.on('data', data => serverErrors += data);
  const failures = [];
  try {
    for (let i = 0; i < 100; i++) {
      if (server.exitCode !== null) throw Error(`Preview server failed: ${serverErrors}`);
      try { if ((await fetch(`${url}/health`)).ok) break; } catch {}
      if (i === 99) throw Error(`Preview server timeout: ${serverErrors}`);
      await pause(100);
    }
    browser = await chromium.launch({headless: true});
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, colorScheme: 'light'});
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], {origin: url});
    const page = await context.newPage();
    page.on('pageerror', error => failures.push(error.message));
    const summaryCalls = [];
    await page.route('**/*', route => route.request().url().startsWith(url) ? route.continue() : route.abort());
    await page.route('**/api/advanced-report/summary', async route => {
      summaryCalls.push(route.request().postDataJSON());
      await route.fulfill({json: {headline: 'The tool costs about €1,800, mostly machining.',
        recommendations: ['Keep hot-work steel.', 'India is cheapest.'], watch_outs: ['Thermal fatigue.'], model: 'mock-model', cached: false}});
    });
    await page.addInitScript(base => globalThis.TOOLING_API_BASE_URL = base, url);
    const text = selector => page.locator(selector).first().textContent();
    const check = async (name, test) => {await test(); console.log(`PASS ${++passed}: ${name}`);};
    const shots = process.env.TOOLING_SCREENSHOTS;
    if (shots) fs.mkdirSync(shots, {recursive: true});
    const noOverflow = async label => {
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      assert(overflow <= 0, `${label}: page scrolls sideways by ${overflow}px`);
    };

    await check('Landing page offers both modes', async () => {
      await page.goto(`${url}/index.html`);
      const cards = page.locator('.mode-card');
      assert.equal(await cards.count(), 2);
      assert.deepEqual(await cards.evaluateAll(list => list.map(a => a.getAttribute('href'))), ['basic.html', 'advanced.html']);
      assert.equal(await page.evaluate(() => Theme.effective()), 'light');
    });

    await check('Theme toggle switches, persists across pages and changes colours', async () => {
      const lightBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      await page.locator('[data-theme-toggle]').click();
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark');
      const darkBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      assert.notEqual(lightBg, darkBg);
      if (shots) await page.screenshot({path: path.join(shots, 'landing-dark.png'), fullPage: true});
      await page.locator('.mode-card[href="basic.html"]').click();
      await page.waitForURL(/basic\.html/);
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'dark');
      await page.locator('[data-theme-toggle]').click();
      assert.equal(await page.evaluate(() => document.documentElement.dataset.theme), 'light');
    });

    let basicPrice;
    await check('Quick price calculates with a few inputs', async () => {
      await page.waitForFunction(() => !document.getElementById('b-submit').disabled);
      assert.equal(await page.locator('#b-process').inputValue(), 'die_casting');
      assert.equal(await page.locator('#b-material').inputValue(), 'cast_aluminum');
      await page.locator('#b-l').fill('50.8');
      await page.locator('#b-w').fill('28.6');
      await page.locator('#b-h').fill('28.6');
      await page.locator('#b-qty').fill('150000');
      await page.locator('#b-submit').click();
      await page.waitForFunction(() => document.getElementById('b-state').dataset.stale === 'false');
      basicPrice = await text('#b-price');
      assert.match(basicPrice, /^[\d,]+$/);
      assert.match(await text('#b-range'), /^Likely range €[\d,]+ – €[\d,]+/);
      assert.match(await text('#b-per-part'), /over 150,000 parts/);
      assert(await page.locator('#b-drivers .bar-row').count() >= 2);
      const href = await page.locator('#b-advanced').getAttribute('href');
      const params = new URL(href, url).searchParams;
      assert.equal(params.get('process'), 'die_casting');
      assert.equal(params.get('qty'), '150000');
      assert.equal(params.get('l'), '50.8');
      if (shots) await page.screenshot({path: path.join(shots, 'basic-light.png'), fullPage: true});
    });

    await check('Quick price recalculates on change and rejects bad input', async () => {
      await page.locator('#b-qty').fill('50');
      await page.waitForFunction(() => document.getElementById('b-per-part').textContent.includes('over 50 parts'));
      await page.locator('#b-qty').fill('150000');
      await page.waitForFunction(() => document.getElementById('b-per-part').textContent.includes('over 150,000 parts'));
      await page.locator('#b-l').fill('0');
      await page.waitForFunction(() => document.getElementById('b-status').classList.contains('err'));
      assert.match(await text('#b-status'), /Length must be greater than zero/);
      await page.locator('#b-l').fill('50.8');
      await page.waitForFunction(() => document.getElementById('b-state').dataset.stale === 'false');
      assert.equal(await text('#b-price'), basicPrice);
    });

    await check('Full analysis opens prefilled and gives the same price', async () => {
      await page.locator('#b-advanced').click();
      await page.waitForURL(/advanced\.html\?/);
      await page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false', null, {timeout: 30000});
      assert.equal(await page.locator('#inp-process').inputValue(), 'die_casting');
      assert.equal(await page.locator('#inp-l').inputValue(), '50.8');
      assert.equal(await page.locator('#inp-expected-cycles').inputValue(), '150000');
      assert.equal(await page.locator('#inp-tolerance').inputValue(), 'standard');
      const advancedPrice = Number((await text('#out-total')).replace(/,/g, ''));
      assert(Math.abs(advancedPrice - Number(basicPrice.replace(/,/g, ''))) <= 1, `${advancedPrice} vs ${basicPrice}`);
    });

    await check('Production report renders every section', async () => {
      assert.equal(await page.locator('#report').isHidden(), false);
      assert.equal(await text('#report-state'), 'Up to date');
      assert.match(await text('#rk-price'), /^€[\d,]+$/);
      assert.match(await text('#rk-per-part-note'), /150,000 parts/);
      assert(await page.locator('#rp-drivers .stack-seg').count() >= 3);
      assert.equal(await page.locator('#rp-drivers .stack-seg').count(), await page.locator('#rp-drivers .legend-table tr').count());
      assert.equal(await page.locator('#rp-quantity-chart .pt').count(), 6);
      assert.equal(await page.locator('#rp-quantity-chart .pt.current').count(), 1);
      assert.equal(await page.locator('#rp-quantity tr').count(), 6);
      assert.equal(await page.locator('#rp-quantity tr.current').count(), 1);
      assert(await page.locator('#rp-materials .option-card').count() >= 2);
      assert.equal(await page.locator('#rp-materials .option-card.current').count(), 1);
      assert((await page.locator('#rp-materials-hidden .option-card').count()) >= 1);
      assert(await page.locator('#rp-processes .option-card').count() >= 2);
      assert.match(await text('#rp-processes .option-card.current'), /Die casting/);
      assert.equal(await page.locator('#rp-countries .bar-row').count(), 11);
      assert.equal(await page.locator('#rp-countries .bar-row.current').count(), 1);
      assert.match(await text('#rp-risks'), /Thermal fatigue/);
      // 150,000 shots against a ~100,000-shot aluminium HPDC cavity: one replacement set.
      assert.equal(await text('#rl-life'), '100,000 cycles');
      assert.equal(await text('#rl-replacements'), '1');
      assert.match(await text('#rk-per-part-note'), /including 1 replacement set/);
      assert.match(await text('#rp-risks'), /Soldering/);
      assert(await page.locator('#rp-design li').count() >= 1);
      if (shots) await page.locator('#report').screenshot({path: path.join(shots, 'report-light.png')});
    });

    await check('Report goes out of date on edit and refreshes', async () => {
      await page.locator('#inp-expected-cycles').fill('5000');
      await page.waitForFunction(() => document.getElementById('report-state').textContent === 'Up to date'
        && document.getElementById('rk-per-part-note').textContent.includes('5,000 parts'));
    });

    await check('AI summary sends only the calculation request and renders the reply', async () => {
      await page.locator('#ai-btn').click();
      await page.waitForFunction(() => !document.getElementById('ai-output').hidden);
      assert.equal(summaryCalls.length, 1);
      assert.deepEqual(Object.keys(summaryCalls[0]).sort(), ['currency', 'request']);
      assert.equal(summaryCalls[0].request.expected_quantity, 5000);
      assert.match(await text('#ai-headline'), /about €1,800/);
      assert.equal(await page.locator('#ai-recommendations li').count(), 2);
      assert.match(await text('#ai-model'), /mock-model/);
      // A new estimate hides the old summary.
      await page.locator('#inp-expected-cycles').fill('6000');
      await page.waitForFunction(() => document.getElementById('ai-output').hidden && document.getElementById('report-state').textContent === 'Up to date');
    });

    await check('AI summary error is shown without breaking the report', async () => {
      await page.unroute('**/api/advanced-report/summary');
      await page.locator('#ai-btn').click();
      await page.waitForFunction(() => document.getElementById('ai-status').classList.contains('err'));
      assert.match(await text('#ai-status'), /OPENAI_API_KEY/);
      assert.equal(await text('#ai-btn'), 'Try again');
    });

    await check('Quick price for China is costed in USD at the ECB rate and matches the full analysis', async () => {
      await page.goto(`${url}/basic.html`);
      await page.waitForFunction(() => !document.getElementById('b-submit').disabled);
      await page.locator('#b-country').selectOption('DE');
      await page.locator('#b-submit').click();
      await page.waitForFunction(() => document.getElementById('b-state').dataset.stale === 'false');
      const germany = Number((await text('#b-price')).replace(/,/g, ''));
      await page.locator('#b-country').selectOption('CN');
      await page.waitForFunction(() => document.getElementById('b-currency').textContent === '$'
        && document.getElementById('b-state').dataset.stale === 'false');
      assert.match(await text('#b-currency-note'), /US dollars.*European Central Bank.*1 EUR = 1\.16 USD, 2026-11-13/);
      assert.match(await text('#b-range'), /^Likely range \$[\d,]+ – \$[\d,]+/);
      assert.match(await text('#b-per-part'), /^\$/);
      const chinaUsd = Number((await text('#b-price')).replace(/,/g, ''));
      assert(chinaUsd > 0 && chinaUsd !== germany);
      await page.locator('#b-advanced').click();
      await page.waitForURL(/advanced\.html\?/);
      await page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false', null, {timeout: 30000});
      assert.equal(await text('#result-currency'), 'USD');
      assert.equal(await page.locator('#inp-fx').inputValue(), '1.16');
      const advancedUsd = Number((await text('#out-total')).replace(/,/g, ''));
      assert(Math.abs(advancedUsd - chinaUsd) <= 1, `${advancedUsd} vs ${chinaUsd}`);
      assert.match(await text('#rk-price'), /^\$/);
      assert.match(await text('#rp-country-basis'), /1 EUR = 1\.16 USD/);
      assert.match(await text('#rp-countries'), /China \(costed in USD\)/);
      assert.equal(await page.locator('#rp-countries .bar-row').count(), 11);
    });

    await check('Without the ECB rate, a USD country asks for a rate and then calculates', async () => {
      const fresh = await context.newPage();
      fresh.on('pageerror', error => failures.push(error.message));
      await fresh.route('**/*', route => route.request().url().startsWith(url) ? route.continue() : route.abort());
      await fresh.addInitScript(base => globalThis.TOOLING_API_BASE_URL = base, url);
      await fresh.route('**/api/fx/eur-usd', route => route.fulfill({status: 503, json: {detail: 'The European Central Bank exchange rate could not be loaded.'}}));
      await fresh.goto(`${url}/advanced.html`);
      await fresh.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false');
      await fresh.evaluate(() => { document.getElementById('assumptions').open = true; });
      assert.equal(await fresh.locator('#inp-fx').inputValue(), '');
      await fresh.locator('#inp-country').selectOption('IN');
      await fresh.waitForFunction(() => document.getElementById('calc-status').textContent.includes('could not be loaded'));
      assert.match(await fresh.locator('#fx-source').textContent(), /could not be loaded/);
      await fresh.locator('#inp-fx').fill('1.1');
      await fresh.locator('#inp-fx-date').fill('2026-11-01');
      await fresh.locator('#calculate-btn').click();
      await fresh.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false');
      assert.equal(await fresh.locator('#result-currency').textContent(), 'USD');
      assert.match(await fresh.locator('#fx-source').textContent(), /Your own rate/);
      await fresh.close();
    });

    await check('Process matrix drives route advice on both pages', async () => {
      await page.goto(`${url}/basic.html`);
      await page.waitForFunction(() => document.querySelectorAll('#b-detail option').length > 20);
      await page.locator('#b-country').selectOption('DE');
      await page.locator('#b-qty').fill('150000');
      await page.locator('#b-submit').click();
      await page.waitForFunction(() => document.getElementById('b-state').dataset.stale === 'false');
      assert.equal(await page.locator('#b-matrix').isVisible(), true);
      assert.match(await text('#b-matrix-route'), /High-volume HPDC · premium H13 \/ ESR/);
      assert.match(await text('#b-matrix-note'), /matches your process/);
      await page.locator('#b-detail').selectOption('zinc_die_casting');
      await page.waitForFunction(() => document.getElementById('b-matrix-note').textContent.includes('zinc'));
      assert.equal(await page.locator('#b-material').inputValue(), 'cast_aluminum');
      assert.equal(new URL(await page.locator('#b-advanced').getAttribute('href'), url).searchParams.get('detail'), 'zinc_die_casting');
      await page.locator('#b-advanced').click();
      await page.waitForURL(/advanced\.html\?/);
      await page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false'
        && !document.getElementById('report').hidden, null, {timeout: 30000});
      assert.equal(await page.locator('#inp-material-detail').inputValue(), 'zinc_die_casting');
      assert.match(await text('#rp-matrix-summary'), /Zinc — Die casting.*chosen by you/s);
      assert.equal(await page.locator('#rp-matrix-bands tr').count(), 6);
      assert.match(await text('#rp-matrix-bands tr.current'), /Above 100,000.*High-volume HPDC.*Your process/s);
      assert.equal(await text('#rp-matrix-chip'), 'Matches your process');
      assert.match(await text('#rp-matrix-grades'), /Premium H13 \/ ESR/);
      assert.match(await text('#rp-materials'), /Process matrix recommends Premium H13/);
      // At 50 parts the matrix recommends machining without a dedicated tool.
      await page.locator('#inp-expected-cycles').fill('50');
      await page.waitForFunction(() => document.getElementById('report-state').textContent === 'Up to date'
        && document.getElementById('rp-matrix-chip').textContent === 'Different from your process');
      assert.match(await text('#rp-processes'), /no dedicated tool/);
      assert.match(await text('#rp-design'), /process matrix recommends CNC/);
      if (shots) await page.locator('.matrix-card').screenshot({path: path.join(shots, 'matrix-card.png')});
      // Picking a plastic row sets the matching costing material when the process offers it.
      await page.locator('#inp-process').selectOption('plastic_injection');
      await page.locator('#inp-material-detail').selectOption('pvc_corrosive_thermoplastic');
      assert.equal(await page.locator('#inp-workpiece-material').inputValue(), 'corrosive_polymer');
    });

    await check('Summary bar, presets, Try this with Undo, assumptions, link and history', async () => {
      await page.setViewportSize({width: 1440, height: 1000});
      await page.goto(`${url}/advanced.html`);
      await page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false');
      // Results first: calculated on load, summary bar visible, no cents in the price.
      assert.equal(await page.locator('#summary-bar').isVisible(), true);
      assert.match(await text('#sb-price'), /^€[\d,]+$/);
      assert.match(await text('#out-total'), /^[\d,]+$/);
      assert.match(await text('#out-range'), /^Likely range €[\d,]+ – €[\d,]+$/);
      // Quantity presets; the band follows the quantity.
      await page.locator('.presets [data-qty="100000"]').click();
      assert.equal(await page.locator('#inp-expected-cycles').inputValue(), '100000');
      await page.waitForFunction(() => document.getElementById('sb-state').dataset.stale === 'false'
        && document.getElementById('rk-per-part-note').textContent.includes('100,000'));
      // Assumptions: collapsed by default with a one-line summary and an edited count.
      assert.equal(await page.locator('.input-column #assumptions').count(), 1, 'assumptions belong to the inputs');
      assert.equal(await page.locator('#report #assumptions').count(), 0);
      assert.equal(await page.locator('#assumptions').getAttribute('open'), null);
      assert.match(await text('#assumptions-summary'), /Germany rates · EUR/);
      assert.equal(await page.locator('#assumptions-edited').isHidden(), true);
      await page.locator('#assumptions > summary').click();
      await page.locator('#inp-cnc3-rate').fill('150');
      await page.waitForFunction(() => !document.getElementById('assumptions-edited').hidden);
      assert.equal(await text('#assumptions-edited'), '1 edited');
      await page.locator('#reset-country-defaults').click();
      await page.waitForFunction(() => document.getElementById('assumptions-edited').hidden);
      await page.waitForFunction(() => document.getElementById('sb-state').dataset.stale === 'false');
      // Try another country, then undo.
      const before = await text('#sb-price');
      await page.locator('#rp-countries [data-try-value="PL"]').click();
      await page.waitForFunction(() => !document.getElementById('sb-change').hidden);
      assert.equal(await page.locator('#inp-country').inputValue(), 'PL');
      assert.match(await text('#sb-change-text'), /^Country: Poland: €[\d,]+ → €[\d,]+$/);
      await page.locator('#sb-undo').click();
      await page.waitForFunction(() => document.getElementById('inp-country').value === 'DE'
        && document.getElementById('sb-state').dataset.stale === 'false');
      assert.equal(await text('#sb-price'), before);
      // Try another tooling material and another process; the part stays the same.
      const length = await page.locator('#inp-l').inputValue();
      await page.locator('#rp-materials .try-btn').first().click();
      await page.waitForFunction(() => !document.getElementById('sb-change').hidden);
      assert.match(await text('#sb-change-text'), /^Tool steel: /);
      await page.locator('#sb-undo').click();
      await page.waitForFunction(() => document.getElementById('sb-change').hidden && document.getElementById('sb-state').dataset.stale === 'false');
      const processTry = page.locator('#rp-processes .try-btn').first();
      const target = await processTry.getAttribute('data-try-value');
      await processTry.click();
      await page.waitForFunction(t => document.getElementById('inp-process').value === t
        && !document.getElementById('sb-change').hidden, target);
      assert.equal(await page.locator('#inp-l').inputValue(), length);
      await page.locator('#sb-undo').click();
      await page.waitForFunction(() => document.getElementById('inp-process').value === 'die_casting'
        && document.getElementById('sb-state').dataset.stale === 'false');
      // Copy link and history.
      await page.locator('#sb-copy').click();
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      const params = new URL(copied).searchParams;
      assert.equal(params.get('process'), 'die_casting');
      assert.equal(params.get('qty'), '100000');
      await page.locator('#sb-history').click();
      assert(await page.locator('#history-panel li').count() >= 2);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#history-panel').isHidden(), true);
      // Report navigation jumps to a section.
      await page.locator('#report-nav a[href="#rs-sourcing"]').click();
      await page.waitForFunction(() => document.querySelector('#report-nav a[aria-current]')?.getAttribute('href') === '#rs-sourcing');
      // Print layout shows the report and hides the form.
      await page.emulateMedia({media: 'print'});
      assert.equal(await page.locator('.input-column').isVisible(), false);
      assert.equal(await page.locator('#rs-materials').isVisible(), true);
      await page.emulateMedia({media: 'screen'});
      if (shots) await page.screenshot({path: path.join(shots, 'redesign-desktop.png')});
    });

    await check('Phone layout: bottom price bar and collapsible report cards', async () => {
      await page.setViewportSize({width: 390, height: 844});
      await page.goto(`${url}/advanced.html`);
      await page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false');
      const bar = await page.locator('#summary-bar').boundingBox();
      assert(bar.y + bar.height >= 844 - 2, 'summary bar sits at the bottom');
      const card = page.locator('#rs-materials');
      assert.equal(await card.evaluate(el => el.classList.contains('collapsed')), true);
      assert.equal(await page.locator('#rp-materials').isVisible(), false);
      await card.locator('.collapse-toggle').click();
      assert.equal(await page.locator('#rp-materials').isVisible(), true);
      const height = await page.evaluate(() => document.documentElement.scrollHeight);
      assert(height < 844 * 12, `phone page is ${(height / 844).toFixed(1)} screens`);
      console.log(`      phone page: ${(height / 844).toFixed(1)} screens`);
      if (shots) await page.screenshot({path: path.join(shots, 'redesign-phone.png'), fullPage: false});
    });

    await check('Dark theme and mobile layouts have no sideways scrolling', async () => {
      await page.locator('[data-theme-toggle]').click();
      if (shots) await page.locator('#report').screenshot({path: path.join(shots, 'report-dark.png')});
      for (const [width, height] of [[1440, 1000], [390, 844]]) {
        await page.setViewportSize({width, height});
        for (const target of ['index.html', 'basic.html', 'advanced.html']) {
          await page.goto(`${url}/${target}`);
          await page.waitForLoadState('networkidle');
          await noOverflow(`${target} at ${width}px`);
          if (shots) await page.screenshot({path: path.join(shots, `${target.replace('.html', '')}-${width}-dark.png`), fullPage: target !== 'advanced.html'});
        }
      }
      await page.goto(`${url}/basic.html`);
      await page.waitForFunction(() => !document.getElementById('b-submit').disabled);
      await page.locator('#b-submit').click();
      await page.waitForFunction(() => document.getElementById('b-state').dataset.stale === 'false');
      await noOverflow('basic result at 390px');
      if (shots) await page.screenshot({path: path.join(shots, 'basic-390-result-dark.png'), fullPage: true});
    });

    assert.deepEqual(failures, [], `Runtime errors: ${failures.join('; ')}`);
    console.log(`${passed} mode scenarios passed; AI summary mocked, no paid calls.`);
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  } finally {
    await browser?.close();
    server.kill();
  }
})();
