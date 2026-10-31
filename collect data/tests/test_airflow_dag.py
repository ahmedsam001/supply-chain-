"""
Test Airflow DAG Integrity & Structure for Egypt E-Commerce.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DAGS_DIR = PROJECT_ROOT / "dags"
os.environ["AIRFLOW_HOME"] = str(PROJECT_ROOT / "airflow")


class TestAirflowDAGIntegrity:
    def test_dagbag_imports_without_errors(self):
        """Verify the DAG can be loaded without syntax or import errors."""
        from airflow.models import DagBag

        dagbag = DagBag(dag_folder=str(DAGS_DIR))
        assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"

        dag_id = "egypt_ecommerce_etl"
        assert dag_id in dagbag.dags, f"DAG '{dag_id}' not found in DagBag"

        dag = dagbag.dags[dag_id]
        assert dag is not None
        schedule_val = (
            getattr(dag, "schedule_interval", None)
            or getattr(dag.timetable, "expression", None)
            or str(dag.schedule)
        )
        assert schedule_val == "0 17 * * *"

    def test_dag_tasks_and_dependencies(self):
        """Verify all expected retailer tasks exist and follow the proper dependency chain."""
        from airflow.models import DagBag

        dagbag = DagBag(dag_folder=str(DAGS_DIR))
        dag = dagbag.dags.get("egypt_ecommerce_etl")
        assert dag is not None

        task_ids = set(dag.task_dict.keys())
        expected_tasks = {
            "bootstrap_databricks",
            "scrape_tradeline",
            "scrape_dream2000",
            "scrape_jumia",
            "scrape_two_b",
            "scrape_carrefour",
            "scrape_raya",
            "reconcile_and_audit",
        }
        assert expected_tasks.issubset(task_ids)

        bootstrap_task = dag.get_task("bootstrap_databricks")
        audit_task = dag.get_task("reconcile_and_audit")

        for src in ["tradeline", "dream2000", "jumia", "two_b", "carrefour", "raya"]:
            scraper_task = dag.get_task(f"scrape_{src}")
            assert bootstrap_task in scraper_task.upstream_list
            assert audit_task in scraper_task.downstream_list
