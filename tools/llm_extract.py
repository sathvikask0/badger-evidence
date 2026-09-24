"""Extract enzyme-inhibition values from paper tables with Claude, for comparison against the rule-based extractor.

    pip install anthropic            # (in a venv, or: brew install uv; uv run --with anthropic ...)
    export ANTHROPIC_API_KEY=...     # never commit this
    python3 tools/llm_extract.py bench/mtor_pi3ka --mode images      # only tables published as images
    python3 tools/llm_extract.py bench/mtor_pi3ka --mode all         # every table (LLM-only baseline)
    python3 tools/llm_extract.py bench/mtor_pi3ka --probe            # check image downloads, no API calls

Writes bench/<name>/llm_<mode>.json (other models: llm_<mode>_<model>.json, e.g. llm_all_haiku-4-5.json)
with every extracted value, the model, token usage and cost.
XML tables are sent as text (rows expanded, spans resolved); image tables are downloaded from Europe PMC/PMC
and sent as images with the caption and footnotes. Claude answers through a JSON-schema tool, so output is
structured; values from XML tables are then grounded (the printed value must occur in the table text).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from badger_evidence.extract import expand_rows, parse_xml, text
from badger_evidence.targets import TARGETS

IMAGE_URLS = [
    "https://europepmc.org/articles/{pmcid}/bin/{href}",
    "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/bin/{href}",
    "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/bin/{href}",
]
UNITS = ["pM", "nM", "µM", "mM", "M"]
TO_NM = {"pM": 1e-3, "nM": 1.0, "µM": 1e3, "mM": 1e6, "M": 1e9}

SYSTEM = """You extract enzyme-inhibition potency values from tables in medicinal-chemistry papers into a structured record list.
Rules:
- Only report values for these targets: {targets}. Human, wild-type enzyme only; skip mutants (e.g. H1047R, T790M), other species, and other isoforms or family members.
- Only biochemical/enzymatic or binding measurements: IC50, Ki (including Ki,app) or Kd. Skip cellular assays (cell lines, pAKT/pS6, proliferation, whole blood), % inhibition, pIC50/pKi, selectivity ratios, fold changes, docking or predicted values.
- One record per (compound, target, endpoint) cell. compound_label is exactly as printed in the compound column (e.g. "5a", "PQR309 (1)").
- value_text is the cell text exactly as printed (keep qualifiers and ± parts). value is the central number; relation is "=" unless the cell has <, >, ≤, ≥.
- unit comes from the cell, the column header, the caption or the footnotes. If no unit is stated anywhere, skip the value.
- Never guess. If a cell is unreadable, skip it. If the table has no qualifying values, return an empty list.
Call record_values exactly once."""

TOOL = {
    "name": "record_values",
    "description": "Record every qualifying potency value found in the table.",
    "input_schema": {
        "type": "object",
        "properties": {"values": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "compound_label": {"type": "string"},
                "target": {"type": "string"},
                "endpoint": {"type": "string", "enum": ["IC50", "Ki", "Kd"]},
                "relation": {"type": "string", "enum": ["=", "<", ">", "<=", ">="]},
                "value": {"type": "number"},
                "unit": {"type": "string", "enum": UNITS},
                "value_text": {"type": "string"},
                "column_header": {"type": "string"},
            },
            "required": ["compound_label", "target", "endpoint", "relation", "value", "unit", "value_text"],
        }}},
        "required": ["values"],
    },
}


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "badger-evidence-benchmark/0.1 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read(), r.headers.get("Content-Type", "")
        except Exception:
            if i == tries - 1:
                return None, None
            time.sleep(2 * (i + 1))


def tables(root):
    """(table_id, caption, footnotes, kind, payload) for every table-wrap. kind: xml | image."""
    for wrap in root.iter("table-wrap"):
        tid = wrap.get("id") or ""
        caption, foot = text(wrap.find("caption")), text(wrap.find("table-wrap-foot"))
        table = wrap.find("table")
        if table is not None:
            rows = expand_rows(table.findall(".//tr"), clean=False)
            yield tid, caption, foot, "xml", "\n".join(" | ".join(r) for r in rows)
        else:
            hrefs = []
            for g in wrap.iter("graphic"):
                href = next((v for k, v in g.attrib.items() if k.split("}")[-1] == "href"), None)
                if href:
                    hrefs.append(href)
            if hrefs:
                yield tid, caption, foot, "image", hrefs


DEBUG = False
_page_cache: dict = {}


def pmc_blob_urls(pmcid, name):
    """PMC article pages link figures/tables on a CDN; find the URL for this file name."""
    if pmcid not in _page_cache:
        html, _ = fetch(f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/")
        _page_cache[pmcid] = html.decode("utf-8", "ignore") if html else ""
        if DEBUG:
            print(f"    PMC page {pmcid}: {len(_page_cache[pmcid])} chars")
    stem = re.escape(name.rsplit(".", 1)[0])
    return list(dict.fromkeys(re.findall(r'https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"\s]*?' + stem + r'\.(?:jpg|jpeg|png|gif)', _page_cache[pmcid])))


def candidate_urls(pmcid, name):
    for v in (1, 2, 3):  # PMC Open Access on AWS (versioned article folders)
        yield f"https://pmc-oa-opendata.s3.amazonaws.com/{pmcid}.{v}/{name}"
    yield from pmc_blob_urls(pmcid, name)
    for tpl in IMAGE_URLS:
        yield tpl.format(pmcid=pmcid, href=name)


def get_image(bench, pmcid, href):
    cache = bench / "img" / pmcid
    cache.mkdir(parents=True, exist_ok=True)
    name = href if "." in href.rsplit("/", 1)[-1] else href + ".jpg"
    path = cache / name.replace("/", "_")
    if path.exists():
        return path.read_bytes()
    for url in candidate_urls(pmcid, name):
        data, ctype = fetch(url, tries=2)
        if DEBUG:
            print(f"    {url} -> {ctype or 'no response'} {len(data) if data else 0} bytes")
        if data and ((ctype or "").startswith("image/") or data[:3] in (b"\xff\xd8\xff", b"\x89PN", b"GIF")):
            path.write_bytes(data)
            return data
    return None


class Progress:
    """Single-line progress bar on stderr: [#####-----] 12/69 tables · 17% · ETA 1m 20s · note"""
    def __init__(self, total, unit):
        self.total, self.unit, self.done, self.start = max(total, 1), unit, 0, time.time()

    def step(self, note=""):
        self.done += 1
        frac = self.done / self.total
        elapsed = time.time() - self.start
        eta = elapsed / self.done * (self.total - self.done) if self.done else 0
        bar = "#" * int(frac * 24) + "-" * (24 - int(frac * 24))
        m, sec = divmod(int(eta), 60)
        sys.stderr.write(f"\r[{bar}] {self.done}/{self.total} {self.unit} · {frac:4.0%} · ETA {m}m {sec:02d}s · {note[:50]:<50}")
        sys.stderr.flush()
        if self.done >= self.total:
            sys.stderr.write("\n")


def media_type(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"GIF":
        return "image/gif"
    return "image/jpeg"


def header_conflict(target, header):
    """True if the column header names a different member of the target's family (e.g. PARP2 for PARP1)."""
    m = re.match(r"([A-Z]+)-?(\d+)$", target)
    if not m or not header:
        return False
    fam, num = m.groups()
    nums = re.findall(r"(?<![A-Za-z])" + fam + r"\s?-?(\d+)", header, re.I)
    return bool(nums) and num not in nums


def normalise(s):
    return re.sub(r"[\s  ,]", "", s or "").replace("μ", "µ").replace("−", "-")


PRICES = {  # USD per million tokens (input, output), standard API pricing
    "claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-5": (3.0, 15.0),
}


def llm_file(mode, model):
    """claude-sonnet-4-5 keeps the original name (llm_all.json); other models get their own file."""
    if model == "claude-sonnet-4-5":
        return f"llm_{mode}.json"
    slug = re.sub(r"-20\d{6}$", "", model).replace("claude-", "")
    return f"llm_{mode}_{slug}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bench")
    ap.add_argument("--mode", choices=["images", "all"], default="images")
    ap.add_argument("--model", default="claude-sonnet-4-5", help="any vision-capable Claude model id")
    ap.add_argument("--price-in", type=float, default=None, help="USD per million input tokens (default: known price for --model)")
    ap.add_argument("--price-out", type=float, default=None, help="USD per million output tokens")
    ap.add_argument("--limit", type=int, default=0, help="only the first N papers (for a quick trial)")
    ap.add_argument("--probe", action="store_true", help="download images only; no API calls")
    ap.add_argument("--debug", action="store_true", help="print every download attempt")
    a = ap.parse_args()
    pin, pout = next((v for k, v in PRICES.items() if a.model.startswith(k)), (3.0, 15.0))
    a.price_in = pin if a.price_in is None else a.price_in
    a.price_out = pout if a.price_out is None else a.price_out
    global DEBUG
    DEBUG = a.debug
    bench = Path(a.bench)
    docs = json.loads((bench / "docs.json").read_text())
    gold = json.loads((bench / "gold.json").read_text())
    targets = sorted({g["target"] for rows in gold.values() for g in rows})
    target_desc = "; ".join(f"{k} = {TARGETS[k].name} (UniProt {TARGETS[k].uniprot})" for k in targets)
    items = list(docs.items())[: a.limit or None]

    if a.probe:
        jobs = []
        for _, meta in items:
            root = parse_xml((bench / "xml" / f"{meta['pmcid']}.xml").read_bytes())
            for tid, _, _, kind, payload in tables(root):
                if kind == "image":
                    jobs += [(meta["pmcid"], tid, h) for h in payload]
        bar, ok, missing = Progress(len(jobs), "images"), 0, []
        for pmcid, tid, href in jobs:
            good = get_image(bench, pmcid, href) is not None
            ok += good
            if not good:
                missing.append(f"{pmcid} {tid} {href}")
            bar.step(f"{pmcid} {'ok' if good else 'MISSING'}")
        for m in missing:
            print("  missing:", m)
        print(f"images downloaded: {ok}, missing: {len(missing)}")
        return

    import anthropic
    client = anthropic.Anthropic()
    out_path = bench / llm_file(a.mode, a.model)
    out = json.loads(out_path.read_text()) if out_path.exists() else {"model": a.model, "mode": a.mode, "tables": {}}
    usage = out.setdefault("usage", {"input_tokens": 0, "output_tokens": 0})
    system = SYSTEM.format(targets=target_desc)
    todo = 0
    for _, meta in items:
        for tid, _, _, kind, _ in tables(parse_xml((bench / "xml" / f"{meta['pmcid']}.xml").read_bytes())):
            if f"{meta['pmcid']}|{tid}" not in out["tables"] and not (a.mode == "images" and kind != "image"):
                todo += 1
    print(f"{todo} tables to send to {a.model} ({len(items)} papers, mode={a.mode}); already done tables are skipped.")
    bar = Progress(todo, "tables")
    cost_now = lambda: usage["input_tokens"] / 1e6 * a.price_in + usage["output_tokens"] / 1e6 * a.price_out
    for n, (doc_id, meta) in enumerate(items, 1):
        pmcid = meta["pmcid"]
        root = parse_xml((bench / "xml" / f"{pmcid}.xml").read_bytes())
        for tid, caption, foot, kind, payload in tables(root):
            key = f"{pmcid}|{tid}"
            if key in out["tables"] or (a.mode == "images" and kind != "image"):
                continue
            head = f"Paper {pmcid}, table {tid}.\nCaption: {caption}\nFootnotes: {foot or '(none)'}\n"
            if kind == "xml":
                content = [{"type": "text", "text": head + "Table rows (cells separated by ' | ', header rows first):\n" + payload}]
            else:
                imgs = [d for d in (get_image(bench, pmcid, h) for h in payload) if d]
                if not imgs:
                    out["tables"][key] = {"kind": kind, "error": "image not downloadable", "values": []}
                    bar.step(f"{pmcid} {tid} image missing")
                    continue
                content = [{"type": "image", "source": {"type": "base64", "media_type": media_type(d),
                                                        "data": base64.b64encode(d).decode()}} for d in imgs]
                content.append({"type": "text", "text": head + "The table is shown in the image(s) above."})
            for attempt in range(4):
                try:
                    msg = client.messages.create(model=a.model, max_tokens=8000, system=system, tools=[TOOL],
                                                 tool_choice={"type": "tool", "name": "record_values"},
                                                 messages=[{"role": "user", "content": content}])
                    break
                except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError):
                    time.sleep(10 * (attempt + 1))
            else:
                out["tables"][key] = {"kind": kind, "error": "api failed", "values": []}
                bar.step(f"{pmcid} {tid} API failed")
                continue
            usage["input_tokens"] += msg.usage.input_tokens
            usage["output_tokens"] += msg.usage.output_tokens
            call = next((b for b in msg.content if b.type == "tool_use"), None)
            values = [v for v in (call.input.get("values", []) if call else [])
                      if v.get("target") in targets and not header_conflict(v["target"], v.get("column_header", ""))]
            table_text = normalise(payload) if kind == "xml" else ""
            for v in values:  # models sometimes answer outside the enum: Greek mu, "uM", "nm"
                u = str(v.get("unit", "")).replace("μ", "µ").replace("u", "µ", 1 if str(v.get("unit", "")).startswith("u") else 0)
                v["unit"] = {"nm": "nM", "pm": "pM", "µm": "µM", "mm": "mM", "m": "M"}.get(u.lower(), u) if u not in TO_NM else u
            values = [v for v in values if v["unit"] in TO_NM and isinstance(v.get("value"), (int, float))]
            for v in values:
                v["value_nm"] = v["value"] * TO_NM[v["unit"]]
                v["grounded"] = (normalise(v["value_text"]) in table_text) if kind == "xml" else None
            out["tables"][key] = {"kind": kind, "values": values, "stop_reason": msg.stop_reason}
            out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
            bar.step(f"{pmcid} {tid} {kind}: {len(values)} values · ${cost_now():.2f}")
    cost = usage["input_tokens"] / 1e6 * a.price_in + usage["output_tokens"] / 1e6 * a.price_out
    out["cost_usd"] = round(cost, 4)
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    vals = [v for t in out["tables"].values() for v in t["values"]]
    ungrounded = sum(1 for v in vals if v.get("grounded") is False)
    print(f"Done: {len(vals)} values from {len(out['tables'])} tables; ungrounded (XML tables): {ungrounded}; "
          f"tokens in/out {usage['input_tokens']}/{usage['output_tokens']}; est. cost ${cost:.2f} -> {out_path}")


if __name__ == "__main__":
    main()
