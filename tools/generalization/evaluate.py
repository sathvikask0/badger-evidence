"""Score saved predictions: ChEMBL held-out split (in-distribution) vs values extracted from recent papers.

    python tools/generalization/evaluate.py bench/generalization null rf dmpnn chemeleon
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem
from scipy.stats import spearmanr

from common import load

PREDS = Path("bench/generalization/preds")  # run from the repository root
rng = np.random.default_rng(0)


def rmse(p, y):
    return float(np.sqrt(np.mean((p - y) ** 2)))


def group_spearman(p, y, groups, min_n=5):
    """Mean Spearman within groups of >= min_n values, weighted by group size (how well the model ranks a series)."""
    rs, ws = [], []
    for g in set(groups):
        m = groups == g
        if m.sum() >= min_n and np.ptp(y[m]) > 0 and np.ptp(p[m]) > 0:
            rs.append(spearmanr(p[m], y[m]).statistic)
            ws.append(m.sum())
    return float(np.average(rs, weights=ws)) if rs else float("nan"), len(rs)


def boot(fn, n, k=1000):
    vals = [fn(rng.integers(0, n, n)) for _ in range(k)]
    return [round(float(np.nanpercentile(vals, 2.5)), 3), round(float(np.nanpercentile(vals, 97.5)), 3)]


def scores(p, y, task, series):
    out = {"n": int(len(y)), "rmse": round(rmse(p, y), 3), "mae": round(float(np.mean(np.abs(p - y))), 3),
           "within_1_log": round(float(np.mean(np.abs(p - y) <= 1)), 3)}
    out["rmse_ci"] = boot(lambda i: rmse(p[i], y[i]), len(y))
    r, g = group_spearman(p, y, task)
    out["spearman_within_target"], out["targets_scored"] = round(r, 3), g
    if series is not None:
        r, g = group_spearman(p, y, series)
        out["spearman_within_paper_series"], out["series_scored"] = round(r, 3), g
        out["spearman_within_paper_series_ci"] = boot(lambda i: group_spearman(p[i], y[i], series[i])[0], len(y), 300)
    return out


def main():
    data_dir, names = sys.argv[1], sys.argv[2:]
    tasks, keys, mols, paper = load(data_dir)
    y_paper = np.array([r["p"] for r in paper])
    p_task = np.array([r["task_idx"] for r in paper])
    seen = np.array([r["seen_in_chembl"] for r in paper])
    series = np.array([f"{r['pmcid']}|{r['task']}" for r in paper])

    # nearest-neighbour similarity of each paper compound to the task's ChEMBL training molecules
    gen = AllChem.GetMorganGenerator(radius=2, fpSize=2048)
    fps = {k: gen.GetFingerprint(Chem.MolFromSmiles(m["smiles"])) for k, m in mols.items() if m["split"] != "test"}
    by_task = defaultdict(list)
    for k, fp in fps.items():
        for j in np.where(~np.isnan(mols[k]["y"]))[0]:
            by_task[j].append(fp)
    sim = np.array([max(DataStructs.BulkTanimotoSimilarity(gen.GetFingerprint(Chem.MolFromSmiles(r["std_smiles"])),
                                                           by_task[r["task_idx"]])) for r in paper])
    # noise ceiling: the same compound measured in the paper vs ChEMBL's median for it
    noise = [(r["p"], mols[r["key"]]["y"][r["task_idx"]]) for r in paper if r["seen_in_chembl"]]
    noise = np.array(noise)

    res = {"tasks": tasks, "paper_values": len(paper), "unseen": int((~seen).sum()), "seen": int(seen.sum()),
           "papers": len({r["pmcid"] for r in paper}),
           "noise_ceiling_rmse_same_compound": round(rmse(noise[:, 0], noise[:, 1]), 3) if len(noise) else None,
           "noise_ceiling_n": len(noise),
           "nn_similarity_unseen_median": round(float(np.median(sim[~seen])), 3), "models": {}}
    bins = [(0, 0.4), (0.4, 0.6), (0.6, 1.01)]
    for name in names:
        z = np.load(PREDS / f"{name}.npz")
        te_mask = ~np.isnan(z["y_te"])
        te_task = np.tile(np.arange(len(tasks)), (len(z["y_te"]), 1))[te_mask]
        m = {"chembl_heldout": scores(z["pred_te"][te_mask], z["y_te"][te_mask], te_task, None)}
        pp = z["pred_paper"]
        m["paper_all"] = scores(pp, y_paper, p_task, series)
        m["paper_unseen"] = scores(pp[~seen], y_paper[~seen], p_task[~seen], series[~seen])
        m["paper_seen"] = scores(pp[seen], y_paper[seen], p_task[seen], series[seen])
        m["paper_unseen_by_similarity"] = {}
        for lo, hi in bins:
            s = (~seen) & (sim >= lo) & (sim < hi)
            if s.sum() >= 10:
                m["paper_unseen_by_similarity"][f"{lo}-{min(hi, 1)}"] = {"n": int(s.sum()), "rmse": round(rmse(pp[s], y_paper[s]), 3)}
        per = {}
        for j, t in enumerate(tasks):
            s = (p_task == j) & ~seen
            if s.sum() >= 5:
                per[t] = {"n": int(s.sum()), "rmse": round(rmse(pp[s], y_paper[s]), 3)}
        m["paper_unseen_per_target"] = per
        meta = PREDS / f"{name}.json"
        m["train"] = json.loads(meta.read_text()) if meta.exists() else {}
        res["models"][name] = m
    out = Path("bench/generalization/results.json")
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "models"}, indent=1))
    for name, m in res["models"].items():
        c, u = m["chembl_heldout"], m["paper_unseen"]
        print(f"{name:10s} ChEMBL RMSE {c['rmse']:.2f} rho {c['spearman_within_target']:.2f} | "
              f"paper-unseen RMSE {u['rmse']:.2f} {u['rmse_ci']} rho(target) {u['spearman_within_target']:.2f} "
              f"rho(series) {u['spearman_within_paper_series']:.2f} {u['spearman_within_paper_series_ci']} | "
              f"seen RMSE {m['paper_seen']['rmse']:.2f}")


if __name__ == "__main__":
    main()
