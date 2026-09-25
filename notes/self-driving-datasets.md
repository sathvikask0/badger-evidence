# Reading notes: "Self-Driving Datasets" (Jones et al., 2026)

**Paper:** H. Jones, Y. Zeng, A. Rose, *et al.* (University of Pennsylvania), *Self-Driving Datasets: From 20 Million Papers to Nuanced Biomedical Knowledge at Scale*, arXiv:2605.07022 (v2, May 2026). [arXiv](https://arxiv.org/abs/2605.07022) · preprint, not peer reviewed
**Read:** September 2026, from an ML engineer's point of view. This paper is the closest thing to Badger Evidence at scale, so it gets read against our own pipeline.

---

## TL;DR

- **Thesis.** Manually curated biomedical databases are expensive, lag the literature and throw away experimental context. An agent system over the whole of PubMed can build comparable datasets automatically, for about **$0.001 per record**.
- **Scale.** 22.5M papers (text and tables), 4.5B tagged entities, ~6.3M records across six tasks.
- **Headline.** Error rates of 0.6–7.7% per task, while an audit of established benchmarks finds 5.5–19.7% of their labels "confirmed wrong".
- **My read.** Strong infrastructure, overstated quality claim. "Error" means *unfaithful to the source passage*, not *untrue*; the error rate depends on which LLM grades it; and the tasks chosen avoid the hardest case, context-dependent numeric values like IC50.
- **Takeaway for this project.** Extraction at scale is close to solved for easy labels. What is not solved is exactly what this atlas measures: numeric bioactivity with assay context, values in figures, and the cross-lab noise floor.

---

## How the system works

**1. Entity tagging.** A teacher model (gpt-oss-120b) tags 19 entity types (compounds, genes, diseases, species, …) on 50,000 papers, one type per pass. That is distilled into gpt-oss-20b, which tags the full 22.5M-paper corpus. Frequent entities are normalised against nine ontologies (UMLS, PubChem, ChEBI, UniProt, NCBI Gene, …), with OPSIN for chemical names.

**2. Retrieval.** ~2.5T tokens embedded into ~250M vectors (Qwen3-Embedding-4B). Queries combine hard entity filters (e.g. "paragraph mentions a small molecule AND a species") with a semantic query used for re-ranking.

**3. Starling, phase 1: build the query.** A Proposer writes candidate filters, a Validator samples hits and measures precision, an Investigator explains false positives. Recall gaps are estimated from chunks the semantic queries rank highly but every filter excludes. Stops at ~80% precision and ≤15% estimated recall gap.

**4. Starling, phase 2: extract.** A schema is induced and frozen, an Extractor runs over the retrieved windows, and a Judge (Qwen3.5-9B distilled from GPT-5.4 with SFT + GRPO) keeps or drops each record on five axes: task relevance, primary-label correctness, span fidelity, secondary fields, entity attribution.

ML analogy: a retrieval-augmented labelling pipeline with an auto-tuned query, a frozen annotation guideline and a learned reward model as the quality gate.

---

## The six tasks

| Task | Records kept | Papers | Unique entities | Compared against |
|---|---|---|---|---|
| Blood-brain barrier (BBB) | 304K | 122K | 31.1K | TDC BBB, B3DB |
| Oral bioavailability | 163K | 45K | 19K | TDC Oral |
| LD50 acute toxicity | 91K | 30.3K | 17.6K | TDC LD50 |
| Gene–disease associations | 3.00M | 145K | 19.6K | ClinVar |
| Protein subcellular localisation | 1.79M | 171K | 36.1K | UniProt |
| Chemical reactions | 916K | 259K | 545K | Open Reaction Database |

## Reported quality

| Task | Error (Opus 4.7 judge) | Error (GPT-5.4 judge) |
|---|---|---|
| BBB | 4.05% | 5.88% |
| Gene–disease | 0.88% | 5.70% |
| LD50 | 3.89% | 5.72% |
| Oral bioavailability | 0.56% | 5.06% |
| Localisation | 1.12% | 5.56% |
| Reactions | 4.68% | 7.78% |

At least 3,000 kept records per task were graded by each frontier model. Humans graded 50 per task on BBB and LD50 only: pass rates 97.3% and 94.0%, judge–human agreement 95.8% / 92.0% vs human–human 95.1% / 90.6%.

**Benchmark audit.** For molecules with ≥3 Starling extractions, benchmark labels that the extraction majority disagreed with were reviewed (8,765 extractions in total). "Confirmed wrong": B3DB 19.7% (214 of 1,086), TDC BBB 16.5%, bioavailability 7.3%, LD50 5.5%. Starling on the same molecules: 0–1.8%.

**Downstream.** Adding Starling data to TDC training: oral bioavailability AUROC 0.692 → 0.779, LD50 MAE 0.602 → 0.575, BBB 0.916 → 0.909 on the TDC test set (but 0.768 → 0.890 on a literature test set).

**Release.** Code, prompts, tagger weights, the six datasets with supporting passages, and a hosted MCP server over the full corpus. The corpus itself, extracted text and embeddings cannot be redistributed (publisher licences).

---

## Critique

1. **"Error" is faithfulness, not truth.** The judge checks a record against the passage it came from. A perfectly copied value from a biased assay passes. Systematic lab-to-lab variance is invisible to this metric by construction.
2. **The number depends on the grader.** On gene–disease, Opus finds 0.88% errors and GPT-5.4 finds 5.70%, a 6× gap on the same records. The honest summary is "roughly 1–8% depending on who you ask", and human validation is 50 records on two tasks.
3. **The benchmark audit uses literature majority as ground truth.** A label is suspect when most extractions disagree with it, restricted to well-studied molecules (≥3 extractions). Human review helps, but for BBB "penetrant" is defined by different logBB/logPS cutoffs across papers, so part of the 16–20% is likely definitions, not mistakes. The paper acknowledges this without quantifying it.
4. **The tasks are the easy ones.** BBB and bioavailability are binary, localisation is categorical. The only numeric small-molecule task (LD50) is scored with a 0.5 log-unit tolerance and no RMSE or correlation against TDC. Context-dependent potency (IC50, Ki with assay, target construct, substrate) is not attempted, and figures are excluded entirely.
5. **Recall is self-reported.** The 15% recall gap is Starling's own estimate during query construction, not a measured fraction of the true facts in PubMed.
6. **Downstream gains are modest.** One clear win (bioavailability), one small one (LD50), one slight loss on the standard BBB test set. More data helped less than the headline suggests, which fits the "noise is systematic" argument from the [Black-box data notes](black-box-data.html).
7. **Not reproducible outside the authors' licences.** The pipeline is open, the corpus is not; independent groups can query it only through the hosted MCP server.

**What is good.** Keeping supporting passages and experimental context with every record is the right design, and the judge-as-reward-model setup is a cheap, reusable quality gate. The benchmark audit is a useful provocation: curated datasets deserve the same scrutiny as extracted ones.

---

## Relevance to Badger Evidence

Same bet as this atlas (structured data from published papers, with provenance), five orders of magnitude larger, on easier targets.

- **Where we differ.** Numeric bioactivity with assay context retained; values read from figures via OCSR; and an explicit measurement of cross-lab disagreement (RMSE 0.71 log units for the same compound, see [findings](https://sathvikask0.github.io/badger-evidence/findings.html)). Starling's metric cannot see that noise; ours is built around it.
- **Where we agree.** Extraction faithfulness is not the bottleneck any more. Deciding what a value *means* (assay, threshold, units, species) is.

Open questions for this project:

- If the hosted MCP server is accessible, how much of our 48-enzyme corpus does Starling cover, and how often do its values agree with ours?
- Run the same "literature majority vs database" audit on ChEMBL for our targets, reporting assay-definition mismatches separately from genuine errors.
