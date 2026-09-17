ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN apk add --no-cache jpeg tiff openjpeg zlib libwebp && \
    apk add --no-cache --virtual .build-deps gcc musl-dev jpeg-dev tiff-dev openjpeg-dev zlib-dev libwebp-dev python3-dev && \
    pip install --no-cache-dir . && \
    apk del .build-deps

COPY run.sh /
RUN chmod a+x /run.sh
CMD ["/run.sh"]

