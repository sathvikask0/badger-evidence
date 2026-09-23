# Public hCA II demonstration corpus

The integration files are `sources/` (10 unmodified JATS XML articles), `manifest.json` (metadata, attribution, license, original download URL, SHA-256), and `gold.json` (102 provisional reference measurements). Files outside `sources/` include research scratch material and should not be treated as part of the corpus.

## Selection and licensing

All 10 included articles are marked `research-article` in their JATS XML, contain human carbonic anhydrase II inhibitor measurements in machine-readable tables, and include an explicit Creative Commons Attribution 4.0 license in `article-meta/permissions`. Original XML includes attribution and full license text. The manifest preserves author names, copyright statements, DOI, source links, and license text. All were downloaded from the Europe PMC fullTextXML endpoint. Source articles remain under CC BY 4.0, separately from application code. Any transformed tables should acknowledge these sources and state that formatting/normalization was changed.

Selection is deliberately narrow and convenient: a small open-access corpus with readable tables and repeated assay families. It cannot establish general extraction performance across biology, proprietary spreadsheets, scanned PDFs, supplementary figures, or compound structures. Several articles share laboratories and assay approaches; this is not an independent cross-domain benchmark.

## Reference annotation

`gold.json` contains all reported numeric hCA II measurements from seven complete table columns, including reference inhibitors and four lower bounds. There are 102 numeric records and eight separately listed `NA` entries. A separate corpus-curation agent transcribed the source table row text before seeing application-extractor output. The serialization script only contains typed labels and values; it does not parse XML or call the extractor.

This is agent-transcribed reference data pending scientist review, not human-validated gold, independent adjudication, or a held-out evaluation. The score is useful as a regression check. It should never be described as validated scientific accuracy. To make a real held-out test, a scientist should correct/adjudicate these annotations and add unseen papers that were not used to develop the parser.

Evaluation scopes identify complete hCA II columns, so missed rows and spurious numeric records can count. Expected `NA` values must not become zero potency. Reference labels (`AAZ`, `AZM`, `Acetazolamide`) remain exactly article-local; the same label across papers does not imply the same independently measured experiment. Compound labels such as `1a` and `2b` are not standardized chemical identities.

The reference values retain Ki versus IC50 and nM versus uM. `=` records are point estimates, not claims of exact experimental certainty. Bounds stay bounds. Gold scoring covers central values only; reported uncertainty should remain available in evidence and is not scored here.

## Table layouts and interpretation

| Article | Principal activity table | Important characteristics |
|---|---|---|
| PMC8308639 | pharmaceuticals-14-00693-t002 | Ki nM; 22 rows including 9 controls; `mean ± error`; structure images in separate cells; selectivity ratios are not potency. |
| PMC8955975 | pharmaceuticals-15-00316-t002 | Ki nM; 12 rows; header spells target `hCAII`; next table is microbial enzymes and must be excluded. |
| PMC8196973 | ijms-22-05482-t001 | IC50 nM; 25 rows; endpoint/unit in each isoform header; uncertainty in cells; TPSA column is not potency; `AZM` control label. |
| PMC10222120 | molecules-28-04020-t001 | Ki nM; 13 rows; headers append `(α-CA)` and `(β-CA)`; human and mycobacterial enzymes coexist. |
| PMC8541628 | ijms-22-11119-t001 | Ki nM; 16 rows; four descriptive columns precede isoforms; headers say `CA II`, with human context in caption. Table 2 contains selectivity ratios. |
| PMC8150913 | ijms-22-05082-t001 | Ki nM; two side-by-side repeated compound/isoform blocks; 20 unique experimental compound labels plus control AAZ duplicated in both blocks; uncertainty. Avoid silently treating duplicate control as independent evidence. |
| PMC8910009 | ijms-23-02540-t002 | Ki nM; 16 rows; two-tier header; Table 1 is chemical synthesis and structures, not activity. |
| PMC7736042 | T2 | IC50 uM; bovine and human two-tier header groups; only 9 human numeric IC50 values, 8 `NA`; percentage inhibition at 0.5 mM is a different endpoint. |
| PMC8344263 | t0001 and t0002 | Ki uM with selectivity ratios appended in brackets; footnote cross-references in compound labels; lower bounds; reference compound rows use merged cells. Table 2 repeats some Table 1 values and includes previously published comparators. Preserve table-level provenance. |
| PMC9930818 | t0001 | Ki nM; 11 rows; `>100 000` includes a thin space; four hCA II lower bounds. |

## Assay context

Preserve original methods passages rather than implying universal conditions. In particular:

- Most Ki tables use stopped-flow CO2 hydration assays. The two IC50 papers PMC8196973 and PMC7736042 describe nitrophenyl-acetate esterase assays. Neither a unit conversion nor a shared target makes these measurements interchangeable.
- PMC10222120 describes six-hour preincubation. Several others use 15 minutes. Its alpha-class buffer is pH 7.5 while beta-class is pH 8.4.
- PMC8955975 describes pH 7.4 for alpha-class enzymes and pH 8.3 for beta/gamma enzymes. A parser taking the last pH would assign the wrong condition to hCA II.
- PMC7736042 includes both human and bovine CA-II. Its methods paragraph contains explicit bovine-enzyme details; retain that limitation instead of assigning every phrase to the human result.
- Controls and comparator values may be reused from cited work. Records represent reported observations in a source table, not a guarantee of a new independent experiment.
- This corpus does not resolve chemical structures to SMILES/InChI or validate the underlying experiments.

## Additional source spot-checks

During development, the corpus-curation agent separately compared these nongold rows with the original JATS cells. These are limited checks, not a substitute for scientist review or extra benchmark labels:

- PMC8308639, `pharmaceuticals-14-00693-t002`: compound `1` is Ki 13 ± 0.9 nM; compound `13` is Ki 2.4 ± 0.1 nM. The footnote calls uncertainty the standard error from three assays.
- PMC8150913, `ijms-22-05082-t001`: compound `5a` in the left block is Ki 35.1 ± 3.3 nM; compound `6k` in the right block is Ki 91.6 ± 7.0 nM. `AAZ` at 12.1 ± 0.6 nM is printed twice, once per block, and is duplicated presentation rather than evidence of two independent measurements.
- PMC8344263, `t0001`: compound `8` is Ki 13.0 µM; `AAZ` is Ki 0.012 µM. The latter is repeated in `t0002`. Compound `1` is 41.2 µM with a separate selectivity ratio of 85.8; parsing that cell conservatively as unresolved is preferable to confusing the ratio with potency. Compound `16a` has Ki 0.0052 µM and a separate ratio 9.45, and footnote `c` identifies its data as coming from reference 15. The `VIa–d` comparators in `t0002` are likewise attributed to reference 16. Retain the original table link and footnotes when displaying these records.

Two methods locators require care. PMC7736042 has `In-vitro Assay Protocol` inside `Experimental` (parent section `s2`); the nested assay section lacks an XML ID. PMC8541628 section `sec3dot2-ijms-22-11119`, `3.2. Biological Evaluation`, says the CA stopped-flow procedures are described in cited references and Supporting Materials. Main-article results prose alone does not establish complete assay conditions for that paper.
