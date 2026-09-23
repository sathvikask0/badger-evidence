# Badger Evidence

A proof of concept for Badger Bioworks: turn public biological papers into a searchable, source-linked dataset of enzyme inhibitor measurements.

The dataset covers **145 open-access (CC BY) papers across 31 enzymes**, with a focus on longevity and brain ageing. Pick an enzyme from the Enzyme dropdown on the site; each one shows why it matters. Highlights:

| Target | Why it's here |
| --- | --- |
| mTOR kinase | Rapamycin's target, the best-validated longevity drug in animals |
| SIRT1, SIRT2 | NAD+-dependent sirtuins linked to caloric restriction and ageing |
| Human acetylcholinesterase | Alzheimer's-disease drug target (brain ageing) |
| Human carbonic anhydrase II | The original, most thoroughly benchmarked set |
| EGFR kinase (wild type) | Mature drug-target reference set |

It preserves compound labels, Ki and IC50 measurements, units, qualifiers, table evidence, and article-level assay context. Every record points back to an exact source table and a versioned XML snapshot. Target matching rules live in `badger_evidence/targets.py` and deliberately reject look-alikes (eel vs. human AChE, mutant vs. wild-type EGFR, cell-line vs. enzyme assays, docking predictions).

## Run locally

Requires Python 3.11 or newer. No packages, paid model keys, accounts, or network access are needed to run the bundled demo.

```sh
python3 -m badger_evidence serve
```

Open **http://127.0.0.1:8765**. Search or filter the table, select a measurement to inspect its evidence, and download the filtered CSV. The server listens only on your computer. Stop it with Ctrl+C.

## Public site

A static copy showing only reviewed records is deployed to GitHub Pages on every push to `main` (`.github/workflows/pages.yml`). Build it locally with `python3 -m badger_evidence site`, which writes `site/`.

## Rebuild and test

```sh
python3 -m unittest discover -v
python3 -m badger_evidence build
python3 -m badger_evidence evaluate
```

The build writes `data/generated/dataset.json` and `records.csv`. Evaluation writes `data/generated/evaluation.json` and exits unsuccessfully if numeric predictions differ from the scoped reference annotations. GitHub Actions runs the same checks on Python 3.11–3.14.

To recover missing source files from Europe PMC:

```sh
python3 -m badger_evidence fetch
```

Downloads must match the committed source checksums. Changed remote articles require explicit review and a new manifest version; fetching never silently accepts changed evidence.

## What this first version does

- Reads real structured article tables (JATS XML), including merged headers and repeated column groups.
- Separates human from bovine CA-II and other CA isoforms.
- Keeps **Ki and IC50 distinct**, preserves inequalities and reported uncertainty, and converts concentration units to nM without changing the endpoint.
- Retains the source cell, header, row, caption, footnotes, source link, source hash, and assay passages.
- Flags missing or ambiguous values instead of inventing a number. Repeated measurements are retained with a flag, not silently pooled.
- Provides search, paper and endpoint filters, evidence inspection, and filtered CSV export.
- Compares extraction with 102 independently agent-transcribed numeric reference records and eight missing-value annotations across seven complete target columns.

## Scientific limits

This is a **deterministic extraction baseline**, not a deployed multi-agent bioinformatician. It currently supports CA2 columns in structured JATS tables. Arbitrary PDFs, image-only tables, chemical structure recognition, automatic molecule linking, and prose-based extraction are not implemented.

All extracted records remain **unreviewed**. The reference annotations were transcribed by a separate AI agent before evaluation; they have not been validated by a scientist, and this corpus is a development regression set, not a held-out generalization benchmark. Agreement with these annotations does not establish scientific correctness.

Compound labels such as `1a` are local to a paper, not globally resolved chemical identities. `PMC…:1a` is a scoped label, not a chemical registry identifier. Do not merge compounds across papers by label.

Assay passages are article-level evidence, not automatically assigned structured conditions. The corpus contains different assays, incubation durations, species, and buffers. Ki and IC50, CO₂ hydration and esterase assays, and incomparable experimental conditions must not be pooled. Values with appended selectivity ratios are retained as raw evidence and withheld from numeric normalization for review. The uncertainty field preserves the reported ± number in the original unit; it does not infer SD versus SEM.

The useful next experiment is scientist correction of the annotations, followed by a frozen, unseen paper set. A model-assisted extractor can then be compared against this baseline through the same evidence contract and tests.

## Repository map

```text
badger_evidence/       Extraction, evaluation, local server, browser interface
data/manifest.json    Article metadata, licences, retrieval dates, source hashes
data/source/          Ten unmodified CC BY 4.0 article XML snapshots
data/gold/            Provisional reference annotations and evaluation scopes
data/generated/       Reproducible dataset, CSV, and evaluation report
tests/                Scientific edge cases, regression, integrity, HTTP checks
docs/                 Corpus notes and validation record
```

Source articles retain their original **CC BY 4.0** licences. See [source attribution](data/SOURCE_ATTRIBUTION.md) for author credits and article links, and [corpus notes](docs/CORPUS_NOTES.md) for caveats. No open-source licence for the application code has been selected yet.

Data provider: [Europe PMC full-text service](https://europepmc.org/RestfulWebService).
