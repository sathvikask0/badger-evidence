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
HUMAN = re.compile(r"\bhuman\b|\bh(?:AChE|BChE|BuChE|CA|EGFR|mTOR|MAO)|\bHomo sapiens\b", re.I)

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
    "BCHE": Target("BCHE", "Human butyrylcholinesterase", "P06276",
                   "Second cholinesterase that takes over in the ageing, Alzheimer's-affected brain.",
                   re.compile(r"(?<![A-Za-z])h?Bu?ChE\b|\bbutyrylcholinesterase\b", re.I),
                   re.compile(r"\b(?:eq|Eq|e|m|r)Bu?ChE\b|equine|horse|/|selectiv|ratio|AChE", re.I),
                   needs_human=True, tags=("ageing-related disease",)),
    "MAOB": Target("MAOB", "Human monoamine oxidase B", "P27338",
                   "Brain enzyme whose activity rises with age; target of Parkinson's drugs (selegiline, rasagiline).",
                   re.compile(r"\bh?MAO-?\s?B\b"), re.compile(r"/|selectiv|ratio|\bSI\b|rat|MAO-?\s?A", re.I),
                   needs_human=True, tags=("ageing-related disease",)),
    "MAOA": Target("MAOA", "Human monoamine oxidase A", "P21397",
                   "Neurotransmitter-degrading enzyme; antidepressant target.",
                   re.compile(r"\bh?MAO-?\s?A\b"), re.compile(r"/|selectiv|ratio|\bSI\b|rat|MAO-?\s?B", re.I),
                   needs_human=True),
    "BACE1": Target("BACE1", "BACE1 (β-secretase)", "P56817",
                    "Makes the amyloid-β peptide of Alzheimer's plaques.",
                    re.compile(r"\bBACE-?1\b|β-secretase|beta-secretase", re.I), re.compile(r"/|selectiv|ratio|BACE-?2|cell", re.I),
                    tags=("ageing-related disease",)),
    "GSK3B": Target("GSK3B", "GSK-3β kinase", "P49841",
                    "Insulin-signalling kinase; lowering its activity extends lifespan in flies and is studied for Alzheimer's.",
                    re.compile(r"GSK-?3\s?(?:β|b\b|beta)", re.I), re.compile(r"/|selectiv|ratio", re.I), tags=("longevity",)),
    "PARP1": Target("PARP1", "PARP1", "P09874",
                    "DNA-repair enzyme and major NAD+ consumer; its overactivation drains NAD+ in ageing cells.",
                    re.compile(r"\bPARP-?1\b"), re.compile(r"/|selectiv|ratio|trapp|PARP-?1[0-9]|PAR level", re.I), tags=("longevity",)),
    "HDAC1": Target("HDAC1", "HDAC1", "Q13547",
                    "Histone deacetylase controlling gene expression; part of the epigenetic side of ageing.",
                    re.compile(r"\bHDAC-?\s?1\b(?![0-9])"), re.compile(r"/|selectiv|ratio|\bSI\b", re.I)),
    "HDAC6": Target("HDAC6", "HDAC6", "Q9UBN7",
                    "Cytoplasmic deacetylase involved in protein clean-up (aggresomes); studied in neurodegeneration.",
                    re.compile(r"\bHDAC-?\s?6\b"), re.compile(r"/|selectiv|ratio|\bSI\b", re.I)),
    "PI3KA": Target("PI3KA", "PI3Kα (p110α)", "P42336",
                    "Insulin/IGF-1 pathway kinase; turning this pathway down extends lifespan in worms, flies and mice.",
                    re.compile(r"PI3K\s?-?(?:α|alpha)|p110\s?-?α|PIK3CA", re.I),
                    re.compile(r"/|selectiv|ratio|H1047|E545|E542|mut", re.I), tags=("longevity",)),
    "JAK2": Target("JAK2", "JAK2 kinase", "O60674",
                   "Inflammatory-signalling kinase; JAK inhibitors suppress the harmful secretions of senescent cells.",
                   re.compile(r"\bJAK-?\s?2\b"), re.compile(r"/|selectiv|ratio|V617F|mut", re.I), tags=("longevity",)),
    "COX2": Target("COX2", "COX-2", "P35354",
                   "Inflammation enzyme (target of celecoxib); chronic inflammation drives 'inflammaging'.",
                   re.compile(r"\bCOX-?\s?2\b|cyclooxygenase-2", re.I),
                   re.compile(r"/|selectiv|ratio|\bSI\b|ovine|COX-?\s?1|%", re.I)),
    "DPP4": Target("DPP4", "DPP-4", "P27487",
                   "Type 2 diabetes drug target (sitagliptin); metabolic health is central to ageing.",
                   re.compile(r"\bDPP-?\s?(?:4|IV)\b"), re.compile(r"/|selectiv|ratio|DPP-?\s?(?:8|9)", re.I)),
    "SIRT3": Target("SIRT3", "Sirtuin 3 (SIRT3)", "Q9NTG7",
                    "Mitochondrial sirtuin linked to metabolic health and longevity.",
                    re.compile(r"\bSIRT\s?3\b|\bSirt3\b"), re.compile(r"/|selectiv|ratio|fold|%", re.I), tags=("longevity",)),
    "CD38": Target("CD38", "CD38 (NADase)", "P28907",
                   "Main enzyme destroying NAD+ as we age; blocking it restores NAD+ in old mice.",
                   re.compile(r"\bCD38\b"), re.compile(r"/|selectiv|ratio", re.I), tags=("longevity",)),
    "PTP1B": Target("PTP1B", "PTP1B phosphatase", "P18031",
                    "Switches off insulin signalling; mice lacking it stay lean and insulin-sensitive with age.",
                    re.compile(r"\bPTP-?1B\b|\bPTPN1\b"), re.compile(r"/|selectiv|ratio|TCPTP", re.I), tags=("longevity",)),
    "NAMPT": Target("NAMPT", "NAMPT", "P43490",
                    "Rate-limiting enzyme of NAD+ recycling; NAD+ falls with age.",
                    re.compile(r"\bNAMPT\b"), re.compile(r"/|selectiv|ratio|cell", re.I), tags=("longevity",)),
    "P38A": Target("P38A", "p38α MAP kinase", "Q16539",
                   "Stress kinase that drives the inflammatory secretions (SASP) of senescent cells.",
                   re.compile(r"\bp38\s?-?(?:α|alpha|a\b)|\bp38\s?MAPK\b|MAPK14", re.I),
                   re.compile(r"/|selectiv|ratio|p38\s?-?(?:β|γ|δ)|phospho|p-p38", re.I), tags=("longevity",)),
    "IGF1R": Target("IGF1R", "IGF-1 receptor kinase", "P08069",
                    "Growth-hormone/IGF-1 signalling; lower IGF-1R activity extends lifespan in mice.",
                    re.compile(r"\bIGF-?1R\b|IGF-?IR\b"), re.compile(r"/|selectiv|ratio|cell|phospho", re.I), tags=("longevity",)),
    "SEH": Target("SEH", "Soluble epoxide hydrolase", "P34913",
                  "Inflammation-regulating enzyme studied for cardiovascular and brain ageing.",
                  re.compile(r"\bh?sEH\b|soluble epoxide hydrolase", re.I), re.compile(r"/|selectiv|ratio|\bm-?sEH|\br-?sEH|murine|rat", re.I)),
    "ALOX5": Target("ALOX5", "5-lipoxygenase", "P09917",
                    "Makes inflammatory leukotrienes; part of the inflammaging picture.",
                    re.compile(r"\b5-?LOX\b|\b5-?LO\b|5-lipoxygenase", re.I), re.compile(r"/|selectiv|ratio|soybean|FLAP|cell", re.I)),
    "PDE4B": Target("PDE4B", "PDE4B", "Q07343",
                    "cAMP-degrading enzyme; PDE4 inhibitors are studied for inflammation and memory.",
                    re.compile(r"\bPDE\s?4B\d?\b"), re.compile(r"/|selectiv|ratio", re.I)),
    "PDE5": Target("PDE5", "PDE5", "O76074",
                   "cGMP-degrading enzyme (sildenafil's target); vascular ageing.",
                   re.compile(r"\bPDE\s?5A?\d?\b"), re.compile(r"/|selectiv|ratio", re.I)),
    "LSD1": Target("LSD1", "LSD1 (KDM1A)", "O60341",
                   "Histone demethylase; an epigenetic regulator of ageing-related gene expression.",
                   re.compile(r"\bLSD-?1\b|KDM1A", re.I), re.compile(r"/|selectiv|ratio|cell", re.I)),
    "DYRK1A": Target("DYRK1A", "DYRK1A kinase", "Q13627",
                     "Kinase linked to tau pathology and Down-syndrome-associated early ageing.",
                     re.compile(r"\bDYRK-?1A\b", re.I), re.compile(r"/|selectiv|ratio", re.I), tags=("ageing-related disease",)),
    "CTSK": Target("CTSK", "Cathepsin K", "P43235",
                   "Bone-degrading protease; osteoporosis drug target.",
                   re.compile(r"\bCat(?:hepsin)?\s?-?K\b|\bCTSK\b", re.I), re.compile(r"/|selectiv|ratio", re.I), tags=("ageing-related disease",)),
    "FAAH": Target("FAAH", "FAAH", "O00519",
                   "Breaks down the endocannabinoid anandamide; pain and neuroinflammation target.",
                   re.compile(r"\bh?FAAH\b"), re.compile(r"/|selectiv|ratio|rat|\brFAAH", re.I)),
    "NNMT": Target("NNMT", "NNMT", "P40261",
                   "Consumes NAD+ precursors; rises in ageing muscle and fat.",
                   re.compile(r"\bNNMT\b"), re.compile(r"/|selectiv|ratio|cell", re.I), tags=("longevity",)),
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

