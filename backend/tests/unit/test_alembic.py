import importlib.util
from pathlib import Path
from alembic.config import Config

# Dynamically load backend/alembic/env.py
backend_dir = Path(__file__).resolve().parent.parent.parent
env_path = backend_dir / "alembic" / "env.py"
spec = importlib.util.spec_from_file_location("scout_alembic_env", str(env_path))
env_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env_mod)
include_object = env_mod.include_object


def test_alembic_config_initialization():
    """Verify that alembic.ini is discoverable and points to alembic script location."""
    ini_path = backend_dir / "alembic.ini"
    assert ini_path.is_file()

    alembic_cfg = Config(str(ini_path))
    script_loc = alembic_cfg.get_main_option("script_location")
    assert script_loc.endswith("alembic")
    assert Path(script_loc).is_dir()


def test_include_object_filter():
    """
    Verify that include_object accurately ignores PostGIS internal schemas
    and catalog tables while preserving future application tables.
    """
    class MockTable:
        def __init__(self, name, schema=None):
            self.name = name
            self.schema = schema

    # Core PostGIS system tables must be excluded
    assert not include_object(MockTable("spatial_ref_sys"), "spatial_ref_sys", "table", False, None)
    assert not include_object(MockTable("geometry_columns"), "geometry_columns", "table", False, None)
    assert not include_object(MockTable("geography_columns"), "geography_columns", "table", False, None)

    # PostGIS extension schemas must be excluded
    assert not include_object(MockTable("some_table", schema="topology"), "some_table", "table", False, None)
    assert not include_object(MockTable("some_table", schema="tiger"), "some_table", "table", False, None)
    assert not include_object(MockTable("tiger_faces"), "tiger_faces", "table", False, None)

    # Future SCOUT application tables must NOT be excluded
    assert include_object(MockTable("incidents"), "incidents", "table", False, None)
    assert include_object(MockTable("uploaded_media"), "uploaded_media", "table", False, None)
    assert include_object(MockTable("hazard_predictions"), "hazard_predictions", "table", False, None)
    assert include_object(MockTable("environmental_observations"), "environmental_observations", "table", False, None)
    assert include_object(MockTable("detection_results"), "detection_results", "table", False, None)
