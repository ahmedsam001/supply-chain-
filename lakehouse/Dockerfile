FROM python:3.11-slim

WORKDIR /app

# Install lightweight Lakehouse dependencies only (DuckDB + dbt-duckdb + Azure Blob SDK)
COPY lakehouse/requirements-lakehouse.txt /app/lakehouse/requirements-lakehouse.txt
RUN pip install --no-cache-dir -r /app/lakehouse/requirements-lakehouse.txt

# Copy dbt project, Azure sync helper, and Lakehouse runner
COPY transformations /app/transformations
COPY data_collection/azure_sync.py /app/data_collection/azure_sync.py
COPY data_collection/dwh/azure_sync.py /app/data_collection/dwh/azure_sync.py
COPY lakehouse/run_lakehouse.py /app/lakehouse/run_lakehouse.py

# Ensure dwh directory exists for pulled DuckDB state
RUN mkdir -p /app/data_collection/dwh /app/data_collection/data

# Default to daily full Lakehouse build; override args with ["--mode", "hourly"] for hourly job
ENTRYPOINT ["python", "lakehouse/run_lakehouse.py"]
CMD ["--mode", "daily"]
