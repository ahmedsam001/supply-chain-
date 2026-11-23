-- ============================================================================
-- Azure Synapse Serverless SQL Pool — Gold Galaxy Schema Views over ADLS Gen2
-- ============================================================================
-- Storage Account: stegyptretaillake2026 (container: gold)
-- Pricing: ~$5 per 1 TB scanned (~$0.10/month for this dataset).
-- Power BI connects directly to this SQL endpoint with DirectQuery or Import!
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = 'retail_lakehouse_gold')
BEGIN
    CREATE DATABASE retail_lakehouse_gold;
END;
GO
USE retail_lakehouse_gold;
GO

-- Conformed Dimensions (7 Core + 6 Junk Dimensions)
CREATE OR ALTER VIEW dbo.dim_date AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_date/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_store AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_store/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_branch AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_branch/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_warehouse AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_warehouse/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_supplier AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_supplier/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_customer AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_customer/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_product AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_product/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_order_details AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_order_details/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_shipment_details AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_shipment_details/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_po_details AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_po_details/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_inventory_status AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_inventory_status/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_market_status AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_market_status/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.dim_price_event_status AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/dim_price_event_status/*.parquet', FORMAT='PARQUET') AS r;
GO

-- Pure Gold Fact Tables (6 Facts: Keys + Dates + Numbers only)
CREATE OR ALTER VIEW dbo.fct_sales AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_sales/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.fct_shipments AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_shipments/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.fct_procurement AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_procurement/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.fct_inventory_snapshots AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_inventory_snapshots/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.fct_market_snapshots AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_market_snapshots/*.parquet', FORMAT='PARQUET') AS r;
GO
CREATE OR ALTER VIEW dbo.fct_price_changes AS
SELECT * FROM OPENROWSET(BULK 'https://stegyptretaillake2026.dfs.core.windows.net/gold/fct_price_changes/*.parquet', FORMAT='PARQUET') AS r;
GO
