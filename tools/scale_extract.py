"""Extract potency values from a discovered corpus with Claude through the Message Batches API (half price).

    export ANTHROPIC_API_KEY=...          # your own terminal only
    uv run --with anthropic tools/scale_extract.py corpus/scale1              # submit, wait, collect
    uv run --with anthropic tools/scale_extract.py corpus/scale1 --estimate   # count tables and estimate cost only

Same prompt, JSON-schema tool and checks as tools/llm_extract.py (grounding for XML tables, header-conflict guard,
unit normalisation). Each table is sent with the enzymes the paper was found for plus any registry enzyme named in
the table or its caption. Resumable: batch ids are saved, so re-running after a disconnect just keeps waiting.
Writes corpus/<name>/llm_all_<model>.json in the llm_extract format.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from badger_evidence.extract import parse_xml
from badger_evidence.targets import TARGETS
from llm_extract import (PRICES, SYSTEM, TO_NM, TOOL, Progress, get_image, header_conflict, llm_file,
                         media_type, normalise, tables)

CHUNK_BYTES = 150 * 1024 * 1024  # stay under the 256 MB batch limit
CHUNK_REQUESTS = 5000


def table_targets(paper_targets, caption, payload):
    blob = caption + " " + (payload if isinstance(payload, str) else "")
    found = set(paper_targets) | {k for k, t in TARGETS.items() if t.header.search(blob)}
    return sorted(found)


def unit_ok(v):
    u = str(v.get("unit", "")).replace("μ", "µ")
    if u.startswith("u"):
        u = "µ" + u[1:]
    v["unit"] = u if u in TO_NM else {"nm": "nM", "pm": "pM", "µm": "µM", "mm": "mM", "m": "M"}.get(u.lower(), u)
    return v["unit"] in TO_NM and isinstance(v.get("value"), (int, float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N papers")
    a = ap.parse_args()
    corpus = Path(a.corpus)
    docs = json.loads((corpus / "docs.json").read_text())
    items = list(docs.values())[: a.limit or None]
    pin, pout = next((v for k, v in PRICES.items() if a.model.startswith(k)), (3.0, 15.0))
    pin, pout = pin / 2, pout / 2  # batch discount
    out_path = corpus / llm_file("all", a.model)
    state_path = corpus / f"batch_{out_path.stem}.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {"model": a.model, "mode": "all", "batch": True, "tables": {}}
    state = json.loads(state_path.read_text()) if state_path.exists() else {"batches": [], "jobs": {}}

    # 1. build requests for tables not yet done or submitted
    submitted = {j["key"] for j in state["jobs"].values()}
    jobs, requests, chars = [], [], 0
    bar = Progress(len(items), "papers")
    for meta in items:
        pmcid = meta["pmcid"]
        root = parse_xml((corpus / "xml" / f"{pmcid}.xml").read_bytes())
        for tid, caption, foot, kind, payload in tables(root):
            key = f"{pmcid}|{tid}"
            if key in out["tables"] or key in submitted:
                continue
            targets = table_targets(meta["targets"], caption + " " + foot, payload)
            desc = "; ".join(f"{k} = {TARGETS[k].name} (UniProt {TARGETS[k].uniprot})" for k in targets)
            head = f"Paper {pmcid}, table {tid}.\nCaption: {caption}\nFootnotes: {foot or '(none)'}\n"
            if kind == "xml":
                content = [{"type": "text", "text": head + "Table rows (cells separated by ' | ', header rows first):\n" + payload}]
            elif a.estimate:
                content = [{"type": "text", "text": head + "x" * 6000}]  # an image table costs roughly this much
            else:
                imgs = [d for d in (get_image(corpus, pmcid, h) for h in payload) if d]
                if not imgs:
                    out["tables"][key] = {"kind": kind, "error": "image not downloadable", "values": []}
                    continue
                content = [{"type": "image", "source": {"type": "base64", "media_type": media_type(d),
                                                        "data": base64.b64encode(d).decode()}} for d in imgs]
                content.append({"type": "text", "text": head + "The table is shown in the image(s) above."})
            cid = f"t{len(state['jobs']) + len(jobs)}"
            jobs.append((cid, {"key": key, "kind": kind, "targets": targets,
                               "grounding": normalise(payload) if kind == "xml" else None}))
            params = {"model": a.model, "max_tokens": 8000, "system": SYSTEM.format(targets=desc), "tools": [TOOL],
                      "tool_choice": {"type": "tool", "name": "record_values"},
                      "messages": [{"role": "user", "content": content}]}
            requests.append({"custom_id": cid, "params": params})
            chars += len(json.dumps(params))
        bar.step(pmcid)
    est_in = chars / 4  # rough chars-per-token; benchmark runs averaged ~250 output tokens per table
    est = est_in / 1e6 * pin + len(requests) * 300 / 1e6 * pout
    print(f"{len(requests)} new tables from {len(items)} papers; estimated cost with {a.model} (batch): ~${est:.2f}")
    if a.estimate:
        return

    import anthropic
    client = anthropic.Anthropic()
    # 2. submit in chunks
    if requests:
        chunk, size, n_sub = [], 0, 0
        for (cid, job), req in zip(jobs, requests):
            s = len(json.dumps(req))
            if chunk and (size + s > CHUNK_BYTES or len(chunk) >= CHUNK_REQUESTS):
                b = client.messages.batches.create(requests=chunk)
                state["batches"].append(b.id); n_sub += len(chunk); chunk, size = [], 0
            chunk.append(req); size += s
        if chunk:
            b = client.messages.batches.create(requests=chunk)
            state["batches"].append(b.id); n_sub += len(chunk)
        state["jobs"].update(dict(jobs))
        state_path.write_text(json.dumps(state))
        out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"Submitted {n_sub} tables in {len(state['batches'])} batch(es); usually done within an hour, at most 24 h.")

    # 3. wait
    usage = out.setdefault("usage", {"input_tokens": 0, "output_tokens": 0})
    pending = [b for b in state["batches"] if b not in state.get("collected", [])]
    total = sum(1 for j in state["jobs"].values() if j["key"] not in out["tables"])
    t0 = time.time()
    while pending:
        done = 0
        infos = [client.messages.batches.retrieve(b) for b in pending]
        for i in infos:
            c = i.request_counts
            done += c.succeeded + c.errored + c.canceled + c.expired
        el = int(time.time() - t0)
        frac = done / max(total, 1)
        sys.stderr.write(f"\r[{'#' * int(24 * frac):24s}] {done}/{total} tables processed · {frac:4.0%} · "
                         f"waiting {el // 60}m {el % 60:02d}s ")
        sys.stderr.flush()
        if all(i.processing_status == "ended" for i in infos):
            sys.stderr.write("\n")
            break
        time.sleep(30)

    # 4. collect
    for b in pending:
        for r in client.messages.batches.results(b):
            job = state["jobs"].get(r.custom_id)
            if not job:
                continue
            if r.result.type != "succeeded":
                out["tables"][job["key"]] = {"kind": job["kind"], "error": r.result.type, "values": []}
                continue
            msg = r.result.message
            usage["input_tokens"] += msg.usage.input_tokens
            usage["output_tokens"] += msg.usage.output_tokens
            call = next((c for c in msg.content if c.type == "tool_use"), None)
            values = [v for v in (call.input.get("values", []) if call else [])
                      if v.get("target") in job["targets"] and not header_conflict(v["target"], v.get("column_header", ""))
                      and unit_ok(v)]
            for v in values:
                v["value_nm"] = v["value"] * TO_NM[v["unit"]]
                v["grounded"] = (normalise(v["value_text"]) in job["grounding"]) if job["grounding"] is not None else None
            out["tables"][job["key"]] = {"kind": job["kind"], "values": values, "stop_reason": msg.stop_reason}
        state.setdefault("collected", []).append(b)
        state_path.write_text(json.dumps(state))
        out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    cost = usage["input_tokens"] / 1e6 * pin + usage["output_tokens"] / 1e6 * pout
    out["cost_usd"] = round(cost, 4)
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    vals = [v for t in out["tables"].values() for v in t["values"]]
    papers = {k.split("|")[0] for k, t in out["tables"].items() if t["values"]}
    by_t = {}
    for v in vals:
        by_t[v["target"]] = by_t.get(v["target"], 0) + 1
    print(f"Done: {len(vals)} values from {len(papers)} papers; ungrounded (XML): "
          f"{sum(1 for v in vals if v.get('grounded') is False)}; cost ${cost:.2f} -> {out_path}")
    print("per enzyme:", dict(sorted(by_t.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
