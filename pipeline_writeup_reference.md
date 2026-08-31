# Data Collation and Analysis Pipeline — Reference for Write-up

Companion to `results_summary_studies_1_2_3.md` (results) and
`thesis_methodology_outline.md` (full chapter outline, §3.1-3.8 cover this same
ground at a higher level). This document is the code-grounded detail layer —
every claim below is traceable to a specific script and line.

**Flag before drafting**: §3.4 of the methodology outline states wall-clock time was
deliberately downgraded to an operational/descriptive metric (cache-hit confound),
with turn count as the real efficiency measure. The actual analysis (this pipeline)
built full primary GLMMs on wall-time, and several headline results depend on it
(Study 2's uniform speedup, Study 3/2v3's model-specific slowdowns). This needs to be
stated as an explicit, justified deviation, not silently presented as if wall-time
was always a primary outcome. The justification that holds up: §3.4's cache-independence
safeguard (a per-trial random token in the user message) was already in place, which
addresses the original confound directly — so treating wall-time as a real outcome
once that safeguard exists is defensible, but say so explicitly.

---

## Part 1 — Data collation

**Script**: `scripts/collate_studies_1_2_3.py`. Input: per-trial JSON result files
under `study_{1,2,3}/results/{model}/{repo}/{issue_idx}/{condition}/rep{N}.json`.
Output: `data/compiled_results_combined.pkl` (one row per trial, all 3 studies).

### 1.1 Provenance — built from an existing notebook, not from scratch

The condition-harmonization logic (`CONDITION_ROOT`, the map-type grouping, the
4-model anchor panel) was ported directly from `notebooks/study_comparison_by_map_type.ipynb`,
which had already worked this out but never persisted its in-memory dataframe to
disk. This script is the first time that harmonization logic produces a saved,
reusable artifact — worth stating explicitly as a provenance note (methodology §3.8's
"saved, reusable, version-controlled script" standard).

### 1.2 Condition harmonization — the core mapping

Three studies use different condition-name vocabularies for the same underlying map
types. `CONDITION_META` (lines 97-110) is the single source of truth mapping each
raw condition name to `(study, harmonized_map_condition, delivery_mechanism, submission_mode)`:

| raw condition | study | map_condition | delivery_mechanism | submission_mode |
|---|---|---|---|---|
| `none` | 1 | `baseline` | control | n/a |
| `ast_compact` | 1 | `structural` | injection | n/a |
| `freq` | 1 | `temporal_frequency` | injection | n/a |
| `cochange` | 1 | `temporal_cochange` | injection | n/a |
| `structural` | 2 | `structural` | on_demand | voluntary |
| `temporal_frequency` | 2 | `temporal_frequency` | on_demand | voluntary |
| `temporal_cochange` | 2 | `temporal_cochange` | on_demand | voluntary |
| `all_tools` | 2 | `all_tools` | on_demand | voluntary |
| `structural_required` | 3 | `structural` | on_demand | required |
| `temporal_frequency_required` | 3 | `temporal_frequency` | on_demand | required |
| `temporal_cochange_required` | 3 | `temporal_cochange` | on_demand | required |
| `all_tools_required` | 3 | `all_tools` | on_demand | required |

