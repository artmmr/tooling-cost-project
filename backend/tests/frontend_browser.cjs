// Real Chromium, real FastAPI, and no calls to the deployed Render service.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const frontend = fs.existsSync(path.join(root, 'frontend')) ? path.join(root, 'frontend') : path.join(root, '..', 'frontend');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const closeTo = (a, b, message) => assert(Math.abs(a - b) < 1e-7 * Math.max(1, Math.abs(b)), `${message || 'Values differ'}: ${a} vs ${b}`);

(async () => {
  const socket = net.createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const server = spawn(process.env.PYTHON || 'python3', ['-c',
    'import os,uvicorn;from app.main import app;from fastapi.staticfiles import StaticFiles;app.mount("/",StaticFiles(directory=os.environ["TEST_FRONTEND"],html=True));uvicorn.run(app,host="127.0.0.1",port=int(os.environ["TEST_PORT"]),log_level="error")'],
    {cwd:root, env:{...process.env, TEST_PORT:String(port), TEST_FRONTEND:frontend}, stdio:['ignore','pipe','pipe']});
  let serverErrors = '', browser;
  server.stderr.on('data', data => serverErrors += data);
  const failures = [], requests = [];
  let passed = 0;
  try {
    for (let i = 0; i < 100; i++) {
      if (server.exitCode !== null) throw Error(`Preview server failed: ${serverErrors}`);
      try { if ((await fetch(`${url}/health`)).ok) break; } catch {}
      if (i === 99) throw Error(`Preview server timeout: ${serverErrors}`);
      await pause(100);
    }
    browser = await chromium.launch({headless:true,
      ...(process.env.TOOLING_CHROMIUM_EXECUTABLE ? {executablePath:process.env.TOOLING_CHROMIUM_EXECUTABLE,
        args:['--no-sandbox','--no-zygote','--single-process','--disable-dev-shm-usage','--disable-webgl']} : {})});
    const page = await browser.newPage({viewport:{width:1440,height:1080}});
    page.on('pageerror', error => failures.push(error.message));
    page.on('request', request => {if(request.url().endsWith('/api/calculate')) requests.push(request.postDataJSON());});
    // Fonts are optional; make the test independent of external network access.
    await page.route('**/*', route => route.request().url().startsWith(url) ? route.continue() : route.abort());
    await page.addInitScript(base => globalThis.TOOLING_API_BASE_URL = base, url);
    const value = id => page.locator(`#${id}`).inputValue();
    const text = id => page.locator(`#${id}`).textContent();
    const state = () => page.evaluate(() => readState());
    const latest = () => requests[requests.length - 1];
    const ready = () => page.waitForFunction(() => document.getElementById('estimate-state').dataset.stale === 'false');
    const change = async (id, input) => {
      const field = page.locator(`#${id}`);
      if (await field.evaluate(el => el.tagName === 'SELECT')) await field.selectOption(String(input));
      else {await field.fill(String(input)); await field.blur();}
    };
    const edit = async (id, input) => {await change(id,input); await ready();};
    const openComponent = async id => {
      const detail = page.locator(`#block-${id}-pieces`).locator('xpath=ancestor::details[1]');
      if ((await detail.getAttribute('open')) === null) await detail.locator('summary').click();
    };
    const check = async (name, test) => {await test(); console.log(`PASS ${++passed}: ${name}`);};
    await page.goto(`${url}/index.html`);
    await page.waitForFunction(() => document.getElementById('calc-status').textContent === 'Ready to calculate.');

    await check('Catalog, six bands, initial calculation and nautical miles', async () => {
      assert.equal(await page.locator('#inp-process option').count(),29);
      assert.equal(await page.locator('#inp-cycles option').count(),6);
      assert.equal(await value('inp-process'),'die_casting');
      closeTo(Number(await value('inp-sea')),19800/1.852);
      await page.locator('#calculate-btn').click(); await ready();
      assert.equal(await page.locator('#out-blocks tbody tr').count(),2);
      assert.equal(await page.locator('#block-editors details').count(),2);
      assert((await text('block-counts')).startsWith('2 machined blocks'));
      assert((await text('rec-confidence')).includes('Engineering review'));
      assert((await text('confidence-explanation')).length>100);
    });
    await check('Quantity boundaries alter guidance without resizing stock', async () => {
      await edit('inp-expected-cycles',20);
      const stock = await page.locator('#out-blocks tbody tr td:nth-child(4)').allTextContents();
      await edit('inp-expected-cycles',21);
      assert.equal(await value('inp-cycles'),'q2');
      assert.equal(latest().expected_quantity,21);
      assert((await text('rec-reasons')).includes('21–100'));
      assert.deepEqual(await page.locator('#out-blocks tbody tr td:nth-child(4)').allTextContents(),stock);
    });
    await check('Wall thickness, explicit envelopes, automatic updates and component reset', async () => {
      await edit('inp-material-thickness',5);
      closeTo(Number(await value('block-P03-C02-nominal_length_mm')),90);
      await openComponent('P03-C01');
      const initial = await value('block-P03-C01-nominal_length_mm');
      const total = await text('out-total');
      await edit('block-P03-C01-nominal_length_mm',200);
      assert.notEqual(await text('out-total'),total);
      assert.equal(await value('block-P03-C01-nominal_length_mm'),'200');
      assert.equal(latest().block_overrides[0].nominal_length_mm,200);
      await edit('inp-expected-cycles',101);
      assert.equal(await value('block-P03-C01-nominal_length_mm'),'200');
      await page.locator('[data-reset-component="P03-C01"]').click(); await ready();
      assert.equal(await value('block-P03-C01-nominal_length_mm'),initial);
      assert.equal(latest().block_overrides.length,0);
    });
    await check('Per-component material, route validation, reset and zero removal volume', async () => {
      const original = Number(await value('block-P03-C01-block_price_per_tonne'));
      const total = await text('out-total');
      await edit('block-P03-C01-block_price_per_tonne',original*2);
      assert.notEqual(await text('out-total'),total);
      assert.equal(Number(await value('block-P03-C01-block_price_per_tonne')),original*2);
      await change('block-P03-C01-cnc_3_axis_share',0);
      await page.waitForFunction(() => document.getElementById('calc-status').classList.contains('err'));
      assert.equal(await page.locator('#estimate-state').getAttribute('data-stale'),'true');
      assert((await text('calc-status')).includes('100'),await text('calc-status'));
      await page.locator('[data-reset-component="P03-C01"]').click(); await ready();
      assert.equal(Number(await value('block-P03-C01-block_price_per_tonne')),original);
      await edit('block-P03-C01-machining_volume_m3',0);
      assert.equal(latest().block_overrides[0].machining_volume_m3,0);
      await edit('block-P03-C01-material_family','aluminum_tooling');
      assert.equal(latest().block_overrides[0].material_family,'aluminum_tooling');
      await page.locator('#reset-blocks').click(); await ready();
    });
    await check('Reference mode locks part dimensions and stock form can change', async () => {
      await edit('inp-l',200);
      await edit('inp-sizing-mode','reference');
      assert(await page.locator('#inp-l').isDisabled());
      assert.equal(await value('inp-l'),'100');
      await openComponent('P03-C01');
      await edit('block-P03-C01-stock_form','Round billet');
      assert(await page.locator('#block-P03-C01-nominal_width_mm').isDisabled());
      assert((await page.locator('#out-blocks tbody tr').first().innerText()).includes('Diameter'));
      await edit('block-P03-C01-stock_form','Rectangular block');
      assert(!(await page.locator('#block-P03-C01-nominal_width_mm').isDisabled()));
      await edit('inp-sizing-mode','part_scaled');
      assert(!(await page.locator('#inp-l').isDisabled()));
    });
    await check('Country flags, missing FX, USD conversion and pending overrides', async () => {
      const countryDetails = page.locator('#inp-cnc3-rate').locator('xpath=ancestor::details[1]');
      await countryDetails.locator('summary').click();
      await edit('inp-cnc3-rate',999);
      assert((await text('country-defaults-flag')).includes('modified'));
      await page.locator('#reset-country-defaults').click(); await ready();
      assert.equal(await text('country-defaults-flag'),'Country defaults');
      await openComponent('P03-C01');
      const price = Number(await value('block-P03-C01-block_price_per_tonne'));
      await change('inp-country','CN');
      await page.waitForFunction(() => document.getElementById('calc-status').textContent.includes('exchange rate'));
      assert(await page.locator('#block-P03-C01-block_price_per_tonne').isDisabled());
      await change('inp-fx',1.2); await change('inp-fx-date','2026-10-14'); await ready();
      closeTo(Number(await value('block-P03-C01-block_price_per_tonne')),price*1.2);
      await edit('block-P03-C01-block_price_per_tonne',price*2*1.2);
      closeTo((await state()).block_overrides[0].tooling_material_assumptions.block_price_per_tonne,price*2);
      await edit('inp-fx',1.5);
      closeTo(Number(await value('block-P03-C01-block_price_per_tonne')),price*2*1.5);
      // A currency edit before the debounce must preserve the pending EUR value.
      await change('block-P03-C01-block_price_per_tonne',price*3*1.5);
      await change('inp-fx',2); await ready();
      closeTo(Number(await value('block-P03-C01-block_price_per_tonne')),price*3*2);
      await edit('inp-country','DE');
      closeTo(Number(await value('block-P03-C01-block_price_per_tonne')),price*3);
    });
    await check('Purchased assembly is explicitly partial until price and mass are supplied', async () => {
      await edit('inp-process','sheet_hydroforming');
      assert.equal(latest().block_overrides.length,0);
      assert((await text('estimate-scope')).includes('Partial subtotal'));
      assert((await text('block-counts')).includes('1 purchased'));
      await openComponent('P20-C03');
      await edit('block-P20-C03-purchased_unit_cost_eur',1200);
      assert((await text('estimate-scope')).includes('Partial subtotal'));
      await edit('block-P20-C03-purchased_unit_weight_kg',30);
      assert.equal(await text('estimate-scope'),'');
      await edit('block-P20-C03-purchased_unit_cost_eur',0);
      await edit('block-P20-C03-purchased_unit_weight_kg',0);
      assert.equal(await text('estimate-scope'),'');
      await page.locator('#reset-blocks').click(); await ready();
      assert((await text('estimate-scope')).includes('Partial subtotal'));
    });
    await check('Every detailed process renders its component editor; tool sets count once', async () => {
      const processes = await page.locator('#inp-process optgroup').first().locator('option').evaluateAll(options=>options.map(o=>o.value));
      for (const process of processes) {
        await edit('inp-process',process);
        assert.equal(latest().process,process);
        assert((await page.locator('#block-editors details').count())>0,process);
      }
      await edit('inp-process','progressive_die_stamping');
      assert((await text('block-counts')).startsWith('10 machined'));
      await edit('inp-pqty',2);
      assert((await text('block-counts')).startsWith('20 machined'));
    });
    await check('Legacy calculation and tooling overrides remain available', async () => {
      await edit('inp-process','plastic_injection');
      assert(await page.locator('#workbook-results').isHidden());
      assert(await page.locator('#legacy-tooling-assumptions').isVisible());
      if((await page.locator('#legacy-tooling-assumptions').getAttribute('open'))===null) await page.locator('#legacy-tooling-assumptions > summary').click();
      const price = Number(await value('inp-tool-price'));
      const total = await text('out-total');
      await edit('inp-tool-price',price*2);
      assert.notEqual(await text('out-total'),total);
      assert.equal(Number(await value('inp-tool-price')),price*2);
      await page.locator('#reset-tooling-defaults').click(); await ready();
      assert.equal(Number(await value('inp-tool-price')),price);
      assert(!('expected_quantity' in latest()));
    });
    await check('Zero freight, restore, and whole-unit input arrows', async () => {
      await page.locator('[data-tab="transport"]').click();
      await edit('road-rate',0); await edit('sea-rate',0);
      assert((await text('freight-breakdown')).includes('Total freight: EUR 0.00'));
      await page.locator('#reset-logistics').click(); await ready();
      closeTo(Number(await value('road-rate')),5.6);
      await page.locator('[data-tab="calc"]').click();
      const sea = page.locator('#inp-sea'); await sea.fill('10'); await sea.press('ArrowUp'); await sea.blur(); await ready();
      assert.equal(await value('inp-sea'),'11');
      await edit('inp-process','die_casting'); await openComponent('P03-C01');
      const field=page.locator('#block-P03-C01-allowance_mm');
      await field.fill('3'); await field.press('ArrowUp'); await field.blur(); await ready();
      assert.equal(await field.inputValue(),'4');
      assert(await page.locator('input[type=number]').evaluateAll(fields=>fields.every(f=>f.step==='1')));
    });
    await check('Late responses cannot replace newer edits', async () => {
      let release, captured;
      const blocked = new Promise(resolve=>release=resolve);
      const intercepted = new Promise(resolve=>captured=resolve);
      let first=true;
      await page.route('**/api/calculate',async route=>{
        if(first){first=false;const response=await route.fetch();captured();await blocked;try{await route.fulfill({response});}catch{}}
        else await route.continue();
      });
      await change('inp-l',110); await intercepted;
      await edit('inp-l',210);
      const newest=await text('out-total'); release(); await pause(200);
      assert.equal(await text('out-total'),newest); assert.equal(latest().part.length_mm,210);
      await page.unroute('**/api/calculate');
    });
    await check('Desktop and mobile layout with no document overflow or runtime errors', async () => {
      await page.locator('#reset-blocks').click(); await ready();
      await page.locator('#use-reference-part').click(); await ready();
      const screenshots=process.env.TOOLING_SCREENSHOTS;
      if(screenshots)fs.mkdirSync(screenshots,{recursive:true});
      for(const [width,height] of [[1440,1080],[390,844]]){
        await page.setViewportSize({width,height});
        await page.evaluate(()=>scrollTo(0,0));
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Page overflows at ${width}px`);
        if(screenshots)await page.screenshot({path:path.join(screenshots,`tooling-${width}.png`),fullPage:true});
      }
      assert.deepEqual(failures,[]);
    });
    console.log(`${passed} browser scenarios passed, ${requests.length} calculation requests; no deployed API calls.`);
  } finally {
    if(browser)await browser.close();
    server.kill();
    await new Promise(resolve=>server.exitCode!==null?resolve():server.once('exit',resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
