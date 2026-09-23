"""Build a static copy of the explorer (reviewed records only) for GitHub Pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .evaluation import evaluate
from .pipeline import DATA

STATIC = Path(__file__).resolve().parent / "static"


def build_site(dataset: dict, output: Path, data_dir: Path = DATA) -> Path:
    gold_file = data_dir / "gold" / "annotations.json"
    report = evaluate([r for r in dataset["records"] if r.get("target") == "CA2"], json.loads(gold_file.read_text())) if gold_file.exists() else {"error": "No evaluation annotations found"}
    records = [r for r in dataset["records"] if r.get("review_status") == "reviewed"]
    keep = {r["pmcid"] for r in records}
    shown = {**dataset, "records": records, "articles": [a for a in dataset["articles"] if a["pmcid"] in keep]}
    if output.exists():
        shutil.rmtree(output)
    (output / "api" / "source").mkdir(parents=True)
    for name in ("app.js", "style.css", "favicon.svg"):
        shutil.copy(STATIC / name, output / name)
    html = (STATIC / "index.html").read_text()
    html = html.replace("<head>", '<head>\n    <meta name="static-site" content="1">', 1)
    (output / "index.html").write_text(html)
    (output / "api" / "dataset").write_text(json.dumps(shown, ensure_ascii=False))
    (output / "api" / "evaluation").write_text(json.dumps(report, ensure_ascii=False))
    for article in shown["articles"]:
        name = article.get("filename", article["pmcid"] + ".xml")
        shutil.copy(data_dir / "source" / name, output / "api" / "source" / (article["pmcid"] + ".xml"))
    (output / ".nojekyll").write_text("")
    return output