**`none` (Study 1's baseline) is the single shared no-map control for all three
studies** — Studies 2 and 3 were deliberately not given their own baseline
(user-confirmed design decision, stated in the script's own docstring). This is why
every Study 2/3/2v3 script's data-loading function pulls in `study==1 & map_condition=="baseline"`
alongside its own study's rows.

### 1.3 Two deliberate scoring decisions (both explicit, both user-confirmed this session)

**1. Case-insensitive scoring is the primary criterion, not a flag.**
`gpt-oss-120b` was found to sometimes recapitalize an otherwise-correct file path on
resubmission (`scripts/audit_case_sensitivity.py`: 11/7704 trials — the docstring's
"9" figure is an earlier undercounted version, later corrected to 11 once the
recovery logic matched the collation script's own; 100% gpt-oss-120b, mean F1 delta
+0.88-0.96 when it happens). The harness's own `scorable_files()` filter is itself
case-sensitive, so a miscapitalized-but-correct prediction gets **silently dropped**
before scoring — not scored as wrong, just missing.

- `recover_case_only_drops()` (lines 113-133): for each raw prediction that matches a
  ground-truth file case-insensitively but is missing from the already-harness-filtered
  scorable set, re-adds the correctly-cased ground-truth form. A 1:1 recovery of a
  genuinely-dropped entry, not an extra/fabricated prediction.
- `compute_case_insensitive_scores()` (lines 136-152): standard precision/recall/F1,
  computed on the case-recovered prediction list.
- Both case-insensitive (`precision`/`recall`/`f1`, primary) and exact-match
  (`precision_exact`/`recall_exact`/`f1_exact`, reference/audit) columns are kept in
  the output — worth citing both in a methods paragraph as the audit trail.

**2. The "answer overwrite" pattern gets no correction and no flag.**
`scripts/audit_answer_overwrites.py` found 209/7704 trials where a well-formed
earlier candidate answer was replaced by a different final one — either via Study 3's
submit-gate rejecting a non-compliant submission, or the forced final-answer
elicitation prompt. Explicit decision, stated in the script's docstring: the
gate-rejection cases **are Study 3's experimental manipulation itself**, not a bug to
correct; the content-stated cases are ordinary mid-trial deliberation, not a
discarded final answer the way Study 0's empty-prediction bug was (cross-ref
methodology §2.4.1 for that contrast). `final_files_predicted` is used as-is.

This is a direct methodological contrast worth stating side-by-side in the write-up:
case-sensitivity is corrected because it's a scoring artifact unrelated to whether
the right file was found; answer-overwrites are not corrected because — in the gate
case — they *are* the thing being measured.

### 1.4 Cost recomputation

`total_cost` is **recomputed from token counts and the price sheet**
(`load_price_lookup()`, `compute_actual_cost()`), not taken from the harness's own
LiteLLM-reported cost — that raw value is kept alongside as `total_cost_litellm_raw`
for reference. This matters because of Study 0's price-sheet corrections (cached-token
pricing for Mistral/Fireworks models, sourced from primary provider docs) — recomputing
downstream from the corrected price sheet, rather than trusting a possibly-stale
harness-reported figure, is the same "current data, not stale computation" standard
as methodology §3.8.

### 1.5 Sample composition and what's excluded

- 7704 total trials collated across all 3 studies (12 conditions × 4 models × 45
  issues × up to 15 reps combined; reps 1-3 = primary 3-rep design, reps 4-15 = the
  expanded-replication trials for select issues per DEVLOG 2026-08-08).
- **Nothing is silently dropped for the expanded-replication reps** — they're kept in
  the output with their real rep number, filtered downstream (`rep<=3`) by every
  analysis script rather than excluded at collation time. Matches the source
  notebook's own behavior.
- A trial is excluded (routed to `data/compiled_results_combined_flagged.csv` instead
  of the main output) only for: unreadable/invalid JSON, missing ground truth
  (`scores.f1 is None`), or an issue not present in `issue_selection_final.csv`.
  Report the flagged count from a fresh run's console output when drafting — it's
  printed but not hardcoded here since it can shift if source data changes.

---

## Part 2 — Statistical analysis pipeline

### 2.1 Per-comparison structure (applies identically to Studies 1, 2, 3, and 2-vs-3)

Each of the 4 comparisons follows the same three-stage pipeline:

1. **R data export** — `scripts/export_for_r.py --study {1,2,3}` (studies vs. shared
   baseline) or `scripts/export_2v3_for_r.py` (the direct comparison, no baseline row).
   Produces `data/stats_study{N}/study{N}_for_r.csv`: one row per trial, with
   `model_short` remapped to underscore-safe R factor names (`deepseek_flash`,
   `gpt_oss_120b`, `ministral_3b`, `nemotron_super`) and boolean columns (`success`,
   `hit_turn_cap`) cast to 0/1 rather than left as pandas' `"True"`/`"False"` strings
   — R's `read.csv` only auto-coerces `"TRUE"`/`"FALSE"` (all-caps) to logical, so this
   was a real bug caught and fixed during this session (see §2.4 below).

