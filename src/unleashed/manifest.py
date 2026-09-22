"""Declarative resource descriptions.

Adding a resource means writing a manifest. Nothing in the generator, the client, or
the output layer may name a specific resource — that rule mirrors the API's own
"Adding a Resource" contract, and it is what keeps a new resource to one file.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import StrEnum

from unleashed.errors import ManifestError


class FieldType(StrEnum):
    STRING = "string"
    DATE = "date"
    BOOL = "bool"
    INT = "int"
    MAP = "map"


@dataclass(frozen=True)
class Field:
    """One API field, and the consequences of its attributes.

    read_only       no flag is generated; the field can never be sent
    immutable       flag on create, absent from update
    update_only     flag on update, absent from create
    nullable        gains a paired --clear-<field> flag on update
    """

    name: str
    type: FieldType = FieldType.STRING
    required_on_create: bool = False
    immutable: bool = False
    update_only: bool = False
    nullable: bool = False
    read_only: bool = False
    enum: tuple[str, ...] | None = None
    help: str = ""

    def __post_init__(self) -> None:
        if self.read_only and (
            self.required_on_create or self.immutable or self.update_only or self.nullable
        ):
            raise ManifestError(
                f"{self.name} is read-only, so it cannot also carry write attributes."
            )
        if self.immutable and self.update_only:
            raise ManifestError(f"{self.name} cannot be both immutable and update-only.")

    @property
    def is_writable(self) -> bool:
        return not self.read_only

    @property
    def flag_name(self) -> str:
        return "--" + self.name.replace("_", "-")

    @property
    def clear_flag_name(self) -> str:
        return "--clear-" + self.name.replace("_", "-")


@dataclass(frozen=True)
class Filter:
    """One index query parameter. Filters are not fields — some match no column."""

    name: str
    type: FieldType = FieldType.STRING
    enum: tuple[str, ...] | None = None
    help: str = ""

    @property
    def flag_name(self) -> str:
        return "--" + self.name.replace("_", "-")


@dataclass(frozen=True)
class Attachment:
    """A singular sub-resource that links one existing record to the parent.

    PUT /<resource>/<uuid>/<name> with {<id_field>: ...} attaches, replacing whatever
    was attached before. DELETE on the same path detaches. It becomes a nested
    `<resource> <name> attach|detach` group — still noun verb, never an ad-hoc verb.
    """

    name: str
    id_field: str
    help: str = ""

    @property
    def id_flag_name(self) -> str:
        return "--" + self.id_field.replace("_", "-")


@dataclass(frozen=True)
class KeyValueMap:
    """A flat map sub-resource the API merges into or replaces wholesale.

    PATCH /<resource>/<uuid>/<name> merges: keys sent overwrite, a null deletes one,
    keys not sent are kept. PUT replaces the whole map. It becomes a nested
    `<resource> <name> merge|replace` group.
    """

    name: str
    help: str = ""


@dataclass(frozen=True)
class Resource:
    name: str
    fields: tuple[Field, ...] | list[Field]
    filters: tuple[Filter, ...] | list[Filter] = dataclass_field(default_factory=tuple)
    sorts: tuple[str, ...] | list[str] = dataclass_field(default_factory=tuple)
    attachments: tuple[Attachment, ...] | list[Attachment] = dataclass_field(default_factory=tuple)
    maps: tuple[KeyValueMap, ...] | list[KeyValueMap] = dataclass_field(default_factory=tuple)
    #: For names that do not singularise by dropping an s, such as people.
    singular_name: str | None = None

    def __post_init__(self) -> None:
        names = [f.name for f in self.fields]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ManifestError(f"{self.name} declares duplicate fields: {sorted(duplicates)}")
        unknown_sorts = [s for s in self.sorts if s not in names and s != "created_at"]
        if unknown_sorts:
            raise ManifestError(
                f"{self.name} allows a sort on {unknown_sorts}, which are not fields."
            )
        nested = [a.name for a in self.attachments] + [m.name for m in self.maps]
        clashing = {n for n in nested if nested.count(n) > 1}
        if clashing:
            raise ManifestError(f"{self.name} declares duplicate sub-resources: {sorted(clashing)}")

    @property
    def singular(self) -> str:
        return self.singular_name or self.name.rstrip("s").replace("-", " ")

    def field(self, name: str) -> Field:
        for candidate in self.fields:
            if candidate.name == name:
                return candidate
        raise ManifestError(f"{self.name} has no field named {name}.")

    @property
    def writable_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.is_writable)

    @property
    def create_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.writable_fields if not f.update_only)

    @property
    def update_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.writable_fields if not f.immutable)

    @property
    def nullable_update_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.update_fields if f.nullable)

    @property
    def sort_choices(self) -> tuple[str, ...]:
        """Allowlisted columns, each in both directions. A minus prefix means descending."""
        return tuple(column for name in self.sorts for column in (name, f"-{name}"))

    @property
    def required_create_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.create_fields if f.required_on_create)
