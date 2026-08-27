import json

import pytest

from unleashed.errors import UsageError
from unleashed.output import OutputFormat, render

RECORD = {"uuid": "ep-1", "name": "Episode 101", "description": None}


def test_json_output_is_the_record_verbatim():
    assert json.loads(render(RECORD, OutputFormat.JSON)) == RECORD


def test_table_output_is_a_readable_key_value_block():
    lines = render(RECORD, OutputFormat.TABLE).splitlines()
    assert any(line.startswith("uuid") and "ep-1" in line for line in lines)


def test_table_output_renders_null_as_an_empty_cell_not_the_word_none():
    assert "None" not in render(RECORD, OutputFormat.TABLE)


def test_text_output_is_tab_separated_values_in_field_order():
    assert render(RECORD, OutputFormat.TEXT) == "ep-1\tEpisode 101\t"


def test_a_query_plucks_a_single_field():
    assert render(RECORD, OutputFormat.TEXT, query="name") == "Episode 101"


def test_a_query_applies_before_json_rendering():
    assert json.loads(render(RECORD, OutputFormat.JSON, query="[uuid, name]")) == [
        "ep-1",
        "Episode 101",
    ]


def test_an_invalid_query_is_a_usage_error():
    with pytest.raises(UsageError, match="query"):
        render(RECORD, OutputFormat.JSON, query="[[[")


def test_a_query_matching_nothing_renders_empty_not_a_crash():
    assert render(RECORD, OutputFormat.TEXT, query="missing") == ""


def test_a_list_renders_as_one_text_row_per_item():
    rows = [{"uuid": "a"}, {"uuid": "b"}]
    assert render(rows, OutputFormat.TEXT) == "a\nb"


def test_non_ascii_survives_json_output_unescaped():
    """An em dash in a title must stay an em dash, not become \\u2014."""
    rendered = render({"name": "Episode 101 — Something"}, OutputFormat.JSON)
    assert "—" in rendered
    assert "\\u2014" not in rendered


def test_non_ascii_survives_a_nested_cell():
    assert "—" in render({"meta": {"note": "a — b"}}, OutputFormat.TEXT)


def test_a_projected_row_is_tab_separated_not_stacked():
    """`--query "[].[uuid,name]"` yields a list of lists. Each inner list is one row."""
    rows = [["a", "First"], ["b", "Second"]]
    assert render(rows, OutputFormat.TEXT) == "a\tFirst\nb\tSecond"
