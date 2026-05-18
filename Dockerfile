FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir .

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips='*' make uvicorn honor X-Forwarded-Proto
# from Railway's edge proxy. Without these, Starlette generates 307 redirects with
# Location: http://... (downgrade), and the MCP Streamable HTTP client refuses to
# follow them. See task el-cg0zq.
CMD uvicorn app.server:http_app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
