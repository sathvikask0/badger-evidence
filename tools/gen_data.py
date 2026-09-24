"""Build the ChEMBL training table for the generalization experiment (after tools/gen_fetch.py).

    python3 tools/gen_data.py

For every (target, endpoint) in bench/generalization/paper_test.json: ChEMBL exact (=) values with a pChEMBL,
no data-validity warning, and NOT from any paper in the test set (matched by DOI), aggregated to one median
value per molecule. Writes bench/generalization/chembl_train.csv (target_endpoint, molecule, smiles, p, n, year).
"""
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

OUT = Path("bench/generalization")


def main():
    test = json.loads((OUT / "paper_test.json").read_text())
    smiles = json.loads((OUT / "chembl_smiles.json").read_text())
    test_dois = {(r["doi"] or "").lower() for r in test["rows"] if r.get("doi")}
    rows, dropped_doc = [], 0
    for k, pair in enumerate(test["pairs"], 1):
        target, endpoint = pair.split("|")
        print(f"\r  [{'#' * (30 * k // len(test['pairs'])):30s}] {k}/{len(test['pairs'])} {target:8s}", end="", flush=True)
        d = json.loads(Path(f"data/chembl/{target}.json").read_text())
        vals, years = defaultdict(list), defaultdict(list)
        for aid, mol, name, typ, rel, val, units, pch, assay, doc, year, validity in d["rows"]:
            if typ != endpoint or pch is None or validity or (rel or "=").strip("'") != "=":
                continue
            doi = ((d["docs"].get(doc) or [None])[0] or "").lower()
            if doi and doi in test_dois:
                dropped_doc += 1
                continue
            vals[mol].append(pch)
            years[mol].append(year or 0)
        for mol, v in vals.items():
            if smiles.get(mol):
                rows.append({"task": pair, "molecule": mol, "smiles": smiles[mol], "p": round(statistics.median(v), 3),
                             "n": len(v), "year": min(y for y in years[mol] if y) if any(years[mol]) else ""})
    print()
    with open(OUT / "chembl_train.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} (task, molecule) rows over {len(test['pairs'])} tasks; "
          f"dropped {dropped_doc} ChEMBL values from test-set papers")


if __name__ == "__main__":
    main()
