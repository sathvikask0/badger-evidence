"""Score an already-trained model on a new external test set (no retraining).

    python tools/generalization/predict_external.py bench/generalization bench/generalization/paper_test_scale1.json \
        bench/generalization/preds/ckpt_chemeleon/<best>.ckpt [--name scale1]

DATA_DIR supplies the training data (chembl_train.csv, paper_test.json) so tasks are ordered exactly as in
training and compounds can be marked seen/unseen. Writes bench/generalization/results_<name>.json.
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem

from common import load, standardise
from evaluate import rmse, scores

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("test")
    ap.add_argument("ckpt")
    ap.add_argument("--name", default="scale1")
    a = ap.parse_args()
    tasks, keys, mols, _ = load(a.data)
    ti = {t: i for i, t in enumerate(tasks)}
    ext = json.loads(Path(a.test).read_text())
    rows = []
    for r in ext["rows"]:
        task = f"{r['target']}|{r['endpoint']}"
        smi, key = standardise(r["smiles"])
        if smi and task in ti:
            j = ti[task]
            known = key in mols and not np.isnan(mols[key]["y"][j])
            rows.append({**r, "task": task, "task_idx": j, "std_smiles": smi, "key": key, "seen_in_chembl": known,
                         "chembl_p": float(mols[key]["y"][j]) if known else None})
    import torch
    from chemprop import data, featurizers, models
    model = models.MPNN.load_from_checkpoint(a.ckpt, map_location="cpu")
    model.eval()
    feat = featurizers.SimpleMoleculeMolGraphFeaturizer()
    ds = data.MoleculeDataset([data.MoleculeDatapoint.from_smi(r["std_smiles"]) for r in rows], feat)
    with torch.no_grad():
        out = [model(b.bmg).numpy() for b in data.build_dataloader(ds, batch_size=256, shuffle=False, num_workers=0)]
    pred_all = np.concatenate(out)
    p_task = np.array([r["task_idx"] for r in rows])
    pred = pred_all[np.arange(len(rows)), p_task]
    y = np.array([r["p"] for r in rows])
    seen = np.array([r["seen_in_chembl"] for r in rows])
    series = np.array([f"{r['pmcid']}|{r['task']}" for r in rows])

    gen = AllChem.GetMorganGenerator(radius=2, fpSize=2048)
    by_task = defaultdict(list)
    for k, m in mols.items():
        if m["split"] != "test":
            fp = gen.GetFingerprint(Chem.MolFromSmiles(m["smiles"]))
            for j in np.where(~np.isnan(m["y"]))[0]:
                by_task[j].append(fp)
    sim = np.array([max(DataStructs.BulkTanimotoSimilarity(gen.GetFingerprint(Chem.MolFromSmiles(r["std_smiles"])),
                                                           by_task[r["task_idx"]])) for r in rows])
    mu = np.nanmean(np.stack([mols[k]["y"] for k in keys if mols[k]["split"] != "test"]), axis=0)
    base = mu[p_task]
    res = {"test": a.test, "values": len(rows), "papers": len({r["pmcid"] for r in rows}), "unseen": int((~seen).sum()),
           "seen": int(seen.sum()), "tasks": sorted({r["task"] for r in rows}),
           "model_all": scores(pred, y, p_task, series), "model_unseen": scores(pred[~seen], y[~seen], p_task[~seen], series[~seen]),
           "baseline_unseen_rmse": round(rmse(base[~seen], y[~seen]), 3), "baseline_all_rmse": round(rmse(base, y), 3),
           "nn_similarity_unseen_median": round(float(np.median(sim[~seen])), 3) if (~seen).any() else None}
    if seen.any():
        cp = np.array([r["chembl_p"] for r in rows if r["seen_in_chembl"]])
        res["model_seen"] = scores(pred[seen], y[seen], p_task[seen], series[seen])
        res["noise_floor_rmse_seen"] = round(rmse(y[seen], cp), 3)
    res["unseen_by_similarity"] = {f"{lo}-{hi}": {"n": int(s.sum()), "rmse": round(rmse(pred[s], y[s]), 3)}
                                   for lo, hi in ((0, 0.4), (0.4, 0.6), (0.6, 1.01))
                                   if (s := (~seen) & (sim >= lo) & (sim < hi)).sum() >= 10}
    Path(a.data, f"results_{a.name}.json").write_text(json.dumps(res, indent=1))
    Path(a.data, f"preds_{a.name}.json").write_text(json.dumps(
        [{"id": r["id"], "task": r["task"], "compound": r["compound"], "pmcid": r["pmcid"], "p": r["p"],
          "pred": round(float(q), 3), "seen": bool(r["seen_in_chembl"]), "nn_sim": round(float(s_), 3)}
         for r, q, s_ in zip(rows, pred, sim)], indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "tasks"}, indent=1))


if __name__ == "__main__":
    main()
