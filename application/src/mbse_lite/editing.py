from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .core import (
    Model,
    ParsedMarkdownTable,
    SourceRef,
    load_model,
    parse_markdown_tables_with_provenance,
    validate_model,
)


class EditingError(RuntimeError):
    """Base class for a controlled Markdown editing failure."""


class EditConflictError(EditingError):
    """The source value changed after the caller read it."""


class EditValidationError(EditingError):
    """The proposed project model did not pass validation."""


class RequirementCreationUnavailableError(EditingError):
    """No single safe Requirement table can be selected for creation."""


class RequirementTableConflictError(EditConflictError):
    """The authoritative Requirement table changed after the form was opened."""

    def __init__(self, expected: str, actual: str):
        super().__init__(
            "The Requirements table changed since the creation form was opened"
        )
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class UpdateObjectAttribute:
    object_id: str
    attribute: str
    new_value: str
    expected_old_value: str | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class UpdateAttributeResult:
    object_id: str
    attribute: str
    old_value: str
    new_value: str
    source_file: str
    source_ref: SourceRef
    dry_run: bool
    changed: bool
    validation_findings: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CreateRequirement:
    values: Mapping[str, str]
    expected_table_revision: str


@dataclass(frozen=True, slots=True)
class RequirementCreationTarget:
    source_file: str
    source_ref: SourceRef
    columns: tuple[str, ...]
    table_revision: str
    suggested_id: str


@dataclass(frozen=True, slots=True)
class CreateRequirementResult:
    created_object_id: str
    source_file: str
    source_ref: SourceRef
    table_revision: str
    validation_findings: tuple[tuple[str, str], ...]


def editable_attribute_names(obj: object) -> tuple[str, ...]:
    """Return scalar attributes addressable by the controlled writer.

    Editability is derived from parsed attribute provenance, not a browser-side
    allow-list. Stable IDs and object types are deliberately outside the
    attribute mapping and therefore cannot be returned here.
    """

    attributes = getattr(obj, "attributes", {})
    sources = getattr(obj, "attribute_sources", {})
    object_id = getattr(obj, "id", None)
    return tuple(
        name
        for name in attributes
        if (source := sources.get(name)) is not None
        and source.row_id == object_id
        and source.column == name
    )


def encode_markdown_table_cell(value: str) -> str:
    """Encode a semantic string as one physical Markdown table cell."""

    if "\x00" in value:
        raise EditingError("Markdown table values cannot contain NUL characters")

    leading = len(value) - len(value.lstrip())
    trailing_start = len(value.rstrip())
    encoded: list[str] = []
    for index, character in enumerate(value):
        if character == "&":
            encoded.append("&amp;")
        elif character == "|":
            encoded.append("&#124;")
        elif character == "\r":
            encoded.append("&#13;")
        elif character == "\n":
            encoded.append("&#10;")
        elif character.isspace() and (index < leading or index >= trailing_start):
            encoded.append(f"&#{ord(character)};")
        else:
            encoded.append(character)
    return "".join(encoded)


def _row_cell_spans(line: str) -> list[tuple[int, int]]:
    delimiters = [index for index, character in enumerate(line) if character == "|"]
    if not delimiters:
        return []
    starts = [0, *(index + 1 for index in delimiters)]
    ends = [*delimiters, len(line)]
    spans = list(zip(starts, ends))
    if line.startswith("|"):
        spans = spans[1:]
    if line.endswith("|"):
        spans = spans[:-1]
    return spans


def _replace_cell(line: str, column_index: int, new_value: str) -> str:
    spans = _row_cell_spans(line)
    if column_index >= len(spans):
        raise EditingError("The target Markdown row is malformed")
    start, end = spans[column_index]
    raw_cell = line[start:end]
    if raw_cell.strip():
        leading_length = len(raw_cell) - len(raw_cell.lstrip())
        trailing_length = len(raw_cell) - len(raw_cell.rstrip())
        prefix = raw_cell[:leading_length]
        suffix = raw_cell[len(raw_cell) - trailing_length :] if trailing_length else ""
    elif len(raw_cell) >= 2:
        prefix, suffix = raw_cell[:1], raw_cell[1:]
    else:
        prefix, suffix = "", raw_cell
    return line[:start] + prefix + encode_markdown_table_cell(new_value) + suffix + line[end:]


