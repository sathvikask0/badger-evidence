# Validation record

Validated locally on 2026-09-23 with Python 3.14.7 and Node 26.8.1.

- `python3 -m unittest discover -v`: 55 tests pass.
- `python3 -m badger_evidence build`: 10 papers, 179 source-linked records; reproducible dataset ID `60f33a9056249c26`.
- `python3 -m badger_evidence evaluate`: 102/102 numeric reference records match; no extra or missed numeric records in the seven scoped columns; all eight annotated missing cells remain null.
- `node --check badger_evidence/static/app.js`: passes.
- Browser: initial dataset and evidence render; paper plus compound search returns the expected 5.9 nM Ki for PMC8910009 compound 2a; source row and paper link agree.
- Browser: no-match search displays an empty state; Clear filters restores results; selecting PMC7736042, IC50, and Flagged only produces eight missing-value records with “Unavailable” normalized values.
- CSV filtering, source download, unknown routes, source checksums, endpoint separation, unit conversions, species disambiguation, bounds, duplicate controls, footnote retention, and evaluation error cases are tested automatically.

The reference set is agent-transcribed and provisional. This is a regression result on the development corpus, not a claim of independent scientific validation or generalization accuracy. All 179 records are unreviewed; 18 complex cells retain raw text without a parsed numeric value, and eight cells report missing measurements. Some other records carry qualifiers or repeated-report flags.

GitHub Actions is configured to run the automated checks on Python 3.11, 3.12, 3.13, and 3.14. This file records local results; it does not claim remote CI has already run.
