// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { nanoseconds, seek } from "../docs/seek.mjs";

const input = JSON.parse(readFileSync(0, "utf8"));
// These are actual CLI JSON strings, parsed without a custom parser or reviver.
const replay = JSON.parse(input.replay);
const assessment = JSON.parse(input.assessment);
const sought = JSON.parse(input.sought);
for (const snapshot of [...replay.snapshots, sought]) {
  assert.equal(typeof snapshot.time_ns, "string");
  assert.equal(typeof snapshot.source.publish_time_ns, "string");
  nanoseconds(snapshot.time_ns);
  nanoseconds(snapshot.source.publish_time_ns);
}
assert.equal(typeof assessment.time_ns, "string");
nanoseconds(assessment.time_ns);
for (const value of input.invalid) {
  assert.throws(() => nanoseconds(value), /canonical nonnegative decimal string/);
  assert.throws(() => seek(replay.snapshots, value), /canonical nonnegative decimal string/);
}
process.stdout.write(JSON.stringify({
  replay, assessment, sought,
  selections: input.queries.map(time => seek(replay.snapshots, time)),
  empty: seek([], "0"),
  invalid_rejected: input.invalid.length,
}));
