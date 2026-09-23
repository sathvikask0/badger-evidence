"""Build an ML-ready release (Parquet + dataset card) for one target family.

Usage: python3 tools/build_release.py kinase v0.1 [chembl_37_chemreps.txt.gz]

Two tables, kept separate because their licences differ:
  papers.parquet  CC BY 4.0     values extracted here from open-access papers, with structures
                                that are formula-verified (OPSIN) or ChEMBL name-linked
  chembl.parquet  CC BY-SA 3.0  ChEMBL 37 activities for the same targets (needs the chemreps file for SMILES)
Every row carries provenance. Splits are scaffold-based (Bemis-Murcko), assigned by hashing the
scaffold, so the same chemotype never crosses train/valid/test and splits are stable across releases.
"""
import csv, gzip, hashlib, io, json, math, sys, warnings
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from rdkit import Chem, RDLogger
from rdkit.Chem.Scaffolds import MurckoScaffold
from rdkit.Chem.MolStandardize import rdMolStandardize
RDLogger.DisableLog("rdApp.*")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.targets import TARGETS

FAMILIES = {
    "kinase": ["MTOR", "PI3KA", "GSK3B", "JAK2", "P38A", "IGF1R", "EGFR", "CDK2", "CDK4", "CDK5",
               "CSNK1D", "DYRK1A", "LRRK2", "ROCK1", "ROCK2", "TGFBR1"],
}
_largest, _uncharger = rdMolStandardize.LargestFragmentChooser(), rdMolStandardize.Uncharger()


def standardise(smiles):
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return None
    mol = _uncharger.uncharge(_largest.choose(mol))
    if mol.GetNumHeavyAtoms() < 3:
        return None
    return mol


def scaffold_split(mol):
    try:
        scaf = MurckoScaffold.MurckoScaffoldSmiles(mol=mol) or "acyclic"
    except Exception:
        scaf = "acyclic"
    h = int(hashlib.sha1(scaf.encode()).hexdigest(), 16) % 100
    return scaf, ("train" if h < 80 else "valid" if h < 90 else "test")


def p_value(relation, nm):
    return round(9 - math.log10(nm), 3) if relation == "=" and nm and nm > 0 else None


