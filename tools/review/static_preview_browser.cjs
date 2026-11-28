// SPDX-License-Identifier: Apache-2.0
// Optional real Chromium probe; requires an environment with Playwright and Chromium.
const {chromium}=require('playwright');
const fs=require('fs'),crypto=require('crypto'),assert=require('assert/strict'),path=require('path');
const root=process.argv[2], base=process.argv[3];
if(!root || !base) throw Error('Usage: node tools/review/static_preview_browser.cjs PREVIEW_DIRECTORY LOOPBACK_URL');
if(!['127.0.0.1','localhost','[::1]'].includes(new URL(base).hostname)) throw Error('Use a loopback preview URL');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const raw=fs.readFileSync(path.join(root,'data/health.json'));
 const expected=JSON.parse(raw).trials[0].simulator.snapshots.find(s=>s.time_ns==='4440000000');
 let href;
 for(const width of [360,390,430]) {
  const page=await browser.newPage({viewport:{width,height:844}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(base);href=await page.getByRole('link',{name:'Open replay'}).getAttribute('href');
  await page.getByRole('link',{name:'Open replay'}).focus();await page.keyboard.press('Enter');
  await page.waitForSelector('main:not([hidden])');
  await page.locator('#exact').fill('4440000000');await page.locator('#exact').press('Enter');
  assert.deepEqual(JSON.parse(await page.locator('#items').innerText()),expected.items);
  await page.locator('#timeline').focus();await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#observed').innerText(),'4460000000');
  await page.locator('#previous').click();assert.equal(await page.locator('#observed').innerText(),'4440000000');
  assert.equal(await page.locator('#scenario-panel').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(root,`mobile-${width}.png`),fullPage:true});
  console.log('real G1 keyboard/seek/mobile passed',width);
  // Same tab: invalid changed identity must not retain the previous observation.
  await page.evaluate(()=>{location.hash=location.hash.replace(/sha256=[a-f0-9]+/,'sha256='+'0'.repeat(64));});
  await page.getByRole('alert').filter({hasText:'Checksum mismatch'}).waitFor();assert.equal(await page.locator('main').isVisible(),false);
  await page.close();
 }
 const page=await browser.newPage();
 const synthetic=JSON.stringify({format:'livingproof-evaluator-health/1',trials:[{trial:{run_id:'time-only',configuration:'test',index:1},simulator:{provenance:'simulator',sample_count:1,snapshots:[{time_ns:'0'}]}}]});
 const params=new URLSearchParams({file:'data/health.json',sha256:crypto.createHash('sha256').update(synthetic).digest('hex'),run:'time-only',configuration:'test',trial:'1'});
 await page.route('**/data/health.json',route=>route.fulfill({status:200,body:synthetic,contentType:'application/json'}));
 await page.goto(new URL('viewer.html',base).href+'#'+params);await page.waitForSelector('main:not([hidden])');assert.equal(await page.locator('#height').innerText(),'Not reported');
 await page.unroute('**/data/health.json');await page.route('**/data/health.json',route=>route.fulfill({status:404,body:'missing'}));
 await page.reload();await page.getByRole('alert').filter({hasText:'unavailable'}).waitFor();assert.equal(await page.locator('main').isVisible(),false);
 console.log('time-only and missing file visible refusal passed');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
