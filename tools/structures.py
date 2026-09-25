"""Resolve paper-local compound labels ("5a") to structures.

For each reviewed record, find "<chemical name> (<label>)" in the article body,
convert the name with OPSIN, and verify the structure against a molecular formula
stated nearby (HRMS/elemental analysis). Output: data/structures.json
  {"PMCxxx:5a": {"smiles", "inchikey", "name", "method", "formula_check": "match"|"mismatch"|"none", "stated_formula"}}
Only structures that parse and sanitize in RDKit are kept; formula_check says how
strongly each one is supported. Nothing here is inferred from images or SI files.
"""
import json, os, re, sys, warnings
from collections import defaultdict
from pathlib import Path

os.environ.pop("JAVA_TOOL_OPTIONS", None)
warnings.filterwarnings("ignore")
from rdkit import Chem, RDLogger
from rdkit.Chem.rdMolDescriptors import CalcMolFormula
from rdkit.Chem.MolStandardize import rdMolStandardize

_largest = rdMolStandardize.LargestFragmentChooser()
_uncharger = rdMolStandardize.Uncharger()


def parent(mol):
    """Neutral parent: largest fragment (drops HCl etc.), charges neutralised."""
    return _uncharger.uncharge(_largest.choose(mol))
RDLogger.DisableLog("rdApp.*")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.extract import parse_xml

FORMULA = re.compile(r"(?:calcd\.?|calculated|calc\.)\s*(?:for|\.)?\s*(?:\[?M\s*[+-]\s*(?:H|Na|K)\]?\+?\s*)?[:,]?\s*\(?((?:C\d*H\d*)(?:[A-Z][a-z]?\d*)*)", re.I)
FORMULA2 = re.compile(r"\b(C\d{1,3}H\d{1,3}(?:[A-Z][a-z]?\d{0,3}){0,8})\b")


def para_texts(root):
    for p in root.iter("p"):
        yield re.sub(r"\s+", " ", "".join(p.itertext())).strip()
    # Many experimental sections put the compound name in the heading ("... thiazole (2a)") and the data,
    # including the HRMS formula, in the paragraph below it: yield heading + body as one text.
    for sec in root.iter("sec"):
        title = sec.find("title")
        if title is not None:
            body = " ".join("".join(p.itertext()) for p in sec.findall("p"))
            yield re.sub(r"\s+", " ", "".join(title.itertext()) + ". " + body).strip()


def clean_label(label):
    label = re.sub(r"\s*\[[^\]]*\]", "", label).strip()
    return re.sub(r"\s+\d+$", "", label).strip()  # footnote digits like "1a 2"


def candidates(paragraphs, label):
    """Name strings immediately preceding '(label)'."""
    pat = re.compile(r"\(\s*(?:compound\s+)?" + re.escape(label) + r"\s*\)")
    out = []
    for text in paragraphs:
        for m in pat.finditer(text):
            before = text[: m.start()].rstrip()
            seg = re.split(r"(?<=[a-z\)\]])\.\s+(?=[A-Z0-9(])|:\s+|;\s+|\bof\s+(?=[A-Z0-9(])|\bgave\s+|\bafford(?:ed)?\s+|\byield(?:ed)?\s+", before)[-1]
            seg = seg.strip(" ,")
            if 6 <= len(seg) <= 400 and re.search(r"[a-z]{3}", seg):
                after = text[m.end(): m.end() + 2500]
                out.append((seg, after))
    return out


def counts(formula):
    out = {}
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*)", formula or ""):
        out[el] = out.get(el, 0) + (int(n) if n else 1)
    return out


def formula_matches(mol_formula, stated):
    """Same elements, allowing the ions papers report: M, [M+H]+, [M-H]-, [M+Na]+, [M+K]+."""
    stated = re.sub(r"(?<=[A-Z])(?:79|81)(?=Br)", "", stated or "")
    base, want = counts(mol_formula), counts(stated)
    if not want.get("C"):
        return False
    for dh, extra in ((0, None), (1, None), (-1, None), (0, "Na"), (0, "K"), (-1, "Na")):
        c = dict(base)
        c["H"] = c.get("H", 0) + dh
        if extra:
            c[extra] = c.get(extra, 0) + 1
        if {k: v for k, v in c.items() if v} == {k: v for k, v in want.items() if v}:
            return True
    return False


