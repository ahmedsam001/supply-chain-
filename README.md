# supply-chain-

End-to-End Enterprise Supply Chain Intelligence & Market Analytics Platform for Egyptian Retail & E-Commerce.

---

## 📌 Repository Architecture & Roadmap

This repository hosts a multi-phase data platform integrating live retail web scraping, operational ERP data generation, Lakehouse ingestion, conformed dimensional modeling, and predictive analytics:

```
supply-chain-/
├── README.md                          <-- Root Repository Roadmap & Overview
└── collect data/                      <-- Phase 1: Data Collection & Lakehouse Ingestion Platform
    ├── config/                        <-- Source definitions & extraction parameters
    ├── compliance/                    <-- Ethical scraping, robots.txt & rate-limiting checks
    ├── dags/                          <-- Apache Airflow daily orchestration DAGs
    ├── docs/                          <-- Data dictionaries, runbooks & architecture docs
    ├── dwh/                           <-- Lakehouse DDL, Databricks client & ERP generator
    │   ├── databricks_client.py       <-- REST API client for Unity Catalog Delta tables
    │   ├── databricks_schema.sql      <-- Schema DDL for live_market, supply_chain_stage, stage
    │   ├── pipeline.py                <-- Master Lakehouse ingestion pipeline
    │   └── supply_chain_generator.py  <-- Synthetic ERP operational data generator
    ├── extractors/                    <-- Production scrapers (Jumia, Carrefour, Tradeline, etc.)
    ├── geospatial/                    <-- Egyptian governorates, cities & branch geocoding
    ├── normalization/                 <-- EAN/GTIN barcode validation & 14-dept taxonomy
    ├── reports/                       <-- Audit reports & PDF documentation
    ├── samples/                       <-- Sample data observations and branch manifests
    ├── scripts/                       <-- Profiling, null auditing & smoke test utilities
    ├── tests/                         <-- Unit, integration & DAG test suite
    ├── validation/                    <-- Schemas, checksums & change detection
    ├── run_extraction.py              <-- CLI entrypoint for multi-store extraction
    ├── requirements.txt               <-- Python dependencies
    └── README.md                      <-- In-depth 14-page platform documentation & ERD
```

---

## 🚀 Phases

### Phase 1: Data Collection & Lakehouse Ingestion (`collect data/`)
- **Live Market Ingestion (`workspace.live_market`):** Scrapes real-world catalog and pricing data across 6 Egyptian retailers (Jumia, Carrefour, Tradeline, Dream 2000, 2B, Raya) capturing **4,971 products**, **4,971 price histories**, and **250 store branches** across 27 governorates.
- **Enterprise ERP Stage (`workspace.supply_chain_stage`):** Generates 8 realistic transactional tables (**19,400+ rows**) categorized into 10 operational supply chain archetypes with realistic OLTP nuances (timestamps, governorate spellings, stock status, purchase orders, shipments).
- **Lakehouse Parity & Daily DAG:** Full parity across local DuckDB and Databricks Delta Lake, orchestrated via Apache Airflow (`dags/egypt_ecommerce_dag.py`).

### Phase 2: Dimensional Modeling & Data Warehouse (Upcoming)
- Conformed Star Schema dimensional modeling (`workspace.stage` & production marts).
- Fact tables: Sales Orders, Procurement, Inventory Snapshots, Shipments, Market Price Variance.
- Dimensions: Conformed Product, Store, Branch, Supplier, Warehouse, Date & Egyptian Calendar.

### Phase 3: Analytics, BI & Machine Learning (Upcoming)
- Key Metrics: OTIF (On-Time In-Full), Stockout Rate, Lead Time Variance, Competitor Price Elasticity.
- ML Models: Demand forecasting, price optimization, dynamic replenishment thresholds.

---

For complete architecture details, schemas, and ER diagrams of the collection platform, see [`collect data/README.md`](collect%20data/README.md).
