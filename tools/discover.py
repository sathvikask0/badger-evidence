"""Find new open-access (CC BY) papers with potency tables for the benchmark enzymes, for large-scale extraction.

    python3 tools/discover.py --name scale1 --per-target 40

Searches Europe PMC per enzyme (title/abstract mentions the enzyme and inhibitors, open access, full text, 2012+,
newest first), downloads the full-text XML, and keeps a paper only if it is CC BY / CC0 and has a table that looks
like potency data (IC50/Ki/Kd with nM/µM units, or a table image whose caption mentions IC50/Ki/inhibition).
Skips papers already in the atlas or the benchmarks. Standard library only; resumable (XML is cached).
Writes corpus/<name>/docs.json and corpus/<name>/xml/ (gitignored).
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.extract import parse_xml, text

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
# Title/abstract search terms per enzyme (Europe PMC phrase syntax).
TERMS = {
    "ACHE": ['"acetylcholinesterase"'], "BCHE": ['"butyrylcholinesterase"'],
    "BACE1": ['"BACE1"', '"BACE-1"', '"beta-secretase"', '"β-secretase"'],
    "CA2": ['"carbonic anhydrase II"', '"hCA II"', '"CA II"'], "CDK2": ['"CDK2"'],
    "COX2": ['"COX-2"', '"cyclooxygenase-2"'], "CSNK1D": ['"CK1delta"', '"CK1δ"', '"casein kinase 1 delta"'],
    "DYRK1A": ['"DYRK1A"'], "EGFR": ['"EGFR"'], "F10": ['"factor Xa"', '"FXa"'],
    "HDAC1": ['"HDAC1"'], "HDAC6": ['"HDAC6"'],
    "HSD11B1": ['"11beta-HSD1"', '"11β-HSD1"', '"11beta-hydroxysteroid dehydrogenase"'],
    "IDO1": ['"IDO1"', '"indoleamine 2,3-dioxygenase"'], "JAK2": ['"JAK2"'],
    "MAOA": ['"monoamine oxidase"', '"MAO-A"'], "MAOB": ['"monoamine oxidase"', '"MAO-B"'], "MTOR": ['"mTOR"'],
    "PARP1": ['"PARP1"', '"PARP-1"'], "PI3KA": ['"PI3Kalpha"', '"PI3Kα"', '"p110alpha"', '"PI3K alpha"'],
    "PTP1B": ['"PTP1B"'], "ROCK1": ['"ROCK1"', '"Rho kinase"', '"ROCK inhibitor"'],
    "SEH": ['"soluble epoxide hydrolase"'], "SIRT2": ['"SIRT2"'],
    "TGFBR1": ['"ALK5"', '"TGFBR1"', '"TGF-beta type I receptor"', '"TGF-β type I receptor"'],
}
POTENCY = re.compile(r"\b(?:IC|EC)\s?50|IC₅₀|\bK\s?[id]\b", re.I)
UNIT = re.compile(r"[nµμu]M\b")
CAPTION_HINT = re.compile(r"IC\s?50|IC₅₀|\bK\s?i\b|inhibit", re.I)


def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "badger-evidence/0.1 (research)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def bar(label, done, total, t0, note=""):
    frac = done / total if total else 1
    el = time.time() - t0
    eta = el / done * (total - done) if done else 0
    sys.stdout.write(f"\r{label} [{'#' * int(30 * frac):30s}] {done}/{total} {frac:4.0%} "
                     f"eta {eta / 60:4.1f}m {note[:40]:<40}")
    sys.stdout.flush()
    if done >= total:
        sys.stdout.write("\n")


def search(terms, limit):
    """PMCIDs, newest first."""
    phrase = " OR ".join(f"TITLE:{t} OR ABSTRACT:{t}" for t in terms)
    q = f"({phrase}) AND (inhibitor OR inhibitors OR inhibition) AND OPEN_ACCESS:Y AND HAS_FT:Y AND PUB_YEAR:[2012 TO 2026]"
    out, cursor = [], "*"
    while len(out) < limit:
        url = (f"{EPMC}/search?format=json&pageSize=100&resultType=lite&sort=P_PDATE_D%20desc"
               f"&cursorMark={urllib.parse.quote(cursor)}&query={urllib.parse.quote(q)}")
        res = json.loads(get(url))
        hits = res.get("resultList", {}).get("result", [])
        out += [h["pmcid"] for h in hits if h.get("pmcid")]
        nxt = res.get("nextCursorMark")
        if not hits or not nxt or nxt == cursor:
            break
        cursor = nxt
    return out


def cc_by(root):
    lic = root.find("./front/article-meta/permissions")
    if lic is None:
        return False
    blob = ("".join(lic.itertext()) + " " + " ".join(v for e in lic.iter() for k, v in e.attrib.items() if "href" in k)).lower()
    ok = any(s in blob for s in ("licenses/by/", "cc by", "cc-by", "creative commons attribution", "publicdomain/zero", "cc0"))
    return ok and not re.search(r"by-nc|by-nd|noncommercial|non-commercial|no derivatives", blob)


def potency_tables(root):
    n = 0
    for wrap in root.iter("table-wrap"):
        cap = text(wrap.find("caption"))
        if wrap.find("table") is not None:
            body = "".join(wrap.itertext())
            n += bool(POTENCY.search(body) and UNIT.search(body))
        elif CAPTION_HINT.search(cap):
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="scale1")
    ap.add_argument("--per-target", type=int, default=40, help="papers to keep per enzyme")
    ap.add_argument("--targets", nargs="*", default=sorted(TERMS))
    a = ap.parse_args()
    out = Path("corpus") / a.name
    (out / "xml").mkdir(parents=True, exist_ok=True)
    have = {m["pmcid"] for m in json.loads(Path("data/manifest.json").read_text())}
    for f in Path("bench").glob("*/docs.json"):
        have |= {d["pmcid"] for d in json.loads(f.read_text()).values() if d.get("pmcid")}
    docs_path = out / "docs.json"
    docs = json.loads(docs_path.read_text()) if docs_path.exists() else {}
    rejected_path = out / "rejected.json"
    rejected = json.loads(rejected_path.read_text()) if rejected_path.exists() else {}
    print(f"{len(have)} papers already in the atlas/benchmarks are skipped; {len(docs)} kept so far")
    for ti, target in enumerate(a.targets, 1):
        kept = sum(1 for d in docs.values() if target in d["targets"])
        if kept >= a.per_target:
            print(f"[{ti}/{len(a.targets)}] {target}: already {kept}")
            continue
        cands = [p for p in search(TERMS[target], a.per_target * 6) if p not in have]
        t0 = time.time()
        for n, pmcid in enumerate(cands, 1):
            if kept >= a.per_target:
                bar(f"[{ti}/{len(a.targets)}] {target:8s}", len(cands), len(cands), t0, f"kept {kept}")
                break
            if pmcid in docs:
                if target not in docs[pmcid]["targets"]:
                    docs[pmcid]["targets"].append(target)
                    kept += 1
                continue
            if pmcid in rejected:
                continue
            path = out / "xml" / f"{pmcid}.xml"
            try:
                raw = path.read_bytes() if path.exists() else get(f"{EPMC}/{pmcid}/fullTextXML")
                root = parse_xml(raw)
            except Exception:
                rejected[pmcid] = "no full text"
                continue
            if not cc_by(root):
                rejected[pmcid] = "licence"
            elif not potency_tables(root):
                rejected[pmcid] = "no potency table"
            else:
                path.write_bytes(raw)
                ids = {x.get("pub-id-type"): text(x) for x in root.findall("./front/article-meta/article-id")}
                year = text(root.find("./front/article-meta/pub-date/year"))
                docs[pmcid] = {"pmcid": pmcid, "doi": ids.get("doi"), "year": int(year) if year.isdigit() else None,
                               "title": text(root.find("./front/article-meta/title-group/article-title")),
                               "license": "CC BY", "targets": [target]}
                kept += 1
            bar(f"[{ti}/{len(a.targets)}] {target:8s}", n, len(cands), t0, f"kept {kept}")
            if n % 10 == 0:
                docs_path.write_text(json.dumps(docs, indent=1, ensure_ascii=False))
                rejected_path.write_text(json.dumps(rejected))
        else:
            bar(f"[{ti}/{len(a.targets)}] {target:8s}", max(1, len(cands)), max(1, len(cands)), t0, f"kept {kept} (ran out)")
        docs_path.write_text(json.dumps(docs, indent=1, ensure_ascii=False))
        rejected_path.write_text(json.dumps(rejected))
    print(f"Done: {len(docs)} papers in {docs_path}")


if __name__ == "__main__":
    main()
