FROM golang:1.26-alpine AS build

ARG PACKWIZ_COMMIT=dfd8b68a4796c763e25bad50265ea1f1233e24f1
RUN CGO_ENABLED=0 go install "github.com/packwiz/packwiz@${PACKWIZ_COMMIT}"

FROM alpine:3.23
RUN apk add --no-cache ca-certificates
COPY --from=build /go/bin/packwiz /usr/local/bin/packwiz
ENTRYPOINT ["packwiz"]
