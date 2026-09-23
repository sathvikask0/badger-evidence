---
license: other
license_name: mixed-cc-by-4.0-and-cc-by-sa-3.0
pretty_name: Badger Evidence — kinase potency (v0.1)
tags: [chemistry, biology, drug-discovery, bioactivity, kinase, longevity, provenance]
task_categories: [tabular-regression]
size_categories: [10K<n<100K]
configs:
  - config_name: papers
    data_files: papers.parquet
---

# Badger Evidence — kinase potency, v0.1

Enzyme-inhibition measurements (IC50, Ki, Kd) with chemical structures, for 16 kinases
central to ageing biology (MTOR, PI3KA, GSK3B, JAK2, P38A, IGF1R, EGFR, CDK2, CDK4, CDK5, CSNK1D, DYRK1A, LRRK2, ROCK1, ROCK2, TGFBR1). Built for training and benchmarking
potency models, with provenance on every row.

## Two configs, two licences

| config | rows | licence | what it is |
|---|---|---|---|
| `papers` | 144 | **CC BY 4.0** | Values extracted by this project from open-access papers, each linked to the exact table cell. |

Keep them separate if licence matters to you: CC BY-SA is share-alike.

## What is new here

The `papers` rows come from 30 CC BY open-access papers, mostly from journals ChEMBL does not curate
(in this project, 190 of 191 source papers were absent from ChEMBL). Every value keeps its PMCID, table id,
row index, source URL and a SHA-256 of the source XML, so any row can be checked against the paper.

## How structures were obtained (`papers`)

| method | rows |
|---|---|
| opsin_name_formula_verified | 83 |
| chembl_name_match | 61 |

* `opsin_name_formula_verified`: the compound's systematic name was found next to its label (e.g. "… (5a)")
  in the paper's experimental section, converted with OPSIN, standardised (largest fragment, neutralised),
  and **accepted only if its formula matches the formula the paper states** (HRMS or elemental analysis;
  M, [M+H]+, [M−H]−, [M+Na]+, [M+K]+ allowed).
* `chembl_name_match`: named reference compounds (e.g. olaparib) matched to ChEMBL by exact name or synonym.
* Values whose compound could not be resolved to a structure are **not included** (462 such values
  are in the Badger Evidence repository without structures).

## Columns (shared)

`smiles` (RDKit canonical, neutral parent) · `inchikey` · `scaffold` (Bemis–Murcko) · `split` · `target` ·
`uniprot` · `target_name` · `endpoint` (IC50/Ki/Kd, never mixed) · `relation` (=, <, >, …) · `value_nm` ·
`p_value` (9 − log10 nM, only for exact `=` values). `papers` adds `pmcid`, `doi`, `table_id`, `row_index`,
`source_url`, `source_sha256`, `compound_label`, `structure_method`, `review`. `chembl` adds `activity_id`,
`assay_chembl_id`, `assay_description`, `assay_type`, `document_chembl_id`, `doi`, `pchembl_value`,
`data_validity_comment`.

## Splits

Scaffold split: each Bemis–Murcko scaffold is hashed to train (80%), valid (10%) or test (10%), so a chemotype
never appears in two splits and assignments are stable across releases. Splits are shared between configs.

## Rows per target (`papers`)

| target | rows |
|---|---|
| DYRK1A | 44 |
| JAK2 | 26 |
| TGFBR1 | 12 |
| CDK2 | 10 |
| PI3KA | 9 |
| ROCK1 | 8 |
| MTOR | 7 |
| EGFR | 7 |
| CSNK1D | 7 |
| GSK3B | 5 |
| CDK5 | 4 |
| P38A | 3 |
| IGF1R | 1 |
| ROCK2 | 1 |

## Quality and known limits

* **Paper values are AI-checked, not scientist-validated.** Each was compared against its source table cell;
  tables were read to exclude cell assays, animal enzymes, mutant EGFR, docking scores, % inhibition,
  pIC50, selectivity ratios and review tables. Independent audit is pending.
* **Assay conditions are not normalised.** IC50 depends on ATP/substrate concentration and enzyme construct.
  Compare values across papers with care; `endpoint` is never mixed, bounds are kept as `relation`.
* **Structure coverage is partial** (see counts above): many papers give names only in supplementary files or
  structures only as drawings. Supplementary-file and image-to-structure extraction are next.
* Cross-check: where the same paper and compound appear in ChEMBL, 18 of 18 comparable values agree.

## Citation and sources

Source papers: see `data/SOURCE_ATTRIBUTION.md` in the Badger Evidence repository (each row has its PMCID/DOI).
ChEMBL: Zdrazil et al., *Nucleic Acids Research* 2024 (ChEMBL 37, EMBL-EBI).
Name-to-structure: OPSIN (Lowe et al., *J. Chem. Inf. Model.* 2011). Standardisation: RDKit.
