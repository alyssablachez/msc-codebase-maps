#!/usr/bin/env Rscript
# Study 2 vs. Study 3 -- DHARMa residual diagnostics for all 7 fitted
# GLMMs (f1, success, turns, turncap, total_input_tokens, total_cost,
# wall_time_seconds), same convention as scripts/stats_study1_r_dharma.R:
# full diagnostics (QQ + residual-vs-predicted, uniformity, dispersion,
# outliers, quantile trend, zero-inflation, residuals vs. each covariate
# and grouping factor) on the reduced models -- these are what the
# coefficient tables come from -- and a lighter uniformity+dispersion
# sanity check on the full models, since they're only used for the 3-way
# LRT. Covariates checked: submission_mode, map_condition, model_short,
# log_size_c (the fixed effects) plus issue_id, repo (the random-effect
# grouping factors).
#
# Usage:
#   Rscript scripts/stats_study2v3_r_dharma.R

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
data_csv <- file.path(root, "data", "stats_study2v3", "study2v3_for_r.csv")
out_dir <- file.path(root, "data", "stats_study2v3")
plot_dir <- file.path(out_dir, "dharma")
dir.create(plot_dir, showWarnings = FALSE)

df <- read.csv(data_csv, stringsAsFactors = FALSE)
df$submission_mode <- factor(df$submission_mode, levels = c("voluntary", "required"))
df$map_condition <- factor(df$map_condition, levels = c("structural", "temporal_frequency", "temporal_cochange", "all_tools"))
df$model_short <- factor(df$model_short, levels = c("deepseek_flash", "gpt_oss_120b", "ministral_3b", "nemotron_super"))
df$issue_id <- factor(df$issue_id)
df$repo <- factor(df$repo)
df$log_size_c <- df$log_codebase_size - mean(df$log_codebase_size)

models1 <- readRDS(file.path(out_dir, "study2v3_r_models.rds"))
models2 <- readRDS(file.path(out_dir, "study2v3_r_secondary_models.rds"))
models3 <- readRDS(file.path(out_dir, "study2v3_r_tokens_cost_walltime_models.rds"))

set.seed(42)
summary_rows <- list()

record <- function(model_name, test_name, statistic, p_value) {
  summary_rows[[length(summary_rows) + 1]] <<- data.frame(
    model = model_name, test = test_name, statistic = statistic, p_value = p_value
  )
}

run_full_diagnostics <- function(model, model_name) {
  cat("\n", strrep("=", 70), "\n", model_name, " -- DHARMa diagnostics\n", strrep("=", 70), "\n", sep = "")

  res <- simulateResiduals(model, n = 1000, seed = 42)

  png(file.path(plot_dir, paste0(model_name, "_qq_resid.png")), width = 1600, height = 800, res = 150)
  plot(res)
  dev.off()

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

  for (grp_name in c("issue_id", "repo")) {
    grp <- df[[grp_name]]
    png(file.path(plot_dir, paste0(model_name, "_resid_vs_", grp_name, ".png")), width = 1600, height = 800, res = 150)
    tryCatch(plotResiduals(res, form = grp, quantreg = FALSE),
             error = function(e) cat("  (plot vs.", grp_name, "failed:", conditionMessage(e), ")\n"))
    dev.off()
  }

  for (covar_name in c("submission_mode", "map_condition", "model_short", "log_size_c")) {
    covar <- df[[covar_name]]
    png(file.path(plot_dir, paste0(model_name, "_resid_vs_", covar_name, ".png")), width = 1600, height = 800, res = 150)
    tryCatch(plotResiduals(res, form = covar, quantreg = FALSE),
             error = function(e) cat("  (plot vs.", covar_name, "failed:", conditionMessage(e), ")\n"))
    dev.off()
  }
  cat("Saved plots to", plot_dir, "\n")
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

outcomes <- list(
  list(reduced = models1$f1_reduced,        full = models1$f1_full,        name = "f1"),
  list(reduced = models1$succ_reduced,      full = models1$succ_full,      name = "success"),
  list(reduced = models2$turns_reduced,     full = models2$turns_full,     name = "turns"),
  list(reduced = models2$cap_reduced,       full = models2$cap_full,       name = "turncap"),
  list(reduced = models3$tokens_reduced,    full = models3$tokens_full,    name = "total_input_tokens"),
  list(reduced = models3$cost_reduced,      full = models3$cost_full,      name = "total_cost"),
  list(reduced = models3$walltime_reduced,  full = models3$walltime_full,  name = "wall_time_seconds")
)

for (o in outcomes) {
  run_full_diagnostics(o$reduced, paste0(o$name, "_reduced"))
  run_light_check(o$full, paste0(o$name, "_full"))
}

summary_df <- do.call(rbind, summary_rows)
write.csv(summary_df, file.path(out_dir, "study2v3_r_dharma_summary.csv"), row.names = FALSE)
cat("\n", strrep("=", 70), "\nSaved:\n", strrep("=", 70), "\n", sep = "")
cat(" -", file.path(out_dir, "study2v3_r_dharma_summary.csv"), "\n")
cat(" -", plot_dir, "/*.png (diagnostic plots)\n")
