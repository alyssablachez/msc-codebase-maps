#!/usr/bin/env Rscript
# Study 2 vs. Study 3 -- total_input_tokens, total_cost, wall_time_seconds,
# all via glmmTMB Gamma(link="log"), same submission_mode * map_condition *
# model_short + log_size_c structure as scripts/stats_study2v3_r_glmm.R
# (see scripts/stats_study1_r_tokens_cost_walltime.R for why Gamma-log is
# the right family here). This is the most consequential of the three
# secondary metrics for this comparison -- Study 2's wall-time effect was
# uniformly negative (faster) across models, Study 3's split sharply by
# model (gpt-oss-120b/nemotron-super slower, ministral-3b faster), so a
# genuine submission_mode x model interaction is expected here.
#
# Usage:
#   Rscript scripts/stats_study2v3_r_tokens_cost_walltime.R

lib <- "~/R/library"
.libPaths(lib)

suppressMessages({
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

fit_one <- function(outcome_col, out_dir) {
  cat("\n", strrep("=", 70), "\n", outcome_col, " -- glmmTMB, Gamma(link=\"log\"), crossed random effects\n", strrep("=", 70), "\n", sep = "")

  fml_full <- as.formula(paste0(
    outcome_col, " ~ submission_mode * map_condition * model_short + log_size_c + (1 | issue_id) + (1 | repo)"
  ))
  fml_reduced <- as.formula(paste0(
    outcome_col, " ~ (submission_mode + map_condition + model_short)^2 + log_size_c + (1 | issue_id) + (1 | repo)"
  ))

  m_full <- glmmTMB(fml_full, data = df, family = Gamma(link = "log"))
  m_reduced <- glmmTMB(fml_reduced, data = df, family = Gamma(link = "log"))

  lrt <- anova(m_reduced, m_full)
  cat("\nLikelihood-ratio test, full (3-way interaction) vs. reduced:\n")
  print(lrt)

  cat("\nConvergence check (full model):\n")
  cat("  fit$convergence (0 = converged):", m_full$fit$convergence, "\n")
  cat("  pdHess (positive-definite Hessian):", m_full$sdr$pdHess, "\n")

  save_coefs <- function(model, suffix) {
    coef_df <- as.data.frame(summary(model)$coefficients$cond)
    coef_df$term <- rownames(coef_df)
    colnames(coef_df) <- c("estimate", "std_error", "z_value", "p_value", "term")
    write.csv(coef_df[, c("term", "estimate", "std_error", "z_value", "p_value")],
              file.path(out_dir, paste0("study2v3_r_", outcome_col, "_", suffix, "_coefficients.csv")), row.names = FALSE)
  }
  save_coefs(m_reduced, "reduced")
  save_coefs(m_full, "full")

  list(
    lrt_row = data.frame(
      outcome = outcome_col, test = "submission_mode_x_map_x_model_LRT",
      chisq = lrt$Chisq[2], df = lrt[["Chi Df"]][2], p_value = lrt$`Pr(>Chisq)`[2],
      aic_full = AIC(m_full), aic_reduced = AIC(m_reduced)
    ),
    full = m_full, reduced = m_reduced
  )
}

tokens_result <- fit_one("total_input_tokens", out_dir)
cost_result <- fit_one("total_cost", out_dir)
walltime_result <- fit_one("wall_time_seconds", out_dir)

lrt_out <- rbind(tokens_result$lrt_row, cost_result$lrt_row, walltime_result$lrt_row)
write.csv(lrt_out, file.path(out_dir, "study2v3_r_tokens_cost_walltime_lrt_summary.csv"), row.names = FALSE)

cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
for (outcome_col in c("total_input_tokens", "total_cost", "wall_time_seconds")) {
  for (suffix in c("reduced", "full")) {
    cat(" -", file.path(out_dir, paste0("study2v3_r_", outcome_col, "_", suffix, "_coefficients.csv")), "\n")
  }
}
cat(" -", file.path(out_dir, "study2v3_r_tokens_cost_walltime_lrt_summary.csv"), "\n")

saveRDS(list(tokens_full = tokens_result$full, tokens_reduced = tokens_result$reduced,
            cost_full = cost_result$full, cost_reduced = cost_result$reduced,
            walltime_full = walltime_result$full, walltime_reduced = walltime_result$reduced),
       file.path(out_dir, "study2v3_r_tokens_cost_walltime_models.rds"))
cat(" -", file.path(out_dir, "study2v3_r_tokens_cost_walltime_models.rds"), "(fitted model objects, for diagnostics)\n")
