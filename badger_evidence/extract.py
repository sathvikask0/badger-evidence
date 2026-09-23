"""Conservative JATS table extraction. No values or chemical identities are inferred."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from decimal import Decimal

from .targets import TARGETS, caption_target, header_target, is_bare_endpoint

FACTORS = {"pM": Decimal("0.001"), "nM": Decimal(1), "µM": Decimal(1000),
           "mM": Decimal(1000000), "M": Decimal(1000000000)}
UNIT_RE = re.compile(r"(?<![A-Za-z])([pnmµμu]?M)(?![A-Za-z])")
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?"
VALUE_RE = re.compile(rf"^\s*(<=|>=|<|>|=|≤|≥|~|≈)?\s*({NUMBER})(?:\s*±\s*({NUMBER}))?\s*([pnmµμu]?M)?\s*$")


def text(node: ET.Element | None, *, clean: bool = False) -> str:
    if node is None:
        return ""
    def walk(n):
        result = n.text or ""
        for child in n:
            # Superscript letters and xrefs are annotations, not part of a number.
            omit = clean and (child.tag == "xref" or
                             (child.tag == "sup" and re.fullmatch(r"[a-zA-Z*†‡, ]+", "".join(child.itertext()))))
            if not omit:
                result += walk(child)
            result += child.tail or ""
        return result
    return re.sub(r"\s+", " ", walk(node)).strip()


def parse_xml(raw: bytes) -> ET.Element:
    if len(raw) > 20_000_000:
        raise ValueError("Article exceeds the 20 MB limit")
    if re.search(br"<!ENTITY\s", raw, re.I):
        raise ValueError("XML entity declarations are not accepted")
    root = ET.fromstring(raw)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    if root.tag != "article":
        raise ValueError("Expected a JATS article")
    return root


def expand_rows(rows: list[ET.Element], *, clean: bool = True) -> list[list[str]]:
    """Expand HTML/JATS rowspans and colspans without shifting target columns."""
    grid: list[list[str]] = []
    occupied: dict[tuple[int, int], str] = {}
    for y, row in enumerate(rows):
        x = 0
        for cell in row:
            if cell.tag not in ("td", "th"):
                continue
            while (y, x) in occupied:
                x += 1
            rowspan, colspan = int(cell.get("rowspan", "1")), int(cell.get("colspan", "1"))
            if not 1 <= rowspan <= 100 or not 1 <= colspan <= 100:
                raise ValueError("Unsupported table span")
            value = text(cell, clean=clean)
            for dy in range(rowspan):
                for dx in range(colspan):
                    if (y + dy, x + dx) in occupied:
                        raise ValueError("Overlapping table spans")
                    occupied[y + dy, x + dx] = value
            x += colspan
        width = max((col + 1 for (r, col) in occupied if r == y), default=0)
        grid.append([occupied.get((y, col), "") for col in range(width)])
    return grid


def measurement_kind(value: str) -> str | None:
    compact = re.sub(r"[_{}]", "", value)
    kinds = []
    if re.search(r"(?<![A-Za-z])K\s*i(?![A-Za-z])", compact, re.I):
        kinds.append("Ki")
    if re.search(r"(?<![A-Za-z])IC\s*50(?!\d)", compact, re.I):
        kinds.append("IC50")
    if re.search(r"(?<![A-Za-z])K\s*d(?![A-Za-z])", compact, re.I):
        kinds.append("Kd")
    return kinds[0] if len(kinds) == 1 else None


def unit_in(value: str) -> str | None:
    value = re.sub(r"S\.\s?E\.\s?M\.?|\bSEM\b|S\.\s?D\.?", "", value)
    units = {m.replace("μ", "µ").replace("u", "µ") for m in UNIT_RE.findall(value)}
    return units.pop() if len(units) == 1 else None


def is_target(header: str, caption: str) -> bool:
    return header_target(header, caption) == "CA2"


def _legacy_is_ca2(header: str, caption: str) -> bool:
    # Full boundaries keep CA III, CA IX, CA XII and selectivity ratios out.
    compact = re.sub(r"\s+", " ", header).strip()
    compact = re.sub(r"\[[^]]*\]", "", compact).replace("-", " ")
    if re.search(r"\bbovine\b|\bbCA\b", compact, re.I):
        return False
    if "/" in compact:
        return False
    human = bool(re.search(r"\bhCA\s*II\b|\bhuman\b", compact, re.I) or
                 re.search(r"\bhuman\b|\bhCA\b", caption, re.I))
    return human and bool(re.search(r"\b(?:hCA|CA|carbonic anhydrase)\s*II\b", compact, re.I))


def parse_value(raw: str, unit: str | None) -> dict:
    candidate = raw.replace("−", "-").replace("μ", "µ")
    candidate = re.sub(r"(?<=\d)[\s\u2009\u202f]+(?=\d{3}(?:\D|$))", "", candidate)
    match = VALUE_RE.fullmatch(candidate)
    result = {"raw_value": raw, "value": None, "relation": None, "unit": unit,
              "normalized_value_nm": None, "uncertainty": None, "flags": []}
    if not match:
        result["flags"].append("missing_value" if raw.strip().lower() in ("", "nd", "n.d.", "na", "n/a", "-", "–", "—") else "unparsed_value")
        return result
    relation, value, uncertainty, explicit_unit = match.groups()
    relation = {"≤": "<=", "≥": ">=", "≈": "~"}.get(relation, relation or "=")
    if explicit_unit:
        explicit_unit = explicit_unit.replace("u", "µ")
        if unit and explicit_unit != unit:
            result["flags"].append("cell_unit_overrides_header")
        unit = explicit_unit
    number = Decimal(value.replace(",", ""))
    if not number.is_finite() or number.adjusted() > 100:
        result["flags"].append("unparsed_value")
        return result
    result.update(value=float(number), relation=relation, unit=unit,
                  uncertainty=float(Decimal(uncertainty.replace(",", ""))) if uncertainty else None)
    if unit in FACTORS:
        result["normalized_value_nm"] = float(number * FACTORS[unit])
    else:
        result["flags"].append("missing_unit")
    if relation != "=":
        result["flags"].append("qualified_value")
    return result


def extract_article(raw: bytes, metadata: dict | None = None) -> dict:
    root = parse_xml(raw)
    meta = dict(metadata or {})
    ids = {n.get("pub-id-type"): text(n) for n in root.findall("./front/article-meta/article-id")}
    pmcid = meta.get("pmcid") or ids.get("pmcid") or ids.get("pmc")
    if not pmcid:
        raise ValueError("Article needs a PMC identifier")
    pmcid = pmcid if pmcid.startswith("PMC") else "PMC" + pmcid
    if not re.fullmatch(r"PMC\d+", pmcid):
        raise ValueError("Invalid PMC identifier")
    embedded = ids.get("pmcid") or ids.get("pmc")
    if embedded and embedded.removeprefix("PMC") != pmcid.removeprefix("PMC"):
        raise ValueError("Manifest and source PMC identifiers differ")
    meta.update(pmcid=pmcid, title=text(root.find("./front/article-meta/title-group/article-title")),
                doi=ids.get("doi", meta.get("doi", "")), sha256=hashlib.sha256(raw).hexdigest(),
                source_url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
    meta["article_type"] = root.get("article-type", "")
    meta.setdefault("year", text(root.find("./front/article-meta/pub-date/year")))
    meta.setdefault("license", text(root.find("./front/article-meta/permissions/license")))
    # Preserve methods verbatim. This is article-level context, not a claim that
    # every condition applies to every assay in the paper.
    methods = []
    for sec in root.findall("./body//sec"):
        title = text(sec.find("title"))
        assay_title = re.search(r"(?:carbonic anhydrase|\bCA\b|inhibition|enzyme|kinase|mTOR|EGFR|Bcl|cholinesterase|AChE|binding).*(?:assay|activity|inhibition)|(?:assay).*carbonic|in.vitro assay protocol|biological evaluation|\bassays?\b", title, re.I)
        if assay_title:
            paragraphs = [text(p) for p in sec.findall("p") if text(p)]
            if paragraphs:
                methods.append({"section_id": sec.get("id", ""), "title": title, "text": "\n\n".join(paragraphs)})
    records, tables, skipped = [], [], []
    for wrap in root.findall(".//table-wrap"):
        table_id = wrap.get("id")
        table = wrap.find("table")
        if not table_id or table is None:
            skipped.append({"table_id": table_id, "reason": "no_structured_table_or_id"})
            continue
        caption = text(wrap.find("caption"))
        if re.search(r"docking|in silico|predicted|calculated|estimated|computational|MM-?[GP]BSA|binding (?:free )?energ", caption, re.I) and not re.search(r"inhibition data|in vitro|assay|experimental|stopped.flow|enzymatic", caption, re.I):
            skipped.append({"table_id": table_id, "reason": "computational_values"})
            continue
        header_nodes = table.findall("./thead/tr")
        body_nodes = table.findall("./tbody/tr")
        if not body_nodes:
            body_nodes = table.findall("./tr")
        if not header_nodes:
            while body_nodes and body_nodes[0].find("th") is not None:
                header_nodes.append(body_nodes.pop(0))
        header_grid = expand_rows(header_nodes)
        rows = expand_rows(body_nodes)
        original_rows = expand_rows(body_nodes, clean=False)
        width = max((len(row) for row in header_grid), default=0)
        headers = [" | ".join(dict.fromkeys(row[x] for row in header_grid if x < len(row) and row[x])) for x in range(width)]
        col_targets = {x: header_target(h, caption) for x, h in enumerate(headers)}
        col_targets = {x: t for x, t in col_targets.items() if t}
        from_caption = set()
        if not col_targets:
            cap = caption_target(caption)
            if cap:
                col_targets = {x: cap for x, h in enumerate(headers) if is_bare_endpoint(h)}
                from_caption = set(col_targets)
        target_cols = sorted(col_targets)
        if not target_cols:
            continue
        label_cols = [x for x, h in enumerate(headers) if re.search(r"\b(compounds?|comp\.?|cmp|cmpd|cpd|inhibitor|drug|entry|no\.?|N)\b", h.split(" | ")[-1], re.I)]
        if not label_cols and 0 not in col_targets and rows:
            first = [row[0] for row in rows if row]
            if first and sum(bool(re.search(r"[A-Za-z]", c)) or not re.fullmatch(r"[\d.,\s±<>≤≥~−-]*", c) for c in first) >= 0.8 * len(first):
                label_cols = [0]
        if not label_cols:
            skipped.append({"table_id": table_id, "reason": "ambiguous_compound_column"})
            continue
        footnotes = text(wrap.find("table-wrap-foot"))
        tables.append({"pmcid": pmcid, "table_id": table_id, "label": text(wrap.find("label")),
                       "caption": caption, "headers": headers, "rows": rows, "original_rows": original_rows, "footnotes": footnotes})
        for target_col in target_cols:
            header = headers[target_col]
            if "%" in header or re.search(r"docking|binding energy|score|\best\b|calc|predict|ΔG", header, re.I):
                continue
            preceding_labels = [x for x in label_cols if x < target_col]
            if not preceding_labels:
                skipped.append({"table_id": table_id, "reason": "no_preceding_compound_label"})
                continue
            label_col = preceding_labels[-1]
            footnotes_text = text(wrap.find("table-wrap-foot"))
            kind = measurement_kind(header) or measurement_kind(caption) or measurement_kind(" ".join(headers)) or measurement_kind(footnotes_text)
            unit = unit_in(header) or unit_in(caption) or unit_in(" ".join(headers)) or unit_in(footnotes_text)
            for row_index, row in enumerate(rows):
                if len(row) != width:
                    skipped.append({"table_id": table_id, "row_index": row_index, "reason": "irregular_row_width"})
                    continue
                label = row[label_col]
                if not label:
                    skipped.append({"table_id": table_id, "row_index": row_index, "reason": "missing_compound_label"})
                    continue
                parsed = parse_value(row[target_col], unit)
                flags = parsed.pop("flags")
                if not kind:
                    flags.append("missing_measurement_type")
                if not methods:
                    flags.append("missing_assay_context")
                if meta.get("article_type") == "review-article":
                    flags.append("secondary_source")
                if target_col in from_caption:
                    flags.append("target_from_caption")
                record_id = hashlib.sha256(f"{pmcid}/{table_id}/{row_index}/{target_col}".encode()).hexdigest()[:20]
                records.append({"id": record_id, "pmcid": pmcid, "table_id": table_id,
                                "row_index": row_index, "target_column": target_col,
                                "compound_label": label, "compound_id": f"{pmcid}:{label}",
                                "target": col_targets[target_col], "target_name": TARGETS[col_targets[target_col]].name,
                                "taxon_id": 9606 if col_targets[target_col] in ("CA2", "ACHE") else None,
                                "measurement_type": kind, **parsed, "flags": flags,
                                "review_status": "unreviewed", "source_sha256": meta["sha256"],
                                "source_url": f"{meta['source_url']}#{table_id}",
                                "evidence": {"header": header, "row": row, "original_row": original_rows[row_index], "caption": caption, "footnotes": footnotes},
                                "assay_context": methods})
    groups = {}
    for record in records:
        key = (record["target"], record["compound_label"], record["measurement_type"], record["raw_value"], record["unit"])
        groups.setdefault(key, []).append(record)
    for group in groups.values():
        if len(group) > 1:
            for record in group:
                record["flags"].append("repeated_measurement")
    identities = {}
    for record in records:
        identities.setdefault((record["target"], record["compound_label"], record["measurement_type"]), []).append(record)
    for group in identities.values():
        if len({record["table_id"] for record in group}) > 1:
            for record in group:
                record["flags"].append("multiple_reports")
    return {"article": meta, "records": records, "tables": tables, "skipped": skipped}
