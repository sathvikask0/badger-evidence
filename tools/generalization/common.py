"""Shared data preparation for the generalization experiment."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, DataStructs
from rdkit.Chem.MolStandardize import rdMolStandardize

RDLogger.DisableLog("rdApp.*")
_chooser = rdMolStandardize.LargestFragmentChooser()
_uncharger = rdMolStandardize.Uncharger()


def standardise(smi):
    """Largest fragment, neutralised, canonical SMILES + InChIKey connectivity block (first 14 chars)."""
    m = Chem.MolFromSmiles(smi)
    if m is None:
        return None, None
    try:
        m = _uncharger.uncharge(_chooser.choose(m))
        return Chem.MolToSmiles(m), Chem.MolToInchiKey(m)[:14]
    except Exception:
        return None, None


def split_of(key):
    """Deterministic molecule-level 80/10/10 split by InChIKey connectivity (same molecule, same split, every task)."""
    h = int(hashlib.sha1(key.encode()).hexdigest(), 16) % 10
    return "test" if h == 0 else "val" if h == 1 else "train"


def load(data_dir):
    data_dir = Path(data_dir)
    test = json.loads((data_dir / "paper_test.json").read_text())
    tasks = sorted(test["pairs"])
    ti = {t: i for i, t in enumerate(tasks)}
    mols = {}  # key -> dict(smiles, y[task], split)
    with open(data_dir / "chembl_train.csv") as f:
        for r in csv.DictReader(f):
            smi, key = standardise(r["smiles"])
            if not smi:
                continue
            m = mols.setdefault(key, {"smiles": smi, "y": np.full(len(tasks), np.nan), "split": split_of(key)})
            j = ti[r["task"]]
            p = float(r["p"])
            m["y"][j] = p if np.isnan(m["y"][j]) else (m["y"][j] + p) / 2  # salt forms of one parent: average
    seen = {t: set() for t in tasks}
    for key, m in mols.items():
        for j in np.where(~np.isnan(m["y"]))[0]:
            seen[tasks[j]].add(key)
    paper = []
    for r in test["rows"]:
        smi, key = standardise(r["smiles"])
        if not smi:
            continue
        task = f"{r['target']}|{r['endpoint']}"
        paper.append({**r, "task": task, "task_idx": ti[task], "std_smiles": smi, "key": key,
                      "seen_in_chembl": key in seen[task]})
    keys = sorted(mols)
    return tasks, keys, mols, paper


def ecfp(smiles_list, radius=2, n_bits=2048):
    out = np.zeros((len(smiles_list), n_bits), dtype=np.uint8)
    gen = AllChem.GetMorganGenerator(radius=radius, fpSize=n_bits)
    for i, s in enumerate(smiles_list):
        fp = gen.GetFingerprint(Chem.MolFromSmiles(s))
        DataStructs.ConvertToNumpyArray(fp, out[i])
    return out
