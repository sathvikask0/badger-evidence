"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { dataset: null, filtered: [], selectedId: null, loading: false, target: "", chembl: {}, chemblLoading: "", sort: "" };
  const ROW_CAP = 500;
  const numberFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 5 });
  const node = (tag, className, text) => {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined && text !== null) result.textContent = String(text);
    return result;
  };
  const text = (value, fallback = "—") => value === undefined || value === null || value === "" ? fallback : String(value);
  const asArray = (value) => Array.isArray(value) ? value : value === undefined || value === null || value === "" ? [] : [value];
  const flagsFor = (record) => asArray(record.flags);
  const formatted = (value) => typeof value === "number" && Number.isFinite(value) ? numberFormat.format(value) : text(value);
  const contextFor = (record) => record.assay_context || (state.dataset && asArray(state.dataset.articles).find((a) => a.pmcid === record.pmcid)?.assay_context) || [];
  const labelFor = (record) => text(record.compound_label, "Unlabeled compound");

  function safeLink(url, title) {
    const link = node("a", "", title);
    try {
      const parsed = new URL(url, window.location.origin);
      if (!["http:", "https:"].includes(parsed.protocol)) return node("span", "detail-muted", title);
      link.href = parsed.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } catch (_) {
      return node("span", "detail-muted", title);
    }
    return link;
  }

  function currentFilters() {
    return { source: $("source-filter").value, target: state.target, q: $("search").value.trim(), pmcid: $("paper-filter").value, measurement: $("measurement-filter").value, flagged: $("flagged-filter").checked };
  }

  function updateExport(filters) {
    const params = new URLSearchParams();
    if (filters.target) params.set("target", filters.target);
    if (filters.q) params.set("q", filters.q);
    if (filters.pmcid) params.set("pmcid", filters.pmcid);
    if (filters.measurement) params.set("measurement", filters.measurement);
    if (filters.flagged) params.set("flagged", "1");
    $("export-link").href = `api/export.csv${params.size ? `?${params.toString()}` : ""}`;
  }

  const isStatic = Boolean(document.querySelector('meta[name="static-site"]'));
  const csvFields = ["id", "source", "pmcid", "compound_id", "compound_label", "target", "taxon_id", "measurement_type", "relation", "value", "unit", "normalized_value_nm", "uncertainty", "raw_value", "table_id", "row_index", "source_url", "source_sha256", "review_status", "flags", "assay_context"];
  function csvCell(key, value) {
    if (value === null || value === undefined) value = "";
    else if (key === "flags") value = asArray(value).join(";");
    else if (key === "assay_context") value = JSON.stringify(value || []);
    value = String(value);
    if (key !== "relation" && /^\s*[=+\-@\t\r]/.test(value)) value = "'" + value;
    return /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
  }
  function staticExport(event) {
    if (!isStatic || !state.dataset) return;
    event.preventDefault();
    const f = currentFilters();
    const q = f.q.toLowerCase();
    const rows = pool(f).filter((r) => (!q || [r.compound_label, r.pmcid, r.target_name, r.measurement_type].join(" ").toLowerCase().includes(q)) && (!f.target || r.target === f.target) && (!f.pmcid || r.pmcid === f.pmcid) && (!f.measurement || r.measurement_type === f.measurement) && (!f.flagged || flagsFor(r).length > 0));
    const csv = "\ufeff" + [csvFields.join(","), ...rows.map((r) => csvFields.map((k) => csvCell(k, k === "assay_context" ? (r.chembl ? [r.chembl.assay_desc] : contextFor(r)) : k === "source" ? (r.source || "AI-checked papers") : k === "source_url" && r.chembl ? `https://www.ebi.ac.uk/chembl/explore/activity/${r.chembl.activity}` : r[k])).join(","))].join("\r\n") + "\r\n";
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = "badger-evidence.csv"; document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function chemblInfo(key) { return state.dataset && state.dataset.chembl ? state.dataset.chembl[key] : null; }
  function toChemblRecords(key, data) {
    const t = asArray(state.dataset.targets).find((x) => x.key === key) || {};
    return data.rows.map((r) => {
      const [aid, mol, name, type, rel, value, units, pchembl, assay, doc, year, validity] = r;
      const relation = (rel || "=").replaceAll("'", "");
      const v = Number(value);
      return { id: `chembl:${aid}`, source: "chembl", pmcid: "", target: key, target_name: t.name, compound_label: name || mol, compound_id: mol,
        measurement_type: type, relation, value: v, unit: units || "nM", normalized_value_nm: v, raw_value: `${relation === "=" ? "" : relation + " "}${formatted(v)}`,
        flags: validity ? ["chembl_validity_comment"] : [], review_status: "chembl",
        chembl: { mol: (data.mols || {})[mol], activity: aid, assay, assay_desc: (data.assays[assay] || [])[0], assay_type: (data.assays[assay] || [])[1], doc, doc_meta: data.docs[doc] || null, year, pchembl, validity } };
    });
  }
  async function ensureChembl(key) {
    if (!key || state.chembl[key] || !chemblInfo(key)) return;
    state.chemblLoading = key;
    $("results-summary").textContent = "Loading ChEMBL data…";
    try {
      const response = await fetch(`api/chembl/${key}.json`);
      if (!response.ok) throw new Error(String(response.status));
      state.chembl[key] = toChemblRecords(key, await response.json());
    } catch (error) {
      state.chembl[key] = [];
      $("results-summary").textContent = "ChEMBL data could not be loaded.";
    } finally {
      state.chemblLoading = "";
    }
  }
  function pool(filters) {
    const verified = filters.source === "chembl" ? [] : state.dataset.records;
    if (filters.source === "verified" || !filters.target) return verified;
    return verified.concat(state.chembl[filters.target] || []);
  }

  // ---- Shareable URL state -------------------------------------------------
  function writeUrl(filters) {
    const params = new URLSearchParams();
    if (filters.target) params.set("enzyme", filters.target);
    if (filters.source && filters.source !== "verified") params.set("source", filters.source);
    if (filters.q) params.set("q", filters.q);
    if (filters.measurement) params.set("type", filters.measurement);
    if (state.sort) params.set("sort", state.sort);
    if (state.selectedId) params.set("id", state.selectedId);
    const url = `${location.pathname}${params.size ? `?${params}` : ""}`;
    try { history.replaceState(null, "", url); } catch (_) { /* ignore */ }
  }
  function readUrl() {
    const params = new URLSearchParams(location.search);
    return { target: params.get("enzyme") || "", source: params.get("source") || "", q: params.get("q") || "", type: params.get("type") || "", sort: params.get("sort") || "", id: params.get("id") || "" };
  }

  // ---- Theme ------------------------------------------------------------------
  const THEMES = ["auto", "light", "dark"];
  function applyTheme(theme) {
    if (theme === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = theme;
    const button = $("theme-toggle");
    if (button) { button.textContent = theme[0].toUpperCase() + theme.slice(1); button.setAttribute("aria-label", `Colour theme: ${theme}`); }
  }
  function currentTheme() { return document.documentElement.dataset.theme || "auto"; }

  // ---- Potency landscape ------------------------------------------------------
  const LOG_MIN = -3, LOG_MAX = 6, BIN = 0.5; // log10(nM): 1 pM .. 1 mM
  const tickLabel = { "-3": "1 pM", "0": "1 nM", "3": "1 µM", "6": "1 mM" };
  function svgEl(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function renderPotency() {
    const panel = $("potency-panel");
    if (!panel) return;
    const chosen = $("measurement-filter").value;
    const endpoint = chosen || window.BadgerStats.commonestEndpoint(state.filtered);
    const values = window.BadgerStats.potencyValues(state.filtered, endpoint);
    if (!state.target || !endpoint || values.length < 5) { panel.hidden = true; return; }
    panel.hidden = false;
    const target = asArray(state.dataset.targets).find((t) => t.key === state.target);
    $("potency-title").textContent = `Potency landscape · ${target ? target.name : state.target} · ${endpoint}`;
    const nb = Math.round((LOG_MAX - LOG_MIN) / BIN);
    const counts = new Array(nb).fill(0);
    let below = 0, above = 0;
    for (const v of values) {
      const l = Math.log10(v);
      if (l < LOG_MIN) { below++; counts[0]++; } else if (l >= LOG_MAX) { above++; counts[nb - 1]++; } else counts[Math.floor((l - LOG_MIN) / BIN)]++;
    }
    const sorted = values.slice().sort((a, b) => a - b);
    const median = window.BadgerStats.median(sorted);
    $("potency-note").textContent = `${numberFormat.format(values.length)} exact ${endpoint} values${chosen ? "" : " (most common type; change with Measurement)"} · median ${formatted(median)} nM · assay conditions differ`;
    const host = $("potency-chart");
    const W = Math.max(280, host.clientWidth || 800), H = 170, m = { l: 36, r: 12, t: 12, b: 28 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const raw = Math.max(...counts), mag = 10 ** Math.floor(Math.log10(raw));
    const max = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((v) => v >= raw);
    const x = (l) => m.l + ((l - LOG_MIN) / (LOG_MAX - LOG_MIN)) * iw;
    const y = (c) => m.t + ih - (c / max) * ih;
    const svg = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "potency-svg" });
    // recessive grid: 3 lines
    for (const f of [0.5, 1]) {
      const c = max * f;
      svg.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: y(c), y2: y(c), class: "grid" }), svgEl("text", { x: m.l - 6, y: y(c) + 4, class: "axis-label", "text-anchor": "end" }, numberFormat.format(c)));
    }
    svg.append(svgEl("line", { x1: m.l, x2: W - m.r, y1: m.t + ih, y2: m.t + ih, class: "baseline" }));
    const bw = iw / nb;
    counts.forEach((c, i) => {
      const lo = LOG_MIN + i * BIN, x0 = x(lo) + 1, w = Math.max(1, bw - 2);
      const g = svgEl("g", { class: "bin" });
      if (c) {
        const top = y(c), h = m.t + ih - top, r = Math.min(4, w / 2, h);
        g.append(svgEl("path", { class: "bar", d: `M${x0},${m.t + ih}V${top + r}Q${x0},${top} ${x0 + r},${top}H${x0 + w - r}Q${x0 + w},${top} ${x0 + w},${top + r}V${m.t + ih}Z` }));
      }
      const hit = svgEl("rect", { x: x(lo), y: m.t, width: bw, height: ih, class: "hit" });
      const range = `${nice(10 ** lo)}–${nice(10 ** (lo + BIN))} nM`;
      const label = i === 0 && below ? `≤ ${nice(10 ** (lo + BIN))} nM` : i === nb - 1 && above ? `≥ ${nice(10 ** lo)} nM` : range;
      hit.addEventListener("mouseenter", () => showTip(`${numberFormat.format(c)} value${c === 1 ? "" : "s"}`, label, x(lo) + bw / 2));
      hit.addEventListener("mouseleave", hideTip);
      g.append(hit);
      svg.append(g);
    });
    for (let l = LOG_MIN; l <= LOG_MAX; l++) {
      svg.append(svgEl("line", { x1: x(l), x2: x(l), y1: m.t + ih, y2: m.t + ih + 4, class: "tick" }));
      if (tickLabel[l] !== undefined) svg.append(svgEl("text", { x: x(l), y: H - 8, class: "axis-label", "text-anchor": l === LOG_MIN ? "start" : l === LOG_MAX ? "end" : "middle" }, tickLabel[l]));
    }
    const sel = state.filtered.find((r) => r.id === state.selectedId);
    if (sel && sel.normalized_value_nm > 0) {
      const l = Math.min(LOG_MAX, Math.max(LOG_MIN, Math.log10(sel.normalized_value_nm)));
      const sx = x(l);
      svg.append(svgEl("line", { x1: sx, x2: sx, y1: m.t - 4, y2: m.t + ih, class: "marker" }));
      const right = sx > W * 0.7;
      svg.append(svgEl("text", { x: right ? sx - 6 : sx + 6, y: m.t + 8, class: "marker-label", "text-anchor": right ? "end" : "start" }, `${labelFor(sel)}: ${formatted(sel.normalized_value_nm)} nM`));
    }
    host.setAttribute("aria-label", `Histogram of ${values.length} potency values; median ${formatted(median)} nM.`);
    host.replaceChildren(svg);
  }
  const nice = (v) => numberFormat.format(Number(v.toPrecision(2)));
  function showTip(title, detail, px) {
    const tip = $("potency-tip");
    tip.replaceChildren(node("strong", "", title), node("span", "", detail));
    tip.hidden = false;
    const hostW = $("potency-chart").clientWidth;
    tip.style.left = `${Math.min(Math.max(px, 70), hostW - 70)}px`;
  }
  function hideTip() { $("potency-tip").hidden = true; }

  function renderTargets() {
    const data = state.dataset;
    const targets = Array.isArray(data.targets) ? data.targets : [];
    const counts = {};
    for (const record of data.records) counts[record.target] = (counts[record.target] || 0) + 1;
    const options = [new Option(`All enzymes (${numberFormat.format(data.records.length)})`, "")];
    for (const t of targets) {
      const info = chemblInfo(t.key);
      if (!counts[t.key] && !info) continue;
      const longevity = (t.tags || []).includes("longevity") ? " · longevity" : "";
      const db = info ? ` + ${numberFormat.format(info.count)} ChEMBL` : "";
      options.push(new Option(`${t.name} (${numberFormat.format(counts[t.key] || 0)}${db})${longevity}`, t.key));
    }
    $("target-filter").replaceChildren(...options);
    $("target-filter").value = state.target;
    const current = targets.find((t) => t.key === state.target);
    $("scope-name").textContent = current ? current.name : "All enzymes";
    $("scope-meta").textContent = current ? `UniProt ${current.uniprot} · ${numberFormat.format(counts[current.key] || 0)} measurements` : `${targets.length} enzymes · ${numberFormat.format(data.records.length)} measurements`;
    const info = current ? chemblInfo(current.key) : null;
    $("scope-why").textContent = current ? current.why + (info ? ` ChEMBL adds ${numberFormat.format(info.count)} database values${info.crosscheck && info.crosscheck.checked ? `; ${info.crosscheck.agreed} of ${info.crosscheck.checked} AI-checked paper values with a name-linked ChEMBL match agree.` : "."}` : "") : "";
    $("source-filter").disabled = !info;
    if (!info) $("source-filter").value = "verified";
    const papers = new Set(data.records.filter((r) => !state.target || r.target === state.target).map((r) => r.pmcid));
    const paperOptions = [new Option("All papers", "")];
    for (const article of data.articles) if (papers.has(article.pmcid)) paperOptions.push(new Option(`${article.pmcid} · ${text(article.title, "Untitled paper")}`, article.pmcid));
    const selected = $("paper-filter").value;
    $("paper-filter").replaceChildren(...paperOptions);
    $("paper-filter").value = papers.has(selected) ? selected : "";
  }

  function applyFilters() {
    if (!state.dataset) return;
    const filters = currentFilters();
    const query = filters.q.toLowerCase();
    state.filtered = pool(filters).filter((record) => {
      const searchable = [record.compound_label, record.compound_id, record.pmcid, record.target_name, record.measurement_type].filter(Boolean).join(" ").toLowerCase();
      return (!filters.target || record.target === filters.target) && (!query || searchable.includes(query)) && (!filters.pmcid || record.pmcid === filters.pmcid) && (!filters.measurement || record.measurement_type === filters.measurement) && (!filters.flagged || flagsFor(record).length > 0);
    });
    if (state.sort) {
      const dir = state.sort === "asc" ? 1 : -1;
      state.filtered = state.filtered.slice().sort((a, b) => {
        const x = a.normalized_value_nm, y = b.normalized_value_nm;
        if (x == null) return 1; if (y == null) return -1;
        return (x - y) * dir;
      });
    }
    if (!state.filtered.some((record) => record.id === state.selectedId)) state.selectedId = state.filtered[0]?.id ?? null;
    updateExport(filters);
    writeUrl(filters);
    renderPotency();
    renderRows();
    renderEvidence();
  }

  function selectRecord(record, moveToEvidence = false) {
    state.selectedId = record.id;
    for (const row of $("record-rows").children) {
      const selected = row.dataset.recordId === String(record.id);
      row.classList.toggle("selected", selected);
      row.querySelector("button").setAttribute("aria-pressed", String(selected));
    }
    renderEvidence();
    renderPotency();
    writeUrl(currentFilters());
    if (moveToEvidence && window.matchMedia("(max-width: 850px)").matches) $("evidence-panel").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function renderRows() {
    const fragment = document.createDocumentFragment();
    for (const record of state.filtered.slice(0, ROW_CAP)) {
      const selected = record.id === state.selectedId;
      const row = node("tr", selected ? "selected" : "");
      row.dataset.recordId = String(record.id);
      const identity = node("td");
      const button = node("button", "compound-button", labelFor(record));
      button.type = "button";
      button.setAttribute("aria-pressed", String(selected));
      button.setAttribute("aria-label", `Inspect compound ${labelFor(record)} from ${text(record.pmcid)}, ${text(record.measurement_type)} ${text(record.raw_value, formatted(record.value))} ${text(record.unit, "")}`);
      button.addEventListener("click", () => selectRecord(record, true));
      const pid = node("span", "paper-id", record.chembl ? `${record.compound_id} · ` : `${text(record.pmcid)} · `);
      pid.append(node("span", "target-name", text(record.target_name)));
      if (record.chembl) pid.append(node("span", "source-tag", "ChEMBL"));
      identity.append(button, pid);
      const flagCell = node("td");
      const flags = flagsFor(record);
      if (flags.length) {
        const flag = node("span", "flag-icon", "!");
        flag.title = flags.map((item) => String(item).replaceAll("_", " ")).join("; ");
        flag.setAttribute("role", "img");
        flag.setAttribute("aria-label", `${flags.length} review flag${flags.length === 1 ? "" : "s"}: ${flag.title}`);
        flagCell.append(flag);
      }
      row.append(identity, node("td", "measurement-kind", text(record.measurement_type, "Unspecified")), node("td", "number-cell", text(record.raw_value, formatted(record.value))), node("td", "unit-cell", text(record.unit)), flagCell);
      row.addEventListener("click", (event) => { if (!event.target.closest("button")) selectRecord(record, true); });
      fragment.append(row);
    }
    $("record-rows").replaceChildren(fragment);
    $("result-count").textContent = numberFormat.format(state.filtered.length);
    const badge = document.querySelector(".panel-heading .review-badge");
    if (badge) {
      const db = state.filtered.filter((r) => r.chembl).length, paper = state.filtered.length - db;
      badge.textContent = db && paper ? `${numberFormat.format(paper)} AI-checked · ${numberFormat.format(db)} ChEMBL` : db ? "ChEMBL database" : "AI-checked";
    }
    const shownNote = state.filtered.length > ROW_CAP ? ` · showing first ${ROW_CAP}, search to narrow` : "";
    $("results-summary").textContent = `${numberFormat.format(state.filtered.length)} measurements${shownNote}`;
    $("table-wrap").hidden = state.filtered.length === 0;
    $("empty-state").hidden = state.filtered.length !== 0;
  }

  function section(title) {
    const result = node("section", "detail-section");
    result.append(node("h4", "", title));
    return result;
  }

  function structureSection(chemblId, name, inchikey, smiles) {
    const sec = section("Compound identity");
    const img = document.createElement("img");
    img.className = "structure-img"; img.alt = `2D structure of ${name || chemblId}`; img.loading = "lazy";
    img.src = `https://www.ebi.ac.uk/chembl/api/data/image/${encodeURIComponent(chemblId)}.svg`;
    img.addEventListener("error", () => img.remove());
    sec.append(img, node("p", "source-title", name || chemblId));
    const dl = node("dl", "identity-list");
    for (const [k, v] of [["ChEMBL ID", chemblId], ["InChIKey", inchikey], ["SMILES", smiles]]) if (v) dl.append(node("dt", "", k), node("dd", "", v));
    sec.append(dl);
    const links = node("div", "source-links");
    links.append(safeLink(`https://www.ebi.ac.uk/chembl/explore/compound/${chemblId}`, "Compound in ChEMBL"));
    sec.append(links);
    return sec;
  }

  function renderChemblEvidence(record) {
    const c = record.chembl;
    const content = document.createDocumentFragment();
    const hero = node("div", "detail-hero");
    const overline = node("div", "detail-overline", `ChEMBL / ${c.activity}`);
    overline.append(node("span", "source-tag", "Database"));
    hero.append(overline, node("h4", "detail-title", labelFor(record)), node("p", "detail-subtitle", `${record.compound_id} · ${text(record.target_name)}`));
    const strip = node("div", "value-strip");
    const reported = node("div");
    reported.append(node("span", "value-label", `${text(record.measurement_type)} · standardised by ChEMBL`));
    const val = node("div", "value-number", record.raw_value); val.append(node("span", "value-unit", "nM")); reported.append(val);
    const pc = node("div");
    pc.append(node("span", "value-label", "pChEMBL (−log molar)"), node("div", "value-number", text(c.pchembl)));
    strip.append(reported, pc); hero.append(strip); content.append(hero);
    const assay = section("Assay");
    assay.append(node("p", "source-title", text(c.assay_desc, "No description")), node("p", "source-meta", `${c.assay} · type ${text(c.assay_type)}${c.validity ? ` · ChEMBL note: ${c.validity}` : ""}`));
    content.append(assay);
    const mol = c.mol || [];
    content.append(structureSection(record.compound_id, record.compound_label !== record.compound_id ? record.compound_label : "", mol[0], mol[1]));
    const src = section("Source document");
    const d = c.doc_meta;
    if (d) src.append(node("p", "source-title", text(d[3], "Untitled")), node("p", "source-meta", [d[1], d[2], c.doc].filter(Boolean).join(" · ")));
    const links = node("div", "source-links");
    if (d && d[0]) links.append(safeLink(`https://doi.org/${d[0]}`, "Original paper (DOI)"));
    links.append(safeLink(`https://www.ebi.ac.uk/chembl/explore/document/${c.doc}`, "ChEMBL document"), safeLink(`https://www.ebi.ac.uk/chembl/explore/compound/${record.compound_id}`, "Compound in ChEMBL"));
    src.append(links, node("p", "chembl-note", "Curated by ChEMBL (EMBL-EBI), licensed CC BY-SA 3.0. This value links to its paper, not to an exact table cell, and has not been checked by this project."));
    content.append(src);
    $("evidence-detail").replaceChildren(content);
  }

  function renderEvidence() {
    const record = state.filtered.find((item) => item.id === state.selectedId);
    $("evidence-empty").hidden = Boolean(record);
    $("evidence-detail").hidden = !record;
    $("evidence-detail").replaceChildren();
    if (!record) return;
    if (record.chembl) { renderChemblEvidence(record); return; }
    const article = state.dataset.articles.find((item) => item.pmcid === record.pmcid) || {};
    const sourceTable = asArray(state.dataset.tables).find((item) => item.pmcid === record.pmcid && item.table_id === record.table_id) || {};
    const evidence = record.evidence || {};
    const content = document.createDocumentFragment();

    const hero = node("div", "detail-hero");
    const overline = node("div", "detail-overline", `${text(record.pmcid)} / ${text(sourceTable.label, text(record.table_id))}`);
    overline.append(node("span", "review-badge" + (record.review_status === "reviewed" ? " is-reviewed" : ""), record.review_status === "reviewed" ? "AI-checked" : "Unchecked"));
    hero.append(overline, node("h4", "detail-title", `Compound ${labelFor(record)}`), node("p", "detail-subtitle", `Article-local label · ${text(record.target_name)}`));
    const strip = node("div", "value-strip");
    const reported = node("div");
    const value = node("span", "value-number", text(record.raw_value, formatted(record.value)));
    value.append(node("span", "value-unit", text(record.unit, "Unit unspecified")));
    reported.append(node("span", "value-label", `${text(record.measurement_type, "Measurement type unspecified")} · as reported`), value);
    const normalized = node("div");
    const normalizedValue = node("span", "value-number", record.normalized_value_nm === null || record.normalized_value_nm === undefined ? "Unavailable" : `${text(record.relation, "")}${formatted(record.normalized_value_nm)}`);
    if (record.normalized_value_nm !== null && record.normalized_value_nm !== undefined) normalizedValue.append(node("span", "value-unit", "nM"));
    normalized.append(node("span", "value-label", "Normalized value"), normalizedValue);
    strip.append(reported, normalized);
    hero.append(strip);
    content.append(hero);
    const review = record.review_provenance;
    if (review) {
      const checks = section("How this record was checked");
      checks.append(node("p", "detail-muted", `${review.reviewer} · ${review.date}`),
        node("p", "", review.method),
        node("p", "detail-muted", "AI-assisted transcription checks and automated consistency checks. No scientist validation is recorded."));
      content.append(checks);
    }


    const source = section("Original publication");
    source.append(node("p", "source-title", text(article.title, record.pmcid)));
    const metadata = [article.year, article.doi ? `DOI ${article.doi}` : "", article.license ? `License: ${article.license}` : ""].filter(Boolean);
    if (metadata.length) source.append(node("p", "source-meta", metadata.join(" · ")));
    const links = node("div", "source-links");
    const sourceUrl = record.source_url || article.source_url;
    if (sourceUrl) links.append(safeLink(sourceUrl, "Read paper ↗"));
    if (/^PMC\d+$/i.test(record.pmcid || "")) {
      const xml = node("a", "", "Source XML ↓");
      xml.href = `api/source/${encodeURIComponent(record.pmcid)}.xml`;
      xml.download = `${record.pmcid}.xml`;
      links.append(xml);
    }
    source.append(links);
    content.append(source);

    const exact = section("Source row (plain text)");
    const caption = evidence.caption || sourceTable.caption;
    if (caption) exact.append(node("p", "table-caption", caption));
    const cells = asArray(evidence.original_row || evidence.row);
    const headers = Array.isArray(sourceTable.headers) && sourceTable.headers.length ? sourceTable.headers : Array.isArray(evidence.header) ? evidence.header : cells.map((_, index) => index === record.target_column ? text(evidence.header, `Column ${index + 1}`) : `Column ${index + 1}`);
    if (cells.length) {
      const wrap = node("div", "source-table-wrap");
      wrap.tabIndex = 0;
      wrap.setAttribute("role", "region");
      wrap.setAttribute("aria-label", "Source table row in plain text; scroll horizontally for all columns");
      const table = node("table", "source-table");
      table.append(node("caption", "sr-only", `Source row for compound ${labelFor(record)} in ${text(record.pmcid)}`));
      const head = node("thead");
      const headRow = node("tr");
      const body = node("tbody");
      const bodyRow = node("tr");
      const targetColumn = Number.isInteger(record.target_column) ? record.target_column : -1;
      for (let index = 0; index < Math.max(headers.length, cells.length); index += 1) {
        const className = index === targetColumn ? "target-cell" : "";
        const th = node("th", className, text(headers[index], `Column ${index + 1}`));
        th.scope = "col";
        headRow.append(th);
        bodyRow.append(node("td", className, text(cells[index])));
      }
      head.append(headRow);
      body.append(bodyRow);
      table.append(head, body);
      wrap.append(table);
      exact.append(wrap);
      exact.append(node("p", "source-row-note", `Table ${text(record.table_id)} · Source row index ${text(record.row_index)}${targetColumn >= 0 ? " · Extracted column highlighted" : ""}`));
    } else exact.append(node("p", "detail-muted", "No source row is available for this measurement."));
    const footnotes = asArray(evidence.footnotes?.length ? evidence.footnotes : sourceTable.footnotes);
    if (footnotes.length) {
      const notes = node("div", "footnotes");
      notes.append(node("strong", "", "Table notes"));
      for (const note of footnotes) notes.append(node("p", "", typeof note === "object" ? JSON.stringify(note) : note));
      exact.append(notes);
    }
    content.append(exact);

    const flags = flagsFor(record);
    if (flags.length) {
      const review = section("Needs attention");
      const list = node("ul", "flag-list");
      for (const flag of flags) list.append(node("li", "", String(flag).replaceAll("_", " ")));
      review.append(list);
      content.append(review);
    }

    const context = section("Assay context");
    context.append(node("p", "context-note", "Article-level context. These passages have not been confirmed as the conditions for this individual measurement."));
    const contexts = asArray(contextFor(record));
    if (contexts.length) {
      for (const passage of contexts) {
        const entry = node("details", "context-entry");
        entry.append(node("summary", "", text(passage.title, text(passage.section_id, "Methods passage"))), node("p", "", text(passage.text, "Passage text unavailable.")));
        context.append(entry);
      }
    } else context.append(node("p", "detail-muted", "No assay context was captured. Consult the original publication."));
    content.append(context);

    if (record.molecule) {
      const idSec = structureSection(record.molecule.chembl_id, record.molecule.name, record.molecule.inchikey, record.molecule.smiles);
      idSec.insertBefore(node("p", "detail-muted", `The paper's label "${labelFor(record)}" matches this ChEMBL molecule by name.`), idSec.children[1]);
      const same = record.chembl_same_compound;
      if (same) idSec.append(node("p", "chembl-note", `ChEMBL has ${numberFormat.format(same.n)} ${record.measurement_type} value${same.n === 1 ? "" : "s"} for this compound on this enzyme: median ${formatted(same.median_nm)} nM (range ${formatted(same.min_nm)}–${formatted(same.max_nm)} nM). This paper reports ${formatted(record.normalized_value_nm)} nM.`));
      content.append(idSec);
    }
    if (record.chembl_match !== undefined && record.chembl_match !== null) {
      const cross = section("Cross-check with ChEMBL");
      cross.append(node("p", record.chembl_match ? "match-yes" : "match-no", record.chembl_match
        ? "Numerical agreement within 2% or two-significant-figure rounding for the same name-linked compound, paper, target and endpoint. Assay equivalence is not established."
        : "Comparable ChEMBL entries for the same name-linked compound, paper, target and endpoint differ numerically. Check the source assays."));
      content.append(cross);
    }

    const provenance = node("section", "detail-section");
    const details = node("details", "provenance-details");
    details.append(node("summary", "", "Extraction provenance"));
    const definition = node("dl");
    for (const [key, value] of [["Record ID", record.id], ["Compound ID", record.compound_id], ["Source SHA-256", record.source_sha256], ["Extractor", state.dataset.extractor_version]]) {
      definition.append(node("dt", "", key), node("dd", "", text(value)));
    }
    details.append(definition);
    provenance.append(details);
    content.append(provenance);
    $("evidence-detail").append(content);
  }

  async function loadEvaluation() {
    if (!$("benchmark-score")) return;
    try {
      const response = await fetch("api/evaluation", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Evaluation unavailable");
      const report = await response.json();
      if (report.error || typeof report.f1 !== "number") throw new Error("Evaluation unavailable");
      $("benchmark-score").textContent = `${(report.f1 * 100).toFixed(1)}% F1`;
      const expected = report.expected ?? report.true_positives + report.false_negatives;
      $("benchmark-note").textContent = `${numberFormat.format(expected)} numeric reference records · Scoped tables only`;
      $("benchmark-score").title = `Precision ${(report.precision * 100).toFixed(1)}%; recall ${(report.recall * 100).toFixed(1)}%. Agent-transcribed regression set, not independent biological validation.`;
    } catch (_) {
      $("benchmark-score").textContent = "Pending";
      $("benchmark-note").textContent = "Evaluation unavailable · Scientist review required";
    }
  }

  async function loadDataset() {
    if (state.loading) return;
    state.loading = true;
    $("loading-state").hidden = false;
    $("error-state").hidden = true;
    $("empty-state").hidden = true;
    $("table-wrap").hidden = true;
    $("results-summary").textContent = "Loading dataset…";
    try {
      const response = await fetch("api/dataset", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`The dataset request returned status ${response.status}.`);
      const data = await response.json();
      if (!Array.isArray(data.records) || !Array.isArray(data.articles)) throw new Error("The dataset response is missing its articles or records.");
      state.dataset = data;
      $("article-count").textContent = numberFormat.format(data.articles.length);
      $("record-count").textContent = numberFormat.format(data.records.length);
      const reviewedCount = data.records.filter((record) => record.review_status === "reviewed").length;
      const badge = document.querySelector(".panel-heading .review-badge");
      if (badge) badge.textContent = reviewedCount === data.records.length ? "AI-checked" : reviewedCount ? `${numberFormat.format(reviewedCount)} AI-checked · ${numberFormat.format(data.records.length - reviewedCount)} unchecked` : "Unchecked";
      const chembl = Object.values(data.chembl || {});
      $("chembl-count").textContent = numberFormat.format(chembl.reduce((sum, t) => sum + t.count, 0));
      $("enzyme-note").textContent = `${chembl.length} enzymes · loaded per enzyme`;
      const checked = chembl.reduce((sum, t) => sum + (t.crosscheck?.checked || 0), 0), agreed = chembl.reduce((sum, t) => sum + (t.crosscheck?.agreed || 0), 0);
      $("agree-score").textContent = checked ? `${agreed} / ${checked}` : "—";
      $("agree-note").textContent = checked ? "Same compound, paper, target and endpoint" : "No comparable compound-linked values";
      const selectedPaper = $("paper-filter").value;
      const paperOptions = [new Option("All papers", "")];
      for (const article of data.articles) paperOptions.push(new Option(`${article.pmcid} · ${text(article.title, "Untitled paper")}`, article.pmcid));
      $("paper-filter").replaceChildren(...paperOptions);
      $("paper-filter").value = selectedPaper;
      const measurementOptions = [new Option("All types", "")];
      for (const measurement of [...new Set(data.records.map((record) => record.measurement_type).filter(Boolean))].sort()) measurementOptions.push(new Option(measurement, measurement));
      $("measurement-filter").replaceChildren(...measurementOptions);
      const restore = state.restore || {};
      state.restore = null;
      if (restore.target && asArray(data.targets).some((t) => t.key === restore.target)) state.target = restore.target;
      if (restore.q) $("search").value = restore.q;
      if (restore.sort === "asc" || restore.sort === "desc") { state.sort = restore.sort; $("sort-icon").textContent = restore.sort === "asc" ? "↑" : "↓"; }
      renderTargets();
      if (restore.source && chemblInfo(state.target)) { $("source-filter").value = restore.source; await ensureChembl(state.target); }
      if (restore.type) $("measurement-filter").value = restore.type;
      if (restore.id) state.selectedId = restore.id;
      $("dataset-version").textContent = [data.dataset_id, data.extractor_version ? `Extractor ${data.extractor_version}` : ""].filter(Boolean).join(" · ") || "Open data";
      $("export-link").classList.remove("disabled");
      $("export-link").removeAttribute("aria-disabled");
      applyFilters();
    } catch (error) {
      $("error-state").hidden = false;
      $("error-message").textContent = `${error.message} Reload the page to try again.`;
      $("results-summary").textContent = "Dataset unavailable";
    } finally {
      state.loading = false;
      $("loading-state").hidden = true;
    }
  }

  $("filters").addEventListener("submit", (event) => event.preventDefault());
  $("search").addEventListener("input", applyFilters);
  $("export-link").addEventListener("click", staticExport);
  const refresh = async () => {
    renderTargets();
    const hasVerified = state.dataset.records.some((r) => r.target === state.target);
    if (state.target && !hasVerified && chemblInfo(state.target) && $("source-filter").value === "verified") $("source-filter").value = "chembl"; if ($("source-filter").value !== "verified") await ensureChembl(state.target); applyFilters(); };
  $("target-filter").addEventListener("change", () => { state.target = $("target-filter").value; $("paper-filter").value = ""; refresh(); });
  $("source-filter").addEventListener("change", refresh);
  $("sort-button").addEventListener("click", () => {
    state.sort = state.sort === "" ? "asc" : state.sort === "asc" ? "desc" : "";
    $("sort-icon").textContent = state.sort === "asc" ? "↑" : state.sort === "desc" ? "↓" : "↕";
    $("sort-button").closest("th").setAttribute("aria-sort", state.sort === "asc" ? "ascending" : state.sort === "desc" ? "descending" : "none");
    applyFilters();
  });
  $("theme-toggle").addEventListener("click", () => {
    const next = THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length];
    applyTheme(next);
    try { if (next === "auto") localStorage.removeItem("be-theme"); else localStorage.setItem("be-theme", next); } catch (_) { /* ignore */ }
  });
  applyTheme(currentTheme());
  let resizeTimer;
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderPotency, 150); });
  state.restore = readUrl();
  for (const id of ["paper-filter", "measurement-filter", "flagged-filter"]) $(id).addEventListener("change", applyFilters);
  $("reset-button").addEventListener("click", () => { $("filters").reset(); state.target = ""; if (state.dataset) renderTargets(); applyFilters(); $("search").focus(); });
  $("retry-button").addEventListener("click", () => { loadDataset(); loadEvaluation(); });
  loadDataset();
  loadEvaluation();
})();
