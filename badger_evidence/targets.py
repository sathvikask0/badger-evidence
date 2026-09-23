"""Target registry: how each enzyme is named in table headers and captions.

Matching is deliberately conservative. A column is attributed to a target only
when its header names that target (or, for single-target tables, the caption
does and the header is a bare endpoint column). Those caption-derived records
are flagged so they need explicit review before they are shown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    uniprot: str
    why: str
    header: re.Pattern
    exclude: re.Pattern | None = None
    needs_human: bool = False
    tags: tuple = field(default_factory=tuple)


NONHUMAN = re.compile(r"\b(?:bovine|murine|mouse|rat|porcine|electric eel|Electrophorus|Torpedo|eel|yeast|E\.\s*coli|Plasmodium|bacterial)\b", re.I)
HUMAN = re.compile(r"\bhuman\b|\bh(?:AChE|CA|EGFR|mTOR)\b|\bHomo sapiens\b", re.I)

TARGETS = {
    "CA2": Target("CA2", "Human carbonic anhydrase II", "P00918",
                  "Classic, very well-studied enzyme; target of glaucoma drugs.",
                  re.compile(r"\b(?:hCA|CA|carbonic anhydrase)\s*II\b", re.I), needs_human=True),
    "MTOR": Target("MTOR", "mTOR kinase", "P42345",
                   "Central nutrient-sensing kinase; rapamycin, the best-validated longevity drug in animals, acts on it.",
                   re.compile(r"(?<![-\w])mTOR(?:C1|C2)?\b"),
                   re.compile(r"\bp-?mTOR|phospho|/", re.I), tags=("longevity",)),
    "BCLXL": Target("BCLXL", "BCL-xL", "Q07817",
                    "Survival protein that senescent cells depend on; blocking it (e.g. navitoclax) clears them — the 'senolytic' approach.",
                    re.compile(r"\bBcl-?x\s*[lL]\b|\bBCL-?XL\b"),
                    re.compile(r"/|selectiv|ratio", re.I), tags=("longevity",)),
    "SIRT1": Target("SIRT1", "Sirtuin 1 (SIRT1)", "Q96EB6",
                    "NAD+-dependent enzyme linked to caloric restriction and lifespan; the most studied 'longevity' sirtuin.",
                    re.compile(r"\bSIRT\s?1\b|\bSirt1\b"),
                    re.compile(r"/|selectiv|ratio|fold|%", re.I), tags=("longevity",)),
    "SIRT2": Target("SIRT2", "Sirtuin 2 (SIRT2)", "Q8IXJ6",
                    "Sirtuin family member studied in ageing and neurodegeneration.",
                    re.compile(r"\bSIRT\s?2\b|\bSirt2\b"),
                    re.compile(r"/|selectiv|ratio|fold|%", re.I), tags=("longevity",)),
    "ACHE": Target("ACHE", "Human acetylcholinesterase", "P22303",
                   "Alzheimer's-disease drug target (donepezil, galantamine); relevant to healthy brain ageing.",
                   re.compile(r"(?<![A-Za-z])h?AChE\b|\bacetylcholinesterase\b", re.I),
                   re.compile(r"\b(?:ee|Ee|EE|Tc|Dm|m|r)AChE\b|/|selectiv|ratio|BuChE|BChE", re.I),
                   needs_human=True, tags=("ageing-related disease",)),
    "EGFR": Target("EGFR", "EGFR kinase (wild type)", "P00533",
                   "Well-studied cancer drug target; included as a large, mature reference set.",
                   re.compile(r"(?<![-\w])EGFR(?:\s*\(?WT\)?|wt)?(?![-\w])"),
                   re.compile(r"T790M|L858R|C797S|L718Q|G719|del|mut|ex\d|p-?EGFR|phospho|/", re.I)),
}

CELL_LINE = re.compile(r"\bcells?\b|MCF-?7|HepG-?2|K-?562|A-?549|HeLa|HCT-?116|PC-?3|HT-?29|MDA-MB|Jurkat|HEK|U-?87|SK-|NCI-H|H1975|HL-?60|Caco|LoVo|SW-?480|SW-?620|Panc|THP-?1|GI\s*50", re.I)
EGFR_MUTANT = re.compile(r"mutant|mutation|T790M|L858R|C797S|del\s?19|\bLR\b|\bTMLR\b|\bTM\b", re.I)

ENDPOINT_ONLY = re.compile(r"^[\s|]*(?:(?:IC|K)\s*50|IC50|K\s*i|Ki|values?|inhibition|enzym\w*|kinase|mean|±|SD|SEM|S\.?D\.?|S\.?E\.?M\.?|\(|\)|\[|\]|[pnmµμu]?M|,|:|a|b|c|\*|\s)+$", re.I)


def _compact(header: str) -> str:
    compact = re.sub(r"\s+", " ", header).strip()
    return re.sub(r"\[[^]]*\]", "", compact)


def header_target(header: str, caption: str) -> str | None:
    """Target named by this column header, or None."""
    compact = _compact(header)
    if "%" in compact or CELL_LINE.search(compact):
        return None
    found = []
    for key, t in TARGETS.items():
        if key == "CA2":
            c = compact.replace("-", " ")
            if re.search(r"\bbovine\b|\bbCA\b", c, re.I) or "/" in c:
                continue
            human = bool(re.search(r"\bhCA\s*II\b|\bhuman\b", c, re.I) or re.search(r"\bhuman\b|\bhCA\b", caption, re.I))
            if human and t.header.search(c):
                found.append(key)
            continue
        if not t.header.search(compact) or (t.exclude and t.exclude.search(compact)):
            continue
        if key == "EGFR" and (EGFR_MUTANT.search(compact) or EGFR_MUTANT.search(caption)):
            continue
        if NONHUMAN.search(compact):
            continue
        if t.needs_human and not (HUMAN.search(compact) or (HUMAN.search(caption) and not NONHUMAN.search(caption))):
            continue
        found.append(key)
    return found[0] if len(found) == 1 else None


def caption_target(caption: str) -> str | None:
    """Single registered target named by a table caption (non-CA2 only)."""
    if re.search(r"\bcell|antiprolif|cytotox|GI\s*50|growth inhibit", caption, re.I):
        return None
    hits = [k for k, t in TARGETS.items() if k != "CA2" and t.header.search(caption)]
    if len(hits) != 1:
        return None
    t = TARGETS[hits[0]]
    for m in t.header.finditer(caption):
        window = caption[max(0, m.start() - 40): m.end() + 40]
        if t.exclude and t.exclude.search(window.replace("/", "")):
            return None
    if NONHUMAN.search(caption) or (hits[0] == "EGFR" and EGFR_MUTANT.search(caption)):
        return None
    if t.needs_human and not HUMAN.search(caption):
        return None
    return hits[0]


def is_bare_endpoint(header: str) -> bool:
    last = header.split(" | ")[-1]
    return bool(re.search(r"IC\s*50|K\s*i\b", last, re.I)) and bool(ENDPOINT_ONLY.fullmatch(re.sub(r"[_{}]", "", last)))
