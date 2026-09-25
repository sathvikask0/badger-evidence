# /// script
# requires-python = ">=3.10,<3.12"
# dependencies = [
#   "MolScribe @ git+https://github.com/thomas0809/MolScribe.git",
#   "decimer-segmentation",
#   "rapidocr-onnxruntime",
#   "huggingface_hub",
#   "opencv-python-headless",
#   "rdkit",
# ]
# ///
"""Read compound structures from paper figures with open OCSR models, keep only formula-verified ones.

    uv run tools/ocsr.py corpus/scale1 --limit 10        # pilot
    uv run tools/ocsr.py corpus/scale1                   # everything

For each paper with verified values whose compound has no structure yet:
  1. download the paper's figures/schemes (PMC open-access bucket, same as table images)
  2. find each drawn molecule (DECIMER Segmentation, Mask R-CNN)
  3. convert each drawing to a molecule (MolScribe)
  4. read the labels printed in the figure ("5a") with OCR (RapidOCR) and attach the nearest one to each drawing
  5. keep a structure only if its molecular formula matches the formula the paper states for that label
     (HRMS / elemental analysis "calcd for C21H24N4O2") - an unrelated structure almost never matches by chance.
Outputs corpus/<name>/structures_ocsr.json and, for spot checks, corpus/<name>/ocsr_crops/<pmcid>_<label>.png.
Model weights download on first run (MolScribe from Hugging Face, DECIMER from Zenodo). No API calls.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
os.environ.setdefault("GLOG_minloglevel", "3")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from badger_evidence.extract import parse_xml, text
from llm_extract import Progress, get_image
from structures import FORMULA, formula_matches, formula_of, parent

LABEL_RE = re.compile(r"^[A-Za-z]{0,4}-?\d{1,3}[a-z]{0,2}(?:[-‐–]\d+)?$")


def norm_label(label):
    lab = re.sub(r"^(?:compound|cpd\.?|comp\.?)\s*", "", label.strip(), flags=re.I)
    lab = re.sub(r"\s*\[[^\]]*\]|\s*\([^)]*\)", "", lab)
    return re.sub(r"[\s‐–]", "", lab).replace("′", "'")


def stated_formulas(root, labels):
    """label -> formulas stated right after the label's synthesis heading/paragraph ("... (5a). ... calcd for C..")."""
    out = defaultdict(list)
    blocks = []
    for sec in root.iter("sec"):
        title = text(sec.find("title"))
        body = " ".join(re.sub(r"\s+", " ", "".join(p.itertext())) for p in sec.findall("p"))
        blocks.append((title, body))
    for p in root.iter("p"):
        blocks.append(("", re.sub(r"\s+", " ", "".join(p.itertext()))))
    for lab in labels:
        pat = re.compile(r"\(\s*(?:compound\s+)?" + re.escape(lab).replace(r"\ ", r"\s?") + r"\s*\)")
        for title, body in blocks:
            if title and pat.search(title.replace(" ", "")) or pat.search(title):
                window = body[:1800]
            else:
                m = pat.search(body) or re.search(r"(?:data for|compound)\s+" + re.escape(lab) + r"(?![A-Za-z0-9])", body)
                if not m:
                    continue
                window = body[m.end(): m.end() + 1800]
            f = [m.group(1) for m in FORMULA.finditer(window)]
            if f:
                out[lab].append(f[0])
    return out


def figure_hrefs(root):
    for fig in root.iter("fig"):
        for g in fig.iter("graphic"):
            href = next((v for k, v in g.attrib.items() if k.split("}")[-1] == "href"), None)
            if href:
                yield fig.get("id") or "", href