CELL_LINE = re.compile(r"\bcells?\b|MCF-?7|HepG-?2|K-?562|A-?549|HeLa|HCT-?116|PC-?3|HT-?29|MDA-MB|Jurkat|HEK|U-?87|\bSK-N|NCI-H|H1975|HL-?60|Caco|LoVo|SW-?480|SW-?620|Panc|THP-?1|GI\s*50", re.I)
NOT_POTENCY = re.compile(r"\bp(?:IC|K[id])\s?50?|percent|inhibition at|S\.\s?I\.|\bSI\b|selectivity|\bratio\b|\bLE\b|ligand efficiency", re.I)
EGFR_MUTANT = re.compile(r"mutant|mutation|T790M|L858R|C797S|del\s?19|\bLR\b|\bTMLR\b|\bTM\b", re.I)

ENDPOINT_ONLY = re.compile(r"^[\s|]*(?:(?:IC|K)\s*50|IC50|K\s*i|Ki|values?|inhibition|enzym\w*|kinase|mean|±|SD|SEM|S\.?D\.?|S\.?E\.?M\.?|\(|\)|\[|\]|[pnmµμu]?M|,|:|a|b|c|\*|\s)+$", re.I)


def _compact(header: str) -> str:
    compact = re.sub(r"\s+", " ", header).strip()
    return re.sub(r"\[[^]]*\]", "", compact)


def header_target(header: str, caption: str) -> str | None:
    """Target named by this column header, or None."""
    compact = _compact(header)
    if "%" in compact or CELL_LINE.search(compact) or NOT_POTENCY.search(compact):
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
