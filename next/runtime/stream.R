# Fixed, maintainer-owned program. Inputs contain values, never R expressions.
request <- jsonlite::fromJSON('/work/input.json', simplifyVector=FALSE)
frame <- request$frame
parameters <- request$parameters
x <- do.call(rbind,lapply(frame$values,unlist))
colnames(x) <- unlist(frame$feature_names)
center <- rep(0,ncol(x)); spread <- rep(1,ncol(x))
if(isTRUE(frame$standardize)) {
  center <- colMeans(x); spread <- apply(x,2,sd)
  if(any(!is.finite(spread) | spread==0)) stop('Constant training feature cannot be standardized')
}
transform_x <- function(values) sweep(sweep(values,2,center),2,spread,'/')
x <- transform_x(x)
set.seed(as.integer(parameters$seed))
handler <- request$handler
if(handler=='ppci_mcdc') {
  fit <- PPCI::mcdc(x,K=as.integer(parameters$size),verb=0)
  tree <- lapply(seq_along(fit$Nodes),function(index) {
    node <- fit$Nodes[[index]]
    children <- which(fit$Parent==index)
    label <- if(length(children)==0) unique(fit$cluster[node$ixs]) else 0
    if(length(label)!=1) stop('Leaf does not identify one fitted cluster')
    list(v=as.numeric(node$v),b=as.numeric(node$b),children=as.integer(children),label=as.integer(label))
  })
  predict_fixed <- function(values) {
    values <- transform_x(values)
    current <- rep(1L,nrow(values)); labels <- integer(nrow(values))
    for(step in seq_along(tree)) {
      active <- which(labels==0)
      if(length(active)==0) break
      for(index in unique(current[active])) {
        rows <- active[current[active]==index]; node <- tree[[index]]
        if(length(node$children)==0) labels[rows] <- node$label
        else {
          # Source MCDC.R: first child receives X %*% v < b.
          left <- as.numeric(values[rows,,drop=FALSE] %*% node$v) < node$b
          current[rows] <- ifelse(left,node$children[1],node$children[2])
        }
      }
    }
    if(any(labels==0)) stop('Unassigned prediction')
    labels
  }
  original <- do.call(rbind,lapply(frame$values,unlist))
  if(any(predict_fixed(original)!=fit$cluster)) stop('Exported partition differs from original fitted assignments')
  fitted_values <- as.integer(fit$cluster)
  state <- list(tree=tree,rule='source_hyperplane_tree_strict_less_than',package='PPCI',version=as.character(packageVersion('PPCI')))
} else if(handler=='ppr_ols') {
  y <- unlist(frame$response)
  fit <- pprRFA::zppr.numeric(y,as.data.frame(x),nterms=as.integer(parameters$size),criteria='ols')
  predict_fixed <- function(values) {
    newdata <- as.data.frame(transform_x(values)); colnames(newdata) <- colnames(x)
    as.numeric(predict(fit$fit,newdata=newdata))
  }
  fitted_values <- as.numeric(predict(fit$fit))
  state <- list(p=fit$fit$p,q=fit$fit$q,smod=as.numeric(fit$fit$smod),rule='original_stats_predict_ppr',package='pprRFA',version=as.character(packageVersion('pprRFA')))
} else stop('Unregistered model')
emit <- function(value) {
  cat(jsonlite::toJSON(value,auto_unbox=TRUE,digits=17,na='null'), '\n', sep=''); flush(stdout())
}
emit(list(ready=TRUE,result=list(fit_count=1L,training_rows=nrow(x),fitted_values=fitted_values,center=center,scale=spread,feature_names=unlist(frame$feature_names),state=state)))
input <- file('stdin','r')
repeat {
  line <- readLines(input,n=1,warn=FALSE)
  if(length(line)==0) break
  batch <- jsonlite::fromJSON(line,simplifyVector=FALSE)
  values <- do.call(rbind,lapply(batch$values,unlist))
  if(ncol(values)!=ncol(x) || any(!is.finite(values))) stop('Invalid predictor batch')
  predicted <- predict_fixed(values)
  if(length(predicted)!=nrow(values) || any(!is.finite(predicted))) stop('Invalid original model prediction')
  emit(list(values=as.list(as.numeric(predicted))))
}
close(input)
