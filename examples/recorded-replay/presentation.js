// SPDX-License-Identifier: Apache-2.0
// Separate presentation lookup; Replay.seek remains first-at-or-after.
function presentationIndex(rows, time) {
  let lo = 0, hi = rows.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (BigInt(rows[mid].time_ns) <= time) lo = mid + 1;
    else hi = mid;
  }
  return lo - 1; // Last duplicate in stable file order; -1 before first / empty.
}
if (typeof module !== 'undefined') module.exports = {presentationIndex};
