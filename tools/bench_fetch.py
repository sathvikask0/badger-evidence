"""Fetch an extraction benchmark: open-access papers that ChEMBL has curated, with ChEMBL's values as reference.

Run from the repository root on a machine with internet access (standard library only):
    python3 tools/bench_fetch.py --targets MTOR PI3KA --max-docs 150

Writes bench/<name>/:
    gold.json     ChEMBL values per document (reference set)
    docs.json     document metadata incl. PMCID and licence
    xml/*.xml     Europe PMC full text (kept local; gitignored because not all are CC BY)
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
TARGET_IDS = {  # ChEMBL single-protein human targets
    "MTOR": "CHEMBL2842", "PI3KA": "CHEMBL4005", "GSK3B": "CHEMBL262", "JAK2": "CHEMBL2971",
    "PARP1": "CHEMBL3105", "EGFR": "CHEMBL203", "CDK2": "CHEMBL301", "P38A": "CHEMBL260",
}


def get(url, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "badger-evidence-benchmark/0.1 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # network hiccups, 5xx
            if i == tries - 1:
                raise SystemExit(f"Network error after {tries} tries ({e}). Check your connection and rerun; finished steps are cached.")
            wait = min(60, 3 * 2 ** i)
            print(f"\n  network error ({e.__class__.__name__}); retrying in {wait}s", flush=True)
            time.sleep(wait)


def get_json(url):
    return json.loads(get(url))


def activities(target_id):
    fields = "activity_id,molecule_chembl_id,molecule_pref_name,standard_type,standard_relation,standard_value,standard_units,pchembl_value,document_chembl_id,data_validity_comment"
    out, url = [], (f"{CHEMBL}/activity.json?target_chembl_id={target_id}&standard_type__in=IC50,Ki,Kd"
                    f"&pchembl_value__isnull=false&limit=1000&only={fields}")
    while url:
        page = get_json(url)
        out += page["activities"]
        nxt = page["page_meta"].get("next")
        url = f"https://www.ebi.ac.uk{nxt}" if nxt else None
        print(f"  {target_id}: {len(out)}/{page['page_meta']['total_count']}", end="\r", flush=True)
    print()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", default=["MTOR", "PI3KA"])
    ap.add_argument("--max-docs", type=int, default=150)
    ap.add_argument("--name", default=None)
    a = ap.parse_args()
    name = a.name or "_".join(t.lower() for t in a.targets)
    out = Path("bench") / name
    (out / "xml").mkdir(parents=True, exist_ok=True)

    cache = out / "_chembl_cache.json"
    gold = {}
    if cache.exists():
        gold, docs = json.loads(cache.read_text())
        print(f"Using cached ChEMBL data ({len(gold)} documents)")
    for key in ([] if cache.exists() else a.targets):
        print(f"ChEMBL activities for {key} ...")
        for act in activities(TARGET_IDS[key]):
            gold.setdefault(act["document_chembl_id"], []).append({"target": key, **act})
    print(f"{len(gold)} ChEMBL documents")

    if not cache.exists():
        docs = {}
    ids = [] if cache.exists() else list(gold)
    for i in range(0, len(ids), 50):
        page = get_json(f"{CHEMBL}/document.json?limit=50&only=document_chembl_id,pubmed_id,doi,journal,year,src_id"
                        f"&document_chembl_id__in={','.join(ids[i:i + 50])}")
        for d in page["documents"]:
            if d.get("pubmed_id") and d.get("src_id") == 1:
                docs[d["document_chembl_id"]] = d
        print(f"  documents {min(i + 50, len(ids))}/{len(ids)}", end="\r", flush=True)
    print(f"\n{len(docs)} literature documents with a PubMed ID")
    cache.write_text(json.dumps([gold, docs]))

    by_pmid = {str(d["pubmed_id"]): k for k, d in docs.items()}
    pmids = list(by_pmid)
    open_docs, seen_pmc = {}, 0
    for i in range(0, len(pmids), 40):
        batch = pmids[i:i + 40]
        # Parentheses matter: without them AND binds tighter than OR. Open-access status is
        # read from each result (isOpenAccess / pmcid) rather than filtered in the query.
        q = "(" + " OR ".join(f"EXT_ID:{p}" for p in batch) + ") AND SRC:MED"
        res = None
        for attempt in range(5):
            try:
                res = get_json(f"{EPMC}/search?format=json&pageSize=100&resultType=core&query={urllib.parse.quote(q)}")
            except Exception:
                res = None
            if res and "resultList" in res:
                break
            time.sleep(2 * (attempt + 1))
        if not res or "resultList" not in res:
            raise SystemExit(f"Europe PMC search failed for batch starting {batch[0]}; response: {str(res)[:200]}")
        for r in res["resultList"]["result"]:
            if r.get("pmcid"):
                seen_pmc += 1
            if r.get("pmcid") and r.get("isOpenAccess") == "Y" and r.get("id") in by_pmid:
                d = docs[by_pmid[r["id"]]]
                d.update(pmcid=r["pmcid"], license=r.get("license"), title=r.get("title"))
                open_docs[by_pmid[r["id"]]] = d
        print(f"  Europe PMC lookups {min(i + 40, len(pmids))}/{len(pmids)}: {seen_pmc} in PMC, {len(open_docs)} open access", end="\r", flush=True)
        time.sleep(0.3)
    print()
    if not open_docs:
        raise SystemExit("No open-access papers found; not writing an empty benchmark.")

    chosen = sorted(open_docs.values(), key=lambda d: -len(gold[d["document_chembl_id"]]))[: a.max_docs]
    kept = {}
    for n, d in enumerate(chosen, 1):
        path = out / "xml" / f"{d['pmcid']}.xml"
        if not path.exists():
            try:
                path.write_bytes(get(f"{EPMC}/{d['pmcid']}/fullTextXML"))
            except Exception as e:
                print(f"  skip {d['pmcid']}: {e}")
                continue
        kept[d["document_chembl_id"]] = d
        print(f"  full text {n}/{len(chosen)}", end="\r", flush=True)
        time.sleep(0.2)
    print()
    (out / "docs.json").write_text(json.dumps(kept, indent=1))
    (out / "gold.json").write_text(json.dumps({k: gold[k] for k in kept}, indent=1))
    print(f"Done: {len(kept)} open-access papers with ChEMBL reference values in {out}/")


if __name__ == "__main__":
    sys.exit(main())