2. **Primary R GLMMs** — three scripts per comparison:
   - `stats_study{N}_r_glmm.R`: F1 (`glmmTMB`, `ordbeta()` family) and success
     (`lme4::glmer`, `binomial`).
   - `stats_study{N}_r_secondary.R`: turns (`glmmTMB`, `nbinom2()`) and turn-cap
     (`glmer`, `binomial`).
   - `stats_study{N}_r_tokens_cost_walltime.R`: tokens, cost, wall-time, all three via
     `glmmTMB`, `Gamma(link="log")`.

   Every model is fit twice — **full** (`map_condition * log_size_c * model_short`,
   or `submission_mode * map_condition * model_short + log_size_c` for the 2v3
   comparison) and **reduced** (same terms capped at pairwise interactions, `^2`) —
   compared via likelihood-ratio test. Both share crossed random effects
   `(1|issue_id) + (1|repo)`, fit simultaneously (not nested/hierarchical) — the
   reason R was adopted over the original Python/statsmodels approach (statsmodels
   can cluster-robust one grouping variable at a time via GEE, or approximate via
   `BinomialBayesMixedGLM`'s variational Bayes, but can't do a true joint MLE fit
   with two crossed random effects).

   Every script saves **both** full and reduced coefficient tables unconditionally
   (a fix applied mid-session — originally only the reduced model's coefficients were
   saved, on the assumption the full model was "only needed for the LRT," which broke
   the first time an LRT came back significant and the full model's individual
   interaction terms were needed for interpretation).

3. **Nonparametric robustness layer** — `stats_study{N}_f1.py`/`_success.py`/
   `_secondary_nonparametric.py` (or the `stats_study2v3_*` equivalents). Friedman +
   Wilcoxon signed-rank for continuous outcomes (F1, tokens, cost, wall-time, turns),
   Cochran's Q + McNemar for binary outcomes (success, turn-cap), all matched-pairs,
   Holm-corrected within each outcome's own family of comparisons. Shares no
   distributional assumption with the GLMM layer, so agreement between the two is a
   real cross-validation, not redundant computation — this distinction (and why an
   earlier Python GEE/`BinomialBayesMixedGLM` layer *was* redundant and got removed,
   see §2.3) is worth its own methods-section paragraph.

Shared helper module: `scripts/stats_common.py` — `matched_wide()` (generic
pivot-to-matched-pairs, parametrized by which column to pivot on: `map_condition` for
the per-study comparisons, `submission_mode` for 2v3), `mcnemar_row()`,
`wilcoxon_effect_size()` (rank-biserial correlation), `lr_test()`.

### 2.2 Model family choices — the reasoning to state explicitly

- **F1** (`ordbeta`, ordered beta regression): F1 is continuous on [0,1] with real
  point masses at exactly 0 and exactly 1 (a trial that finds nothing, or finds
  exactly the right set) — ordbeta is purpose-built for this shape, unlike a plain
  Beta regression (undefined at the boundaries) or a Binomial quasi-likelihood trick.
- **success/turn-cap** (`binomial`): standard logistic GLMM, genuinely binary outcomes.
- **turns** (`nbinom2`, negative binomial): count data, right-skewed, a hard ceiling
  at `max_turns` censors the tail but nbinom2 is the standard starting point for
  overdispersed counts.
- **tokens/cost/wall-time** (`Gamma(link="log")`): continuous, strictly positive
  (verified zero-minimum before fitting), heavily right-skewed — Gamma-with-log-link
  is the standard family for this shape (constant coefficient of variation), the same
  logic that picked ordbeta/nbinom2 for the other outcomes. **This replaced an earlier
  version of the pipeline that used only the nonparametric Friedman/Wilcoxon layer for
  these three metrics** — flagged as an inconsistency (turns got the same rigor
  treatment, tokens/cost/wall-time didn't, with no principled reason for the
  difference) and corrected to match.

### 2.3 A design choice that was tried and reverted: GEE / BinomialBayesMixedGLM

