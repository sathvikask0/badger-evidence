# Extraction benchmarks vs ChEMBL 37 — summary

| benchmark | papers | ChEMBL values | extracted | precision | recall |
|---|---|---|---|---|---|
| mTOR + PI3Kα | 21 | 224 | 127 | 88.2% (127/127 correct on adjudication) | 50.0% |
| GSK-3β + JAK2 + PARP1 (held out, no tuning) | 24 | 184 | 39 | 100% | 21.2% |
| **combined** | **45** | **408** | **166** | **91% vs ChEMBL; 166/166 correct on adjudication** | **37%** |

* Precision: every extracted value that ChEMBL did not list was traced to its source cell and found correct
  (compounds ChEMBL chose not to record, or the same compound reported in two tables).
* Recall is limited by publishing format, not parsing: most misses are tables published as images, or values
  in text/figures/SI. The second benchmark was run after all extractor fixes, as a held-out check.
* Only ~15% of ChEMBL's source papers for these targets are open access in PMC (24 of 138 in PMC; 892 total),
  which is itself a data-access finding.
* Caveats: 45 papers, 5 kinases/enzymes; ChEMBL is a curation reference, not independent ground truth.
