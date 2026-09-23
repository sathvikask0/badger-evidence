"""Score the extractor against ChEMBL on the benchmark fetched by tools/bench_fetch.py.

    python3 tools/bench_eval.py bench/mtor_pi3ka

Matching is per (paper, target, endpoint): an extracted value matches a ChEMBL value if they agree within
2% or after rounding to two significant figures; each reference value can be matched once.
Reported:
  precision        matched extracted values / extracted values
  recall           matched ChEMBL values / ChEMBL values
  table recall     recall restricted to ChEMBL values whose number appears in a table of the paper
                   (the nM value printed as-is)
                   (ChEMBL also curates values from text, figures and supplementary files, which a
                   table extractor cannot reach)
Writes report.json and report.md next to the benchmark, including unmatched examples for error analysis.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.extract import extract_article, parse_xml

BLOCKING_OK = {"missing_assay_context", "target_from_caption", "repeated_measurement", "multiple_reports", "qualified_value"}


def same(a, b):
    return abs(a - b) <= 0.02 * max(abs(b), 1e-12) or float(f"{a:.2g}") == float(f"{b:.2g}")


def table_numbers(raw):
    root = parse_xml(raw)
    nums = set()
    for wrap in root.iter("table-wrap"):
        for m in re.finditer(r"\d+(?:[.,]\d+)?", "".join(wrap.itertext())):
            try:
                nums.add(float(m.group().replace(",", ".")))
            except ValueError:
                pass
    return nums


def main():
    bench = Path(sys.argv[1])
    if not (bench / "docs.json").exists():
        raise SystemExit(f"{bench}/docs.json not found: run tools/bench_fetch.py first (it did not finish).")
    docs = json.loads((bench / "docs.json").read_text())
    gold = json.loads((bench / "gold.json").read_text())
    targets = sorted({g["target"] for rows in gold.values() for g in rows})
    tp = n_ext = n_gold = n_reach = reach_hit = 0
    per_target = defaultdict(lambda: {"extracted": 0, "gold": 0, "matched_ext": 0, "matched_gold": 0})
    fp_examples, fn_examples, per_doc = [], [], []
    for doc_id, meta in docs.items():
        raw = (bench / "xml" / f"{meta['pmcid']}.xml").read_bytes()
        try:
            result = extract_article(raw, {"pmcid": meta["pmcid"]})
        except Exception as e:
            per_doc.append({"pmcid": meta["pmcid"], "error": str(e)})
            continue
        # ChEMBL reference rows carry a pChEMBL value, i.e. exact measurements only; bounds such as
        # ">10 000" are kept in the dataset but are not scored against it.
        ext = [r for r in result["records"] if r["target"] in targets and r["value"] is not None
               and r["relation"] == "=" and not set(r["flags"]) - BLOCKING_OK]
        ref = [g for g in gold[doc_id] if g.get("standard_units") == "nM" and g.get("standard_value") not in (None, "")]
        nums = table_numbers(raw)
        groups = defaultdict(lambda: ([], []))
        for r in ext:
            groups[(r["target"], r["measurement_type"])][0].append(r)
        for g in ref:
            groups[(g["target"], g["standard_type"])][1].append(g)
        d_tp = 0
        for (target, endpoint), (es, gs) in groups.items():
            used = set()
            for r in es:
                hit = next((i for i, g in enumerate(gs) if i not in used and same(r["normalized_value_nm"], float(g["standard_value"]))), None)
                if hit is None:
                    if len(fp_examples) < 40:
                        fp_examples.append({"pmcid": meta["pmcid"], "target": target, "endpoint": endpoint, "label": r["compound_label"],
                                            "value_nm": r["normalized_value_nm"], "raw": r["raw_value"], "table": r["table_id"], "header": r["evidence"]["header"]})
                else:
                    used.add(hit)
            for i, g in enumerate(gs):
                v = float(g["standard_value"])
                reachable = any(same(v * f, n) or same(v, n * f) for n in nums for f in (1,)) if nums else False
                n_reach += reachable
                if i in used:
                    reach_hit += reachable
                elif reachable and len(fn_examples) < 40:
                    fn_examples.append({"pmcid": meta["pmcid"], "target": target, "endpoint": endpoint,
                                        "chembl_activity": g["activity_id"], "compound": g.get("molecule_pref_name") or g["molecule_chembl_id"], "value_nm": v})
            pt = per_target[target]
            pt["extracted"] += len(es); pt["gold"] += len(gs); pt["matched_ext"] += len(used); pt["matched_gold"] += len(used)
            d_tp += len(used)
        tp += d_tp; n_ext += len(ext); n_gold += len(ref)
        per_doc.append({"pmcid": meta["pmcid"], "extracted": len(ext), "chembl": len(ref), "matched": d_tp})

    pct = lambda a, b: round(100 * a / b, 1) if b else None
    report = {
        "benchmark": bench.name, "papers": len(docs), "targets": targets,
        "extracted": n_ext, "chembl_values": n_gold, "matched": tp,
        "precision_pct": pct(tp, n_ext), "recall_pct": pct(tp, n_gold),
        "chembl_values_in_tables": n_reach, "table_recall_pct": pct(reach_hit, n_reach),
        "papers_with_any_extraction": sum(1 for d in per_doc if d.get("extracted")),
        "per_target": {k: {**v, "precision_pct": pct(v["matched_ext"], v["extracted"]), "recall_pct": pct(v["matched_gold"], v["gold"])} for k, v in per_target.items()},
        "unmatched_extracted_examples": fp_examples, "missed_table_values_examples": fn_examples, "per_paper": per_doc,
    }
    (bench / "report.json").write_text(json.dumps(report, indent=1))
    md = [f"# Extraction benchmark: {bench.name}", "",
          f"{len(docs)} open-access papers curated by ChEMBL; targets: {', '.join(targets)}.", "",
          "| metric | value |", "|---|---|",
          f"| extracted values | {n_ext} |", f"| ChEMBL reference values | {n_gold} |", f"| matched | {tp} |",
          f"| precision | {report['precision_pct']}% |", f"| recall (all ChEMBL values) | {report['recall_pct']}% |",
          f"| recall (values present in paper tables) | {report['table_recall_pct']}% |", "",
          "Unmatched extracted values are not necessarily errors: ChEMBL does not curate every table value.",
          "They are listed in report.json for manual review."]
    (bench / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
