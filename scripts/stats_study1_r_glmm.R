#!/usr/bin/env Rscript
# Study 1 (map-as-context vs. baseline) -- the "real" GLMM fits, replacing
# the Python workarounds documented in scripts/stats_study1_f1.py and
# scripts/stats_study1_success.py:
#   - F1: glmmTMB with an ordered-beta family (family = ordbeta()) instead
#     of a Binomial-family quasi-likelihood trick -- ordbeta is designed
#     for exactly this data shape (continuous [0,1] with real point mass
#     at both 0 and 1), and it supports true crossed random effects.
#   - success: lme4::glmer(family = binomial) -- genuine maximum
#     likelihood instead of BinomialBayesMixedGLM's variational-Bayes
#     approximation, with a real anova()-based LRT.
# Both include (1|issue_id) + (1|repo) simultaneously (crossed random
# effects), which no single model in the Python version could do at once.
#
# Usage:
#   Rscript scripts/stats_study1_r_glmm.R

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

cat(sprintf("Study 1 primary sample: %d trials, %d issues, %d repos, %d models\n",
           nrow(df), nlevels(df$issue_id), nlevels(df$repo), nlevels(df$model_short)))

# ── F1: glmmTMB, ordered beta family ─────────────────────────────────────

cat("\n", strrep("=", 70), "\n1. F1 -- glmmTMB, ordbeta() family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

f1_full <- glmmTMB(
  f1 ~ map_condition * log_size_c * model_short + (1 | issue_id) + (1 | repo),
  data = df, family = ordbeta()
)
f1_reduced <- glmmTMB(
  f1 ~ (map_condition + log_size_c + model_short)^2 + (1 | issue_id) + (1 | repo),
  data = df, family = ordbeta()
)

f1_lrt <- anova(f1_reduced, f1_full)
cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
print(f1_lrt)

cat("\nConvergence check (full model):\n")
print(summary(f1_full)$sdr$pdHess)
cat("Warnings, if any, are printed above by glmmTMB itself at fit time.\n")

save_glmmTMB_coefs <- function(model, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients$cond)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study1_r_f1_", suffix, "_coefficients.csv")), row.names = FALSE)
}
save_glmmTMB_coefs(f1_reduced, "reduced")
save_glmmTMB_coefs(f1_full, "full")

f1_lrt_df <- data.frame(
  outcome = "f1", test = "three_way_interaction_LRT",
  chisq = f1_lrt$Chisq[2], df = f1_lrt[["Chi Df"]][2], p_value = f1_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(f1_full), aic_reduced = AIC(f1_reduced)
)

# Random-effects variance components -- how much of the variance is
# actually attributable to issue-level and repo-level clustering.
vc <- VarCorr(f1_reduced)
cat("\nRandom-effects variance components (F1 model):\n")
# glmmTMB's own print.VarCorr method calls the base-R %||% operator
# (R >= 4.4 only; this environment is R 4.3.3) and errors -- sidestep it
# entirely via as.data.frame(), which uses a different, working code path,
# wrapped in tryCatch as a safety net regardless.
tryCatch(print(as.data.frame(vc)), error = function(e) {
  cat("(variance-component print failed non-fatally:", conditionMessage(e), ")\n")
})

# ── success: lme4::glmer, binomial family ────────────────────────────────

cat("\n", strrep("=", 70), "\n2. success -- lme4::glmer, binomial family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

succ_full <- glmer(
  success ~ map_condition * log_size_c * model_short + (1 | issue_id) + (1 | repo),
  data = df, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
succ_reduced <- glmer(
  success ~ (map_condition + log_size_c + model_short)^2 + (1 | issue_id) + (1 | repo),
  data = df, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)

succ_lrt <- anova(succ_reduced, succ_full)
cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
print(succ_lrt)

cat("\nConvergence check (full model):\n")
print(succ_full@optinfo$conv$opt)
if (length(succ_full@optinfo$conv$lme4$messages) > 0) {
  cat("lme4 convergence messages:\n")
  print(succ_full@optinfo$conv$lme4$messages)
} else {
  cat("No convergence warnings.\n")
}

save_glmer_coefs <- function(model, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study1_r_success_", suffix, "_coefficients.csv")), row.names = FALSE)
}
save_glmer_coefs(succ_reduced, "reduced")
save_glmer_coefs(succ_full, "full")

succ_lrt_df <- data.frame(
  outcome = "success", test = "three_way_interaction_LRT",
  chisq = succ_lrt$Chisq[2], df = succ_lrt$Df[2], p_value = succ_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(succ_full), aic_reduced = AIC(succ_reduced)
)

cat("\nRandom-effects variance components (success model):\n")
tryCatch(print(VarCorr(succ_reduced)), error = function(e) {
  cat("(variance-component print failed non-fatally:", conditionMessage(e), ")\n")
})

# ── save LRT summary, both outcomes ──────────────────────────────────────

lrt_out <- rbind(f1_lrt_df, succ_lrt_df)
write.csv(lrt_out, file.path(out_dir, "study1_r_lrt_summary.csv"), row.names = FALSE)

cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
for (outcome in c("f1", "success")) {
  for (suffix in c("reduced", "full")) {
    cat(" -", file.path(out_dir, paste0("study1_r_", outcome, "_", suffix, "_coefficients.csv")), "\n")
  }
}
cat(" -", file.path(out_dir, "study1_r_lrt_summary.csv"), "\n")

# Save fitted model objects too, for the diagnostics pass (DHARMa) next.
saveRDS(list(f1_full = f1_full, f1_reduced = f1_reduced,
            succ_full = succ_full, succ_reduced = succ_reduced),
       file.path(out_dir, "study1_r_models.rds"))
cat(" -", file.path(out_dir, "study1_r_models.rds"), "(fitted model objects, for diagnostics)\n")
