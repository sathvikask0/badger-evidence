# mTOR / PI3Kα benchmark — adjudication and error analysis

Benchmark: 21 open-access papers that ChEMBL 37 curated for mTOR (CHEMBL2842) or PI3Kα (CHEMBL4005);
224 exact ChEMBL values (pChEMBL present) as reference. Fetched with `tools/bench_fetch.py`,
scored with `tools/bench_eval.py` (match = same paper, target and endpoint; within 2% or equal at 2 s.f.).

## Results

| run | extracted | matched | precision | recall |
|---|---|---|---|---|
| first run | 127 | 74 | 58.3% | 33.0% |
| after scoring fix (bounds such as ">10 000" are not scored: ChEMBL's pChEMBL set is exact values only) | 119 | 106 | 89.1% | 47.3% |
| after 3 extractor fixes found by this benchmark | 127 | 112 | 88.2% | 50.0% |

Extractor fixes found by the benchmark (all generic, none paper-specific; the CA2 regression set still scores 100%):
1. `Kiapp` / `Ki,app` headers were not recognised as Ki.
2. A compound column headed `comp. name` / `Name` was not recognised.
3. An unlabelled first column of short unique identifiers ("2", "3", "7a") was not recognised as the compound column.

## Adjudicated precision: 127 / 127

All 15 extracted values that did not match ChEMBL were traced to their source cells:
* 12 are reference or previously published compounds in the paper's table that ChEMBL did not record for
  this document (PMC8128076 compounds 1, 5, 12b; PMC6792169 compounds 1–3, where ChEMBL curated a
  different, image-only table).
* 3 are the same compound (53, PMC11284801) reported again in a second table; ChEMBL records it once.
None is a transcription error. Precision against ChEMBL (88%) therefore understates correctness; it measures
agreement with ChEMBL's curation choices.

## Why recall is 50%: what a table extractor cannot reach

| reason | papers | ChEMBL values |
|---|---|---|
| no table in the XML (values in text, figures or SI) | 5 | 18 |
| tables published as images | 4 | 22 |
| tables unrelated to potency (reviews, clinical-trial lists; ChEMBL curated from text) | 4 | 4 |
| unsupported layouts: transposed tables (targets as rows), isoform headers split across rows ("α" + "(WT)") | 3 | ~20 |
| reachable and extracted | 5 | 112 |

The largest remaining gains are therefore image-table OCR and text/SI extraction, not table parsing.
Caveat: 21 papers, one target family; reference is ChEMBL's curation, not independent ground truth.
