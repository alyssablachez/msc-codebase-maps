# Results Summary — Studies 1, 2, 3, and the Study 2-vs-3 Comparison

Reference document, not drafted prose — every number here is pulled directly from
the saved CSVs (paths given per section) so it can be cited exactly. Structured for
you to turn into results-chapter prose section by section. Matches the plan in
`thesis_methodology_outline.md` §3.7, with two adaptations noted where the plan was
extended once real data arrived (flag both explicitly per §3.8's convention):
1. F1 (continuous) was added as the primary accuracy metric alongside `success`
   (binary), fit via `glmmTMB`'s `ordbeta()` family rather than only the planned
   logistic GLMM.
2. A 4th test — Study 2 vs. Study 3 direct comparison — was added beyond the
   3 vs.-baseline comparisons, isolating `submission_mode` (voluntary vs. required)
   with map condition and delivery mechanism held fixed.

## How the battery is structured, every comparison

For each of the 4 comparisons (Study 1, Study 2, Study 3, Study 2-vs-3), two parallel
tracks were run per outcome:

- **Primary: R GLMM**, crossed random effects `(1|issue_id) + (1|repo)`, full model
  (3-way interaction) vs. reduced model (all pairwise interactions) compared via
  likelihood-ratio test. Families: `ordbeta()` for F1, `binomial` for success/turn-cap,
  `nbinom2()` for turns, `Gamma(link="log")` for tokens/cost/wall-time.
- **Secondary: nonparametric robustness check** — Friedman + Wilcoxon signed-rank
  (continuous outcomes) or Cochran's Q + McNemar (binary outcomes), matched-pairs,
  Holm-corrected. No shared distributional assumption with the GLMM, so agreement
  between the two is a real robustness signal, not duplication (see conversation
  earlier this session for the full reasoning on why both are kept).

Every R script saves **both** full and reduced coefficient tables unconditionally
(`data/stats_study{N}/study{N}_r_{outcome}_{reduced,full}_coefficients.csv`) — read
the reduced model when the LRT is non-significant, the full model when it is
significant (only Study 1's cost and wall-time, and Study 3's wall-time, hit this).

**Known fixed bug**: an early version of every `_r_glmm.R`/`_r_secondary.R`/
`_r_tokens_cost_walltime.R` script mis-extracted the LRT's degrees-of-freedom column
for `glmmTMB`-family models (pulled the model's total parameter count instead of the
actual Chi-square df, because `glmmTMB`'s `anova()` names these two different things
"Df" while `lme4::glmer`'s `anova()` names the LRT df "Df" directly) — `chisq` and
`p_value` were always correct, only the `df` column was wrong. Fixed across all 12
affected scripts and all saved CSVs regenerated; worth one sentence in §3.8 alongside
the other data-quality corrections.

---

## Study 1 — map-as-context (injection) vs. baseline

**Design**: 2160 trials, `rep<=3`. 4 conditions × 540 each: `baseline` (no map),
`structural`, `temporal_frequency`, `temporal_cochange` — all `delivery_mechanism="injection"`
(map content pushed into the prompt unconditionally). 45 issues, 15 repos, 4 models
(deepseek-flash, gpt-oss-120b, ministral-3b, nemotron-super; deepseek-flash and
baseline are the GLMM reference levels).

Data: `data/stats_study1/`

### F1
- GLMM 3-way LRT: χ²=9.99, df=9, **p=.351** — not significant.
- Friedman: χ²=6.69, df=3, p=.082 — not significant, close.
- Wilcoxon pooled vs. baseline: nothing survives Holm (best: temporal_cochange p_holm=.151).
- Wilcoxon per-model: deepseek-flash × temporal_cochange closest (p_holm=.062), doesn't survive.
- **Conclusion: no F1 effect from maps, consistently across every method.**
- Diagnostic caveat: mild DHARMa deviation (KS p=.0022, quantile-trend p=.0017), not
  localized to any covariate — plausibly F1's discreteness vs. ordbeta's continuous
  assumption, amplified by n=2160. Doesn't change the null conclusion.

### success (recall==1.0)
- GLMM 3-way LRT: χ²=3.65, df=9, **p=.933** — not significant.
- Cochran's Q: p=.057 — not significant, close.
- McNemar pooled: nothing survives Holm.
- McNemar per-model: **deepseek-flash × temporal_cochange survives Holm (p_holm=.046)**
  — the one significant accuracy result anywhere in Study 1.
- Diagnostic: this model is completely clean on DHARMa — state this result with confidence,
  but frame it as one narrow significant cell among many tested, not a general claim.

### turns
- GLMM 3-way LRT: χ²=5.48, df=9, p=.791 — not significant.
- Reduced-model main effect: `structural` significantly reduces turns for the reference
  model (β=−0.228, p<.0001, ≈20% fewer turns, log link).
- Wilcoxon pooled (added later in this session): **all three map conditions
  significantly reduce turns** — structural r=−.55 (p<1e-25), temporal_frequency r=−.30
  (p<1e-8), temporal_cochange r=−.21 (p=6e-5).
- Wilcoxon per-model: significant reductions for deepseek-flash (2/3 conditions),
  ministral-3b (3/3), nemotron-super (3/3). **gpt-oss-120b: none survive Holm** —
  matches the GLMM's `map_condition:model_shortgpt_oss_120b` interaction terms, which
  show gpt-oss-120b benefiting less from these maps' turn-reduction than other models.
- Diagnostic: mostly clean, one borderline uniformity flag.

### turn-cap (hit_turn_cap)
- GLMM 3-way LRT: χ²=2.65, df=9, p=.977 — not significant.
- **Quasi-separation**: gpt-oss-120b (2/540 cap-hits) and ministral-3b (1/540) have
  near-zero cap rates → absurd SEs (thousands) on their individual coefficients.
  Only deepseek-flash's and nemotron-super's turn-cap coefficients are interpretable.
- Cochran's Q (added later): p=.001, significant.
- McNemar pooled: significant for all 3 conditions, direction = maps reduce cap-hits.
- McNemar per-model: several cells for gpt-oss-120b/ministral-3b show
  `n_discordant_pairs=0` with `p_raw=0.000000`/`statistic=inf` — a **divide-by-zero
  artifact**, not a real result (same underlying data-sparsity as the GLMM quasi-separation).
  Don't cite those specific cells.
- Descriptive: turn-cap hit rate baseline 8%, structural 5%, temporal_frequency 6%,
  temporal_cochange 6% (`figures/study1_turn_cap_barplot.png`).

### tokens / cost / wall-time
- **tokens**: 3-way LRT p=.138, not significant. Friedman χ²=534.2, p<.0001 — every
  condition costs significantly more tokens than baseline, structural largest (r≈.86).
  Diagnostic: real underdispersion (ratio=.66, p=.004) → conservative bias.
- **cost**: 3-way LRT **χ²=23.17, df=9, p=.0058, significant** — driven by gpt-oss-120b,
  whose cost scales disproportionately with codebase size under every map condition
  (structural β=+0.294 p<.0001, temporal_frequency β=+0.233 p=.0018, temporal_cochange
  β=+0.222 p=.0029, all relative to deepseek-flash). **Diagnostic caveat, important**:
  real overdispersion (ratio=1.35, p=.034) → anti-conservative bias, so this p=.0058
  is likely optimistic; state the gpt-oss-120b pattern as real (visible in coefficient
  magnitudes) but hedge the exact p-value.
- **wall-time**: 3-way LRT **χ²=49.15, df=9, p=1.55e-7, significant, strongly** — same
  gpt-oss-120b-driven pattern (structural β=+0.340 p<.0001, temporal_frequency β=+0.149
  p=.035, temporal_cochange β=+0.229 p=.0011). Diagnostic clean (ratio=1.07, p=.40) —
  **trustworthy at face value**, unlike cost.
- Notable per-model detail: nemotron-super shows **no** significant wall-time effect
  for any condition despite significant token/cost increases.

---

## Study 2 — on-demand tools, voluntary vs. baseline

**Design**: Study 2's 4 conditions (structural, temporal_frequency, temporal_cochange,
`all_tools`; all `delivery_mechanism="on_demand"`, `submission_mode="voluntary"`) plus
Study 1's `baseline` as the shared cross-study control = 2700 trials.

Data: `data/stats_study2/`

### F1
- GLMM 3-way LRT: p=.313 — not significant.
- Friedman: χ²=13.25, df=4, **p=.010, significant** — but no individual condition
  survives Holm vs. baseline (pooled or per-model). Signal is diffuse, not localized
  to one condition.

### success
- GLMM 3-way LRT: p=.837 — not significant.
- Cochran's Q: p=.144 — not significant. Nothing significant anywhere.

### turns / turn-cap
- Both LRTs not significant (turns p=.640, turn-cap p=.973).
- Turn-cap McNemar: nothing survives Holm correction, pooled or per-model — weak/absent
  effects in the voluntary condition (contrast with Study 3, below).

### tokens / cost / wall-time — the standout result of Study 2
- **tokens**: up significantly for `temporal_frequency`, `temporal_cochange`,
  `all_tools` (p<.04), **not** `structural` — consistent with on-demand/selective use.
- **cost**: up significantly for `temporal_cochange` (p=.024) and `all_tools` (p=.012) only.
- **wall-time**: GLMM main effect for `structural` significant and **negative**
  (β=−0.185, p=.0083, ≈17% faster) — the standout finding. Wilcoxon confirms: **all
  four conditions significantly faster** than baseline (all p_holm<1e-9).
- **No 3-way interactions anywhere** (tokens p=.757, cost p=.561, wall-time p=.540) —
  unlike Study 1, effects are consistent across models and codebase sizes.
- **Headline**: on-demand map tools appear to let the model skip costly manual
  exploration, making trials *faster* despite using more tokens — opposite direction
  from Study 1's injection-based maps.

---

## Study 3 — on-demand tools, required vs. baseline

**Design**: same structure as Study 2 (2700 trials), but `submission_mode="required"`
instead of `"voluntary"` — tool use is mandated, not optional.

Data: `data/stats_study3/`

### F1 / success
- Both completely null, every method: F1 GLMM LRT p=.489, Friedman p=.803 (not even
  close, unlike Study 2's p=.010); success GLMM LRT p=.812, Cochran's Q p=.192, closest
  McNemar cell (temporal_cochange, p_raw=.040) doesn't survive Holm (p_holm=.159).
  **Requiring tool use doesn't move accuracy at all**, in either direction.

### turns / turn-cap
- Both LRTs not significant (turns p=.385, turn-cap p=.498).
- Turn-cap McNemar (added later): gpt-oss-120b shows significant increases for
  `temporal_frequency` (p_holm=.023) and `all_tools` (p_holm=.010).

### tokens / cost / wall-time
- **tokens**, **cost**: both massively significant pooled (Friedman χ²=305.6 and
  138.3, both p<1e-30) — much stronger than Study 2's voluntary condition, as expected
  under mandatory use. Neither shows a significant 3-way LRT (tokens p=.342, cost p=.159).
- **wall-time**: 3-way LRT **χ²=22.29, df=12, p=.034, significant**. Pooled Friedman
  is **not** significant (p=.383) — the effects cancel out across models. Real story,
  from the reduced-model's `map_condition:model_short` 2-way terms (all 12 significant,
  most p<1e-5): **gpt-oss-120b and nemotron-super get significantly slower** under every
  condition (β=+0.26 to +0.67 vs. deepseek-flash), **ministral-3b gets significantly
  faster** (β=−0.45 to −0.73), deepseek-flash roughly neutral. The 3-way term itself
  is a weak, diffuse layer on top (only 2 of 12 terms individually significant) — the
  dominant driver is model identity, not codebase size.
- **Headline contrast with Study 2**: same map conditions, same delivery mechanism,
  but making tool use *required* splits models into wall-time winners and losers,
  instead of Study 2's "everyone gets faster."

---

## Study 2-vs-3 — direct comparison (voluntary vs. required)

**Design**: Study 2 + Study 3 together, no baseline row — 4320 trials. Both share the
same 4 map conditions and `delivery_mechanism="on_demand"`; only `submission_mode`
differs. Matched unit: (model, issue, rep, map_condition) — each Study 2 trial pairs
directly with its Study 3 counterpart. This is the 4th test, isolating the
required-vs-voluntary manipulation with everything else held fixed.

Data: `data/stats_study2v3/`

### F1
- GLMM 3-way LRT: p=.399 — not significant.
- **Wilcoxon pooled: significant, required is better** (p=.027, small positive effect).
- Per-map-condition: driven by `temporal_cochange` (p_holm=.018).
- **Note the partial disagreement**: the GLMM's `submission_mode:temporal_cochange`
  interaction term itself is positive but **not significant** (p=.355) — state this as
  suggestive-but-not-robustly-established, not a settled finding, given the mismatch
  between methods.

### success
- GLMM 3-way LRT: p=.995 — not significant.
- **McNemar pooled: significant, required is better** (p=.012).
- GLMM confirms specifically via the `submission_mode:temporal_cochange` interaction
  (β=0.80, **p=.025**) — this one agrees closely with McNemar's per-condition result
  (p_holm=.017). Unlike F1, this result can be stated plainly.

### turns / turn-cap
- Both LRTs not significant (turns p=.585, turn-cap p=.121).
- Turn-cap McNemar (added later): **pooled significant** (p=.0018, more cap-hits under
  required) — per-model, **gpt-oss-120b (p_holm=.0029) and nemotron-super (p_holm=.0029)**
  are the two models significantly more likely to hit the cap under required — same two
  models as the wall-time slowdown below.

### tokens / cost / wall-time — the headline result of the whole battery
- **tokens**: up significantly (main effect β=+0.13, p=.011); no 3-way interaction (p=.598).
- **cost**: up significantly (β=+0.09, p=.036); no 3-way interaction (p=.774).
- **wall-time**: no significant main effect at the reference model (p=.542, and the
  raw coefficient even points the "wrong" direction) — but this is a reference-level
  artifact, not a real null. The `submission_mode:model_short` interaction terms show a
  **huge, highly significant model-specific slowdown**: gpt-oss-120b (β=+0.587,
  p=3.8e-34) and nemotron-super (β=+0.503, p=1.3e-25) get dramatically slower under
  required; ministral-3b more modestly (β=+0.116, p=.016); deepseek-flash essentially
  unaffected (matches its own non-significant Wilcoxon result, p=.337).
- **The single most citable finding across the whole combined chapter**: making tool
  use mandatory buys a small, `temporal_cochange`-specific accuracy gain (both F1 and
  success move the same direction, F1's significance borderline) at the cost of a
  large, consistent token/cost increase and a wall-time penalty that's free for
  deepseek-flash but severe for gpt-oss-120b and nemotron-super. This resolves the
  Study 2/Study 3 puzzle: Study 2's "everyone gets faster" and Study 3's "split by
  model" are two ends of the same effect — `required` mode specifically removes the
  speed advantage voluntary, selective tool use gave certain models.

---

## Cross-cutting themes (for a discussion/synthesis section)

1. **No accuracy effect from maps or tool-use policy, anywhere**, except two narrow
   significant cells: Study 1's deepseek-flash×temporal_cochange (success), and Study
   2v3's temporal_cochange interaction (success, confirmed; F1, suggestive only).
   State this as the primary accuracy finding across all three studies — maps and
   tool-use requirements don't move correctness, in either direction, for the large
   majority of model×condition combinations.
2. **gpt-oss-120b is the recurring outlier on cost/time metrics** — drives Study 1's
   cost/wall-time 3-way interactions, Study 3's wall-time 2-way interaction, and the
   Study 2v3 wall-time/turn-cap slowdown. Worth a dedicated paragraph on this model's
   behavior specifically.
3. **Delivery mechanism flips the wall-time story**: injection (Study 1) costs time
   uniformly across models; on-demand+voluntary (Study 2) saves time uniformly;
   on-demand+required (Study 3, and confirmed directly in Study 2v3) removes that
   saving in a strongly model-dependent way.
4. **turns is the one process metric with a clean, model-general, always-in-the-same-
   direction finding**: maps (especially `structural`) reliably reduce turn count, with
   gpt-oss-120b again the partial exception.

## Diagnostic caveats to cite in a limitations paragraph

- F1 (ordbeta) models across all 4 comparisons show a mild, large-N-driven distributional
  deviation (visually near-perfect QQ fit, but KS/quantile-trend tests significant at
  n>2000) — plausible cause: F1's discreteness vs. ordbeta's continuous-density assumption.
- Study 1's `total_cost` model: real overdispersion (ratio=1.35) → anti-conservative,
  treat its significant 3-way LRT (p=.0058) with caution.
- Study 1 and Study 2v3's `total_input_tokens` (and Study 2v3's `wall_time_seconds`)
  models: real underdispersion (ratios .66–.81) → conservative bias, so their
  significant findings are trustworthy if anything understated.
- Turn-cap quasi-separation for gpt-oss-120b and ministral-3b in every single-study
  comparison (near-zero cap-hit rates) — their individual GLMM coefficients and some
  McNemar cells are uninterpretable; only deepseek-flash/nemotron-super are reliable.
- McNemar's zero-discordant-pairs artifact (`p_raw=0.000000`, `statistic=inf`) appears
  wherever a model's turn-cap hit rate is near-zero under both compared conditions —
  a statsmodels divide-by-zero, not a real result.

## Pipeline / script reference

- Data export: `scripts/export_for_r.py --study {1,2,3}`, `scripts/export_2v3_for_r.py`
- Primary GLMMs: `scripts/stats_study{N}_r_glmm.R` (F1, success),
  `scripts/stats_study{N}_r_secondary.R` (turns, turn-cap),
  `scripts/stats_study{N}_r_tokens_cost_walltime.R` (tokens, cost, wall-time)
- Nonparametric robustness: `scripts/stats_study{N}_f1.py`, `scripts/stats_study{N}_success.py`,
  `scripts/stats_study{N}_secondary_nonparametric.py`
- Diagnostics: `scripts/stats_study{N}_r_dharma.R` / `_dharma_secondary.R`,
  plots in `data/stats_study{N}/dharma/`
- Shared helpers: `scripts/stats_common.py`
- `N` = `1`, `2`, `3`, or `2v3`
