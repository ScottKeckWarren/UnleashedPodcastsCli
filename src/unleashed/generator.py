"""Turns a resource manifest into Click commands.

Nothing here names a resource. If a resource needs behaviour this file does not have,
the behaviour belongs in the manifest as a new field attribute — the same rule the API
follows for adding a resource.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any

import click

from unleashed.client import Client, DescribedRequest
from unleashed.config import Config, load_config
from unleashed.errors import UsageError
from unleashed.manifest import Attachment, Field, FieldType, Filter, KeyValueMap, Resource
from unleashed.output import OutputFormat, default_output, render
from unleashed.reporting import handle_errors

DATE_FORMAT = "%Y-%m-%d"

_TYPES: dict[FieldType, click.ParamType[Any]] = {
    FieldType.STRING: click.STRING,
    FieldType.INT: click.INT,
    FieldType.DATE: click.DateTime(formats=[DATE_FORMAT]),
    FieldType.BOOL: click.BOOL,
}


# --- option construction -----------------------------------------------------


def _param_type(spec: Field | Filter) -> click.ParamType[Any]:
    if spec.enum:
        return click.Choice(spec.enum)
    return _TYPES[spec.type]


def _option_for(spec: Field | Filter, *, required_note: bool = False) -> click.Option:
    """One flag per writable field or filter.

    A boolean becomes a --flag/--no-flag pair rather than a value option, so that
    `--is-published` reads the way a user expects and the negative form still exists.
    """
    help_text = spec.help
    if required_note and isinstance(spec, Field) and spec.required_on_create:
        help_text = f"{help_text} Required.".strip()

    if spec.type is FieldType.MAP:
        return click.Option(
            [spec.flag_name, spec.name],
            multiple=True,
            metavar="KEY=VALUE",
            help=f"{help_text} Repeat for several keys. Values are sent as strings.".strip(),
        )
    if spec.type is FieldType.BOOL and not spec.enum:
        flag = spec.name.replace("_", "-")
        return click.Option(
            [f"--{flag}/--no-{flag}", spec.name],
            default=None,
            help=help_text or None,
        )
    return click.Option(
        [spec.flag_name, spec.name],
        type=_param_type(spec),
        default=None,
        help=help_text or None,
    )


def _clear_option(field: Field) -> click.Option:
    """The unambiguous way to send null. Only nullable fields get one."""
    return click.Option(
        [field.clear_flag_name, f"clear_{field.name}"],
        is_flag=True,
        default=False,
        help=f"Send {field.name} as null, clearing it.",
    )


def _common_options(*, accepts_json: bool = True) -> list[click.Parameter]:
    params: list[click.Parameter] = []
    if accepts_json:
        params.append(
            click.Option(
                ["--cli-input-json"],
                default=None,
                help="A JSON object to send instead of field flags.",
            )
        )
    params.extend(
        [
            click.Option(
                ["--output", "-o"],
                type=click.Choice([f.value for f in OutputFormat]),
                default=None,
                help="Output format. Defaults to table on a terminal, json when piped.",
            ),
            click.Option(
                ["--query"], default=None, help="JMESPath expression applied to the result."
            ),
            click.Option(
                ["--dry-run"],
                is_flag=True,
                default=False,
                help="Print the request with the token redacted and send nothing.",
            ),
        ]
    )
    return params


# --- value handling ----------------------------------------------------------


def _serialise(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    return value


def _pairs(raw: tuple[str, ...], flag: str) -> dict[str, str]:
    """Turn repeated KEY=VALUE flags into a map. Only the first = splits."""
    pairs: dict[str, str] = {}
    for item in raw:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise UsageError(f"{flag} expects KEY=VALUE, got '{item}'.")
        pairs[key.strip()] = value
    return pairs


def _field_value(field: Field, value: Any) -> Any:
    if field.type is FieldType.MAP:
        return _pairs(value, field.flag_name)
    return _serialise(value)


def _as_query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(_serialise(value))


def _given(ctx: click.Context, name: str) -> bool:
    """True only when the caller actually passed the flag.

    An omitted flag must leave its key out of the body entirely — the API treats an
    absent key and a null key differently.
    """
    source = ctx.get_parameter_source(name)
    return source is not None and source is not click.core.ParameterSource.DEFAULT


def _body_from_flags(
    ctx: click.Context, fields: tuple[Field, ...], values: dict[str, Any]
) -> dict[str, Any]:
    body = {f.name: _field_value(f, values[f.name]) for f in fields if _given(ctx, f.name)}
    for field in fields:
        if not field.nullable or not values.get(f"clear_{field.name}"):
            continue
        if field.name in body:
            raise UsageError(
                f"{field.flag_name} and {field.clear_flag_name} contradict each other. "
                "Pass one or the other."
            )
        body[field.name] = None
    return body


def _body_from_json(raw: str, resource: Resource, fields: tuple[Field, ...]) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--cli-input-json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise UsageError("--cli-input-json must be a JSON object for this action.")

    writable = {f.name for f in fields}
    rejected = sorted(set(parsed) - writable)
    if rejected:
        raise UsageError(
            f"--cli-input-json contains keys that cannot be sent to {resource.name}: "
            f"{', '.join(rejected)}"
        )
    return parsed


def _resolve_body(
    ctx: click.Context,
    resource: Resource,
    fields: tuple[Field, ...],
    values: dict[str, Any],
    raw_json: str | None,
) -> dict[str, Any]:
    if raw_json is None:
        return _body_from_flags(ctx, fields, values)

    conflicting = [f.flag_name for f in fields if _given(ctx, f.name)]
    conflicting += [
        f.clear_flag_name for f in fields if f.nullable and values.get(f"clear_{f.name}")
    ]
    if conflicting:
        raise UsageError(
            f"--cli-input-json cannot be combined with field flags: {', '.join(conflicting)}"
        )
    return _body_from_json(raw_json, resource, fields)


def _require_create_fields(resource: Resource, body: dict[str, Any]) -> None:
    missing = [f for f in resource.required_create_fields if f.name not in body]
    if missing:
        names = ", ".join(f"{f.flag_name} ({f.name})" for f in missing)
        raise UsageError(f"Missing required field(s): {names}")


# --- shared plumbing ---------------------------------------------------------


class _Runtime:
    """Everything an action needs once the common options are stripped off."""

    def __init__(self, ctx: click.Context, values: dict[str, Any]) -> None:
        chosen = values.pop("output", None)
        self.output = OutputFormat(chosen) if chosen else default_output(sys.stdout.isatty())
        self.query: str | None = values.pop("query", None)
        self.dry_run: bool = values.pop("dry_run", False)
        self.raw_json: str | None = values.pop("cli_input_json", None)

        self.config: Config = load_config(ctx.obj["env"], profile=ctx.obj.get("profile"))
        for warning in self.config.warnings:
            click.echo(f"Warning: {warning}", err=True)
        self.client = Client(self.config)

    def show(self, value: Any) -> None:
        click.echo(render(value, self.output, self.query))

    def describe(
        self, method: str, path: str, body: dict[str, Any] | None = None, params: Any = None
    ) -> None:
        described = self.client.describe(method, path, body)
        click.echo(f"# profile {self.config.profile}{_source_note(self.config)}")
        click.echo(_describe(described, params))


def _source_note(config: Config) -> str:
    """Say which file supplied the credentials, so a wrong account is visible."""
    return f" (from {config.sources[-1]})" if config.sources else " (from the environment)"


def _describe(described: DescribedRequest, params: Any = None) -> str:
    url = described.url
    if params:
        url += "?" + "&".join(f"{key}={value}" for key, value in params.items())
    lines = [f"{described.method} {url}"]
    lines.extend(f"{key}: {value}" for key, value in sorted(described.headers.items()))
    if described.body is not None:
        lines.append("")
        lines.append(json.dumps(described.body, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def _uuid_argument() -> click.Argument:
    return click.Argument(["uuid"])


# --- the five actions --------------------------------------------------------


def build_create_command(resource: Resource) -> click.Command:
    fields = resource.create_fields
    singular = resource.singular

    @handle_errors
    def callback(**values: Any) -> None:
        ctx = click.get_current_context()
        run = _Runtime(ctx, values)
        body = _resolve_body(ctx, resource, fields, values, run.raw_json)
        _require_create_fields(resource, body)

        if run.dry_run:
            run.describe("POST", f"/{resource.name}", body)
            return
        run.show(run.client.create(resource.name, body))

    params: list[click.Parameter] = [_option_for(f, required_note=True) for f in fields]
    params.extend(_common_options())
    return click.Command(
        name="create",
        params=params,
        callback=callback,
        short_help=f"Create one {singular}.",
        help=(
            f"Create one {singular}.\n\n"
            "Only the flags you pass are sent. Read-only fields have no flag."
        ),
    )


def build_update_command(resource: Resource) -> click.Command:
    fields = resource.update_fields
    singular = resource.singular

    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        run = _Runtime(ctx, values)
        body = _resolve_body(ctx, resource, fields, values, run.raw_json)
        path = f"/{resource.name}/{uuid}"

        if run.dry_run:
            run.describe("PATCH", path, body)
            return
        run.show(run.client.request("PATCH", path, json=body))

    params: list[click.Parameter] = [_uuid_argument()]
    params.extend(_option_for(f) for f in fields)
    params.extend(_clear_option(f) for f in resource.nullable_update_fields)
    params.extend(_common_options())
    return click.Command(
        name="update",
        params=params,
        callback=callback,
        short_help=f"Update one {singular}.",
        help=(
            f"Update one {singular}.\n\n"
            "An omitted flag leaves the field alone. Use --clear-<field> to send null. "
            "Passing no flags at all is a successful no-op."
        ),
    )


def build_get_command(resource: Resource) -> click.Command:
    singular = resource.singular

    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        run = _Runtime(ctx, values)
        path = f"/{resource.name}/{uuid}"
        if run.dry_run:
            run.describe("GET", path)
            return
        run.show(run.client.request("GET", path))

    params: list[click.Parameter] = [_uuid_argument()]
    params.extend(_common_options(accepts_json=False))
    return click.Command(
        name="get", params=params, callback=callback, short_help=f"Fetch one {singular}."
    )


def build_delete_command(resource: Resource) -> click.Command:
    singular = resource.singular

    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        run = _Runtime(ctx, values)
        path = f"/{resource.name}/{uuid}"
        if run.dry_run:
            run.describe("DELETE", path)
            return
        run.client.request("DELETE", path)
        run.show({"uuid": uuid, "deleted": True})

    params: list[click.Parameter] = [_uuid_argument()]
    params.extend(_common_options(accepts_json=False))
    return click.Command(
        name="delete",
        params=params,
        callback=callback,
        short_help=f"Delete one {singular}.",
        help=f"Delete one {singular}. The API soft-deletes; there is no restore.",
    )


def build_list_command(resource: Resource) -> click.Command:
    filters = tuple(resource.filters)

    @handle_errors
    def callback(**values: Any) -> None:
        ctx = click.get_current_context()
        sort: str | None = values.pop("sort")
        per_page: int | None = values.pop("per_page")
        paginate: bool = not values.pop("no_paginate")
        max_items: int | None = values.pop("max_items")
        run = _Runtime(ctx, values)

        params: dict[str, str] = {
            f.name: _as_query_value(values[f.name]) for f in filters if _given(ctx, f.name)
        }
        if sort:
            _check_sort(resource, sort)
            params["sort"] = sort
        if per_page:
            params["per_page"] = str(per_page)

        if run.dry_run:
            run.describe("GET", f"/{resource.name}", params=params)
            return
        run.show(run.client.index(resource.name, params, paginate=paginate, max_items=max_items))

    params: list[click.Parameter] = [_option_for(f) for f in filters]
    params.extend(
        [
            click.Option(
                ["--sort"],
                default=None,
                metavar="COLUMN",
                help="Allowlisted column. Prefix with - for descending.",
            ),
            click.Option(["--per-page"], type=click.INT, default=None, help="Max 100."),
            click.Option(
                ["--no-paginate"],
                is_flag=True,
                default=False,
                help="Return only the first page instead of every record.",
            ),
            click.Option(
                ["--max-items"], type=click.INT, default=None, help="Stop after this many records."
            ),
        ]
    )
    params.extend(_common_options(accepts_json=False))
    return click.Command(
        name="list",
        params=params,
        callback=callback,
        short_help=f"List {resource.name}.",
        help=(
            f"List {resource.name}.\n\n"
            "Every page is fetched by default, so a result is never a silent truncation. "
            "Use --no-paginate or --max-items to spend less."
        ),
    )


def _check_sort(resource: Resource, sort: str) -> None:
    """Catch a bad sort here rather than spending a request to be told 422."""
    if sort not in resource.sort_choices:
        allowed = ", ".join(resource.sorts)
        raise UsageError(f"Cannot sort by '{sort}'. Allowed columns: {allowed} (prefix - for desc)")


# --- attachments -------------------------------------------------------------


def build_attach_command(resource: Resource, attachment: Attachment) -> click.Command:
    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        record_id: str = values.pop(attachment.id_field)
        run = _Runtime(ctx, values)
        path = f"/{resource.name}/{uuid}/{attachment.name}"
        body = {attachment.id_field: record_id}
        if run.dry_run:
            run.describe("PUT", path, body)
            return
        run.show(run.client.request("PUT", path, json=body))

    params: list[click.Parameter] = [
        _uuid_argument(),
        click.Option(
            [attachment.id_flag_name, attachment.id_field],
            required=True,
            help=attachment.help or None,
        ),
    ]
    params.extend(_common_options(accepts_json=False))
    return click.Command(
        name="attach",
        params=params,
        callback=callback,
        short_help=f"Attach a {attachment.name} to one {resource.singular}.",
        help=(
            f"Attach a {attachment.name} to one {resource.singular}.\n\n"
            "Replaces whatever was attached before."
        ),
    )


def build_detach_command(resource: Resource, attachment: Attachment) -> click.Command:
    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        run = _Runtime(ctx, values)
        path = f"/{resource.name}/{uuid}/{attachment.name}"
        if run.dry_run:
            run.describe("DELETE", path)
            return
        run.show(run.client.request("DELETE", path))

    params: list[click.Parameter] = [_uuid_argument()]
    params.extend(_common_options(accepts_json=False))
    return click.Command(
        name="detach",
        params=params,
        callback=callback,
        short_help=f"Detach the {attachment.name} from one {resource.singular}.",
        help=(
            f"Detach the {attachment.name} from one {resource.singular}.\n\n"
            "The detached record itself is kept. Detaching when nothing is attached "
            "succeeds and changes nothing."
        ),
    )


def build_attachment_group(resource: Resource, attachment: Attachment) -> click.Group:
    group = click.Group(
        name=attachment.name,
        help=f"Attach or detach the {attachment.name} of one {resource.singular}.",
    )
    group.add_command(build_attach_command(resource, attachment))
    group.add_command(build_detach_command(resource, attachment))
    return group


# --- key-value maps ----------------------------------------------------------

_SCALARS = (str, int, float, bool)


def _map_from_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--cli-input-json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise UsageError("--cli-input-json must be a JSON object for this action.")
    nested = sorted(k for k, v in parsed.items() if v is not None and not isinstance(v, _SCALARS))
    if nested:
        raise UsageError(
            f"--cli-input-json values must be strings, numbers, booleans, or null. "
            f"Nested values under: {', '.join(nested)}"
        )
    return parsed


def _map_command(
    resource: Resource, kv: KeyValueMap, *, name: str, method: str, merge: bool
) -> click.Command:
    @handle_errors
    def callback(uuid: str, **values: Any) -> None:
        ctx = click.get_current_context()
        raw_set: tuple[str, ...] = values.pop("set")
        raw_unset: tuple[str, ...] = values.pop("unset", ())
        run = _Runtime(ctx, values)

        if run.raw_json is not None:
            if raw_set or raw_unset:
                raise UsageError("--cli-input-json cannot be combined with --set or --unset.")
            body = _map_from_json(run.raw_json)
        else:
            body = {**_pairs(raw_set, "--set"), **dict.fromkeys(raw_unset)}
            if not merge and not body:
                raise UsageError(
                    f"Nothing to replace {kv.name} with. Pass --set, or "
                    "--cli-input-json '{}' to clear every key."
                )

        path = f"/{resource.name}/{uuid}/{kv.name}"
        if run.dry_run:
            run.describe(method, path, body)
            return
        run.show(run.client.request(method, path, json=body))

    params: list[click.Parameter] = [
        _uuid_argument(),
        click.Option(
            ["--set", "set"],
            multiple=True,
            metavar="KEY=VALUE",
            help="Key to write. Repeat for several. Values are sent as strings.",
        ),
    ]
    if merge:
        params.append(
            click.Option(
                ["--unset", "unset"],
                multiple=True,
                metavar="KEY",
                help="Key to delete. Repeat for several.",
            )
        )
    params.extend(_common_options())

    if merge:
        help_text = (
            f"Merge keys into the {kv.name} of one {resource.singular}.\n\n"
            "Keys you --set overwrite, keys you --unset are deleted, every other key is "
            "kept. Use --cli-input-json for number, boolean, or null values."
        )
    else:
        help_text = (
            f"Replace the whole {kv.name} of one {resource.singular}.\n\n"
            "Every key you do not --set is removed. Use --cli-input-json for number or "
            "boolean values, or --cli-input-json '{}' to clear every key."
        )
    return click.Command(
        name=name,
        params=params,
        callback=callback,
        short_help=help_text.split("\n", 1)[0],
        help=help_text,
    )


def build_map_group(resource: Resource, kv: KeyValueMap) -> click.Group:
    group = click.Group(
        name=kv.name,
        help=kv.help or f"Merge into or replace the {kv.name} of one {resource.singular}.",
    )
    group.add_command(_map_command(resource, kv, name="merge", method="PATCH", merge=True))
    group.add_command(_map_command(resource, kv, name="replace", method="PUT", merge=False))
    return group


BUILDERS = (
    build_create_command,
    build_list_command,
    build_get_command,
    build_update_command,
    build_delete_command,
)


def build_group(resource: Resource) -> click.Group:
    """One group per resource, five standard actions, no ad-hoc verbs.

    Attachments nest as their own noun, so `<resource> <attachment> attach` keeps the
    noun verb shape instead of inventing a verb per sub-resource.
    """
    group = click.Group(name=resource.name, help=f"Work with {resource.name}.")
    for builder in BUILDERS:
        group.add_command(builder(resource))
    for attachment in resource.attachments:
        group.add_command(build_attachment_group(resource, attachment))
    for kv in resource.maps:
        group.add_command(build_map_group(resource, kv))
    return group
