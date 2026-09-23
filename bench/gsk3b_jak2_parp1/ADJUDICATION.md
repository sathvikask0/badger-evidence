# GSK-3β / JAK2 / PARP1 benchmark — adjudication

24 open-access papers curated by ChEMBL 37 (892 ChEMBL documents with a PubMed ID; 138 in PMC; 24 open access).
184 exact ChEMBL reference values. Extractor unchanged from the mTOR/PI3Kα run (no tuning on this set).

| | extracted | matched | precision | recall |
|---|---|---|---|---|
| all | 39 | 39 | **100%** | 21.2% |

Every extracted value matches ChEMBL. No new extractor bugs were found.

## Where the 145 missed values are

| reason | ~ChEMBL values |
|---|---|
| potency tables published as images (e.g. PMC11181332: all 3 SAR tables are images) | ~80 |
| no data table in the XML: values in text, figures or structure-only tables | ~29 |
| values ChEMBL took from text/SI of a paper whose table we did extract (PMC11215726) | 17 |
| non-potency tables or reviews (clinical-trial lists, antimicrobial, PK) where ChEMBL curated a value from text | ~19 |

Note: `recall (values present in paper tables)` over-counts reachable values here, because it matches
numbers anywhere in any table (e.g. PK tables). Manual review found no reachable potency value that was missed
apart from one transposed table (compounds as columns, PMC9884089 tbl4).

## Conclusion
Table extraction is precise; recall is bounded by publishing format. The next gains require reading
image tables (OCR / vision models) and text/SI, not better table parsing.
