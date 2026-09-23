"""Versioned offline build and filtered, spreadsheet-safe CSV export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from . import __version__
from .extract import extract_article

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def build_dataset(data_dir: Path = DATA) -> dict:
    manifest_bytes = (data_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    entries = manifest if isinstance(manifest, list) else manifest["articles"]
    dataset = {"schema_version": 1, "extractor_version": __version__, "articles": [], "records": [], "tables": [], "skipped": []}
    seen = set()
    for entry in entries:
        pmcid = entry["pmcid"]
        if pmcid in seen:
            raise ValueError(f"Duplicate article {pmcid}")
        seen.add(pmcid)
        filename = entry.get("filename", pmcid + ".xml")
        if Path(filename).name != filename or not filename.endswith(".xml"):
            raise ValueError("Source filename must be a plain XML filename")
        raw = (data_dir / "source" / filename).read_bytes()
        expected = entry.get("sha256")
        if expected and hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f"Source checksum mismatch: {pmcid}")
        result = extract_article(raw, entry)
        dataset["articles"].append(result["article"])
        for key in ("records", "tables", "skipped"):
            dataset[key].extend(result[key])
    reviews_path = data_dir / "reviews.json"
    if reviews_path.exists():
        reviews = json.loads(reviews_path.read_text()).get("records", {})
        for record in dataset["records"]:
            # Informational flags that a reviewer has explicitly checked do not block review.
            if record["id"] in reviews and not set(record["flags"]) - {"missing_assay_context", "target_from_caption"}:
                record["review_status"] = reviews[record["id"]]
    from .targets import TARGETS
    counts = {}
    for record in dataset["records"]:
        counts[record["target"]] = counts.get(record["target"], 0) + 1
    dataset["targets"] = [{"key": t.key, "name": t.name, "uniprot": t.uniprot, "why": t.why, "tags": list(t.tags)}
                          for t in TARGETS.values() if counts.get(t.key)]
    # Hash the actual generated content, so code or data changes change the ID.
    content = json.dumps(dataset, sort_keys=True, ensure_ascii=False).encode()
    dataset["dataset_id"] = hashlib.sha256(content).hexdigest()[:16]
    return dataset


def filter_records(records: list[dict], query: str = "", pmcid: str = "", measurement: str = "", flagged: bool = False, target: str = "") -> list[dict]:
    query = query.casefold().strip()
    return [r for r in records if
            (not query or query in " ".join(str(r.get(k, "")) for k in ("compound_label", "pmcid", "target_name", "measurement_type")).casefold())
            and (not pmcid or r["pmcid"] == pmcid)
            and (not target or r.get("target") == target)
            and (not measurement or r["measurement_type"] == measurement)
            and (not flagged or bool(r["flags"]))]


def csv_export(records: list[dict]) -> str:
    stream = io.StringIO(newline="")
    fields = ["id", "pmcid", "compound_id", "compound_label", "target", "taxon_id", "measurement_type", "relation", "value", "unit", "normalized_value_nm", "uncertainty", "raw_value", "table_id", "row_index", "source_url", "source_sha256", "review_status", "flags", "assay_context"]
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for record in records:
        row = {k: record.get(k) for k in fields}
        row["flags"] = ";".join(record["flags"])
        row["assay_context"] = json.dumps(record.get("assay_context", []), ensure_ascii=False)
        for key, value in row.items():
            if key == "relation" and value in ("=", "<", ">", "<=", ">=", "~", None):
                continue
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                row[key] = "'" + value
        writer.writerow(row)
    return stream.getvalue()


def save_dataset(dataset: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n")
    temp.replace(output)
