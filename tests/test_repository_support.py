from datetime import UTC, datetime

from src.services.repository_support import (
    deserialize_jsonb,
    deserialize_jsonb_fields,
    normalize_row,
    serialize_jsonb,
    serialize_jsonb_fields,
)


def test_serialize_jsonb_converts_mappings_and_datetimes_to_json_text():
    serialized = serialize_jsonb(
        {
            "source": "Reuters",
            "published_at": datetime(2026, 3, 13, tzinfo=UTC),
            "entities": ["OPEC", "Brent"],
        }
    )

    assert '"source": "Reuters"' in serialized
    assert "2026-03-13 00:00:00+00:00" in serialized
    assert '"entities": ["OPEC", "Brent"]' in serialized


def test_serialize_jsonb_fields_only_serializes_selected_keys():
    serialized = serialize_jsonb_fields(
        {
            "status": "active",
            "metadata": {"region": "middle east"},
            "payload": ["Brent"],
        },
        ("metadata",),
    )

    assert serialized["status"] == "active"
    assert serialized["metadata"] == '{"region": "middle east"}'
    assert serialized["payload"] == ["Brent"]


def test_deserialize_jsonb_round_trips_mapping_text():
    deserialized = deserialize_jsonb('{"region": "middle east", "channels": ["energy"]}')

    assert deserialized == {"region": "middle east", "channels": ["energy"]}


def test_deserialize_jsonb_unwraps_double_serialized_mapping_text():
    deserialized = deserialize_jsonb('"{\\"region\\": \\"middle east\\", \\"channels\\": [\\"energy\\"]}"')

    assert deserialized == {"region": "middle east", "channels": ["energy"]}


def test_deserialize_jsonb_fields_only_deserializes_selected_keys():
    fields = deserialize_jsonb_fields(
        {
            "status": "active",
            "metadata": '{"region": "middle east"}',
            "summary": "unchanged",
        },
        ("metadata",),
    )

    assert fields["status"] == "active"
    assert fields["metadata"] == {"region": "middle east"}
    assert fields["summary"] == "unchanged"


def test_normalize_row_deserializes_selected_json_fields():
    row = normalize_row(
        {
            "event_id": "evt_1",
            "brief_json": '{"eventId": "evt_1", "totalScore": 0.91}',
        },
        json_field_names=("brief_json",),
    )

    assert row == {
        "event_id": "evt_1",
        "brief_json": {"eventId": "evt_1", "totalScore": 0.91},
    }


def test_normalize_row_deserializes_double_serialized_json_fields():
    row = normalize_row(
        {
            "event_id": "evt_1",
            "brief_json": '"{\\"eventId\\": \\"evt_1\\", \\"totalScore\\": 0.91}"',
        },
        json_field_names=("brief_json",),
    )

    assert row == {
        "event_id": "evt_1",
        "brief_json": {"eventId": "evt_1", "totalScore": 0.91},
    }
