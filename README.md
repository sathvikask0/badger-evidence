# Badger Evidence

A proof of concept for Badger Bioworks: turn public biological papers into a searchable, source-linked dataset of enzyme inhibitor measurements.

**Live site:** https://sathvikask0.github.io/badger-evidence/  
**Write-up** (what's hard about AI extraction of bioactivity data): https://badger-bioactivity-extraction.sathvik-avas-4796.chatgpt.site/  
**MCP server:** [docs/MCP.md](docs/MCP.md)

The dataset covers **191 open-access (CC BY) papers across 48 enzymes**, with a focus on longevity and brain ageing. Pick an enzyme from the Enzyme dropdown on the site; each one shows why it matters. Highlights:

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

## ChEMBL layer

`data/chembl/<TARGET>.json` holds ChEMBL 37 activities for every enzyme in the registry (IC50/Ki/Kd in nM with a pChEMBL value; about 279,000 values across 55 targets). They load on demand when you pick an enzyme and set **Source** to include ChEMBL; enzymes with no paper-verified values (e.g. CD38, NNMT) open straight on ChEMBL. They are clearly labelled as database values: they link to their paper and ChEMBL record, not to a table cell, and are not reviewed by this project.

**Cross-check.** Comparisons require a name-linked ChEMBL molecule identity, the same DOI, target and endpoint, and exact (`=`), unflagged ChEMBL values in nM. Missing identity or coverage is excluded rather than counted as disagreement. Agreement means within 2% or the same value rounded to two significant figures; it does not establish matching assay conditions or scientific validity. The UI computes the current comparable count from the dataset.

**Compound identity.** Named compounds in papers (reference drugs like olaparib or donepezil, 117 names) are linked to ChEMBL molecules by exact name or synonym, with InChIKey, SMILES and a structure image. Their detail panel shows how the paper's value compares with all ChEMBL values for the same compound on the same enzyme. Numbered compounds ("5a") are paper-local and are not matched.

ChEMBL data: Zdrazil et al., *Nucleic Acids Res.* 2024; EMBL-EBI, licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Files in `data/chembl/` and `data/compound_ids.json` stay under that licence.

## MCP server

`badger_evidence/mcp_server.py` exposes the dataset to Claude and other MCP clients (six tools: search, evidence, summaries, compound profiles). Every answer carries a citation to a table cell or ChEMBL record. Setup: [docs/MCP.md](docs/MCP.md).

## Extraction benchmark: rules vs Claude

`tools/bench_fetch.py` builds a benchmark from open-access papers that ChEMBL has curated (ChEMBL values as reference). `tools/llm_extract.py` extracts values with Claude (XML tables as text, image tables as images, structured JSON output, grounding and header-conflict checks). `tools/bench_eval.py` scores exact values against ChEMBL for the rule extractor, Claude, or a hybrid.

45 papers, 5 targets (mTOR, PI3Kα, GSK-3β, JAK2, PARP1), 408 exact ChEMBL values:

| method | extracted | matched ChEMBL | precision | recall | cost |
|---|---|---|---|---|---|
| rules | 166 | 151 | 91.0% | 37.0% | $0 |
| hybrid (Claude on image tables only) | 263 | 233 | 88.6% | 57.1% | ~$0.50 |
| Claude on every table | 313 | 283 | 90.4% | 69.4% | $1.65 |

Every disagreement was traced back to the paper; see [bench/LLM_COMPARISON.md](bench/LLM_COMPARISON.md), [bench/SUMMARY.md](bench/SUMMARY.md) and the `ADJUDICATION.md` files per benchmark.

Cheaper models on the same 45 papers (raw precision / recall, both benchmarks):

| model | precision | recall | cost |
|---|---|---|---|
| Sonnet 4.5 | 87–97% | 54–82% | $1.65 |
| **Sonnet 5** (used for scale-up) | 87–100% | 54–80% | **$1.12** |
| Haiku 4.5 | 60–72% | 51–54% | $0.62 |

Haiku is cheaper but loses 15–38 points of precision and breaks the output schema (e.g. Greek μ for µ).

```sh
python3 tools/bench_fetch.py --targets MTOR PI3KA --max-docs 150    # needs internet; standard library only
export ANTHROPIC_API_KEY=...                                         # never commit or paste this
uv run --with anthropic tools/llm_extract.py bench/mtor_pi3ka --mode all
python3 tools/bench_eval.py bench/mtor_pi3ka --method rules|llm|hybrid
sh tools/compare_models.sh                                           # Haiku 4.5 and Sonnet 5 on both benchmarks
```

### Scale-up

`tools/discover.py` finds new CC BY papers with potency tables in Europe PMC (per enzyme, skipping papers already in the atlas); `tools/scale_extract.py` extracts them with Sonnet 5 through the Message Batches API (half price, runs server-side, resumable). First run: 397 papers, 1,511 tables, about $4–7.

```sh
python3 tools/discover.py --name scale1 --per-target 40
uv run --with anthropic tools/scale_extract.py corpus/scale1 --estimate   # cost estimate, no API calls
uv run --with anthropic tools/scale_extract.py corpus/scale1              # submit, wait, collect (re-run to resume)
```

## Generalization: do models trained on ChEMBL work on new papers?

Almost none of the atlas papers are in ChEMBL (1 of 191), so their values are data public models have not seen. `bench/generalization/paper_test.json` holds 401 exact IC50/Ki values with known structures (97 papers, 25 enzymes). Models are trained on ChEMBL for the same enzymes, excluding every test paper, and scored on ChEMBL's own held-out split and on the paper values, separately for compounds ChEMBL has and has not seen.

Models: a per-enzyme mean baseline, a random forest on Morgan fingerprints, a Chemprop D-MPNN from scratch, and Chemprop fine-tuned from [CheMeleon](https://arxiv.org/abs/2506.15792) (a GNN pre-trained on ~1M molecules). Metrics: RMSE, ranking within each paper's compound series, error vs similarity to training data, and a noise floor (the same compound measured by two labs).

```sh
python3 tools/gen_fetch.py        # needs internet: ChEMBL structures + CheMeleon weights
python3 tools/gen_data.py         # -> bench/generalization/chembl_train.csv
sh tools/generalization/run_all.sh  # trains and evaluates all four models (Apple GPU / CUDA / CPU; needs uv)
```

Results ([full write-up](bench/generalization/GENERALIZATION.md)), RMSE in log units on 215 paper values for compounds ChEMBL has never measured:

| model | ChEMBL held-out | new papers (unseen compounds) | ranking within a paper's series (ρ) |
|---|---|---|---|
| enzyme-mean baseline | 1.18 | 1.15 | — |
| random forest | 0.63 | 0.88 | 0.10 |
| D-MPNN (scratch) | 0.70 | 0.94 | 0.46 |
| CheMeleon fine-tuned | 0.63 | **0.79** | 0.40 |

Pre-training ties with a random forest on ChEMBL but wins on new papers (by 0.10, 95% CI 0.02–0.18). Error is close to the lab-to-lab noise floor (0.71), yet ranking analogs within a paper stays weak.

## ML release

`release/<family>-<version>/` holds a machine-learning-ready export (Parquet + Hugging Face dataset card). Build it with:

```sh
pip install rdkit py2opsin pyarrow        # OPSIN needs Java
python3 tools/structures.py               # resolve paper labels ("5a") to formula-verified structures -> data/structures.json
python3 tools/build_release.py kinase v0.1 [chembl_37_chemreps.txt.gz]
python3 tools/dataset_card.py kinase v0.1
```

Paper structures come from each compound's systematic name in the experimental section (OPSIN), standardised with RDKit, and are kept **only when they match the molecular formula the paper states**; named drugs are linked via ChEMBL. Splits are scaffold-based and hash-assigned, so they stay stable across releases.

## Public site

A static copy showing only reviewed records is deployed to GitHub Pages on every push to `main` (`.github/workflows/pages.yml`). Build it locally with `python3 -m badger_evidence site`, which writes `site/`.

## Rebuild and test

```sh
python3 -m unittest discover -v
node --test tests/test_stats.cjs
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

This is a **deterministic extraction baseline**, not a deployed multi-agent bioinformatician. It supports the registered targets in structured JATS tables. Arbitrary PDFs, image-only tables, chemical structure recognition, structure-based molecule resolution, and prose-based extraction are not implemented.

Paper records marked **AI-checked** retain the reviewer, date and method from `data/reviews.json`. These are AI-assisted transcription and automated consistency checks, not scientist validation. Other extracted records remain unreviewed. The reference annotations were transcribed by a separate AI agent before evaluation; they have not been validated by a scientist, and this corpus is a development regression set, not a held-out generalization benchmark. Agreement with these annotations does not establish scientific correctness.

Compound labels such as `1a` are local to a paper, not globally resolved chemical identities. `PMC…:1a` is a scoped label, not a chemical registry identifier. Do not merge compounds across papers by label.

Assay passages are article-level evidence, not automatically assigned structured conditions. The corpus contains different assays, incubation durations, species, and buffers. Ki and IC50, CO₂ hydration and esterase assays, and incomparable experimental conditions must not be pooled. Values with appended selectivity ratios are retained as raw evidence and withheld from numeric normalization for review. The uncertainty field preserves the reported ± number in the original unit; it does not infer SD versus SEM.

The useful next experiment is scientist correction of the annotations, followed by a frozen, unseen paper set. A model-assisted extractor can then be compared against this baseline through the same evidence contract and tests.

## Repository map

```text
badger_evidence/       Extraction, evaluation, local server, browser interface
data/manifest.json    Article metadata, licences, retrieval dates, source hashes
data/source/          Versioned CC BY article XML snapshots
data/gold/            Provisional reference annotations and evaluation scopes
data/generated/       Reproducible dataset, CSV, and evaluation report
data/chembl/          ChEMBL 37 values per target (CC BY-SA 3.0)
data/structures.json  Paper compound labels resolved to formula-verified structures
tools/                Ingest, review, ChEMBL import, release, benchmark, Claude extractor
tools/generalization/ Model training and evaluation for the generalization experiment
bench/                Extraction benchmarks, adjudications, generalization test set
release/              Machine-learning-ready Parquet exports with dataset cards
tests/                Scientific edge cases, regression, integrity, HTTP checks
docs/                 Corpus notes and validation record
```

Source articles retain their original **CC BY 4.0** licences. See [source attribution](data/SOURCE_ATTRIBUTION.md) for author credits and article links, and [corpus notes](docs/CORPUS_NOTES.md) for caveats. See `LICENSE` for the application code licence.

Data provider: [Europe PMC full-text service](https://europepmc.org/RestfulWebService).

The potency chart requires one enzyme and one endpoint. It excludes bounds and flagged values; displayed distributions still span differing assay conditions.
