"use strict";
// Flags that describe context, not the value itself; they do not disqualify a value.
const INFO_FLAGS = new Set(["missing_assay_context", "target_from_caption"]);
const blocking = (r) => (r.flags || []).some((f) => !INFO_FLAGS.has(f));
const BadgerStats = {
  potencyValues(records, endpoint) {
    if (!endpoint) return [];
    return records.filter(r => r.measurement_type === endpoint && r.relation === "=" && !blocking(r))
      .map(r => r.normalized_value_nm).filter(v => Number.isFinite(v) && v > 0);
  },
  commonestEndpoint(records) {
    const counts = {};
    for (const r of records) if (r.relation === "=" && !blocking(r) && Number.isFinite(r.normalized_value_nm) && r.normalized_value_nm > 0) counts[r.measurement_type] = (counts[r.measurement_type] || 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] || "";
  },
  median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }
};
if (typeof module !== "undefined") module.exports = BadgerStats;
if (typeof window !== "undefined") window.BadgerStats = BadgerStats;
