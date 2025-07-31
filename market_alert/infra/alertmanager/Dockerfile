FROM alpine AS builder
RUN apk add --no-cache gettext

FROM prom/alertmanager:latest AS upstream

FROM alpine
RUN apk add --no-cache gettext
COPY --from=builder /usr/bin/envsubst /usr/local/bin/envsubst

COPY --from=upstream /bin/alertmanager /bin/alertmanager
COPY --from=upstream /bin/amtool /bin/amtool
COPY --from=upstream /etc/alertmanager /etc/alertmanager
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN mkdir -p /alertmanager && chown -R nobody:nobody /etc/alertmanager /alertmanager
USER nobody
WORKDIR /alertmanager
ENTRYPOINT ["/entrypoint.sh"]
CMD ["--storage.path=/alertmanager"]
