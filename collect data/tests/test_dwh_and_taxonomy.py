"""
Unit & Integration Tests for Department Taxonomy & DWH Pipeline.

Covers:
1. Canonical department classification (English & Arabic) across all 13 departments:
   - mobiles_tablets, computing, electronics_tv, home_appliances
   - fresh_meats_poultry, dairy_cheese_eggs, fruits_vegetables, grocery_pantry
   - beverages, bakery_snacks, frozen_foods, household_cleaning, personal_care_beauty
2. Department CLI alias resolution (--department phones, meats, laptops, electronics, etc.)
3. DuckDB DWH schema creation, dim_department seeding, and isolated SQL views (v_dept_*)
4. Department-partitioned pipeline execution and isolated department JSON output
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from dwh.pipeline import get_db, run_pipeline
from normalization.taxonomy import (
    DEPARTMENT_CATALOG,
    Department,
    classify_product,
    resolve_department_alias,
)


class TestDepartmentTaxonomy:
    @pytest.mark.parametrize(
        "product_name,category,expected_dept",
        [
            # Mobiles & Tablets
            ("Samsung Galaxy A55 5G 256GB", "Mobiles", Department.MOBILES_TABLETS.value),
            ("موبايل آيفون 16 برو ماكس 256 جيجا", None, Department.MOBILES_TABLETS.value),
            ("شاحن حائط Cardoo بقوة 45 وات PD بمنفذي USB-C", "Chargers", Department.MOBILES_TABLETS.value),
            ("Apple AirPods Pro 2nd Gen", "Accessories", Department.MOBILES_TABLETS.value),
            # Computing & Laptops
            ("Lenovo LOQ 15IAX9 Gaming Laptop Core i7", "Laptops", Department.COMPUTING.value),
            ("لابتوب ديل انسبيرون 15 رام 16 جيجا", None, Department.COMPUTING.value),
            # Electronics & TVs
            ("LG 55 Inch 4K UHD Smart TV", "TVs", Department.ELECTRONICS_TV.value),
            ("تليفزيون سامسونج 65 بوصة سمارت 4K", None, Department.ELECTRONICS_TV.value),
            ("Sony PlayStation 5 Slim Console", "Electronics", Department.ELECTRONICS_TV.value),
            # Home Appliances
            ("ثلاجة شارب انفرتر 450 لتر ديجيتال", "Appliances", Department.HOME_APPLIANCES.value),
            ("Tornado Gas Water Heater 10L", "Home Appliances", Department.HOME_APPLIANCES.value),
            ("قلاية بدون زيت إير فراير فيليبس", None, Department.HOME_APPLIANCES.value),
            # Fresh Meats, Poultry & Seafood
            ("Fresh Beef Minced Meat 1kg", "Supermarket", Department.FRESH_MEATS_POULTRY.value),
            ("مكعبات لحم بقري بلدي كندوز 1 كيلو", "البقالة", Department.FRESH_MEATS_POULTRY.value),
            ("صدور دجاج بانيه طازج شهد 1 كجم", None, Department.FRESH_MEATS_POULTRY.value),
            ("جمبري وسط مقشر طازج", None, Department.FRESH_MEATS_POULTRY.value),
            # Dairy, Cheese & Eggs
            ("Juhayna Full Cream Milk 1.5L", "Supermarket", Department.DAIRY_CHEESE_EGGS.value),
            ("جبنة موتزاريلا دومتي 500 جرام", None, Department.DAIRY_CHEESE_EGGS.value),
            ("كرتونة بيض أبيض 30 بيضة", None, Department.DAIRY_CHEESE_EGGS.value),
            # Fruits & Vegetables
            ("طماطم بلدي طازجة 1 كجم", None, Department.FRUITS_VEGETABLES.value),
            ("Fresh Red Apple Fruit 1kg", "Produce", Department.FRUITS_VEGETABLES.value),
            # Grocery & Pantry
            ("أرز مصري الضحى 5 كجم", "Supermarket", Department.GROCERY_PANTRY.value),
            ("Crystal Sunflower Cooking Oil 2.2L", "Grocery", Department.GROCERY_PANTRY.value),
            ("مكرونة الملكة 400 جرام", None, Department.GROCERY_PANTRY.value),
            # Beverages
            ("شاي العروسة ناعم 250 جرام", None, Department.BEVERAGES.value),
            ("Nescafe Classic Instant Coffee 200g", "Beverages", Department.BEVERAGES.value),
            # Bakery & Snacks
            ("خبز توست ريتش بيك أبيض", None, Department.BAKERY_SNACKS.value),
            ("Cadbury Dairy Milk Chocolate Bar", "Snacks", Department.BAKERY_SNACKS.value),
            # Frozen Foods
            ("بطاطس نصف مقلية مجمدة فارم فريتس 2.5 كجم", None, Department.FROZEN_FOODS.value),
            ("Frozen Chicken Nuggets 1kg", None, Department.FROZEN_FOODS.value),
            # Household & Cleaning
            ("مسحوق غسيل أريال أوتوماتيك 4 كجم", None, Department.HOUSEHOLD_CLEANING.value),
            ("Dettol Antiseptic Disinfectant Liquid", "Cleaning", Department.HOUSEHOLD_CLEANING.value),
            # Personal Care & Beauty
            ("شامبو بانتين ضد القشرة 400 مل", None, Department.PERSONAL_CARE_BEAUTY.value),
            ("Pampers Baby Dry Diapers Size 4", "Baby", Department.PERSONAL_CARE_BEAUTY.value),
        ],
    )
    def test_classify_product_across_all_13_departments(
        self, product_name, category, expected_dept
    ):
        result = classify_product(product_name=product_name, category=category)
        assert result["department"] == expected_dept
        assert result["department_ar"] == DEPARTMENT_CATALOG[expected_dept]["name_ar"]

    @pytest.mark.parametrize(
        "alias,expected",
        [
            ("mobiles", "mobiles_tablets"),
            ("phones", "mobiles_tablets"),
            ("laptops", "computing"),
            ("computing", "computing"),
            ("electronics", "electronics_tv"),
            ("tvs", "electronics_tv"),
            ("appliances", "home_appliances"),
            ("meats", "fresh_meats_poultry"),
            ("poultry", "fresh_meats_poultry"),
            ("dairy", "dairy_cheese_eggs"),
            ("produce", "fruits_vegetables"),
            ("grocery", "grocery_pantry"),
            ("beverages", "beverages"),
            ("bakery", "bakery_snacks"),
            ("frozen", "frozen_foods"),
            ("cleaning", "household_cleaning"),
            ("beauty", "personal_care_beauty"),
        ],
    )
    def test_resolve_department_alias(self, alias, expected):
        assert resolve_department_alias(alias) == expected

    def test_unknown_department_alias_raises(self):
        with pytest.raises(ValueError, match="Unknown department"):
            resolve_department_alias("non_existent_dept")


class TestDWHPipelineAndViews:
    def test_dwh_pipeline_populates_tables_and_department_views(self, tmp_path: Path):
        import asyncio

        db_file = tmp_path / "test_dwh.duckdb"
        asyncio.run(
            run_pipeline(
                db_path=db_file,
                sources=["jumia", "two_b", "carrefour", "tradeline", "dream2000", "raya"],
                offline=True,
                limit=10,
            )
        )

        conn = duckdb.connect(str(db_file), read_only=True)
        try:
            # 14 canonical departments seeded
            dept_count = conn.execute("SELECT COUNT(*) FROM dim_department").fetchone()[0]
            assert dept_count == 14

            # All 18 fixture products inserted and none left in 'other'
            prod_count = conn.execute("SELECT COUNT(*) FROM dim_product").fetchone()[0]
            assert prod_count == 18

            other_count = conn.execute(
                "SELECT COUNT(*) FROM dim_product WHERE department = 'other' OR department IS NULL"
            ).fetchone()[0]
            assert other_count == 0

            # Isolated SQL views per department work independently
            mobiles_rows = conn.execute("SELECT COUNT(*) FROM v_dept_mobiles_tablets").fetchone()[0]
            computing_rows = conn.execute("SELECT COUNT(*) FROM v_dept_computing").fetchone()[0]
            tv_rows = conn.execute("SELECT COUNT(*) FROM v_dept_electronics_tv").fetchone()[0]

            assert mobiles_rows >= 12
            assert computing_rows >= 2
            assert tv_rows >= 3

            # v_department_summary aggregates properly
            summary = conn.execute(
                "SELECT department_id, products_count FROM v_department_summary WHERE products_count > 0"
            ).fetchall()
            summary_map = dict(summary)
            assert summary_map["mobiles_tablets"] == 13
            assert summary_map["electronics_tv"] == 3
            assert summary_map["computing"] == 2
        finally:
            conn.close()

    def test_dwh_pipeline_department_filter_isolates_single_department(self, tmp_path: Path):
        import asyncio

        db_file = tmp_path / "filtered_dwh.duckdb"
        asyncio.run(
            run_pipeline(
                db_path=db_file,
                sources=["carrefour", "two_b", "raya"],
                offline=True,
                limit=10,
                department="electronics",
            )
        )

        conn = duckdb.connect(str(db_file), read_only=True)
        try:
            depts = [
                r[0]
                for r in conn.execute("SELECT DISTINCT department FROM dim_product").fetchall()
            ]
            assert depts == ["electronics_tv"]
            tv_count = conn.execute("SELECT COUNT(*) FROM v_dept_electronics_tv").fetchone()[0]
            assert tv_count == 3
        finally:
            conn.close()

    def test_upsert_locations_sanitizes_out_of_bounds_coordinates(self, tmp_path: Path):
        from dwh.pipeline import upsert_locations

        db_file = tmp_path / "test_locations.duckdb"
        conn = get_db(db_file)
        try:
            locations = [
                {
                    "location_id": "loc_valid_cairo",
                    "location_type": "branch",
                    "branch_name": "Cairo Downtown",
                    "latitude": 30.0444,
                    "longitude": 31.2357,
                },
                {
                    "location_id": "loc_invalid_north_pole",
                    "location_type": "branch",
                    "branch_name": "Assiut Bad Lat",
                    "latitude": 90.0,
                    "longitude": 31.1859,
                },
                {
                    "location_id": "loc_invalid_string",
                    "location_type": "branch",
                    "branch_name": "Corrupt Coords",
                    "latitude": "not_a_number",
                    "longitude": 31.2,
                },
            ]
            upsert_locations(conn, locations, "test_source", "2026-10-02T00:00:00Z")

            cairo = conn.execute(
                "SELECT latitude, longitude FROM dim_location WHERE location_id = 'loc_valid_cairo'"
            ).fetchone()
            assert cairo[0] == pytest.approx(30.0444)
            assert cairo[1] == pytest.approx(31.2357)

            bad_lat = conn.execute(
                "SELECT latitude, longitude FROM dim_location WHERE location_id = 'loc_invalid_north_pole'"
            ).fetchone()
            assert bad_lat[0] is None
            assert bad_lat[1] is None

            bad_str = conn.execute(
                "SELECT latitude, longitude FROM dim_location WHERE location_id = 'loc_invalid_string'"
            ).fetchone()
            assert bad_str[0] is None
            assert bad_str[1] is None
        finally:
            conn.close()

    def test_databricks_export_dry_run_and_target_schema(self):
        from dwh.export_to_databricks import DEFAULT_DB, export_to_databricks, load_databricks_config

        cfg = load_databricks_config()
        assert cfg["username"] == "by234DEPI"
        assert cfg["password"] == "DEPI@234"
        assert cfg["catalog"] == "hive_metastore"
        assert cfg["schema"] == "default"

        counts = export_to_databricks(duck_db=DEFAULT_DB, cfg=cfg, dry_run=True)
        assert "dim_product" in counts
        assert "fact_observation" in counts
        assert counts["dim_product"] > 0

