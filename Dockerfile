FROM python:3.11-slim

WORKDIR /app

# All packages in requirements.txt ship pre-built wheels — no gcc needed
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY config.py   ./
COPY app.py      ./
COPY data/       ./data/
COPY analysis/   ./analysis/
COPY backtest/   ./backtest/
COPY monitor/    ./monitor/

# Streamlit config
RUN mkdir -p /root/.streamlit
COPY .streamlit/config.toml /root/.streamlit/config.toml

# watchlist.json is stored in this volume
VOLUME ["/app/data_store"]
ENV WATCHLIST_DIR=/app/data_store

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

ENTRYPOINT ["streamlit", "run", "app.py", \
            "--server.port=8501", \
            "--server.address=0.0.0.0", \
            "--server.headless=true"]
