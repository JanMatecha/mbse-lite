from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .core import (
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
    "EditConflictError",
    "EditingError",
    "EditValidationError",
    "UpdateAttributeResult",
    "UpdateObjectAttribute",
    "encode_markdown_table_cell",
    "update_object_attribute",
]
