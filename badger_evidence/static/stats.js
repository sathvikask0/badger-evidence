"use strict";
const BadgerStats = {
  potencyValues(records, endpoint) {
    if (!endpoint) return [];
    return records.filter(r => r.measurement_type === endpoint && r.relation === "=" && !(r.flags || []).length)
      .map(r => r.normalized_value_nm).filter(v => Number.isFinite(v) && v > 0);
  },
  median(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }
};
if (typeof module !== "undefined") module.exports = BadgerStats;
if (typeof window !== "undefined") window.BadgerStats = BadgerStats;