def _table_for_ref(
    tables: list[ParsedMarkdownTable], source_ref: SourceRef
) -> ParsedMarkdownTable:
    for table in tables:
        if table.source_ref.table_index == source_ref.table_index:
            return table
    raise EditingError(
        f"Markdown table {source_ref.table_index} no longer exists in {source_ref.file}"
    )


def _patch_source_bytes(
    source_path: Path,
    source_file: str,
    source_ref: SourceRef,
    object_id: str,
    attribute: str,
    loaded_value: str,
    new_value: str,
) -> tuple[bytes, bytes, SourceRef]:
    original_bytes = source_path.read_bytes()
    has_bom = original_bytes.startswith(b"\xef\xbb\xbf")
    try:
        text = original_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise EditingError(f"Source file is not valid UTF-8: {source_file}") from error

    tables = parse_markdown_tables_with_provenance(
        source_path, source_file=source_file
    )
    table = _table_for_ref(tables, source_ref)
    if table.headers.count("ID") != 1:
        raise EditingError(
            f"Table {source_ref.table_index} of {source_file} must contain exactly one ID column"
        )
    attribute_count = table.headers.count(attribute)
    if attribute_count == 0:
        raise EditingError(
            f"Attribute {attribute!r} no longer exists in table {source_ref.table_index} "
            f"of {source_file}"
        )
    if attribute_count > 1:
        raise EditingError(
            f"Attribute {attribute!r} is ambiguous in table {source_ref.table_index} "
            f"of {source_file}"
        )
    column_index = table.headers.index(attribute)

    matches = [
        (row, row_ref)
        for row, row_ref in zip(table.rows, table.row_sources)
        if row.get("ID", "").strip() == object_id
    ]
    if len(matches) != 1:
        raise EditingError(
            f"Expected exactly one row with stable ID {object_id!r} in table "
            f"{source_ref.table_index} of {source_file}; found {len(matches)}"
        )
    current_row, current_ref = matches[0]
    current_value = current_row.get(attribute, "")
    if current_value != loaded_value:
        raise EditConflictError(
            f"Conflict for {object_id}.{attribute}: the Markdown value changed from "
            f"{loaded_value!r} to {current_value!r} while the update was being prepared"
        )
    if current_ref.line is None:
        raise EditingError(f"No physical source line is available for {object_id!r}")

    lines = text.splitlines(keepends=True)
    line_index = current_ref.line - 1
    if line_index >= len(lines):
        raise EditingError(f"Source line for {object_id!r} no longer exists")
    physical_line = lines[line_index]
    body = physical_line.rstrip("\r\n")
    line_ending = physical_line[len(body) :]
    lines[line_index] = _replace_cell(body, column_index, new_value) + line_ending
    patched_text = "".join(lines)
    patched_bytes = patched_text.encode("utf-8")
    if has_bom:
        patched_bytes = b"\xef\xbb\xbf" + patched_bytes
    return original_bytes, patched_bytes, current_ref.for_column(attribute)


def _all_validation_findings(project_path: Path) -> tuple[tuple[str, str], ...]:
    from .visualization import validate_visualizations

    model = load_model(project_path)
    return tuple((*validate_model(model), *validate_visualizations(model)))


def _validate_candidate(
    project_path: Path, source_file: str, patched_bytes: bytes
) -> tuple[tuple[str, str], ...]:
    with tempfile.TemporaryDirectory(prefix="mbse-lite-edit-") as temporary:
        candidate_root = Path(temporary) / "project"
        for markdown_path in project_path.rglob("*.md"):
            relative = markdown_path.relative_to(project_path)
            destination = candidate_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(markdown_path, destination)
        candidate_source = candidate_root / Path(source_file)
        candidate_source.parent.mkdir(parents=True, exist_ok=True)
        candidate_source.write_bytes(patched_bytes)
        findings = _all_validation_findings(candidate_root)
    errors = [message for severity, message in findings if severity == "ERROR"]
    if errors:
        formatted = "; ".join(errors)
        raise EditValidationError(f"Update would make the project invalid: {formatted}")
    return findings