Early in this pipeline's development, the "primary" GLMM-equivalent test for F1 and
success was fit in Python via `statsmodels`: `sm.GEE` (cluster-robust standard errors,
but only one grouping variable — issue OR repo, never both) and
`BinomialBayesMixedGLM` (a variational-Bayes approximation to the crossed-random-effects
model, not a true likelihood fit). Once the R environment was working, these became
**strictly dominated** by the real GLMM fits — same formula, same family, weaker
estimation — and were removed from all 6 `stats_study{1,2,3}_{f1,success}.py` scripts,
leaving only the genuinely complementary nonparametric tests (Friedman/Wilcoxon/
Cochran's Q/McNemar) alongside the R GLMMs. Worth a sentence in the methods section on
why R was adopted over a pure-Python pipeline: `lme4`/`glmmTMB` support true joint MLE
fitting with multiple crossed random effects, which `statsmodels` does not.

### 2.4 Corrections made during this analysis (for §3.8's data-quality throughline)

1. **R boolean-column parsing bug**: pandas writes bool columns as `"True"`/`"False"`
   in CSV; R's `read.csv` only coerces `"TRUE"`/`"FALSE"` to logical. Caught when
   `hit_turn_cap ~ ...` and `success ~ ...` GLMMs errored (`response must be numeric or
   factor`). Fixed at the export step (`export_for_r.py`/`export_2v3_for_r.py` now
   write these columns as 0/1 directly) rather than patching every downstream R script.
2. **LRT degrees-of-freedom extraction bug**: `glmmTMB`'s `anova()` output names the
   per-model parameter-count column `"Df"` and the actual likelihood-ratio-test df
   `"Chi Df"`; `lme4::glmer`'s `anova()` names the LRT df `"Df"` directly (its
   per-model count is `"npar"`). Code written for one convention (`$Df[2]`) was
   silently wrong when applied to the other — every glmmTMB-based LRT summary (F1,
   turns, tokens, cost, wall-time, across all 4 comparisons) had a nonsensical `df`
   column (the full model's total parameter count, not the LRT's actual df), while
   every glmer-based one (success, turn-cap) was correct. **The `chisq` and `p_value`
   columns were never affected** — only the reported `df` label. Caught by
   cross-checking a printed R console table against its saved CSV during a walkthrough
   of `study1_r_lrt_summary.csv`. Fixed in all 12 affected scripts; all LRT summary
   CSVs regenerated directly from the already-fitted `.rds` model objects (no
   refitting needed, since the models themselves were never wrong).
3. **McNemar zero-discordant-pairs artifact**: `statsmodels.stats.contingency_tables.mcnemar`
   divides by zero when a comparison has no discordant pairs at all (every matched
   pair identical) — produces `statistic=inf`, `p_raw=0.000000`, which reads as
   "extremely significant" but is actually "no data to test with." Surfaces
   specifically for gpt-oss-120b and ministral-3b's turn-cap comparisons, since those
   two models' turn-cap hit rate is near-zero under most conditions. Not corrected in
   code (it's a real edge case in the test itself, not a data problem) — documented as
   a read-time caveat: any row with `n_discordant_pairs=0` should be treated as
   undefined, not significant.

### 2.5 Diagnostics — DHARMa

`scripts/stats_study{N}_r_dharma.R` / `_dharma_secondary.R`. For each comparison's
reduced models (the ones whose coefficients are actually reported): simulated-residual
QQ plot, uniformity (KS test), dispersion, outliers, quantile-trend, zero-inflation,
plus residuals plotted against every fixed-effect covariate and both random-effect
grouping factors. Full models (used only for the LRT) get a lighter
uniformity+dispersion sanity check. Findings summarized in
`results_summary_studies_1_2_3.md`'s "Diagnostic caveats" section — the short version
for a methods paragraph: F1 shows a mild, large-N-driven deviation across all 4
comparisons (plausibly ordbeta's continuous-density assumption vs. F1's real
discreteness); Study 1's cost model shows real overdispersion (anti-conservative,
treat its p-value with caution); Study 1's and Study 2v3's tokens/wall-time models
show real underdispersion (conservative, so their significant findings are if
anything understated).

---

## Sample sizes, for quick reference

| comparison | n | conditions | baseline source |
|---|---|---|---|
| Study 1 | 2160 | baseline + 3 (injection) | own (`none`) |
| Study 2 | 2700 | baseline + 4 (on-demand, voluntary) | shared, from Study 1 |
| Study 3 | 2700 | baseline + 4 (on-demand, required) | shared, from Study 1 |
| Study 2-vs-3 | 4320 | 4 × 2 submission modes, no baseline row | n/a (direct comparison) |

All: 45 issues, 15 repos, 4 models, `rep<=3` (primary 3-rep design).
