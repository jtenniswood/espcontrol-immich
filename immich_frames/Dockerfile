ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

ARG SOURCE_COMMIT=local
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY custom_components ./custom_components
RUN apk add --no-cache python3 py3-pip jpeg tiff openjpeg zlib libwebp && \
    apk add --no-cache --virtual .build-deps gcc musl-dev jpeg-dev tiff-dev openjpeg-dev zlib-dev libwebp-dev python3-dev && \
    python3 -m pip install --break-system-packages --no-cache-dir . && \
    apk del .build-deps

COPY immich_frames/run.sh /run.sh
RUN chmod a+x /run.sh
CMD ["/run.sh"]
