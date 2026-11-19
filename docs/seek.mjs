// SPDX-License-Identifier: Apache-2.0
// Browser-compatible reference for the wire contract; no Node or server APIs.
export function nanoseconds(value) {
  if (typeof value !== "string" || value.match(/^(0|[1-9][0-9]*)$/)?.[0] !== value) {
    throw new TypeError("Timestamp must be a canonical nonnegative decimal string, e.g. '0'");
  }
  return BigInt(value);
}

export function seek(snapshots, timeNs) {
  const target = nanoseconds(timeNs);
  // Replay.to_json() supplies stable ascending order. Retain duplicate order.
  let low = 0;
  let high = snapshots.length;
  while (low < high) {
    const middle = low + Math.floor((high - low) / 2);
    if (nanoseconds(snapshots[middle].time_ns) < target) low = middle + 1;
    else high = middle;
  }
  return snapshots[low] ?? null;
}
