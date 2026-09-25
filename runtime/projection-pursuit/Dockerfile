FROM r-base:4.6.1@sha256:35e6abb402187fc899df89d5b1037126d412c4987d57828a860d011af745cd37
RUN Rscript --vanilla -e 'options(timeout=120); install.packages(c("Rcpp", "RcppArmadillo", "rARPACK", "jsonlite", "evd", "nsRFA"), repos="https://cloud.r-project.org", Ncpus=2); stopifnot(all(vapply(c("Rcpp", "RcppArmadillo", "rARPACK", "jsonlite", "evd", "nsRFA"), requireNamespace, logical(1), quietly=TRUE)))'
COPY PPCI-master /opt/source/PPCI
COPY pprRFA-master /opt/source/pprRFA
RUN R CMD INSTALL /opt/source/PPCI /opt/source/pprRFA

COPY runner.R /opt/coastmas/runner.R
