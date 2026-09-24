"""Train one model and save predictions for the ChEMBL test split and the paper test set.

    python tools/generalization/train.py bench/generalization {null,rf,dmpnn,chemeleon} [--epochs N] [--weights bench/generalization/chemeleon_mp.pt]
"""
import argparse
import json
import os
import time

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # Apple GPU: run the rare unsupported op on CPU
from pathlib import Path

import numpy as np

from common import ecfp, load

OUT = Path("bench/generalization/preds")  # run from the repository root


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("model", choices=["null", "rf", "dmpnn", "chemeleon"])
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--device", choices=["auto", "mps", "cuda", "cpu"], default="auto",
                    help="auto = Apple GPU (mps) or NVIDIA (cuda) if present, else CPU")
    ap.add_argument("--weights", default=None, help="chemeleon_mp.pt")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    t0 = time.time()
    tasks, keys, mols, paper = load(a.data)
    split = np.array([mols[k]["split"] for k in keys])
    Y = np.stack([mols[k]["y"] for k in keys])
    smiles = [mols[k]["smiles"] for k in keys]
    tr, va, te = (split == "train"), (split == "val"), (split == "test")
    p_smiles = [r["std_smiles"] for r in paper]
    p_task = np.array([r["task_idx"] for r in paper])
    print(f"{len(keys)} molecules ({tr.sum()} train / {va.sum()} val / {te.sum()} test), {len(tasks)} tasks, "
          f"{len(paper)} paper values; load {time.time() - t0:.0f}s", flush=True)

    if a.model == "null":  # predict each task's training mean
        mu = np.nanmean(Y[tr | va], axis=0)
        pred_te = np.tile(mu, (te.sum(), 1))
        pred_paper = mu[p_task]

    elif a.model == "rf":
        from sklearn.ensemble import RandomForestRegressor
        X = ecfp(smiles)
        Xp = ecfp(p_smiles)
        pred_te = np.full((te.sum(), len(tasks)), np.nan)
        pred_paper = np.full(len(paper), np.nan)
        for j, t in enumerate(tasks):
            m = (tr | va) & ~np.isnan(Y[:, j])
            rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=1, max_features=0.3, n_jobs=-1, random_state=0)
            rf.fit(X[m], Y[m, j])
            pred_te[:, j] = rf.predict(X[te])
            sel = p_task == j
            if sel.any():
                pred_paper[sel] = rf.predict(Xp[sel])
            print(f"  rf [{'#' * (30 * (j + 1) // len(tasks)):30s}] {j + 1}/{len(tasks)} {t} ({m.sum()} train)", flush=True)

    else:
        import torch
        from lightning import pytorch as pl
        from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
        from chemprop import data, featurizers, models, nn

        if a.device == "auto":
            a.device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        print(f"device: {a.device}; CPU threads: {torch.get_num_threads()}", flush=True)
        feat = featurizers.SimpleMoleculeMolGraphFeaturizer()

        def dset(idx, y=True):
            dps = [data.MoleculeDatapoint.from_smi(smiles[i], Y[i] if y else None) for i in idx]
            return data.MoleculeDataset(dps, feat)

        tr_ds, va_ds = dset(np.where(tr)[0]), dset(np.where(va)[0])
        tr_ds.cache = va_ds.cache = True  # featurize molecules once, not every epoch (uses a few GB of RAM)
        scaler = tr_ds.normalize_targets()
        va_ds.normalize_targets(scaler)
        out_t = nn.UnscaleTransform.from_standard_scaler(scaler)
        if a.model == "chemeleon":
            ck = torch.load(a.weights, weights_only=True)
            mp = nn.BondMessagePassing(**ck["hyper_parameters"])
            mp.load_state_dict(ck["state_dict"])
            ffn = nn.RegressionFFN(input_dim=mp.output_dim, hidden_dim=2048, n_tasks=len(tasks), output_transform=out_t)
            lr = dict(init_lr=1e-4, max_lr=5e-4, final_lr=1e-5)
        else:
            mp = nn.BondMessagePassing()
            ffn = nn.RegressionFFN(input_dim=mp.output_dim, n_tasks=len(tasks), output_transform=out_t)
            lr = dict(init_lr=1e-4, max_lr=1e-3, final_lr=1e-4)
        model = models.MPNN(mp, nn.MeanAggregation(), ffn, batch_norm=False, metrics=[nn.metrics.RMSE()], **lr)
        ckdir = OUT / f"ckpt_{a.tag or a.model}"
        cb = ModelCheckpoint(dirpath=ckdir, monitor="val_loss", mode="min", save_top_k=1)
        trainer = pl.Trainer(max_epochs=a.epochs, accelerator=a.device, devices=1, logger=False, enable_progress_bar=True,
                             callbacks=[cb, EarlyStopping(monitor="val_loss", patience=6)])
        trainer.fit(model, data.build_dataloader(tr_ds, batch_size=a.batch, num_workers=0),
                    data.build_dataloader(va_ds, batch_size=256, num_workers=0, shuffle=False))
        model = models.MPNN.load_from_checkpoint(cb.best_model_path)
        model.eval()

        def predict(smis):
            ds = data.MoleculeDataset([data.MoleculeDatapoint.from_smi(s) for s in smis], feat)
            out = trainer.predict(model, data.build_dataloader(ds, batch_size=256, num_workers=0, shuffle=False))
            return torch.cat([o for o in out]).numpy().reshape(len(smis), -1)

        pred_te = predict([smiles[i] for i in np.where(te)[0]])
        pred_paper = predict(p_smiles)[np.arange(len(paper)), p_task]
        print(f"best val_loss {cb.best_model_score:.4f} at {cb.best_model_path}", flush=True)

    OUT.mkdir(exist_ok=True)
    np.savez(OUT / f"{a.tag or a.model}.npz", pred_te=pred_te, y_te=Y[te], pred_paper=pred_paper,
             y_paper=np.array([r["p"] for r in paper]), p_task=p_task)
    (OUT / f"{a.tag or a.model}.json").write_text(json.dumps({"model": a.model, "seconds": round(time.time() - t0),
                                                              "epochs": a.epochs}))
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
