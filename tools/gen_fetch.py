"""Fetch what the generalization experiment needs from the internet (run on a machine with open network access).

    python3 tools/gen_fetch.py

1. SMILES for every ChEMBL molecule (from the ChEMBL 37 bulk structure file, ~250 MB, downloaded automatically) measured on the benchmark targets -> bench/generalization/chembl_smiles.json
2. CheMeleon, a GNN pre-trained on ~1M PubChem molecules (Chemprop foundation model, Zenodo 15460715)
   -> bench/generalization/chemeleon_mp.pt
Standard library only; resumable (re-run after a network drop and it continues).
"""
import gzip
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OUT = Path("bench/generalization")
API = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
CHEMREPS = Path("chembl_37_chemreps.txt.gz")  # bulk structure file from the ChEMBL FTP; much faster than the API
CHEMREPS_URL = "https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/releases/chembl_37/chembl_37_chemreps.txt.gz"
WEIGHTS = "https://zenodo.org/records/15460715/files/chemeleon_mp.pt"
BATCH = 200


def bar(label, done, total, t0, extra=""):
    frac = done / total if total else 1
    el = time.time() - t0
    eta = el / done * (total - done) if done else 0
    fill = int(30 * frac)
    sys.stdout.write(f"\r{label} [{'#' * fill}{'.' * (30 - fill)}] {done}/{total} {frac:5.1%} "
                     f"elapsed {el / 60:4.1f}m eta {eta / 60:4.1f}m {extra}   ")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "badger-evidence/0.1 (research)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def download(url, dest, label):
    """Stream url to dest with a progress bar; resumes nothing, but never leaves a half file under the final name."""
    req = urllib.request.Request(url, headers={"User-Agent": "badger-evidence/0.1 (research)"})
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        mb, done, t0 = max(1, total >> 20), 0, time.time()
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                bar(label, min(done >> 20, mb - 1), mb, t0, "MB")
        if total:
            bar(label, mb, mb, t0, "MB")
    tmp.rename(dest)


def batch(ids):
    url = (f"{API}?limit={len(ids)}&only=molecule_chembl_id,molecule_structures"
           f"&molecule_chembl_id__in={','.join(ids)}")
    out = {}
    for m in json.loads(get(url))["molecules"]:
        s = (m.get("molecule_structures") or {}).get("canonical_smiles")
        out[m["molecule_chembl_id"]] = s
    for i in ids:  # molecules without a structure are recorded too, so they are not re-fetched
        out.setdefault(i, None)
    return out


def main():
    test = json.loads((OUT / "paper_test.json").read_text())
    ids, t0 = set(), time.time()
    pairs = list(test["pairs"])
    for n, pair in enumerate(pairs, 1):
        target, endpoint = pair.split("|")
        d = json.loads(Path(f"data/chembl/{target}.json").read_text())
        ids |= {r[1] for r in d["rows"] if r[3] == endpoint}
        bar("Reading ChEMBL files ", n, len(pairs), t0, target)
    path = OUT / "chembl_smiles.json"
    smiles = json.loads(path.read_text()) if path.exists() else {}
    missing = ids - set(smiles)
    if missing and not CHEMREPS.exists():
        download(CHEMREPS_URL, CHEMREPS, "Downloading ChEMBL structures")
    if missing and CHEMREPS.exists():
        total, t0, found = CHEMREPS.stat().st_size, time.time(), 0
        with open(CHEMREPS, "rb") as raw, gzip.open(raw, "rt") as f:
            next(f)  # header: chembl_id, canonical_smiles, standard_inchi, standard_inchi_key
            for n, line in enumerate(f):
                cid, smi = line.split("\t", 2)[:2]
                if cid in ids:
                    smiles[cid] = smi or None
                    found += 1
                if n % 50000 == 0:
                    bar("Reading chemreps file", raw.tell() >> 20, max(1, total >> 20), t0, "MB")
        bar("Reading chemreps file", max(1, total >> 20), max(1, total >> 20), t0, "MB")
        print(f"{found} structures from {CHEMREPS}")
    todo = sorted(ids - set(smiles))
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{len(ids)} molecules; {len(smiles)} already cached; fetching {len(todo)} in {len(chunks)} requests")
    t0, failed = time.time(), 0
    if chunks:
        bar("Fetching structures  ", 0, len(chunks), t0)
        with ThreadPoolExecutor(4) as pool:
            futs = [pool.submit(batch, c) for c in chunks]
            for n, f in enumerate(as_completed(futs), 1):
                try:
                    smiles.update(f.result())
                except Exception:
                    failed += 1
                if n % 20 == 0 or n == len(chunks):
                    path.write_text(json.dumps(smiles))
                bar("Fetching structures  ", n, len(chunks), t0, f"failed {failed}" if failed else "")
    path.write_text(json.dumps(smiles))
    print(f"SMILES: {sum(1 for v in smiles.values() if v)} of {len(smiles)} molecules -> {path}")
    if failed:
        print(f"{failed} requests failed (network). Re-run the same command to fetch just those.")

    w = OUT / "chemeleon_mp.pt"
    if not w.exists():
        download(WEIGHTS, w, "Downloading CheMeleon")
    print(f"CheMeleon weights: {w} ({w.stat().st_size / 1e6:.0f} MB)")
    print("Done." if not failed else "Done, with failures: re-run to complete.")


if __name__ == "__main__":
    sys.exit(main())
