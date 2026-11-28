// SPDX-License-Identifier: Apache-2.0
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
globalThis.crypto = webcrypto;
const {loadDetails} = require('../examples/recorded-replay/loader.js');
const base='http://127.0.0.1:8000/viewer.html';
const doc=rows=>({format:'livingproof-evaluator-health/1',trials:[{trial:{run_id:'run',configuration:'stock',index:1},simulator:{provenance:'simulator',sample_count:rows.length,snapshots:rows},robot:{status:'no robot health telemetry'}}]});
async function input(value) {
 const raw=new TextEncoder().encode(JSON.stringify(value));
 const sha=Buffer.from(await crypto.subtle.digest('SHA-256',raw)).toString('hex');
 return {raw,fragment:new URLSearchParams({file:'data/health.json',sha256:sha,run:'run',configuration:'stock',trial:'1'}).toString()};
}
(async()=>{
 const valid=await input(doc([{time_ns:'4440000000',items:{text:'</script><img src=x onerror=alert(1)>'}}]));
 let calls=0;
 const fetcher=async (url,opts)=>{calls++;assert.equal(url,'http://127.0.0.1:8000/data/health.json');assert.equal(opts.redirect,'error');assert.equal(opts.credentials,'omit');return new Response(valid.raw)};
 const result=await loadDetails(valid.fragment,base,fetcher);
 assert.equal(result.replay.snapshots[0].time_ns,'4440000000');assert.equal(result.report.observations_only,true);
 for(const rows of [[],[{time_ns:'0'}]]) {const v=await input(doc(rows));assert.deepEqual((await loadDetails(v.fragment,base,async()=>new Response(v.raw))).replay.snapshots,rows);}
 for(const file of ['../health.json','https://other.test/health.json','/data/health.json','data/%2e%2e.json','data/a.json?x=1','data/a.json#x','data/a\\b.json']) {
  const p=new URLSearchParams(valid.fragment);p.set('file',file);const n=calls;await assert.rejects(loadDetails(p.toString(),base,fetcher));assert.equal(calls,n);
 }
 for(const key of ['sha256','run','configuration','trial']) {const p=new URLSearchParams(valid.fragment);p.delete(key);await assert.rejects(loadDetails(p.toString(),base,fetcher));}
 const wrong=new URLSearchParams(valid.fragment);wrong.set('sha256','0'.repeat(64));await assert.rejects(loadDetails(wrong.toString(),base,fetcher),/Checksum mismatch/);
 await assert.rejects(loadDetails(valid.fragment,base,async()=>new Response('not even JSON')),/Checksum mismatch/);
 await assert.rejects(loadDetails(valid.fragment,base,async()=>new Response('missing',{status:404})),/unavailable/);
 await assert.rejects(loadDetails(valid.fragment,base,async()=>{throw Error('redirect refused')}),/redirect/);
 await assert.rejects(loadDetails(valid.fragment,base,async()=>new Response('',{headers:{'content-length':16777217}})),/16 MiB/);
 await assert.rejects(loadDetails(valid.fragment,base,async()=>new Response(new Uint8Array(16777217))),/16 MiB/);
 for (const mutate of [d=>d.trials.push(d.trials[0]),d=>d.trials[0].trial.run_id='wrong',d=>delete d.trials[0].simulator.snapshots,d=>d.trials[0].simulator.sample_count=2,d=>d.trials[0].simulator.snapshots[0].time_ns=0]) {
  const d=doc([{time_ns:'0'}]);mutate(d);const v=await input(d);await assert.rejects(loadDetails(v.fragment,base,async()=>new Response(v.raw)));
 }
 console.log('static loader: valid, empty, time-only, identity, digest, tamper, paths, missing, redirect and byte limits passed');
})().catch(e=>{console.error(e);process.exitCode=1});
