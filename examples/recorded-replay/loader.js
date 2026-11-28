// SPDX-License-Identifier: Apache-2.0
// Trusted local preview code. The link supplies data identity, never executable content.
async function loadDetails(fragment, base, fetcher = fetch) {
  const params = new URLSearchParams(fragment.replace(/^#/, ''));
  const keys = ['file', 'sha256', 'run', 'configuration', 'trial'];
  if ([...params.keys()].length !== keys.length || keys.some(k => params.getAll(k).length !== 1 || !params.get(k))) {
    throw Error('Link must include one file, checksum, run, configuration and trial.');
  }
  const file = params.get('file'), sha = params.get('sha256'), trial = params.get('trial');
  if (!/^data\/[A-Za-z0-9_-]+\.json$/.test(file)) throw Error('Expected a JSON file inside the preview data directory.');
  if (!/^[a-f0-9]{64}$/.test(sha)) throw Error('Expected the report-published SHA-256.');
  if (!/^[1-9][0-9]*$/.test(trial) || !Number.isSafeInteger(Number(trial))) throw Error('Expected a positive trial index.');
  const url = new URL(file, base);
  if (url.origin !== new URL(base).origin || !['http:', 'https:'].includes(url.protocol)) throw Error('Data must use the same HTTP origin.');
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
  const limit = 16 * 1024 * 1024;
  let reader;
  try {
    const response = await fetcher(url.href, {redirect:'error', credentials:'omit', cache:'no-store', signal:controller.signal});
    if (!response.ok || response.redirected || (response.url && response.url !== url.href)) throw Error('Recorded data is unavailable or redirected. Return to the source report.');
    if (Number(response.headers.get('content-length')) > limit) throw Error('Recorded data exceeds 16 MiB.');
    if (!response.body) throw Error('Recorded data has no response body.');
    reader = response.body.getReader();
    const chunks = []; let size = 0;
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw Error('Recorded data exceeds 16 MiB.');
      chunks.push(value);
    }
    const bytes = new Uint8Array(size); let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2,'0')).join('');
    if (digest !== sha) throw Error('Checksum mismatch. No observations displayed.');
    const doc = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes));
    return detailsPresentation(doc, params);
  } finally {
    controller.abort();
    if (reader) await reader.cancel().catch(() => {});
    clearTimeout(timeout);
  }
}
function detailsPresentation(doc, params) {
  const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const time = x => typeof x === 'string' && /^(0|[1-9][0-9]*)$/.test(x);
  if (!object(doc) || doc.format !== 'livingproof-evaluator-health/1' || !Array.isArray(doc.trials) || doc.trials.some(t => !object(t))) throw Error('Unsupported Health details envelope.');
  const selected = doc.trials.filter(t => object(t.trial) && t.trial.run_id === params.get('run') && t.trial.configuration === params.get('configuration') && t.trial.index === Number(params.get('trial')));
  if (selected.length !== 1) throw Error('Expected exactly one matching trial.');
  const trial = selected[0], sim = trial.simulator;
  if (!object(sim) || sim.provenance !== 'simulator' || !Array.isArray(sim.snapshots) || !Number.isSafeInteger(sim.sample_count) || sim.sample_count !== sim.snapshots.length) throw Error('Simulator observations, provenance or sample count are invalid.');
  const rows = sim.snapshots;
  for (const row of rows) {
    if (!object(row) || !time(row.time_ns) || ('items' in row && !object(row.items)) || (object(row.source) && 'publish_time_ns' in row.source && !time(row.source.publish_time_ns))) throw Error('Invalid snapshot or timestamp.');
  }
  // JSON.parse accepts overflowing numbers. Never present those as observations.
  const pending = [doc];
  while (pending.length) {
    const value = pending.pop();
    if (typeof value === 'number' && !Number.isFinite(value)) throw Error('Nonfinite observation.');
    if (value && typeof value === 'object') for (const child of Object.values(value)) pending.push(child);
  }
  const sorted = [...rows].sort((a,b) => BigInt(a.time_ns) < BigInt(b.time_ns) ? -1 : BigInt(a.time_ns) > BigInt(b.time_ns) ? 1 : 0);
  const {snapshots, ...simIdentity} = sim;
  return {replay:{snapshots:sorted}, report:{
    input:{provenance:'Simulator observations; robot telemetry: ' + (typeof trial.robot?.status === 'string' ? trial.robot.status : 'Not reported'), details_sha256:params.get('sha256'), identity:{...trial, simulator:simIdentity}},
    limitations:'Recorded samples only. No health verdict, grade or hardware health proof. Missing robot telemetry is not healthy telemetry. Digest checks supplied bytes against the selected report, not producer authenticity.',
    observations_only:true
  }};
}
if (typeof module !== 'undefined') module.exports = {loadDetails, detailsPresentation};
