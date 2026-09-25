# Fixed adapter; no user-provided expressions or scripts are evaluated.
args <- commandArgs(trailingOnly = TRUE)
input <- jsonlite::fromJSON('/work/input.json', simplifyVector = FALSE)$frame
parameters <- jsonlite::fromJSON('/work/parameters.json')
x <- do.call(rbind, lapply(input$values, unlist))
colnames(x) <- unlist(input$feature_names)
row_ids <- unlist(input$row_ids)
center <- rep(0, ncol(x))
spread <- rep(1, ncol(x))
if (isTRUE(input$standardize)) {
  center <- colMeans(x)
  spread <- apply(x, 2, sd)
  if (any(!is.finite(spread) | spread == 0)) stop('Cannot standardize a constant feature')
  x <- sweep(sweep(x, 2, center), 2, spread, '/')
}
set.seed(as.integer(parameters$seed))
preprocessing <- list(standardize = isTRUE(input$standardize), center = center, scale = spread,
                      feature_names = unlist(input$feature_names), feature_units = unlist(input$feature_units))
if (args[1] == 'ppci_mcdc') {
  fit <- PPCI::mcdc(x, K = as.integer(parameters$clusters), verb = 0)
  labels <- as.integer(fit$cluster)
  if (length(labels) != nrow(x) || anyNA(labels)) stop('Incomplete clustering output')
  result <- list(method = 'PPCI::mcdc', package_version = as.character(packageVersion('PPCI')),
                 row_ids = row_ids, cluster = labels, preprocessing = preprocessing)
} else if (args[1] == 'ppr_ols') {
  y <- unlist(input$response)
  # Upstream exports numeric implementation but does not register its S3 method.
  # Call that original implementation explicitly; do not replace the algorithm.
  fit <- pprRFA::zppr.numeric(y, as.data.frame(x), nterms = as.integer(parameters$terms), criteria = 'ols')
  predicted <- as.numeric(predict(fit$fit))
  if (length(predicted) != length(y) || any(!is.finite(predicted))) stop('Invalid regression output')
  result <- list(method = 'pprRFA::zppr.numeric', package_version = as.character(packageVersion('pprRFA')),
                 row_ids = row_ids, fitted = predicted, residuals = y - predicted,
                 response_unit = input$response_unit, rmse = sqrt(mean((y - predicted)^2)),
                 prediction_scope = 'training_fit_not_external_validation', preprocessing = preprocessing)
} else stop('Unknown registered method')
cat(jsonlite::toJSON(list(result = result), auto_unbox = TRUE, digits = 16, na = 'null'))
