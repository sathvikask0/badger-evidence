"""Run with python -m badger_evidence. All default operations work offline."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from .evaluation import evaluate
from .pipeline import DATA, build_dataset, csv_export, save_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description="Badger Evidence — biological evidence from open papers")
    parser.add_argument("command", choices=("build", "serve", "evaluate", "fetch", "site"), nargs="?", default="serve")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "fetch":
            manifest = json.loads((args.data_dir / "manifest.json").read_text())
            entries = manifest if isinstance(manifest, list) else manifest["articles"]
            (args.data_dir / "source").mkdir(parents=True, exist_ok=True)
            for article in entries:
                pmcid = article["pmcid"]
                filename = article.get("filename", pmcid + ".xml")
                if not re.fullmatch(r"PMC\d+", pmcid) or Path(filename).name != filename:
                    raise ValueError("Invalid manifest identifier or filename")
                destination = args.data_dir / "source" / filename
                if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == article["sha256"]:
                    print(f"{pmcid}: cached source matches")
                    continue
                url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
                with urlopen(Request(url, headers={"User-Agent": "BadgerEvidence/0.1 (research POC)"}), timeout=45) as response:
                    raw = response.read(20_000_001)
                if hashlib.sha256(raw).hexdigest() != article["sha256"]:
                    raise ValueError(f"{pmcid}: remote content changed; existing snapshot preserved. Review before updating manifest.")
                destination.write_bytes(raw)
                print(f"{pmcid}: downloaded and verified")
            return 0
        dataset = build_dataset(args.data_dir)
        if args.command == "build":
            save_dataset(dataset, args.data_dir / "generated" / "dataset.json")
            (args.data_dir / "generated" / "records.csv").write_text(csv_export(dataset["records"]), encoding="utf-8-sig")
            print(f"Built {dataset['dataset_id']}: {len(dataset['articles'])} papers, {len(dataset['records'])} records")
        elif args.command == "evaluate":
            gold = json.loads((args.data_dir / "gold" / "annotations.json").read_text())
            result = evaluate([r for r in dataset["records"] if r.get("target") == "CA2"], gold)
            output = args.data_dir / "generated" / "evaluation.json"
            save_dataset(result, output)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            checks = ("false_positives", "false_negatives", "unexpected_abstentions", "unreported_missing_values", "fabricated_missing_values")
            return 0 if all(result[key] == 0 for key in checks) else 1
        elif args.command == "site":
            from .site import build_site
            out = build_site(dataset, Path("site"), args.data_dir)
            print(f"Static site written to {out}/", flush=True)
            return 0
        else:
            from .server import make_server
            server = make_server(dataset, args.data_dir, args.port)
            print(f"Badger Evidence: http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
        return 0
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