def link_labels(bboxes, ocr, labels):
    """Attach the nearest OCR'd label (from the paper's own label list) to each drawing's box."""
    wanted = {norm_label(l): l for l in labels}
    tokens = []
    for box, txt, score in ocr or []:
        t = norm_label(re.sub(r"[,.;:]$", "", txt.strip()))
        if t in wanted and score > 0.5:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            tokens.append((wanted[t], (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))
    links = {}
    for i, (y0, x0, y1, x1) in enumerate(bboxes):
        cx, h, w = (x0 + x1) / 2, y1 - y0, x1 - x0
        best = None
        for lab, tx, ty in tokens:
            if not (x0 - 0.25 * w <= tx <= x1 + 0.25 * w):
                continue
            if y0 + 0.5 * h <= ty <= y1 + 0.6 * h:  # labels sit under (or in the lower half of) the drawing
                d = abs(ty - y1) + abs(tx - cx) * 0.5
                if best is None or d < best[0]:
                    best = (d, lab)
        if best:
            links[i] = best[1]
    return links


def to_rgb(seg):
    """DECIMER segments are RGBA (alpha = mask); flatten onto white for MolScribe."""
    import numpy as np
    if seg.ndim == 2:
        return np.stack([seg] * 3, axis=-1)
    if seg.shape[2] == 4:
        alpha = seg[..., 3:4].astype("float32") / 255.0
        return (seg[..., :3] * alpha + 255 * (1 - alpha)).astype("uint8")
    return seg[..., :3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--limit", type=int, default=0, help="only the first N papers (pilot)")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps"])
    a = ap.parse_args()
    corpus = Path(a.corpus)
    values = json.loads((corpus / "values.json").read_text())
    have = json.loads((corpus / "structures.json").read_text()) if (corpus / "structures.json").exists() else {}
    out_path = corpus / "structures_ocsr.json"
    done = json.loads(out_path.read_text()) if out_path.exists() else {}
    crops = corpus / "ocsr_crops"
    crops.mkdir(exist_ok=True)

    need = defaultdict(set)
    for r in values:
        if r["status"] != "verified" or r["secondary_source"]:
            continue
        key = f"{r['pmcid']}:{r['compound_label']}"
        if have.get(key, {}).get("formula_check") != "match" and LABEL_RE.match(norm_label(r["compound_label"])):
            need[r["pmcid"]].add(r["compound_label"])
    plan = []
    for pmcid, labels in sorted(need.items()):
        root = parse_xml((corpus / "xml" / f"{pmcid}.xml").read_bytes())
        forms = stated_formulas(root, sorted({norm_label(l) for l in labels}))
        if forms and pmcid not in done.get("_papers_done", []):
            plan.append((pmcid, labels, forms, list(figure_hrefs(root))))
    plan = plan[: a.limit or None]
    n_labels = sum(len(p[1]) for p in plan)
    n_forms = sum(len(p[2]) for p in plan)
    print(f"{len(plan)} papers, {n_labels} labels without a structure, {n_forms} of them with a stated formula, "
          f"{sum(len(p[3]) for p in plan)} figures")

    import numpy as np
    import cv2
    import torch
    from huggingface_hub import hf_hub_download
    from rdkit import Chem, RDLogger
    from rapidocr_onnxruntime import RapidOCR
    from decimer_segmentation import segment_chemical_structures
    from molscribe import MolScribe
    RDLogger.DisableLog("rdApp.*")
    dev = a.device if a.device != "auto" else ("mps" if torch.backends.mps.is_available() else "cpu")
    print("loading models (first run downloads weights) ...", flush=True)
    scribe = MolScribe(hf_hub_download("yujieq/MolScribe", "swin_base_char_aux_1m.pth"), device=torch.device(dev))
    ocr = RapidOCR()

    stats = defaultdict(int)
    bar = Progress(sum(len(p[3]) for p in plan), "figures")
    for pmcid, labels, forms, figs in plan:
        found = {}
        for fid, href in figs:
            data = get_image(corpus, pmcid, href)
            if not data:
                stats["figure not downloadable"] += 1
                bar.step(f"{pmcid} {fid} missing")
                continue
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                bar.step(f"{pmcid} {fid} unreadable")
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            try:
                segs, bboxes = segment_chemical_structures(img, expand=True, return_bboxes=True)
                segs = [to_rgb(x) for x in segs]
            except Exception as e:
                stats["segmentation error"] += 1
                bar.step(f"{pmcid} {fid} seg error")
                continue
            stats["drawings found"] += len(segs)
            links = link_labels(bboxes, ocr(img)[0], [l for l in labels])
            stats["drawings with a label"] += len(links)
            todo = [(i, lab) for i, lab in links.items() if norm_label(lab) in forms and lab not in found]
            if todo:
                preds = scribe.predict_images([segs[i] for i, _ in todo], return_confidence=True)
                for (i, lab), p in zip(todo, preds):
                    mol = Chem.MolFromSmiles(p.get("smiles") or "")
                    if mol is None or "*" in p["smiles"]:
                        stats["unparseable / R-group drawing"] += 1
                        continue
                    mol = parent(mol)
                    f = formula_of(mol)
                    ok = any(formula_matches(f, s) for s in forms[norm_label(lab)])
                    stats["formula match" if ok else "formula mismatch"] += 1
                    if ok:
                        found[lab] = {"smiles": Chem.MolToSmiles(mol), "inchikey": Chem.MolToInchiKey(mol),
                                      "method": "ocsr_molscribe_decimer", "formula_check": "match", "formula": f,
                                      "stated_formula": forms[norm_label(lab)][0], "confidence": round(float(p.get("confidence", 0)), 3),
                                      "figure": fid, "href": href}
                        cv2.imwrite(str(crops / f"{pmcid}_{norm_label(lab)}.png"), cv2.cvtColor(segs[i], cv2.COLOR_RGB2BGR))
            bar.step(f"{pmcid} {fid}: {len(segs)} drawings, {len(found)} verified")
        for lab, rec in found.items():
            done[f"{pmcid}:{lab}"] = rec
        done.setdefault("_papers_done", []).append(pmcid)
        out_path.write_text(json.dumps(done, indent=1))
    verified = {k: v for k, v in done.items() if not k.startswith("_")}
    vals = sum(1 for r in values if r["status"] == "verified" and f"{r['pmcid']}:{r['compound_label']}" in verified)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in stats.items()))
    print(f"Done: {len(verified)} formula-verified structures from drawings, covering {vals} verified values -> {out_path}")
    print(f"Spot-check crops in {crops}/")


if __name__ == "__main__":
    main()
