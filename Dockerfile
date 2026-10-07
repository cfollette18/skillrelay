FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 skillrelay \
    && mkdir /data && chown skillrelay:skillrelay /data
USER skillrelay
VOLUME ["/data"]
EXPOSE 8765
ENTRYPOINT ["skillrelay", "--home", "/data", "serve", "--transport", "http", "--host", "0.0.0.0"]
