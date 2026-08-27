import pytest

from unleashed.manifest import Field, FieldType, ManifestError, Resource
from unleashed.resources.episodes import EPISODES
from unleashed.resources.leads import LEADS


def test_flag_name_kebab_cases_the_field():
    assert Field("podcast_uuid").flag_name == "--podcast-uuid"


def test_clear_flag_name_is_derived_from_the_field():
    assert Field("description", nullable=True).clear_flag_name == "--clear-description"


def test_a_read_only_field_generates_no_flag():
    assert Field("transcript_status", read_only=True).is_writable is False


def test_read_only_cannot_also_be_required_on_create():
    with pytest.raises(ManifestError, match="read-only"):
        Field("uuid", read_only=True, required_on_create=True)


def test_read_only_cannot_also_be_nullable():
    with pytest.raises(ManifestError, match="read-only"):
        Field("uuid", read_only=True, nullable=True)


def test_a_field_cannot_be_both_immutable_and_update_only():
    with pytest.raises(ManifestError, match="immutable"):
        Field("nonsense", immutable=True, update_only=True)


def test_create_fields_exclude_read_only_and_update_only():
    names = [f.name for f in EPISODES.create_fields]
    assert "podcast_uuid" in names
    assert "transcript_status" not in names
    assert "podcast_name" not in names
    assert "is_published" not in names


def test_update_fields_exclude_immutable_fields():
    names = [f.name for f in EPISODES.update_fields]
    assert "podcast_uuid" not in names
    assert "is_published" in names
    assert "name" in names


def test_required_create_fields_are_reported():
    assert [f.name for f in EPISODES.required_create_fields] == [
        "podcast_uuid",
        "name",
        "target_published_date",
    ]


def test_resource_rejects_duplicate_field_names():
    with pytest.raises(ManifestError, match="duplicate"):
        Resource(name="x", fields=[Field("a"), Field("a")])


def test_resource_rejects_a_sort_column_that_is_not_a_field():
    with pytest.raises(ManifestError, match="sort"):
        Resource(name="x", fields=[Field("a")], sorts=["nope"])


def test_enum_fields_carry_their_allowed_values():
    status = EPISODES.field("status")
    assert status.enum is not None
    assert "Published" in status.enum


def test_episodes_manifest_matches_the_documented_contract():
    assert EPISODES.name == "episodes"
    assert EPISODES.field("target_published_date").type is FieldType.DATE
    assert EPISODES.field("is_published").type is FieldType.BOOL
    assert EPISODES.field("podcast_uuid").immutable is True


def test_leads_manifest_exists_as_a_fixture_for_the_generator():
    assert LEADS.name == "leads"
    assert LEADS.field("llm_estimate").type is FieldType.INT
    assert LEADS.field("contacted_at").read_only is True
