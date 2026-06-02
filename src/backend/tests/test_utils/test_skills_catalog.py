from app.skills import CATALOG, catalog_as_dicts
from app.utils.routing import Role

_VALID_ROLES = {
    Role.CHUNK_EXTRACTION, Role.ONTOLOGY, Role.PROFILE, Role.QUERY,
    Role.ANALYSIS, Role.DEDUP, Role.CANONICAL, Role.REFINEMENT,
    Role.SIMULATION, Role.DIGEST,
}
_VALID_COST = {"low", "high"}
_VALID_MODE = {"on_demand", "scheduled", "continuous"}


def test_catalog_not_empty():
    assert len(CATALOG) >= 6


def test_skill_names_unique():
    names = [s.name for s in CATALOG]
    assert len(names) == len(set(names))


def test_every_skill_has_valid_fields():
    for s in CATALOG:
        assert s.role in _VALID_ROLES
        assert s.cost_profile in _VALID_COST
        assert s.execution_mode in _VALID_MODE
        assert s.inputs and s.outputs
        assert s.description


def test_catalog_as_dicts_is_json_serializable():
    import json
    json.dumps(catalog_as_dicts())
