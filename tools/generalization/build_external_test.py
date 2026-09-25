"""Build an external test set from a verified scale-up corpus: verified, primary-source, exact values on enzymes
the model covers, with a formula-verified structure (name->structure, drawing->structure) or a named drug.

    python3 tools/generalization/build_external_test.py corpus/scale1 bench/generalization/paper_test_scale1.json
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


def name_key(label):
    return re.sub(r"\s*\(.*?\)|\s*\[.*?\]|[*†‡§]|\s+\d+$", "", label).strip().lower()


def main():
    corpus, out = Path(sys.argv[1]), Path(sys.argv[2])
    vals = json.loads((corpus / "values.json").read_text())
    docs = json.loads((corpus / "docs.json").read_text())
    structs = json.loads((corpus / "structures.json").read_text())
    ocsr = json.loads((corpus / "structures_ocsr.json").read_text()) if (corpus / "structures_ocsr.json").exists() else {}
    tasks = set(json.loads(Path("bench/generalization/paper_test.json").read_text())["pairs"])
    ids = json.loads(Path("data/compound_ids.json").read_text())
    rows, why = [], Counter()
    for i, r in enumerate(vals):
        task = f"{r['target']}|{r['endpoint']}"
        if r["status"] != "verified":
            why["not verified"] += 1; continue
        if r["secondary_source"]:
            why["review article"] += 1; continue
        if r["relation"] != "=":
            why["bound"] += 1; continue
        if task not in tasks:
            why["enzyme/endpoint not in model"] += 1; continue
        key = f"{r['pmcid']}:{r['compound_label']}"
        st, o = structs.get(key), ocsr.get(key)
        if st and st["formula_check"] == "match":
            smi, method = st["smiles"], "opsin_formula_verified"
        elif o:
            smi, method = o["smiles"], "ocsr_formula_verified"
        elif name_key(r["compound_label"]) in ids:
            smi, method = ids[name_key(r["compound_label"])][3], "name_matched_chembl"
        else:
            why["no structure"] += 1; continue
        d = docs[r["pmcid"]]
        rows.append({"id": f"{corpus.name}-{i}", "target": r["target"], "endpoint": r["endpoint"], "compound": r["compound_label"],
                     "smiles": smi, "structure_method": method, "value_nm": r["value_nm"],
                     "p": round(9 - math.log10(r["value_nm"]), 3), "pmcid": r["pmcid"], "doi": d.get("doi"), "year": d.get("year"),
                     "table_id": r["table_id"], "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{r['pmcid']}/", "secondary_source": False})
    pairs = {t: {} for t in sorted({f"{r['target']}|{r['endpoint']}" for r in rows})}
    out.write_text(json.dumps({"pairs": pairs, "rows": rows, "source": f"{corpus} (Claude batch extraction, rule-verified)"}, indent=1))
    print(dict(why), "->", len(rows), "rows,", len({r["pmcid"] for r in rows}), "papers", dict(Counter(r["structure_method"] for r in rows)))
    print(Counter(f"{r['target']}|{r['endpoint']}" for r in rows).most_common())


if __name__ == "__main__":
    main()