def formula_of(mol):
    return CalcMolFormula(mol).split("+")[0].split("-")[0]


def main():
    """Atlas (default) or a scale-up corpus: python3 tools/structures.py corpus/scale1  (uses its values.json)."""
    data = Path("data")
    want = defaultdict(set)
    if len(sys.argv) > 1:
        corpus = Path(sys.argv[1])
        xml_dir, out_path = corpus / "xml", corpus / "structures.json"
        for r in json.loads((corpus / "values.json").read_text()):
            if r["status"] in ("verified", "species_unstated", "unverified", "image"):
                want[r["pmcid"]].add(r["compound_label"])
    else:
        xml_dir, out_path = data / "source", data / "structures.json"
        ds = json.loads((data / "generated" / "dataset.json").read_text())
        for r in ds["records"]:
            if r.get("review_status") == "reviewed":
                want[r["pmcid"]].add(r["compound_label"])
    jobs = []  # (key, name variant, after-text)
    for pmcid, labels in want.items():
        root = parse_xml((xml_dir / f"{pmcid}.xml").read_bytes())
        body = root.find("./body")
        paragraphs = list(para_texts(body if body is not None else root))
        for label in labels:
            lab = clean_label(label)
            if not re.fullmatch(r"[A-Za-z]{0,4}-?\d{1,3}[a-z]{0,2}(?:[-‐–]\d+)?|\d{1,3}[a-z]?[′']?", lab):
                continue  # only paper-local numbering like 5a, 12, 7-3, SN-12
            for seg, after in candidates(paragraphs, lab):
                words = seg.split(" ")
                for i in range(0, min(len(words), 12)):
                    name = " ".join(words[i:])
                    if len(name) >= 6:
                        jobs.append((f"{pmcid}:{label}", name, after))
    from py2opsin import py2opsin  # imported here so other tools can reuse this module without Java/OPSIN
    names = sorted({j[1] for j in jobs})
    print("labels with name candidates:", len({j[0] for j in jobs}), "OPSIN queries:", len(names), flush=True)
    smiles = {}
    B = 500
    for i in range(0, len(names), B):
        chunk = names[i:i + B]
        res = py2opsin(chunk)
        for n, s in zip(chunk, res):
            if s:
                smiles[n] = s
    print("parsed:", len(smiles), flush=True)
    best = {}
    for key, name, after in jobs:
        s = smiles.get(name)
        if not s:
            continue
        mol = Chem.MolFromSmiles(s)
        if mol is None:
            continue
        mol = parent(mol)
        if mol.GetNumHeavyAtoms() < 6:
            continue
        # prefer the longest parsed name for a key (earliest start = more words)
        prev = best.get(key)
        stated = [m.group(1) for m in FORMULA.finditer(after[:1500])] or FORMULA2.findall(after[:1500])
        f = formula_of(mol)
        check = "none"
        if stated:
            check = "match" if any(formula_matches(f, x) for x in stated[:3]) else "mismatch"
        rank = (check == "match", len(name))
        if prev and prev["_rank"] >= rank:
            continue
        best[key] = {"_rank": rank, "smiles": Chem.MolToSmiles(mol), "inchikey": Chem.MolToInchiKey(mol), "name": name,
                     "method": "opsin_name_in_text", "formula_check": check, "formula": f,
                     "stated_formula": stated[0] if stated else None}
    # A structure shared by several labels in one paper is a fragment or reagent, not the compound.
    from collections import Counter
    shared = Counter((k.split(":")[0], v["inchikey"]) for k, v in best.items())
    for k, v in best.items():
        v.pop("_rank", None)
        if shared[(k.split(":")[0], v["inchikey"])] > 1 and v["formula_check"] != "match":
            v["formula_check"] = "ambiguous"
    out_path.write_text(json.dumps(best, indent=1, ensure_ascii=False))
    from collections import Counter
    print("resolved:", len(best), Counter(v["formula_check"] for v in best.values()))


if __name__ == "__main__":
    main()
