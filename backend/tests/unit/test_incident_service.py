import uuid
from datetime import datetime, timezone
import pytest

from app.core.exceptions import (
    ArchivedIncidentModificationError,
    InvalidStatusTransitionError,
)
from app.models.incident import Incident
from app.schemas.incident import (
    CoordinateInput,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)
from app.services.incident_service import ALLOWED_TRANSITIONS, SEVERITY_ORDER


def test_status_transition_matrix_rules():
    """Verify approved transition matrix mappings."""
    assert ALLOWED_TRANSITIONS["reported"] == {"investigating", "active", "false_alarm"}
    assert ALLOWED_TRANSITIONS["investigating"] == {"active", "contained", "resolved", "false_alarm"}
    assert ALLOWED_TRANSITIONS["active"] == {"contained", "resolved"}
    assert ALLOWED_TRANSITIONS["contained"] == {"active", "resolved"}
    assert ALLOWED_TRANSITIONS["resolved"] == {"active"}
    assert ALLOWED_TRANSITIONS["false_alarm"] == set()


def test_invalid_status_transitions_rejected():
    """Verify that forbidden state transitions are identified."""
    # false_alarm is terminal
    for target in ["reported", "investigating", "active", "contained", "resolved"]:
        assert target not in ALLOWED_TRANSITIONS["false_alarm"]

    # reported cannot jump directly to contained or resolved
    assert "contained" not in ALLOWED_TRANSITIONS["reported"]
    assert "resolved" not in ALLOWED_TRANSITIONS["reported"]

    # active cannot regress to investigating or reported
    assert "investigating" not in ALLOWED_TRANSITIONS["active"]
    assert "reported" not in ALLOWED_TRANSITIONS["active"]


def test_severity_ranking_hierarchy():
    """Verify that operational ranking maps critical (1) > high (2) > moderate (3) > low (4)."""
    # SEVERITY_ORDER maps to integers: critical=1, high=2, moderate=3, low=4
    rank_dict = {c.value: v.value for c, v in SEVERITY_ORDER.whens}
    assert rank_dict["critical"] == 1
    assert rank_dict["high"] == 2
    assert rank_dict["moderate"] == 3
    assert rank_dict["low"] == 4
