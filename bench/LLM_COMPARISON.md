# Rules vs Claude vs hybrid — extraction benchmark against ChEMBL 37

45 open-access papers that ChEMBL curated for mTOR, PI3Kα, GSK-3β, JAK2 and PARP1; 408 exact ChEMBL values
as reference. Claude = `claude-sonnet-4-5` via `tools/llm_extract.py` (every table: XML tables as text, image
tables as images; JSON-schema tool output; values from XML tables must occur verbatim in the table text;
a column whose header names a different family member, e.g. PARP2 for PARP1, is rejected).

| method | extracted | matched ChEMBL | precision vs ChEMBL | recall | cost |
|---|---|---|---|---|---|
| rules (deterministic) | 166 | 151 | 91.0% | 37.0% | $0 |
| hybrid (rules + Claude on image tables only) | 263 | 233 | 88.6% | 57.1% | ~$0.5 |
| **Claude on every table** | **313** | **283** | **90.4%** | **69.4%** | **$1.65 total (~$0.04/paper)** |

Per benchmark (Claude, all tables): mTOR+PI3Kα 81.7% recall; GSK-3β+JAK2+PARP1 54.3% recall.

## Adjudication

All 30 Claude values that ChEMBL does not list were traced to the source (images checked by eye):
duplicates of the same compound reported in two tables (ChEMBL records one), reference compounds ChEMBL did
not record (e.g. veliparib, olaparib), and one value ChEMBL rounded (0.0007 µM printed; ChEMBL stores 1 nM).
**No transcription or hallucination errors were found among them.**

Errors found before the guard: **9 values, one table** (PMC9884089 tbl1). The table has no PARP1 column;
Claude recorded the PARP2 column as PARP1 *while reporting the header as "PARP2"*. The model's own
`column_header` field exposed the mistake, so a one-line check now rejects such values. Lesson: ask the model
for the evidence it used (header, cell text) and verify that evidence, rather than trusting the label.

Five values in one XML table were flagged "ungrounded": ">10⁴" printed with a superscript; they are bounds and
are not scored. No invented numbers were found.

## Findings

1. **Claude beats the rules even on XML tables**: Claude-everywhere (69%) > hybrid (57%). The gap comes from
   XML tables with layouts the rules miss (transposed tables, isoform headers split across rows).
2. **Image tables are readable**: most of the recall gain on the GSK-3β/JAK2/PARP1 set came from image-only
   SAR tables that rules cannot read at all.
3. **Precision holds**: ~90% agreement with ChEMBL for every method; on review, disagreements were ChEMBL
   curation choices, not extraction errors, apart from the single mislabelled column above.
4. **What still limits recall**: values that are only in text, figures or supplementary files; ChEMBL
   curators read those too.
5. **Cost** is negligible at this scale (~$0.04 per paper).

Caveats: 45 papers, 5 targets; ChEMBL is a curation reference, not independent ground truth; one model, one prompt.
