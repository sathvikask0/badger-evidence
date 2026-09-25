# Do potency models trained on ChEMBL work on new papers?

**Setup.** Test set: 401 exact IC50/Ki values with known structures, extracted from 97 open-access papers across 25
enzymes (`paper_test.json`). ChEMBL has never curated these papers, except one. 215 values are for compounds ChEMBL
has never measured on that enzyme ("unseen"). The other 186 are compounds ChEMBL already has, mostly reference drugs.
Training data: ChEMBL 37 values for the same 25 enzymes (113k task–molecule pairs), with every test-set paper
removed. Values are expressed as pIC50/pKi (log units), so an error of 1.0 means a 10× miss. For comparison, ChEMBL's
own held-out split uses a random 10% of molecules.

Models:
- **Baseline:** predict each enzyme's average.
- **Random forest:** on Morgan fingerprints.
- **Chemprop D-MPNN:** trained from scratch.
- **Chemprop fine-tuned from CheMeleon:** a message-passing GNN pre-trained on about 1M PubChem molecules.

All four are multitask or per-enzyme, trained on an M3 Pro.

## Results

| model | ChEMBL held-out RMSE | new papers, unseen compounds: RMSE | rank order within enzyme (ρ) | rank order within one paper's series (ρ) |
|---|---|---|---|---|
| baseline (enzyme mean) | 1.18 | 1.15 [1.04–1.26] | — | — |
| random forest | **0.63** | 0.88 [0.80–0.97] | 0.26 | 0.10 [−0.08–0.28] |
| D-MPNN (scratch) | 0.70 | 0.94 [0.86–1.03] | 0.47 | 0.46 [0.26–0.55] |
| **CheMeleon fine-tuned** | **0.63** | **0.79 [0.72–0.86]** | **0.51** | 0.40 [0.22–0.54] |

- On ChEMBL held-out data, within-enzyme ρ is 0.84 for both the random forest and CheMeleon.
- The noise floor is RMSE 0.71. That is how far a paper's value for a compound sits from ChEMBL's value for the
  same compound (186 pairs), i.e. lab-to-lab disagreement.
- Brackets are 95% bootstrap intervals.

## What this shows

1. **Pre-training only pays off out of distribution.** On ChEMBL's own held-out data, the random forest and CheMeleon
   tie (0.63). On new papers, CheMeleon is better by 0.10 log units (paired bootstrap 95% CI 0.02–0.18; better in
   99% of resamples). The gap is largest for compounds unlike anything in training (Tanimoto similarity < 0.4):
   random forest 1.03, CheMeleon 0.77.
2. **ChEMBL benchmarks overstate performance.** Error rises 25–40% for every model when moving from ChEMBL held-out data to new
   papers. A random ChEMBL split leaks near-duplicate analogs; new papers do not.
3. **RMSE looks nearly solved, but ranking isn't.** CheMeleon's 0.79 is close to the 0.71 lab-to-lab noise floor.
   Yet within a single paper's compound series, the question a medicinal chemist actually asks ("which analog is
   better?"), ranking is weak. The best models reach ρ ≈ 0.4–0.5, and the random forest is close to chance (0.10).
   The models get the chemical series' ballpark right but not the order of analogs within it.
4. **Implication for data.** Better models need more series-level data from recent literature. Pooling more of
   ChEMBL won't supply that. Extracted, source-linked paper data is exactly this kind of data.

## Caveats

- **Small test set.** There are 215 unseen values, and per-enzyme numbers (in `results.json`) rest on 5–26 values
  each.
- **Optimistic in-distribution baseline.** A scaffold split of ChEMBL would narrow the gap in point 2.
- **Undertrained scratch model.** The D-MPNN hit its 40-epoch cap while still improving. CheMeleon early-stopped at
  epoch 12.
- **Conditions not normalised.** Assay conditions differ between papers and ChEMBL. This is part of the noise floor.
- **One seed per model.** No hyperparameter search was run.

Reproduce: `sh tools/generalization/run_all.sh` (see README).

## Replication on a second, independent set of papers (scale-up run 1)

The same fine-tuned CheMeleon checkpoint (no retraining) was scored on values from 397 newly found CC BY papers,
extracted by Claude Sonnet 5 (Batch API) and kept only if a rule-based check confirmed the value, its compound row and
a column header naming the right human enzyme (`tools/verify_scale.py`). Structures come from the compound names in
the experimental section (OPSIN), kept only when the name's formula matches the paper's HRMS/analysis formula
(`tools/structures.py`, which now also reads names from section headings), or from named drugs.
Test set: 351 values, 273 of them compounds ChEMBL has never measured on that enzyme, from 56 papers
(`build_external_test.py`).

| | first test set (97 atlas papers) | replication (56 new papers) |
|---|---|---|
| unseen compounds | 215 | 273 |
| CheMeleon RMSE | 0.79 [0.72–0.86] | **1.24 [1.15–1.34]** |
| enzyme-mean baseline RMSE | 1.15 | **1.12** |
| ranking within a paper's series (ρ) | 0.40 [0.22–0.54] | 0.20 [0.06–0.35] |
| error by similarity to training (<0.4 / 0.4–0.6 / >0.6) | 0.77 / 0.73 / 0.87 | 1.72 / 1.09 / 0.93 |

**The first result does not replicate.** On the larger, independent set the model is no better than predicting each
enzyme's average (worse overall; 1.00 vs 1.02 after removing the five most extreme paper series). An earlier, smaller
version of this check (159 values, 39 papers, before the heading fix) looked favourable (0.86 vs 1.07); it was too
small and too concentrated on two enzymes to trust.

What drives the error:
- **Paper-level offsets, not within-paper noise.** Removing each paper's average offset cuts RMSE from 1.24 to 0.57.
  Whole series sit 1.5–2.7 log units away from what ChEMBL-trained models expect (assay format, reference standard,
  enzyme source, or reporting quality).
- **Suspicious reports.** One paper reports every compound at 40–60 nM against AChE and BChE (and similar values for
  CA I/II), a flat, uniformly potent profile that the model puts near 25 µM. The extraction is faithful; the question is
  the source. Large model-vs-paper disagreement is a useful flag for papers worth a human look.
- **Novel chemistry.** Error rises steeply for compounds unlike anything in ChEMBL (1.72 at Tanimoto < 0.4).

Takeaway: RMSE on one curated test set overstated generalization. Evaluating on many independent papers, and
reporting paper-level offsets separately from within-series ranking, gives a more honest picture.
