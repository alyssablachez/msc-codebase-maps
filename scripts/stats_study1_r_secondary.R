#!/usr/bin/env Rscript
# Study 1 -- tests 8-9 from the agreed battery, same rigor level as the
# F1/success GLMMs in scripts/stats_study1_r_glmm.R:
#   8. turns_used -- glmmTMB, negative-binomial (nbinom2) family. Turns is
#      a count with a hard ceiling (max_turns=30) censoring the right tail,
#      but nbinom2 is still the standard starting point for overdispersed
#      count data; the turn-cap barplot (figures/study1_turn_cap_barplot.png)
#      is the separate descriptive check on how much that ceiling bites.
#   9. hit_turn_cap -- lme4::glmer, binomial family. Same model shape as
#      the success model in stats_study1_r_glmm.R, just a different binary
#      outcome (turn-cap tests are supplementary/robustness for tokens
#      test 8's censoring, not a primary hypothesis test).
# Both use the same crossed random effects (1|issue_id) + (1|repo) and the
# same full (3-way interaction) vs. reduced (all 2-way interactions) LRT
# structure as the F1/success models, for consistency across the battery.
#
# Usage:
#   Rscript scripts/stats_study1_r_secondary.R

lib <- "~/R/library"
.libPaths(lib)

suppressMessages({
  library(lme4)
  library(glmmTMB)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg))
root <- normalizePath(file.path(dirname(script_path), ".."))
data_csv <- file.path(root, "data", "stats_study1", "study1_for_r.csv")
out_dir <- file.path(root, "data", "stats_study1")

df <- read.csv(data_csv, stringsAsFactors = FALSE)
df$map_condition <- factor(df$map_condition, levels = c("baseline", "structural", "temporal_frequency", "temporal_cochange"))
df$model_short <- factor(df$model_short, levels = c("deepseek_flash", "gpt_oss_120b", "ministral_3b", "nemotron_super"))
df$issue_id <- factor(df$issue_id)
df$repo <- factor(df$repo)
df$log_size_c <- df$log_codebase_size - mean(df$log_codebase_size)
# pandas writes bool columns as "True"/"False" (not R's "TRUE"/"FALSE"), so
# read.csv leaves this as character rather than coercing to logical.
df$hit_turn_cap <- as.integer(df$hit_turn_cap == "True")

cat(sprintf("Study 1 primary sample: %d trials, %d issues, %d repos, %d models\n",
           nrow(df), nlevels(df$issue_id), nlevels(df$repo), nlevels(df$model_short)))

# ── 8. turns_used: glmmTMB, negative-binomial (nbinom2) ──────────────────

cat("\n", strrep("=", 70), "\n8. turns_used -- glmmTMB, nbinom2() family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

turns_full <- glmmTMB(
  turns_used ~ map_condition * log_size_c * model_short + (1 | issue_id) + (1 | repo),
  data = df, family = nbinom2()
)
turns_reduced <- glmmTMB(
  turns_used ~ (map_condition + log_size_c + model_short)^2 + (1 | issue_id) + (1 | repo),
  data = df, family = nbinom2()
)

turns_lrt <- anova(turns_reduced, turns_full)
cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
print(turns_lrt)

cat("\nConvergence check (full model):\n")
cat("  fit$convergence (0 = converged):", turns_full$fit$convergence, "\n")
cat("  pdHess (positive-definite Hessian):", turns_full$sdr$pdHess, "\n")

turns_summary <- summary(turns_reduced)
save_glmmTMB_coefs <- function(model, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients$cond)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study1_r_turns_", suffix, "_coefficients.csv")), row.names = FALSE)
}
save_glmmTMB_coefs(turns_reduced, "reduced")
save_glmmTMB_coefs(turns_full, "full")

turns_lrt_df <- data.frame(
  outcome = "turns_used", test = "three_way_interaction_LRT",
  chisq = turns_lrt$Chisq[2], df = turns_lrt[["Chi Df"]][2], p_value = turns_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(turns_full), aic_reduced = AIC(turns_reduced)
)

cat("\nRandom-effects variance components (turns model):\n")
tryCatch(print(turns_summary$varcor), error = function(e) {
  cat("(variance-component print failed non-fatally:", conditionMessage(e), ")\n")
})

# ── 9. hit_turn_cap: lme4::glmer, binomial ────────────────────────────────

cat("\n", strrep("=", 70), "\n9. hit_turn_cap -- lme4::glmer, binomial family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

cap_full <- glmer(
  hit_turn_cap ~ map_condition * log_size_c * model_short + (1 | issue_id) + (1 | repo),
  data = df, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
cap_reduced <- glmer(
  hit_turn_cap ~ (map_condition + log_size_c + model_short)^2 + (1 | issue_id) + (1 | repo),
  data = df, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)

cap_lrt <- anova(cap_reduced, cap_full)
cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
print(cap_lrt)

cat("\nConvergence check (full model):\n")
print(cap_full@optinfo$conv$opt)
if (length(cap_full@optinfo$conv$lme4$messages) > 0) {
  cat("lme4 convergence messages:\n")
  print(cap_full@optinfo$conv$lme4$messages)
} else {
  cat("No convergence warnings.\n")
}

save_glmer_coefs <- function(model, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study1_r_turncap_", suffix, "_coefficients.csv")), row.names = FALSE)
}
save_glmer_coefs(cap_reduced, "reduced")
save_glmer_coefs(cap_full, "full")

cap_lrt_df <- data.frame(
  outcome = "hit_turn_cap", test = "three_way_interaction_LRT",
  chisq = cap_lrt$Chisq[2], df = cap_lrt$Df[2], p_value = cap_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(cap_full), aic_reduced = AIC(cap_reduced)
)

cat("\nRandom-effects variance components (turn-cap model):\n")
tryCatch(print(VarCorr(cap_reduced)), error = function(e) {
  cat("(variance-component print failed non-fatally:", conditionMessage(e), ")\n")
})

# ── save LRT summary, both outcomes ──────────────────────────────────────

lrt_out <- rbind(turns_lrt_df, cap_lrt_df)
write.csv(lrt_out, file.path(out_dir, "study1_r_secondary_lrt_summary.csv"), row.names = FALSE)

cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
for (outcome in c("turns", "turncap")) {
  for (suffix in c("reduced", "full")) {
    cat(" -", file.path(out_dir, paste0("study1_r_", outcome, "_", suffix, "_coefficients.csv")), "\n")
  }
}
cat(" -", file.path(out_dir, "study1_r_secondary_lrt_summary.csv"), "\n")

saveRDS(list(turns_full = turns_full, turns_reduced = turns_reduced,
            cap_full = cap_full, cap_reduced = cap_reduced),
       file.path(out_dir, "study1_r_secondary_models.rds"))
cat(" -", file.path(out_dir, "study1_r_secondary_models.rds"), "(fitted model objects, for diagnostics)\n")
