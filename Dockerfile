FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_DEBUG=0 \
    HOST=0.0.0.0 \
    PORT=5000 \
    RUNTIME_DATA_DIR=/app/data/runtime

WORKDIR /app

# Runtime libraries commonly needed by geospatial Python wheels and Matplotlib.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Generate the static Folium/Leaflet map as part of the image build.
RUN python build_map.py

EXPOSE 5000

# Use a production WSGI server rather than Flask's development server.
# One worker is intentional because the current application uses shared
# per-selection runtime filenames under data/runtime/.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "run:app"]
