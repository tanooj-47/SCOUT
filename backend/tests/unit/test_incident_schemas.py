import pytest
from pydantic import ValidationError

from app.schemas.incident import (
    CoordinateInput,
    CoordinatePoint,
    DisasterType,
    IncidentCreate,
    IncidentStatus,
    IncidentUpdate,
    Severity,
)


def test_coordinate_input_valid():
    """Verify that valid WGS 84 latitude and longitude pairs pass validation."""
    coord = CoordinateInput(latitude=34.0522, longitude=-118.2437)
    assert coord.latitude == 34.0522
    assert coord.longitude == -118.2437


def test_coordinate_input_boundary_limits():
    """Verify boundary checks on latitude (-90 to 90) and longitude (-180 to 180)."""
    # Exact boundary edges
    assert CoordinateInput(latitude=-90.0, longitude=-180.0) is not None
    assert CoordinateInput(latitude=90.0, longitude=180.0) is not None

    # Exceeding latitude bounds
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=90.001, longitude=0.0)
    assert "latitude" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=-90.001, longitude=0.0)
    assert "latitude" in str(exc.value)

    # Exceeding longitude bounds
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=180.001)
    assert "longitude" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=-180.001)
    assert "longitude" in str(exc.value)


def test_coordinate_input_rejects_nan_and_infinities():
    """Verify that allow_inf_nan=False explicitly rejects NaN, +inf, and -inf."""
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=float("nan"), longitude=0.0)
    assert "finite" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=float("inf"), longitude=0.0)
    assert "finite" in str(exc.value).lower()

    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=0.0, longitude=float("-inf"))
    assert "finite" in str(exc.value).lower()


def test_coordinate_input_rejects_extra_fields():
    """Verify extra='forbid' rejects client-supplied srid or unknown fields."""
    with pytest.raises(ValidationError) as exc:
        CoordinateInput(latitude=10.0, longitude=20.0, srid=4326)  # type: ignore[call-arg]
    assert "extra_forbidden" in str(exc.value) or "Extra inputs are not permitted" in str(exc.value)


def test_coordinate_point_server_srid_default():
    """Verify response schema provides constant server-controlled SRID 4326."""
    point = CoordinatePoint(latitude=21.15, longitude=79.08)
    assert point.srid == 4326


def test_incident_create_valid():
    """Verify valid IncidentCreate schema initialization and title trimming."""
    create = IncidentCreate(
        title="  Ridge Fire Incident  ",
        disaster_type=DisasterType.WILDFIRE,
        severity=Severity.HIGH,
        location=CoordinateInput(latitude=37.7749, longitude=-122.4194),
        metadata={"agency": "USFS", "tier": 1},
    )
    assert create.title == "Ridge Fire Incident"
    assert create.disaster_type == DisasterType.WILDFIRE
    assert create.severity == Severity.HIGH
    assert create.location.latitude == 37.7749
    assert create.metadata["agency"] == "USFS"


def test_incident_create_invalid_title():
    """Verify rejection of empty or excessively short titles."""
    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="   ",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
        )
    assert "at least 3 non-whitespace" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="ab",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
        )
    assert "at least 3" in str(exc.value).lower()


def test_incident_create_rejects_unexpected_fields():
    """Verify extra='forbid' on IncidentCreate prevents injection of protected fields."""
    with pytest.raises(ValidationError) as exc:
        IncidentCreate(
            title="Valid Title",
            disaster_type=DisasterType.WILDFIRE,
            location=CoordinateInput(latitude=0.0, longitude=0.0),
            status=IncidentStatus.ACTIVE,  # type: ignore[call-arg]
        )
    assert "extra_forbidden" in str(exc.value) or "Extra inputs are not permitted" in str(exc.value)


def test_incident_update_omitted_fields():
    """Verify that omitted fields in PATCH remain unset in model_fields_set."""
    update = IncidentUpdate(title="Updated Title")
    assert update.model_fields_set == {"title"}
    assert update.title == "Updated Title"
    assert update.status is None
    assert update.severity is None
    assert update.location is None
    assert update.metadata is None


def test_incident_update_rejects_empty_payload():
    """Verify that an empty PATCH body ({}) is explicitly rejected."""
    with pytest.raises(ValidationError) as exc:
        IncidentUpdate()
    assert "At least one mutable field must be provided" in str(exc.value)


def test_incident_update_rejects_explicit_null_on_non_nullable():
    """Verify that passing explicit null for non-nullable fields is rejected."""
    non_nullable_payloads = [
        {"title": None},
        {"status": None},
        {"severity": None},
        {"location": None},
        {"metadata": None},
    ]
    for payload in non_nullable_payloads:
        with pytest.raises(ValidationError) as exc:
            IncidentUpdate.model_validate(payload)
        assert "is non-nullable and cannot be set to null" in str(exc.value)


def test_incident_update_metadata_replacement():
    """Verify metadata replacement payload validation."""
    update = IncidentUpdate(metadata={"replacement_key": 42})
    assert update.metadata == {"replacement_key": 42}
    assert "metadata" in update.model_fields_set
