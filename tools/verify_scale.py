"""Check Claude's extracted values against the source tables with deterministic rules.

    python3 tools/verify_scale.py corpus/scale1 [llm_all_sonnet-5.json]

Sonnet 5 usually omitted the optional column_header field, so we recover the evidence ourselves: for each value
from an XML table, find the compound's row and the cell with the printed value, read that column's header, and
ask the rule-based target matcher (badger_evidence.targets, which rejects other isoforms, species and mutants)
which enzyme that column is for. Status per value:
  verified          column header (or a single-enzyme caption) names the same enzyme, human/wild type
  rejected          header or caption names a different enzyme, a non-human species, or the value is implausible
  species_unstated  the column/caption names the right enzyme but not its species (e.g. "AChE", often eel) (flagged)
  unverified        cell found but the column cannot be attributed by rules (kept, flagged)
  unlocated         printed value/compound not found in the table (kept out)
  image             value read from a table image; cannot be checked against text (kept, flagged)
Writes corpus/<name>/values.json.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.extract import expand_rows, parse_xml, text
from badger_evidence.targets import NONHUMAN, TARGETS, caption_target, header_target


def named(textblob):
    """Registry enzymes a header/caption names by pattern alone (no species rules)."""
    return {k for k, t in TARGETS.items() if t.header.search(textblob) and not (t.exclude and t.exclude.search(textblob))}


def norm(s):
    return re.sub(r"[\s  ,*†‡§#]", "", s or "").replace("μ", "µ").replace("−", "-").replace("–", "-").lower()


def grid_of(wrap):
    table = wrap.find("table")
    trs = table.findall(".//tr")
    try:
        rows = expand_rows(trs, clean=False)
    except ValueError:
        rows = [[text(c) for c in tr if c.tag in ("td", "th")] for tr in trs]
    thead = table.find("thead")
    n_head = len(thead.findall(".//tr")) if thead is not None else 1
    return rows, max(1, n_head)


def same_label(cell, lab):
    return cell == lab or (lab and cell.startswith(lab + "(")) or (len(lab) > 3 and lab in cell)


def locate(rows, n_head, label, value_text):
    """Headers of every cell that shows the printed value next to the compound: same row (compounds down the
    side, including side-by-side label/value pairs) or same column (transposed tables, compounds across the top)."""
    lab, val = norm(label), norm(value_text)
    num = re.match(r"[<>≤≥~]?-?\d+(?:\.\d+)?", val)
    hit = lambda c: c == val or (num and len(num.group()) >= 2 and c.startswith(num.group()))
    grid = [[norm(c) for c in r] for r in rows]
    found = []
    for i, r in enumerate(grid[n_head:], n_head):  # compounds down the side
        for jl, c in enumerate(r):
            if same_label(c, lab):
                found += [header_of(rows, n_head, j) for j, x in enumerate(r) if j != jl and hit(x)]
                break
        if found:
            return found
    for i in range(n_head):  # compounds across the top
        for jl, c in enumerate(grid[i]):
            if same_label(c, lab):
                found += [" ".join(x for x in rows[k][:1] + [header_of(rows, n_head, 0)] if x)
                          for k in range(n_head, len(grid)) if jl < len(grid[k]) and hit(grid[k][jl])]
        if found:
            return found
    return []


def header_of(rows, n_head, j):
    return " ".join(dict.fromkeys(r[j] for r in rows[:n_head] if j < len(r) and r[j]))


MASS_UNITS = re.compile(r"[µμu]g\s*/\s*m[Ll]|mg\s*/\s*m?[Ll]|ng\s*/\s*m[Ll]", re.I)
SPECIES = re.compile(r"\b(?:ee|Ee|EE|eq|Eq|EQ|e)(?:AChE|BChE|BuChE)\b|electric eel|equine|horse serum", re.I)


def main():
    corpus = Path(sys.argv[1])
    llm = json.loads((corpus / (sys.argv[2] if len(sys.argv) > 2 else "llm_all_sonnet-5.json")).read_text())
    out, stats, cache = [], Counter(), {}
    for key, t in llm["tables"].items():
        pmcid, tid = key.split("|", 1)
        if pmcid not in cache:
            root = parse_xml((corpus / "xml" / f"{pmcid}.xml").read_bytes())
            cache.clear()
            cache[pmcid] = {w.get("id") or "": w for w in root.iter("table-wrap")}
            cache["_review"] = root.get("article-type") in ("review-article", "systematic-review")
        wrap = cache[pmcid].get(tid)
        caption = text(wrap.find("caption")) + " " + text(wrap.find("table-wrap-foot")) if wrap is not None else ""
        for v in t["values"]:
            rec = {"pmcid": pmcid, "table_id": tid, "secondary_source": cache["_review"], **{k: v.get(k) for k in (
                "compound_label", "target", "endpoint", "relation", "value", "unit", "value_text", "value_nm")}}
            if v["unit"] == "M" or v["value"] is None or v["value"] <= 0 or not (1e-4 <= v["value_nm"] <= 1e8):
                rec["status"], rec["reason"] = "rejected", "implausible value/unit"
            elif t["kind"] == "image" or wrap is None or wrap.find("table") is None:
                rec["status"] = "image"
                if NONHUMAN.search(caption) and not re.search(r"\bhuman\b|\bh[A-Z]", caption):
                    rec["status"], rec["reason"] = "rejected", "caption names a non-human enzyme"
            else:
                rows, n_head = grid_of(wrap)
                heads = locate(rows, n_head, v["compound_label"], v["value_text"])
                if not heads:
                    rec["status"] = "unlocated"
                else:  # several cells can show the same text (">100"): prefer the one whose header names this enzyme
                    header = next((h for h in heads if v["target"] in named(h)), heads[0])
                    rec["column_header"] = header
                    ht = header_target(header, caption)
                    if MASS_UNITS.search(header) and not re.search(r"[nµμu]M\b", header):
                        rec["status"], rec["reason"] = "rejected", "column is in mass units (µg/mL), not molar"
                    elif SPECIES.search(header):
                        rec["status"], rec["reason"] = "rejected", "non-human enzyme"
                    elif ht == v["target"]:
                        rec["status"] = "verified"
                    elif ht:
                        rec["status"], rec["reason"] = "rejected", f"column is {ht}"
                    elif NONHUMAN.search(header) or (NONHUMAN.search(caption) and not re.search(r"\bhuman\b|\bh[A-Z]", header + " " + caption)):
                        rec["status"], rec["reason"] = "rejected", "non-human enzyme"
                    elif caption_target(caption) == v["target"]:
                        rec["status"] = "verified"
                    elif (h := named(header)) and v["target"] not in h:
                        rec["status"], rec["reason"] = "rejected", f"column names {'/'.join(sorted(h))}"
                    elif v["target"] in named(header) or named(caption) == {v["target"]}:
                        rec["status"] = "species_unstated"  # right enzyme, but human vs e.g. eel not stated
                    else:
                        rec["status"] = "unverified"
            stats[rec["status"]] += 1
            out.append(rec)
    (corpus / "values.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(dict(stats), "->", corpus / "values.json")
    print("reasons:", Counter(r.get("reason") for r in out if r["status"] == "rejected").most_common(8))


if __name__ == "__main__":
    main()
