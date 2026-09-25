"""Read-only local evidence browser. Bind to loopback; no credentials required."""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .evaluation import evaluate
from .notes import NOTES, render_note
from .pipeline import DATA, csv_export, filter_records

STATIC = Path(__file__).parent / "static"


def make_server(dataset: dict, data_dir: Path = DATA, port: int = 8765) -> ThreadingHTTPServer:
    gold_file = data_dir / "gold" / "annotations.json"
    report = evaluate([r for r in dataset["records"] if r.get("target") == "CA2"], json.loads(gold_file.read_text())) if gold_file.exists() else {"error": "No evaluation annotations found"}
    # Only reviewed records are shown and exported; the full extraction stays in data/generated.
    shown = [r for r in dataset["records"] if r.get("review_status") == "reviewed"]
    keep = {r["pmcid"] for r in shown}
    dataset = {**dataset, "records": shown, "articles": [a for a in dataset["articles"] if a["pmcid"] in keep]}
    sources = {a["pmcid"]: a.get("filename", a["pmcid"] + ".xml") for a in dataset["articles"]}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def respond(self, body: bytes, content_type: str, status: int = 200, filename: str | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def json(self, value, status=200):
            self.respond(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/api/dataset":
                return self.json(dataset)
            if url.path == "/api/evaluation":
                return self.json(report)
            if url.path == "/api/export.csv":
                params = parse_qs(url.query)
                get = lambda k: params.get(k, [""])[0]
                records = filter_records(dataset["records"], get("q"), get("pmcid"), get("measurement"), get("flagged") == "1", get("target"))
                return self.respond(csv_export(records).encode("utf-8-sig"), "text/csv; charset=utf-8", filename="badger-evidence.csv")
            chembl = re.fullmatch(r"/api/chembl/([A-Z0-9]+)\.json", url.path)
            if chembl and (data_dir / "chembl" / f"{chembl[1]}.json").exists():
                return self.respond((data_dir / "chembl" / f"{chembl[1]}.json").read_bytes(), "application/json; charset=utf-8")
            match = re.fullmatch(r"/api/source/(PMC\d+)\.xml", url.path)
            if match and match[1] in sources:
                raw = (data_dir / "source" / sources[match[1]]).read_bytes()
                return self.respond(raw, "application/xml; charset=utf-8", filename=match[1] + ".xml")
            note = re.fullmatch(r"/notes/([a-z0-9-]+)\.html", url.path)
            if note and (NOTES / f"{note[1]}.md").exists():
                return self.respond(render_note(NOTES / f"{note[1]}.md").encode(), "text/html; charset=utf-8")
            assets = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/stats.js": ("stats.js", "text/javascript"), "/style.css": ("style.css", "text/css"), "/favicon.svg": ("favicon.svg", "image/svg+xml"), "/findings.html": ("findings.html", "text/html"), "/notes.html": ("notes.html", "text/html")}
            if url.path in assets:
                name, mime = assets[url.path]
                return self.respond((STATIC / name).read_bytes(), mime + "; charset=utf-8")
            return self.json({"error": "Not found"}, 404)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
