FROM scratch
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.version="RELEASE.2025-10-15T17-29-55Z.coastmas-source"
COPY minio /usr/bin/minio
COPY health /usr/bin/health
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY LICENSE /usr/share/minio/LICENSE
COPY source.tar.gz /usr/share/minio/source.tar.gz
COPY --chown=10001:10001 data /data
COPY --chown=10001:10001 --chmod=1777 tmp /tmp
ENV HOME=/tmp
USER 10001:10001
EXPOSE 9000 9001
HEALTHCHECK --interval=5s --timeout=4s --retries=20 CMD ["/usr/bin/health"]
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
