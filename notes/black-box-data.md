# Reading notes: "Black-box data" (Naef & Bronstein, 2026)

**Paper:** L. Naef and M. Bronstein, *Black-box data: a new paradigm for biomedicine in the AI era*, Chem. Sci., 2026, 17, 8327–8344. [DOI: 10.1039/D6SC01189F](https://doi.org/10.1039/D6SC01189F) · open access, CC BY-NC 3.0
**Read:** September 2026, from an ML engineer's point of view (no biology background).

---

## TL;DR

- **Thesis.** The "Bitter Lesson" already happened to algorithms: learned features beat hand-crafted ones. The authors argue the same should happen to *data*. Design experiments for models to read, not for humans, and trade interpretability for 100–1000× more throughput.
- **Bottleneck.** Biology doesn't need "the next AlphaFold" so much as "the next PDB": a huge, diverse training set. The PDB took ~50 years and up to ~$50B. We can't do that again for every problem.
- **Toolkit.** Seven recurring tricks for making cheap, noisy, model-friendly data (below).
- **My read.** A useful taxonomy wrapped in advocacy. The authors have equity in a company built on this bet, the "more noisy data wins" argument assumes random noise when lab noise is mostly systematic, and clean data is still required for evaluation.
- **Takeaway for this project.** Bias in biological data is mostly a *design* problem (shared controls, forced overlap across labs), not something a model can learn away after the fact.

---

## How I approached it

1. Tried to open the publisher PDF; the signed CDN link was too long to fetch, so located the paper by DOI and read the open-access HTML full text.
2. Summarised the main argument, then separated **what it claims** from **what it's selling**.
3. Went back through every concept I didn't follow and re-derived it with ML analogies (pretraining, active learning, implicit feedback), since I don't come from biology.
4. Proposed my own fix for lab bias and stress-tested it.

---

## Background terms

**PDB (Protein Data Bank).** The global public archive of experimentally determined 3D structures of proteins, DNA and RNA, founded in 1971. Over 200,000 structures, each months to years of lab work. AlphaFold was trained on it. The paper's point: AlphaFold worked partly because this dataset already existed, built by structural biologists for their own reasons. Most other areas of biology (drug binding, toxicity, cell behaviour) have nothing comparable.

**"Quantity is quality"** (a phrase the paper borrows from Aviv Regev). Flips "quality over quantity". Humans need a few clean points to reason from; models can average over millions of noisy points. Their evidence: an MNIST classifier still exceeds 90% accuracy with 100 wrong labels per correct one, as long as there are enough correct labels in absolute terms.
*Catch:* this holds for **random** noise. Biological noise is often **systematic** (a whole lab's batch skewed the same way). More biased data doesn't average out; it makes the model confidently wrong.

---

## Core idea: what makes data "black-box"

How black-box a dataset is = how far the thing you measure is from the thing you want, i.e. how much model machinery sits between the raw readout and the answer. It's a spectrum:

| End of spectrum | What happens | Example | ML analogy |
|---|---|---|---|
| Barely black-box | You measure the target directly, but noisily; ML denoises it | Test an unpurified drug molecule; ML cleans up false hits | Deblurring a photo: still the same photo |
| Fully black-box | You measure something *different*, only indirectly related; the relationship is learned implicitly | Splash RNA with a cheap chemical that reacts with its floppy parts; 40M such readings teach a model to predict 3D shape | Pretraining an LLM on next-word prediction when you want QA |

The paper's pitch: biology should deliberately generate cheap "next-word-prediction-style" data instead of only expensive, directly labelled data.

---

## The seven tricks

| # | Trick | Plain version | ML analogy |
|---|---|---|---|
| 1 | **Low-resolution readouts** | Measure a sparse, cheap version: "these two parts of a protein are within ~30Å" for a few pairs (crosslinking mass spec) instead of the full 3D structure | Masked autoencoders / inpainting |
| 2 | **Amplifiable signal** | Tag each variant with a DNA barcode, test a million at once in one tube, count surviving barcodes by sequencing | One batched pass instead of a million separate calls |
| 3 | **Latent pretraining data** | Train on abundant, indirectly related data; fine-tune on scarce direct labels | LLM pretraining → fine-tuning |
| 4 | **Hypothesis-free screens** | Test 100,000 random candidates instead of 500 expert picks | Random sampling for coverage vs a biased curated distribution |
| 5 | **Proxy readouts** | Photograph liver cells in a dish after drug exposure to predict real toxicity | Training on a proxy metric; Goodhart risk if it drifts from the target |
| 6 | **Skip the cleaning** | Test crude reaction mixtures without purifying; the model absorbs the extra false positives/negatives | Training on raw web crawl |
| 7 | **Signal in missing data** | "Failed" measurements carry information: missing NMR peaks indicate the protein is moving (→ Dyna-1); mutations never seen in nature are probably harmful (→ AlphaMissense) | Implicit negative feedback in recommenders |

**Common thread:** accept worse individual data points in exchange for vastly more of them, and let the model do the reconstruction.

### Trick 2, explained simply

The marathon analogy. Instead of timing a million runners one by one, pin a bib on each and run one race. At the finish line, count bibs.

- **Bib** = a short DNA tag saying which protein variant it is.
- **Race** = add an enzyme that chews up weak, floppy proteins. Sturdy ones survive.
- **Finish line** = DNA sequencing reads millions of tags in one go.
- **Why "amplifiable":** DNA can be photocopied billions of times (PCR), so a microscopic signal becomes readable. Most things in biology can't be copied; experiments that convert their result into "count of DNA tags" get this for free.

**Relative sturdiness works too**, and it's how the real experiment (MEGAscale, Rocklin lab) runs. Run the pool at increasing enzyme doses; the dose at which half a variant's tags disappear becomes its stability score. Comparing near-identical variants (one building block changed) shows which positions matter; the paper cites over 776,000 such measurements.
Caveats: within-tube comparisons are reliable, cross-experiment ones need calibration (batch effects again); PCR copies some tags slightly better than others (sampling bias); scores saturate at the extremes, so ranking is only meaningful in the middle range.

---

## The paper's outlook

1. **Lab-in-the-loop.** The model picks what it's unsure about, the lab runs those experiments, retrain, repeat. *Active learning with a lab as the labelling service.*
2. **Share raw data, not conclusions.** Standardised repositories of raw readouts with full experimental metadata (early examples: OpenBind, the Diffuse Project).
3. **Experts still matter.** Choosing which cheap measurement actually contains signal is a design decision, not something scale solves.
4. **Clean data for evaluation.** Training tolerates noise; testing doesn't. Pretrain noisy, fine-tune and benchmark clean.
5. **Science flips order.** From *understand → encode → simulate* to *encode → simulate → understand* via mechanistic interpretability. Example cited: an Alzheimer's biomarker (DNA fragment length) extracted from a trained model's weights.

---

## Critique: the narratives it's pushing

1. **Conflict of interest.** Both authors hold equity in Proxima Bio, whose business is exactly "cheap noisy data + foundation model"; its platform is the headline example for Trick 1. Bronstein is also on Recursion's advisory board (Trick 5's headline example). Disclosed, but the paper reads as a company thesis.
2. **Their own evidence cuts against them.** AlphaFold 3 still depends on MSAs and a geometry-inspired architecture, and more general models do worse. The Bitter Lesson hasn't finished playing out even in their flagship domain.
3. **"More noisy data wins" assumes random noise.** The support is MNIST with random label flips. Lab noise is mostly systematic, which the paper's own Trick 7 implicitly admits.
4. **Old ideas, new label.** DNA barcoding, Cell Painting, CMap/L1000 and shotgun sequencing are 10–25 years old. The taxonomy is useful; "new paradigm" oversells it.
5. **Expensive clean data doesn't disappear.** If clean data is needed for benchmarking and post-training, cost moves rather than vanishes. They never estimate how much is needed.
6. **The interpretability promise is thin.** Rests on a couple of examples, one from a company blog post.

---

## My idea: removing lab bias, and where it breaks

**Proposal.** Label every data point with lab-level and operator-level metadata, use cheap models to learn each source's bias automatically and subtract it, or use robots to remove human variance.

**What holds up.** Rich metadata (operator, reagent lot, instrument, date, plate position) is cheap and underdone. That's where batch effects hide.

**What breaks.**
- **Confounding, not model capacity.** If Lab A only studies liver cells and Lab B only neurons, lab bias and real biology are perfectly entangled. No model can separate them. Existing batch-correction tools (ComBat, Harmony, scVI) already use batch labels and routinely *overcorrect*, erasing real biology with the bias.
- **Robots swap human variance for machine variance.** Recursion runs a highly automated lab and still corrects for reagent lots, plate-edge effects and run dates.

**Stronger version.** Automated labs with *forced overlap*: shared reference samples and controls on every plate, randomised placement, deliberate replication across sites. Metadata falls out as a side effect, and correction models get something to calibrate against. The robot's real value is making good experimental design cheap enough to always do.

---

## Relevance to Badger Evidence

This atlas is built from exactly what the paper calls data "produced as a byproduct of scientific inquiry": values extracted from published tables. Two of our own [findings](https://sathvikask0.github.io/badger-evidence/findings.html) line up with the critique above:

- The lab-to-lab noise floor (RMSE 0.71 log units for the same compound) is systematic, cross-lab variance: the kind more data won't average away.
- Every model's error rises 25–40% on new papers vs ChEMBL's own test split: evaluation data matters more than training scale.

Open question for this project: can extracted literature data carry enough lab/assay metadata to act as the "shared reference" layer, e.g. compounds measured by many labs as natural bridging samples?