def main():
    family, version = sys.argv[1], sys.argv[2]
    chemreps = sys.argv[3] if len(sys.argv) > 3 else None
    keys = FAMILIES[family]
    data = Path("data")
    out = Path("release") / f"{family}-{version}"
    out.mkdir(parents=True, exist_ok=True)
    ds = json.loads((data / "generated" / "dataset.json").read_text())
    structs = json.loads((data / "structures.json").read_text())
    articles = {a["pmcid"]: a for a in ds["articles"]}
    stats = {"family": family, "version": version, "targets": keys}

    # ---- papers (CC BY 4.0) ----
    rows, skipped = [], Counter()
    for r in ds["records"]:
        if r["target"] not in keys or r.get("review_status") != "reviewed":
            continue
        s = structs.get(f"{r['pmcid']}:{r['compound_label']}")
        if s and s["formula_check"] == "match":
            smi, method = s["smiles"], "opsin_name_formula_verified"
        elif r.get("molecule") and r["molecule"].get("smiles"):
            smi, method = r["molecule"]["smiles"], "chembl_name_match"
        else:
            skipped["no_structure"] += 1
            continue
        mol = standardise(smi)
        if mol is None or r.get("normalized_value_nm") is None:
            skipped["unusable"] += 1
            continue
        scaf, split = scaffold_split(mol)
        t = TARGETS[r["target"]]
        a = articles.get(r["pmcid"], {})
        rows.append({
            "smiles": Chem.MolToSmiles(mol), "inchikey": Chem.MolToInchiKey(mol), "scaffold": scaf, "split": split,
            "target": r["target"], "uniprot": t.uniprot, "target_name": t.name,
            "endpoint": r["measurement_type"], "relation": r["relation"], "value_nm": r["normalized_value_nm"],
            "p_value": p_value(r["relation"], r["normalized_value_nm"]),
            "reported_value": r["raw_value"], "reported_unit": r["unit"],
            "compound_label": r["compound_label"], "structure_method": method,
            "pmcid": r["pmcid"], "doi": a.get("doi"), "year": str(a.get("year") or ""), "table_id": r["table_id"],
            "row_index": r["row_index"], "source_url": r["source_url"], "source_sha256": r["source_sha256"],
            "review": "ai_checked_transcription", "record_id": r["id"],
        })
    pq.write_table(pa.Table.from_pylist(rows), out / "papers.parquet", compression="zstd")
    stats["papers"] = {"rows": len(rows), "skipped": dict(skipped), "molecules": len({x["inchikey"] for x in rows}),
                       "papers": len({x["pmcid"] for x in rows}), "by_target": dict(Counter(x["target"] for x in rows)),
                       "by_method": dict(Counter(x["structure_method"] for x in rows)),
                       "by_split": dict(Counter(x["split"] for x in rows))}

    # ---- ChEMBL (CC BY-SA 3.0) ----
    if chemreps:
        needed = set()
        tables = {}
        for k in keys:
            path = data / "chembl" / f"{k}.json"
            if path.exists():
                tables[k] = json.loads(path.read_text())
                needed.update(r[1] for r in tables[k]["rows"])
        smiles = {}
        with gzip.open(chemreps, "rt") as fh:
            reader = csv.reader(fh, delimiter="\t")
            header = next(reader)
            i_id, i_smi, i_key = header.index("chembl_id"), header.index("canonical_smiles"), header.index("standard_inchi_key")
            for line in reader:
                if line[i_id] in needed:
                    smiles[line[i_id]] = line[i_smi]
        crow, cskip = [], Counter()
        cache = {}
        for k, tbl in tables.items():
            t = TARGETS[k]
            for r in tbl["rows"]:
                aid, mid, name, typ, rel, val, units, pch, assay, doc, year, validity = r
                if mid not in cache:
                    mol = standardise(smiles.get(mid))
                    cache[mid] = (Chem.MolToSmiles(mol), Chem.MolToInchiKey(mol), *scaffold_split(mol)) if mol else None
                c = cache[mid]
                if not c:
                    cskip["no_structure"] += 1
                    continue
                rel = (rel or "=").replace("'", "")
                meta = (tbl["docs"].get(doc) or [None, None, None, None])
                crow.append({"smiles": c[0], "inchikey": c[1], "scaffold": c[2], "split": c[3],
                             "target": k, "uniprot": t.uniprot, "target_name": t.name,
                             "endpoint": typ, "relation": rel, "value_nm": float(val), "p_value": p_value(rel, float(val)),
                             "pchembl_value": pch, "molecule_chembl_id": mid, "molecule_name": name,
                             "activity_id": aid, "assay_chembl_id": assay,
                             "assay_description": (tbl["assays"].get(assay) or [None])[0],
                             "assay_type": (tbl["assays"].get(assay) or [None, None])[1],
                             "document_chembl_id": doc, "doi": meta[0], "year": str(year or ""),
                             "data_validity_comment": validity})
        pq.write_table(pa.Table.from_pylist(crow), out / "chembl.parquet", compression="zstd")
        stats["chembl"] = {"rows": len(crow), "skipped": dict(cskip), "molecules": len({x["inchikey"] for x in crow}),
                           "by_target": dict(Counter(x["target"] for x in crow)), "by_split": dict(Counter(x["split"] for x in crow))}
        paper_keys = {x["inchikey"] for x in rows}
        stats["overlap"] = {"paper_molecules_also_in_chembl_kinase_set": len(paper_keys & {x["inchikey"] for x in crow}),
                            "paper_molecules": len(paper_keys)}
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    print(json.dumps(stats, indent=1)[:1500])


if __name__ == "__main__":
    main()