def _atomic_write(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        shutil.copymode(path, temporary_path)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


_REQUIREMENT_ID = re.compile(r"^REQ-(?P<number>[0-9]+)$")


def _resolved_source_path(project_path: Path, source_file: str) -> Path:
    source_path = (project_path / Path(source_file)).resolve()
    try:
        source_path.relative_to(project_path)
    except ValueError as error:
        raise EditingError(
            f"Source provenance escapes the project directory: {source_file}"
        ) from error
    if not source_path.is_file():
        raise EditingError(f"Source file no longer exists: {source_file}")
    return source_path


def _table_content_and_bytes(
    source_path: Path, source_file: str, source_ref: SourceRef
) -> tuple[ParsedMarkdownTable, bytes, str, list[str], str]:
    original_bytes = source_path.read_bytes()
    has_bom = original_bytes.startswith(b"\xef\xbb\xbf")
    try:
        text = original_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise EditingError(f"Source file is not valid UTF-8: {source_file}") from error
    tables = parse_markdown_tables_with_provenance(source_path, source_file=source_file)
    table = _table_for_ref(tables, source_ref)
    if table.source_ref.line is None or not table.row_sources:
        raise RequirementCreationUnavailableError(
            "The Requirement table has no stable physical source range."
        )
    lines = text.splitlines(keepends=True)
    start = table.source_ref.line - 1
    end = max(source.line or 0 for source in table.row_sources)
    raw_table = "".join(lines[start:end])
    revision = hashlib.sha256(
        (source_file + "\0" + str(source_ref.table_index) + "\0" + raw_table).encode(
            "utf-8"
        )
    ).hexdigest()
    return table, original_bytes, text, lines, ("bom:" if has_bom else "") + revision


def _next_requirement_id(model: Model) -> str:
    numbers: list[int] = []
    widths: list[int] = []
    for obj in model.objects.values():
        if obj.type != "Requirement":
            continue
        match = _REQUIREMENT_ID.fullmatch(obj.id)
        if match is None:
            raise RequirementCreationUnavailableError(
                f"Requirement ID {obj.id!r} is not a numeric REQ-* stable ID."
            )
        digits = match.group("number")
        numbers.append(int(digits))
        widths.append(len(digits))
    next_number = max(numbers, default=0) + 1
    width = max(3, *widths, len(str(next_number)))
    return f"REQ-{next_number:0{width}d}"


def resolve_requirement_creation_target(
    project_dir: str | Path, model: Model | None = None
) -> RequirementCreationTarget:
    """Resolve the one existing table that owns Requirement objects."""

    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise EditingError(f"Project directory does not exist: {project_path}")
    current_model = model if model is not None else load_model(project_path)
    candidate_keys = {
        (obj.source_ref.file, obj.source_ref.table_index)
        for obj in current_model.objects.values()
        if obj.type == "Requirement" and obj.source_ref is not None
    }
    if not candidate_keys:
        raise RequirementCreationUnavailableError(
            "No existing writable Requirement table was found."
        )
    if len(candidate_keys) != 1:
        raise RequirementCreationUnavailableError(
            "Multiple Requirement tables are present; creation target is ambiguous."
        )
    source_file, table_index = next(iter(candidate_keys))
    source_ref = SourceRef(file=source_file, table_index=table_index)
    source_path = _resolved_source_path(project_path, source_file)
    if not source_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise RequirementCreationUnavailableError(
            "The Requirement table source is not writable."
        )
    table, _, _, _, revision = _table_content_and_bytes(
        source_path, source_file, source_ref
    )
    if table.headers.count("ID") != 1:
        raise RequirementCreationUnavailableError(
            "The Requirement table must contain exactly one ID column."
        )
    if len(set(table.headers)) != len(table.headers):
        raise RequirementCreationUnavailableError(
            "The Requirement table contains duplicate column names."
        )
    columns = tuple(header for header in table.headers if header != "ID")
    if not columns:
        raise RequirementCreationUnavailableError(
            "The Requirement table has no writable creation columns."
        )
    if current_model.duplicate_ids:
        raise RequirementCreationUnavailableError(
            "Stable IDs are not globally unique in the current project."
        )
    return RequirementCreationTarget(
        source_file=source_file,
        source_ref=source_ref,
        columns=columns,
        table_revision=revision,
        suggested_id=_next_requirement_id(current_model),
    )


def requirement_creation_metadata(project_dir: str | Path) -> dict[str, object]:
    """Return browser-safe dynamic form metadata without filesystem locations."""

    try:
        target = resolve_requirement_creation_target(project_dir)
    except EditingError as error:
        return {"enabled": False, "reason": str(error)}
    semantic_required = {"Name", "Requirement", "Description"}
    return {
        "enabled": True,
        "columns": [
            {
                "name": column,
                "editable": True,
                "required": column in semantic_required,
                **({"default": "Draft"} if column == "Status" else {}),
            }
            for column in target.columns
        ],
        "expected_table_revision": target.table_revision,
        "suggested_id": target.suggested_id,
    }


def _creation_row_bytes(
    project_path: Path,
    target: RequirementCreationTarget,
    model: Model,
    object_id: str,
    values: Mapping[str, str],
) -> tuple[Path, bytes, bytes]:
    source_path = _resolved_source_path(project_path, target.source_file)
    table, original_bytes, _, lines, actual_revision = _table_content_and_bytes(
        source_path, target.source_file, target.source_ref
    )
    if actual_revision != target.table_revision:
        raise RequirementTableConflictError(target.table_revision, actual_revision)
    requirement_rows = [
        source
        for row, source in zip(table.rows, table.row_sources)
        if model.objects.get(row.get("ID", "").strip()) is not None
        and model.objects[row.get("ID", "").strip()].type == "Requirement"
    ]
    if not requirement_rows:
        raise RequirementCreationUnavailableError(
            "The resolved Requirement table no longer contains Requirement rows."
        )
    insertion_line = max(source.line or 0 for source in requirement_rows)
    template_body = lines[insertion_line - 1].rstrip("\r\n")
    row_values = {"ID": object_id, **{column: values.get(column, "") for column in target.columns}}
    new_row = template_body
    for index, header in enumerate(table.headers):
        new_row = _replace_cell(new_row, index, row_values[header])
    physical = lines[insertion_line - 1]
    line_ending = physical[len(physical.rstrip("\r\n")) :]
    if not line_ending:
        line_ending = "\r\n" if "\r\n" in "".join(lines[:2]) else "\n"
        lines.insert(insertion_line, line_ending + new_row)
    else:
        lines.insert(insertion_line, new_row + line_ending)
    patched_bytes = "".join(lines).encode("utf-8")
    if original_bytes.startswith(b"\xef\xbb\xbf"):
        patched_bytes = b"\xef\xbb\xbf" + patched_bytes
    return source_path, original_bytes, patched_bytes


def _assert_created_model(
    original: Model,
    candidate: Model,
    target: RequirementCreationTarget,
    object_id: str,
    values: Mapping[str, str],
) -> None:
    expected_ids = set(original.objects) | {object_id}
    if set(candidate.objects) != expected_ids or candidate.duplicate_ids:
        raise EditValidationError(
            "Requirement creation did not preserve exactly the existing objects plus one new object."
        )
    for existing_id, existing in original.objects.items():
        current = candidate.objects[existing_id]
        if current.type != existing.type or current.attributes != existing.attributes:
            raise EditValidationError(
                f"Requirement creation unexpectedly changed existing object {existing_id}."
            )
    created = candidate.objects.get(object_id)
    expected_attributes = {column: values.get(column, "") for column in target.columns}
    if (
        created is None
        or created.type != "Requirement"
        or created.attributes != expected_attributes
        or created.source_ref is None
        or created.source_ref.file != target.source_file
        or created.source_ref.table_index != target.source_ref.table_index
    ):
        raise EditValidationError(
            "The candidate project does not contain the requested Requirement exactly once with normal provenance."
        )
    original_relations = [
        (relation.source, relation.relation, relation.target, relation.source_file)
        for relation in original.relations
    ]
    candidate_relations = [
        (relation.source, relation.relation, relation.target, relation.source_file)
        for relation in candidate.relations
    ]
    if candidate_relations != original_relations:
        raise EditValidationError("Requirement creation must not create or change relations.")


def _validate_creation_candidate(
    project_path: Path,
    source_file: str,
    patched_bytes: bytes,
    original: Model,
    target: RequirementCreationTarget,
    object_id: str,
    values: Mapping[str, str],
) -> tuple[tuple[tuple[str, str], ...], Model]:
    with tempfile.TemporaryDirectory(prefix="mbse-lite-create-") as temporary:
        candidate_root = Path(temporary) / "project"
        for markdown_path in project_path.rglob("*.md"):
            relative = markdown_path.relative_to(project_path)
            destination = candidate_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(markdown_path, destination)
        candidate_source = candidate_root / Path(source_file)
        candidate_source.parent.mkdir(parents=True, exist_ok=True)
        candidate_source.write_bytes(patched_bytes)
        findings = _all_validation_findings(candidate_root)
        errors = [message for severity, message in findings if severity == "ERROR"]
        if errors:
            raise EditValidationError(
                "Requirement creation would make the project invalid: " + "; ".join(errors)
            )
        candidate = load_model(candidate_root)
        _assert_created_model(original, candidate, target, object_id, values)
    return findings, candidate


def create_requirement(
    project_dir: str | Path, command: CreateRequirement
) -> CreateRequirementResult:
    """Create one validated Requirement row in the provenance-resolved table."""

    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise EditingError(f"Project directory does not exist: {project_path}")
    if not isinstance(command.values, Mapping):
        raise EditingError("Requirement values must be a mapping of column names to strings.")
    if not isinstance(command.expected_table_revision, str) or not command.expected_table_revision:
        raise EditingError("expected_table_revision must be a non-empty string.")
    values = dict(command.values)
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
        raise EditingError("Requirement column names and values must be strings.")
    if "ID" in values:
        raise EditingError("The stable Requirement ID is assigned by the application.")

    model = load_model(project_path)
    target = resolve_requirement_creation_target(project_path, model)
    if command.expected_table_revision != target.table_revision:
        raise RequirementTableConflictError(
            command.expected_table_revision, target.table_revision
        )
    unknown = sorted(set(values) - set(target.columns))
    if unknown:
        raise EditingError("Unknown Requirement columns: " + ", ".join(unknown))
    required = [
        column
        for column in target.columns
        if column in {"Name", "Requirement", "Description"}
    ]
    missing_required = [
        column for column in required if not values.get(column, "").strip()
    ]
    if missing_required:
        raise EditingError(
            "Required Requirement values must not be blank: "
            + ", ".join(missing_required)
        )
    object_id = _next_requirement_id(model)
    if object_id in model.objects or object_id in model.duplicate_ids:
        raise EditingError(f"Allocated stable ID is not globally unique: {object_id}")

    source_path, original_bytes, patched_bytes = _creation_row_bytes(
        project_path, target, model, object_id, values
    )
    findings, _ = _validate_creation_candidate(
        project_path,
        target.source_file,
        patched_bytes,
        model,
        target,
        object_id,
        values,
    )
    if source_path.read_bytes() != original_bytes:
        current = resolve_requirement_creation_target(project_path)
        raise RequirementTableConflictError(target.table_revision, current.table_revision)
    _atomic_write(source_path, patched_bytes)
    try:
        findings = _all_validation_findings(project_path)
        errors = [message for severity, message in findings if severity == "ERROR"]
        if errors:
            raise EditValidationError(
                "Committed Requirement creation failed validation: " + "; ".join(errors)
            )
        committed = load_model(project_path)
        _assert_created_model(model, committed, target, object_id, values)
        refreshed_target = resolve_requirement_creation_target(project_path, committed)
    except Exception:
        if source_path.read_bytes() == patched_bytes:
            _atomic_write(source_path, original_bytes)
        raise
    created = committed.objects[object_id]
    assert created.source_ref is not None
    return CreateRequirementResult(
        created_object_id=object_id,
        source_file=target.source_file,
        source_ref=created.source_ref,
        table_revision=refreshed_target.table_revision,
        validation_findings=findings,
    )


def update_object_attribute(
    project_dir: str | Path, command: UpdateObjectAttribute
) -> UpdateAttributeResult:
    """Apply one provenance-resolved, validated, atomic Markdown cell update."""

    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise EditingError(f"Project directory does not exist: {project_path}")
    if command.attribute.strip().casefold() == "id":
        raise EditingError(
            "Stable IDs are immutable through update-attribute; use a dedicated refactoring operation"
        )

    model = load_model(project_path)
    obj = model.objects.get(command.object_id)
    if obj is None:
        raise EditingError(f"Unknown object ID: {command.object_id}")
    if command.attribute not in obj.attributes:
        raise EditingError(
            f"Object {command.object_id} has no attribute {command.attribute!r}"
        )
    source_ref = obj.attribute_sources.get(command.attribute)
    if source_ref is None or source_ref.row_id != command.object_id:
        raise EditingError(
            f"No stable source provenance is available for "
            f"{command.object_id}.{command.attribute}"
        )

    old_value = obj.attributes[command.attribute]
    if (
        command.expected_old_value is not None
        and old_value != command.expected_old_value
    ):
        raise EditConflictError(
            f"Conflict for {command.object_id}.{command.attribute}: expected "
            f"{command.expected_old_value!r}, found {old_value!r}"
        )

    source_path = (project_path / Path(source_ref.file)).resolve()
    try:
        source_path.relative_to(project_path)
    except ValueError as error:
        raise EditingError(
            f"Source provenance escapes the project directory: {source_ref.file}"
        ) from error
    if not source_path.is_file():
        raise EditingError(f"Source file no longer exists: {source_ref.file}")

    original_bytes, patched_bytes, current_ref = _patch_source_bytes(
        source_path,
        source_ref.file,
        source_ref,
        command.object_id,
        command.attribute,
        old_value,
        command.new_value,
    )
    findings = _validate_candidate(project_path, source_ref.file, patched_bytes)
    changed = original_bytes != patched_bytes

    if changed and not command.dry_run:
        if source_path.read_bytes() != original_bytes:
            raise EditConflictError(
                f"Conflict for {command.object_id}.{command.attribute}: "
                f"{source_ref.file} changed before commit"
            )
        _atomic_write(source_path, patched_bytes)
        try:
            findings = _all_validation_findings(project_path)
            errors = [message for severity, message in findings if severity == "ERROR"]
            if errors:
                raise EditValidationError(
                    "Committed update failed validation: " + "; ".join(errors)
                )
        except Exception:
            if source_path.read_bytes() == patched_bytes:
                _atomic_write(source_path, original_bytes)
            raise

    return UpdateAttributeResult(
        object_id=command.object_id,
        attribute=command.attribute,
        old_value=old_value,
        new_value=command.new_value,
        source_file=source_ref.file,
        source_ref=current_ref,
        dry_run=command.dry_run,
        changed=changed,
        validation_findings=findings,
    )


__all__ = [
    "CreateRequirement",
    "CreateRequirementResult",
    "EditConflictError",
    "EditingError",
    "EditValidationError",
    "RequirementCreationTarget",
    "RequirementCreationUnavailableError",
    "RequirementTableConflictError",
    "UpdateAttributeResult",
    "UpdateObjectAttribute",
    "create_requirement",
    "editable_attribute_names",
    "encode_markdown_table_cell",
    "requirement_creation_metadata",
    "resolve_requirement_creation_target",
    "update_object_attribute",
]
