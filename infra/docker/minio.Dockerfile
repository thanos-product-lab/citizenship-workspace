# syntax=docker/dockerfile:1
#
# MinIO, built from its source tag.
#
# MinIO no longer distributes the community server as an image or a binary. Three sources
# went in turn: `bitnami/minio` (moved to `bitnamilegacy/`, then emptied), `docker.io/minio/
# minio` (stopped serving any tag, September 2026), and finally `quay.io/minio/minio` and
# `dl.min.io`, which by late September 2026 answered 401 and 410 Gone for every release. Only
# the source is still published, on GitHub under AGPL, so this builds the exact release the
# project has always run rather than switching to a different S3 server.
#
# **Why not a different S3-compatible server.** The upload size limit and content type live
# in the signed POST policy, and `tests/evidence/test_storage_minio.py` proves MinIO enforces
# them. Many S3 emulators accept a POST whatever its policy says, which would leave that test
# green while the control it checks had quietly stopped existing.
#
# **This file is the only place the release is pinned.** `docker-compose.yml` and CI both
# build it without overriding `MINIO_RELEASE`, so local and CI cannot run different
# servers; `tests/core/test_pinned_images.py` checks that.

ARG MINIO_RELEASE=RELEASE.2025-09-07T16-13-09Z

FROM golang:1.24-alpine AS build
ARG MINIO_RELEASE
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${MINIO_RELEASE}" https://github.com/minio/minio.git /src
WORKDIR /src
# MinIO's own release build (`make build`): static, no cgo, with the version stamped in by
# its ldflags generator so `minio --version` names the release rather than DEVELOPMENT.
RUN CGO_ENABLED=0 go build -tags kqueue -trimpath \
      -ldflags "$(go run buildscripts/gen-ldflags.go)" -o /out/minio .

FROM alpine:3.20
# `curl` for the health check; MinIO's `mc` client is a separate project and is not needed.
RUN apk add --no-cache ca-certificates curl
COPY --from=build /out/minio /usr/bin/minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
