# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.2"]
# ///
"""Badger Evidence as an MCP server.

Gives an AI assistant (e.g. Claude) cited access to enzyme-inhibitor potency data:
values extracted from open-access papers (each linked to its exact table cell) and
ChEMBL 37 activities for the same enzymes.

Run:   uv run badger_evidence/mcp_server.py          (stdio transport)
Test:  npx @modelcontextprotocol/inspector uv run badger_evidence/mcp_server.py
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# Flags that describe missing context, not a problem with the value itself.
INFO_FLAGS = {"missing_assay_context", "target_from_caption"}

INSTRUCTIONS = """Badger Evidence: enzyme-inhibitor potency data (IC50, Ki, Kd) for ~55 enzymes relevant to ageing biology.
Two sources, always kept distinct:
- 'paper' values: extracted from CC BY open-access papers; every value links to its exact table cell (PMCID + table id + row).
  They are AI-checked for transcription, not validated by a scientist.
- 'chembl' values: ChEMBL 37 database records (CC BY-SA 3.0), linked to their source paper and assay.
When answering: cite PMCID/DOI and table for paper values and the ChEMBL activity/document for ChEMBL values;
never mix IC50, Ki and Kd; note that assay conditions differ between papers, so values are not strictly comparable.
Use get_evidence to show the source row before making a strong claim about a single value."""

mcp = FastMCP("badger-evidence", instructions=INSTRUCTIONS)


# ---------------------------------------------------------------- data loading
@lru_cache(maxsize=1)
def dataset() -> dict:
    return json.loads((DATA / "generated" / "dataset.json").read_text())


@lru_cache(maxsize=1)
def structures() -> dict:
    path = DATA / "structures.json"
    return json.loads(path.read_text()) if path.exists() else {}


@lru_cache(maxsize=64)
def chembl(target: str) -> dict | None:
    path = DATA / "chembl" / f"{target}.json"
    return json.loads(path.read_text()) if path.exists() else None


@lru_cache(maxsize=1)
def indexes() -> dict:
    ds = dataset()
    return {
        "articles": {a["pmcid"]: a for a in ds["articles"]},
        "tables": {(t["pmcid"], t["table_id"]): t for t in ds["tables"]},
        "targets": {t["key"]: t for t in ds.get("targets", [])},
        "records": {r["id"]: r for r in ds["records"] if r.get("review_status") == "reviewed"},
    }


def resolve_target(query: str) -> str:
    """Accept a key ('MTOR'), UniProt ('P42345') or a name fragment ('mTOR', 'sirtuin 1')."""
    targets = indexes()["targets"]
    q = query.strip().lower()
    for key, t in targets.items():
        if q in (key.lower(), t["uniprot"].lower(), t["name"].lower()):
            return key
    compact = re.sub(r"[\s\-_()]", "", q)
    hits = [k for k, t in targets.items() if compact in re.sub(r"[\s\-_()]", "", (t["name"] + " " + k).lower())]
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"Unknown or ambiguous target {query!r}; matches: {hits or 'none'}. Call list_targets.")


# ---------------------------------------------------------------- row shaping
def paper_row(r: dict) -> dict:
    a = indexes()["articles"].get(r["pmcid"], {})
    s = structures().get(f"{r['pmcid']}:{r['compound_label']}")
    structure = None
    if s and s.get("formula_check") == "match":
        structure = {"smiles": s["smiles"], "method": "name->structure (OPSIN), verified against the paper's stated formula"}
    elif r.get("molecule"):
        structure = {"smiles": r["molecule"].get("smiles"), "chembl_id": r["molecule"]["chembl_id"],
                     "method": "named compound matched to ChEMBL by name"}
    return {
        "id": r["id"], "source": "paper", "compound": r["compound_label"], "endpoint": r["measurement_type"],
        "relation": r["relation"], "value_nm": r["normalized_value_nm"], "reported": f"{r['raw_value']} {r['unit'] or ''}".strip(),
        "flags": [f for f in r["flags"] if f not in INFO_FLAGS],
        "citation": {"pmcid": r["pmcid"], "doi": a.get("doi"), "year": a.get("year"), "table_id": r["table_id"],
                     "row_index": r["row_index"], "url": r["source_url"], "title": a.get("title")},
        "structure": structure,
    }


def chembl_row(key: str, data: dict, r: list) -> dict:
    aid, mol, name, typ, rel, val, units, pch, assay, doc, year, validity = r
    meta = data["docs"].get(doc) or [None, None, None, None]
    return {
        "id": f"chembl:{aid}", "source": "chembl", "compound": name or mol, "molecule_chembl_id": mol,
        "endpoint": typ, "relation": (rel or "=").replace("'", ""), "value_nm": val, "pchembl": pch,
        "flags": [validity] if validity else [],
        "citation": {"chembl_activity": aid, "assay": assay, "document": doc, "doi": meta[0], "journal": meta[1],
                     "year": year, "url": f"https://www.ebi.ac.uk/chembl/explore/activity/{aid}"},
    }


def usable(row: dict, exact_only: bool) -> bool:
    return row["value_nm"] is not None and (not exact_only or (row["relation"] == "=" and not row["flags"]))


# ---------------------------------------------------------------- tools
@mcp.tool()
def dataset_info() -> dict:
    """What this dataset contains, how it was made, its licences and its known limits. Call first if unsure."""
    ds = dataset()
    reviewed = [r for r in ds["records"] if r.get("review_status") == "reviewed"]
    cross = [v["crosscheck"] for v in ds.get("chembl", {}).values()]
    return {
        "paper_values": len(reviewed), "papers": len({r["pmcid"] for r in reviewed}),
        "enzymes_with_paper_values": len({r["target"] for r in reviewed}),
        "chembl_values": sum(v["count"] for v in ds.get("chembl", {}).values()),
        "enzymes_with_chembl_values": len(ds.get("chembl", {})),
        "paper_structures_formula_verified": sum(1 for v in structures().values() if v.get("formula_check") == "match"),
        "crosscheck_with_chembl": {"comparable": sum(c["checked"] for c in cross), "agree": sum(c["agreed"] for c in cross)},
        "licences": {"paper values": "CC BY 4.0 (source articles)", "chembl values": "CC BY-SA 3.0 (ChEMBL 37)"},
        "limits": [
            "Paper values are AI-checked for faithful transcription, not validated by a scientist.",
            "Assay conditions (ATP/substrate concentration, enzyme construct) are not normalised across papers.",
            "Compound labels like '5a' are local to one paper; only some have resolved structures.",
            "Coverage is a sample of CC BY open-access papers, not the whole literature.",
        ],
    }


@mcp.tool()
def list_targets() -> list[dict]:
    """All enzymes with data: key, name, UniProt accession, why it matters for ageing, and value counts."""
    counts: dict[str, int] = {}
    for r in indexes()["records"].values():
        counts[r["target"]] = counts.get(r["target"], 0) + 1
    chem = dataset().get("chembl", {})
    return [{"key": k, "name": t["name"], "uniprot": t["uniprot"], "why": t["why"], "tags": t.get("tags", []),
             "paper_values": counts.get(k, 0), "chembl_values": chem.get(k, {}).get("count", 0)}
            for k, t in indexes()["targets"].items()]


@mcp.tool()
def search_measurements(target: str, compound: str | None = None, endpoint: Literal["IC50", "Ki", "Kd"] | None = None,
                        max_nm: float | None = None, source: Literal["paper", "chembl", "both"] = "paper",
                        exact_only: bool = False, limit: int = 20) -> dict:
    """Find potency measurements for one enzyme, most potent first.

    target: enzyme key, UniProt or name (e.g. 'mTOR', 'PARP1', 'acetylcholinesterase').
    compound: optional case-insensitive substring of the compound label/name (e.g. 'olaparib', '5a').
    max_nm: only values at or below this potency (nM). exact_only: drop bounds like '>10 µM' and flagged values.
    Each result carries a citation; paper results can be expanded with get_evidence(id)."""
    key = resolve_target(target)
    rows: list[dict] = []
    if source in ("paper", "both"):
        rows += [paper_row(r) for r in indexes()["records"].values() if r["target"] == key]
    if source in ("chembl", "both") and chembl(key):
        data = chembl(key)
        rows += [chembl_row(key, data, r) for r in data["rows"]]
    q = (compound or "").lower()
    rows = [r for r in rows if usable(r, exact_only) and (not endpoint or r["endpoint"] == endpoint)
            and (max_nm is None or r["value_nm"] <= max_nm)
            and (not q or q in str(r["compound"]).lower() or q in str(r.get("molecule_chembl_id", "")).lower())]
    rows.sort(key=lambda r: r["value_nm"])
    return {"target": key, "target_name": indexes()["targets"][key]["name"], "matches": len(rows),
            "results": rows[:max(1, min(limit, 100))],
            "note": "Sorted by value (lower nM = more potent). Values from different assays are not strictly comparable."}


@mcp.tool()
def get_evidence(record_id: str) -> dict:
    """Full provenance for one value: the source table row with its column headers, caption, footnotes,
    the paper's assay methods, how it was checked, the resolved structure and any ChEMBL cross-check.
    Accepts a paper record id or 'chembl:<activity_id>'."""
    if record_id.startswith("chembl:"):
        aid = int(record_id.split(":", 1)[1])
        for key in indexes()["targets"]:
            data = chembl(key)
            if not data:
                continue
            for r in data["rows"]:
                if r[0] == aid:
                    row = chembl_row(key, data, r)
                    row["assay_description"], row["assay_type"] = (data["assays"].get(r[8]) or [None, None])[:2]
                    row["target"] = key
                    row["note"] = "ChEMBL database value: linked to its paper and assay, not to a table cell; not checked by this project."
                    return row
        raise ValueError(f"No ChEMBL activity {aid} in this dataset.")
    r = indexes()["records"].get(record_id)
    if not r:
        raise ValueError(f"No reviewed paper record {record_id!r}.")
    t = indexes()["tables"].get((r["pmcid"], r["table_id"]), {})
    ev = r["evidence"]
    headers = t.get("headers") or []
    cells = ev.get("original_row") or ev.get("row") or []
    out = paper_row(r)
    out.update({
        "target": r["target"],
        "source_row": [{"column": headers[i] if i < len(headers) else f"col{i}", "cell": c,
                        "extracted": i == r["target_column"]} for i, c in enumerate(cells)],
        "table_caption": ev.get("caption"), "table_footnotes": ev.get("footnotes"),
        "assay_methods": [{"title": m.get("title"), "text": (m.get("text") or "")[:1500]} for m in r.get("assay_context", [])[:3]],
        "licence": indexes()["articles"].get(r["pmcid"], {}).get("license"),
        "check": r.get("review_provenance") or "AI-checked transcription against the source table cell",
        "chembl_crosscheck": ({True: "agrees with ChEMBL (same compound, paper, target, endpoint)",
                               False: "differs from ChEMBL for the same compound and paper"}.get(r.get("chembl_match"))),
        "same_compound_in_chembl": r.get("chembl_same_compound"),
        "source_sha256": r["source_sha256"],
    })
    return out


@mcp.tool()
def potency_summary(target: str, endpoint: Literal["IC50", "Ki", "Kd"] = "IC50",
                    source: Literal["paper", "chembl", "both"] = "both") -> dict:
    """Distribution of exact (=) values for one enzyme and one endpoint: count, median and percentiles in nM,
    plus the 10 most potent compounds with citations."""
    res = search_measurements(target, endpoint=endpoint, source=source, exact_only=True, limit=100000)
    vals = [r["value_nm"] for r in res["results"]]
    if not vals:
        return {"target": res["target"], "endpoint": endpoint, "n": 0}

    def pct(p):
        i = (len(vals) - 1) * p
        lo, hi = math.floor(i), math.ceil(i)
        return vals[lo] + (vals[hi] - vals[lo]) * (i - lo)
    return {"target": res["target"], "target_name": res["target_name"], "endpoint": endpoint, "source": source,
            "n": len(vals), "median_nm": pct(0.5), "p10_nm": pct(0.1), "p90_nm": pct(0.9),
            "most_potent": res["results"][:10],
            "note": "Exact values only; bounds and flagged values excluded. Assay conditions differ across sources."}


@mcp.tool()
def compound_profile(name: str, limit_per_target: int = 5) -> dict:
    """Everything known about one named compound (e.g. 'rapamycin', 'olaparib', 'donepezil') across all enzymes:
    paper values (matched by name) and ChEMBL values (matched by ChEMBL preferred name or ID)."""
    q = name.strip().lower()
    by_target: dict[str, dict] = {}
    for r in indexes()["records"].values():
        mol = r.get("molecule") or {}
        if q in r["compound_label"].lower() or q == (mol.get("name") or "").lower() or q == (mol.get("chembl_id") or "").lower():
            by_target.setdefault(r["target"], {"paper": [], "chembl": []})["paper"].append(paper_row(r))
    for key in indexes()["targets"]:
        data = chembl(key)
        if not data:
            continue
        hits = [chembl_row(key, data, r) for r in data["rows"] if (r[2] or "").lower() == q or r[1].lower() == q]
        if hits:
            by_target.setdefault(key, {"paper": [], "chembl": []})["chembl"] = hits
    out = {}
    for key, v in by_target.items():
        exact = sorted([x["value_nm"] for x in v["chembl"] if x["relation"] == "=" and not x["flags"]])
        out[key] = {"target_name": indexes()["targets"][key]["name"],
                    "paper_values": sorted(v["paper"], key=lambda x: x["value_nm"] or 0)[:limit_per_target],
                    "chembl_count": len(v["chembl"]),
                    "chembl_median_nm": exact[len(exact) // 2] if exact else None,
                    "chembl_examples": sorted(v["chembl"], key=lambda x: x["value_nm"])[:limit_per_target]}
    return {"compound": name, "targets": out, "enzymes_found": len(out)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
