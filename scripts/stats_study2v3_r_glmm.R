#!/usr/bin/env Rscript
# Study 2 vs. Study 3 direct comparison (4th test in the agreed battery):
# does making tool use required rather than voluntary change outcomes,
# holding map conditions and delivery_mechanism="on_demand" fixed? Both
# studies share the same 4 map_condition levels and the same matched
# (model, issue, rep, map_condition) units -- submission_mode is the only
# thing that differs, so it plays the role map_condition played in the
# per-study batteries.
#
# Full:    outcome ~ submission_mode * map_condition * model_short + log_size_c + (1|issue_id) + (1|repo)
# Reduced: outcome ~ (submission_mode + map_condition + model_short)^2 + log_size_c + (1|issue_id) + (1|repo)
# LRT tests whether the required-vs-voluntary effect depends jointly on
# which map tool and which model -- log_size_c is included as a covariate
# but not part of the tested interaction, since the per-study batteries
# already answered the separate question of how map effects scale with
# codebase size.
#
# F1: glmmTMB, ordbeta() family. success: lme4::glmer, binomial family.
# Both with crossed random effects (1|issue_id) + (1|repo), same as
# scripts/stats_study{1,2,3}_r_glmm.R.
#
# Usage:
#   Rscript scripts/stats_study2v3_r_glmm.R

lib <- "~/R/library"
.libPaths(lib)

suppressMessages({
  library(lme4)
  library(glmmTMB)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg))
root <- normalizePath(file.path(dirname(script_path), ".."))
data_csv <- file.path(root, "data", "stats_study2v3", "study2v3_for_r.csv")
out_dir <- file.path(root, "data", "stats_study2v3")

df <- read.csv(data_csv, stringsAsFactors = FALSE)
df$submission_mode <- factor(df$submission_mode, levels = c("voluntary", "required"))
df$map_condition <- factor(df$map_condition, levels = c("structural", "temporal_frequency", "temporal_cochange", "all_tools"))
df$model_short <- factor(df$model_short, levels = c("deepseek_flash", "gpt_oss_120b", "ministral_3b", "nemotron_super"))
df$issue_id <- factor(df$issue_id)
df$repo <- factor(df$repo)
df$log_size_c <- df$log_codebase_size - mean(df$log_codebase_size)

cat(sprintf("Study 2 vs 3 sample: %d trials, %d issues, %d repos, %d models\n",
           nrow(df), nlevels(df$issue_id), nlevels(df$repo), nlevels(df$model_short)))

save_glmmTMB_coefs <- function(model, outcome, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients$cond)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study2v3_r_", outcome, "_", suffix, "_coefficients.csv")), row.names = FALSE)
}
save_glmer_coefs <- function(model, outcome, suffix) {
  coef_df <- as.data.frame(summary(model)$coefficients)
  coef_df$term <- rownames(coef_df)
  colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
  write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
            file.path(out_dir, paste0("study2v3_r_", outcome, "_", suffix, "_coefficients.csv")), row.names = FALSE)
}

# ── F1: glmmTMB, ordered beta family ─────────────────────────────────────

cat("\n", strrep("=", 70), "\n1. F1 -- glmmTMB, ordbeta() family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

f1_full <- glmmTMB(
  f1 ~ submission_mode * map_condition * model_short + log_size_c + (1 | issue_id) + (1 | repo),
  data = df, family = ordbeta()
)
f1_reduced <- glmmTMB(
  f1 ~ (submission_mode + map_condition + model_short)^2 + log_size_c + (1 | issue_id) + (1 | repo),
  data = df, family = ordbeta()
)

f1_lrt <- anova(f1_reduced, f1_full)
cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
print(f1_lrt)

cat("\nConvergence check (full model):\n")
cat("  fit$convergence (0 = converged):", f1_full$fit$convergence, "\n")
cat("  pdHess (positive-definite Hessian):", f1_full$sdr$pdHess, "\n")

save_glmmTMB_coefs(f1_reduced, "f1", "reduced")
save_glmmTMB_coefs(f1_full, "f1", "full")

f1_lrt_df <- data.frame(
  outcome = "f1", test = "submission_mode_x_map_x_model_LRT",
  chisq = f1_lrt$Chisq[2], df = f1_lrt[["Chi Df"]][2], p_value = f1_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(f1_full), aic_reduced = AIC(f1_reduced)
)

# ── success: lme4::glmer, binomial family ────────────────────────────────

cat("\n", strrep("=", 70), "\n2. success -- lme4::glmer, binomial family, crossed random effects\n", strrep("=", 70), "\n", sep = "")

succ_full <- glmer(
  success ~ submission_mode * map_condition * model_short + log_size_c + (1 | issue_id) + (1 | repo),
  data = df, family = binomial,
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
succ_reduced <- glmer(
  success ~ (submission_mode + map_condition + model_short)^2 + log_size_c + (1 | issue_id) + (1 | repo),
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

save_glmer_coefs(succ_reduced, "success", "reduced")
save_glmer_coefs(succ_full, "success", "full")

succ_lrt_df <- data.frame(
  outcome = "success", test = "submission_mode_x_map_x_model_LRT",
  chisq = succ_lrt$Chisq[2], df = succ_lrt$Df[2], p_value = succ_lrt$`Pr(>Chisq)`[2],
  aic_full = AIC(succ_full), aic_reduced = AIC(succ_reduced)
)

# ── save LRT summary, both outcomes ──────────────────────────────────────

lrt_out <- rbind(f1_lrt_df, succ_lrt_df)
write.csv(lrt_out, file.path(out_dir, "study2v3_r_lrt_summary.csv"), row.names = FALSE)

cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
for (outcome in c("f1", "success")) {
  for (suffix in c("reduced", "full")) {
    cat(" -", file.path(out_dir, paste0("study2v3_r_", outcome, "_", suffix, "_coefficients.csv")), "\n")
  }
}
cat(" -", file.path(out_dir, "study2v3_r_lrt_summary.csv"), "\n")

saveRDS(list(f1_full = f1_full, f1_reduced = f1_reduced,
            succ_full = succ_full, succ_reduced = succ_reduced),
       file.path(out_dir, "study2v3_r_models.rds"))
cat(" -", file.path(out_dir, "study2v3_r_models.rds"), "(fitted model objects, for diagnostics)\n")
