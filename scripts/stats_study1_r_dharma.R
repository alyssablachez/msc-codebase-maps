#!/usr/bin/env Rscript
# Study 1 -- DHARMa residual diagnostics for the fitted GLMMs saved by
# scripts/stats_study1_r_glmm.R (data/stats_study1/study1_r_models.rds).
#
# Primary inferential models are the "reduced" ones (all pairwise
# interactions, no 3-way) -- these are what the coefficient tables come
# from, so they get the full diagnostic treatment: simulated-residual QQ +
# residual-vs-predicted plot, uniformity (KS), dispersion, outliers,
# quantile trends, and residuals recomputed against each random-effect
# grouping factor (issue_id, repo) plus the fixed covariates
# (map_condition, model_short, log_size_c). The "full" models (used only
# for the 3-way-interaction LRT) get the lighter uniformity+dispersion
# check as a sanity pass -- if a full model were badly misspecified the
# LRT built on it wouldn't mean much either.
#
# Usage:
#   Rscript scripts/stats_study1_r_dharma.R

lib <- "~/R/library"
.libPaths(lib)

suppressMessages({
  library(lme4)
  library(glmmTMB)
  library(DHARMa)
})

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg))
root <- normalizePath(file.path(dirname(script_path), ".."))
data_csv <- file.path(root, "data", "stats_study1", "study1_for_r.csv")
out_dir <- file.path(root, "data", "stats_study1")
plot_dir <- file.path(out_dir, "dharma")
dir.create(plot_dir, showWarnings = FALSE)

df <- read.csv(data_csv, stringsAsFactors = FALSE)
df$map_condition <- factor(df$map_condition, levels = c("baseline", "structural", "temporal_frequency", "temporal_cochange"))
df$model_short <- factor(df$model_short, levels = c("deepseek_flash", "gpt_oss_120b", "ministral_3b", "nemotron_super"))
df$issue_id <- factor(df$issue_id)
df$repo <- factor(df$repo)
df$log_size_c <- df$log_codebase_size - mean(df$log_codebase_size)

models <- readRDS(file.path(out_dir, "study1_r_models.rds"))

set.seed(42)

summary_rows <- list()

record <- function(model_name, test_name, statistic, p_value, note = "") {
  summary_rows[[length(summary_rows) + 1]] <<- data.frame(
    model = model_name, test = test_name, statistic = statistic, p_value = p_value, note = note
  )
}

run_full_diagnostics <- function(model, model_name) {
  cat("\n", strrep("=", 70), "\n", model_name, " -- DHARMa diagnostics\n", strrep("=", 70), "\n", sep = "")

  res <- simulateResiduals(model, n = 1000, seed = 42)

  png(file.path(plot_dir, paste0(model_name, "_qq_resid.png")), width = 1600, height = 800, res = 150)
  plot(res)
  dev.off()
  cat("Saved:", file.path(plot_dir, paste0(model_name, "_qq_resid.png")), "\n")

  u <- testUniformity(res, plot = FALSE)
  cat(sprintf("  Uniformity (KS test):        D = %.4f, p = %.4f\n", u$statistic, u$p.value))
  record(model_name, "uniformity_ks", u$statistic, u$p.value)

  d <- testDispersion(res, plot = FALSE)
  cat(sprintf("  Dispersion:                   ratio = %.4f, p = %.4f\n", d$statistic, d$p.value))
  record(model_name, "dispersion", d$statistic, d$p.value)

  o <- tryCatch(testOutliers(res, plot = FALSE), error = function(e) NULL)
  if (!is.null(o)) {
    cat(sprintf("  Outliers (bootstrap):         ratio = %.4f, p = %.4f\n", o$statistic, o$p.value))
    record(model_name, "outliers", o$statistic, o$p.value)
  }

  q <- tryCatch(testQuantiles(res, plot = FALSE), error = function(e) NULL)
  if (!is.null(q)) {
    cat(sprintf("  Quantile trend (vs. predicted): p = %.4f\n", q$p.value))
    record(model_name, "quantile_trend", NA, q$p.value)
  }

  zi <- tryCatch(testZeroInflation(res, plot = FALSE), error = function(e) NULL)
  if (!is.null(zi)) {
    cat(sprintf("  Zero-inflation:               ratio = %.4f, p = %.4f\n", zi$statistic, zi$p.value))
    record(model_name, "zero_inflation", zi$statistic, zi$p.value)
  }

  # Residuals vs. each random-effect grouping factor and each fixed covariate.
  for (grp_name in c("issue_id", "repo")) {
    grp <- df[[grp_name]]
    png(file.path(plot_dir, paste0(model_name, "_resid_vs_", grp_name, ".png")), width = 1600, height = 800, res = 150)
    tryCatch(plotResiduals(res, form = grp, quantreg = FALSE),
             error = function(e) cat("  (plot vs.", grp_name, "failed:", conditionMessage(e), ")\n"))
    dev.off()
    grp_test <- tryCatch(testCategorical(res, catPred = grp, plot = FALSE), error = function(e) NULL)
    if (!is.null(grp_test) && !is.null(grp_test$homogeneity)) {
      cat(sprintf("  Within-group homogeneity vs. %s: p = %.4f (Levene-type)\n", grp_name, grp_test$homogeneity$`Pr(>F)`[1]))
      record(model_name, paste0("homogeneity_", grp_name), NA, grp_test$homogeneity$`Pr(>F)`[1])
    }
  }

  for (covar_name in c("map_condition", "model_short", "log_size_c")) {
    covar <- df[[covar_name]]
    png(file.path(plot_dir, paste0(model_name, "_resid_vs_", covar_name, ".png")), width = 1600, height = 800, res = 150)
    tryCatch(plotResiduals(res, form = covar, quantreg = FALSE),
             error = function(e) cat("  (plot vs.", covar_name, "failed:", conditionMessage(e), ")\n"))
    dev.off()
  }
  cat("Saved per-covariate/grouping residual plots to", plot_dir, "\n")

  res
}

run_light_check <- function(model, model_name) {
  cat("\n", strrep("=", 70), "\n", model_name, " -- DHARMa light check (sanity pass for the LRT model)\n", strrep("=", 70), "\n", sep = "")
  res <- simulateResiduals(model, n = 1000, seed = 42)
  u <- testUniformity(res, plot = FALSE)
  d <- testDispersion(res, plot = FALSE)
  cat(sprintf("  Uniformity (KS test): D = %.4f, p = %.4f\n", u$statistic, u$p.value))
  cat(sprintf("  Dispersion:           ratio = %.4f, p = %.4f\n", d$statistic, d$p.value))
  record(model_name, "uniformity_ks", u$statistic, u$p.value)
  record(model_name, "dispersion", d$statistic, d$p.value)
}

# ── F1 model (glmmTMB, ordbeta) ──────────────────────────────────────────
run_full_diagnostics(models$f1_reduced, "f1_reduced")
run_light_check(models$f1_full, "f1_full")

# ── success model (lme4::glmer, binomial) ────────────────────────────────
run_full_diagnostics(models$succ_reduced, "succ_reduced")
run_light_check(models$succ_full, "succ_full")

summary_df <- do.call(rbind, summary_rows)
write.csv(summary_df, file.path(out_dir, "study1_r_dharma_summary.csv"), row.names = FALSE)
cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
cat(" -", file.path(out_dir, "study1_r_dharma_summary.csv"), "\n")
cat(" -", plot_dir, "/*.png (diagnostic plots)\n")
