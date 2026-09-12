from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from .core import (
    export_html,
    export_mermaid,
    export_xlsx,
    import_xlsx_to_markdown,
    load_model,
    validate_model,
)
from .editing import EditingError, UpdateObjectAttribute, update_object_attribute
from .viewer import export_viewer
from .visualization import validate_visualizations


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", type=Path, help="Path to a project directory containing Markdown files")


def _default_viewer_output(project: Path) -> Path:
    project_path = project.resolve()
    if project_path.parent.name == "projects":
        root = project_path.parent.parent
    else:
        root = Path.cwd()
    return root / "generated" / project_path.name / "index.html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mbse-lite", description="Lightweight Markdown-first MBSE toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate IDs, relations and basic traceability")
    _add_project_argument(validate)

    mermaid = sub.add_parser("export-mermaid", help="Generate a Mermaid traceability view")
    _add_project_argument(mermaid)
    mermaid.add_argument("output", type=Path)

    html = sub.add_parser("export-html", help="Generate a static HTML project overview")
    _add_project_argument(html)
    html.add_argument("output", type=Path)

    view = sub.add_parser("view", help="Generate and open a local interactive web viewer bundle")
    _add_project_argument(view)
    view.add_argument("--output", type=Path, default=None, help="Optional output HTML path")
    view.add_argument("--no-open", action="store_true", help="Generate the viewer without opening a browser")

    cad = sub.add_parser(
        "export-cad",
        help="Generate optional CadQuery footprint and conceptual-preview artifacts",
    )
    _add_project_argument(cad)
    cad.add_argument("output_dir", type=Path)

    xlsx = sub.add_parser("export-xlsx", help="Generate a LibreOffice-compatible XLSX workbook")
    _add_project_argument(xlsx)
    xlsx.add_argument("output", type=Path)

    xlsx_import = sub.add_parser(
        "import-xlsx",
        help="Convert an edited MBSE-lite XLSX workbook to normalized Markdown for review",
    )
    xlsx_import.add_argument("input", type=Path)
    xlsx_import.add_argument("output_dir", type=Path)

    update = sub.add_parser(
        "update-attribute",
        help="Safely update one existing object attribute in authoritative Markdown",
    )
    _add_project_argument(update)
    update.add_argument("object_id", help="Stable object ID, for example PART-012")
    update.add_argument("attribute", help="Existing Markdown table column name")
    update.add_argument("value", help="New attribute value")
    update.add_argument(
        "--expect",
        default=None,
        help="Reject the update unless the current value exactly matches this value",
    )
    update.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and validate the update without modifying Markdown",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "import-xlsx":
        written = import_xlsx_to_markdown(args.input, args.output_dir)
        for path in written:
            print(f"Written: {path}")
        print("Review the imported Markdown before replacing source-of-truth project files.")
        return 0

    if args.command == "update-attribute":
        try:
            result = update_object_attribute(
                args.project,
                UpdateObjectAttribute(
                    object_id=args.object_id,
                    attribute=args.attribute,
                    new_value=args.value,
                    expected_old_value=args.expect,
                    dry_run=args.dry_run,
                ),
            )
        except EditingError as error:
            print(f"ERROR: {error}")
            return 1
        print(f"Object: {result.object_id}")
        print(f"Attribute: {result.attribute}")
        print(f"Old value: {result.old_value}")
        print(f"New value: {result.new_value}")
        print(f"Markdown file: {result.source_file}")
        if result.dry_run:
            print("Dry run: validation passed; no files modified")
        elif result.changed:
            print("Updated: validation passed")
        else:
            print("No change: validation passed")
        return 0

    if args.command == "export-cad":
        from .cad import CadError, export_project_cad

        try:
            result = export_project_cad(load_model(args.project), args.output_dir)
        except (CadError, ValueError) as error:
            print(f"ERROR: {error}")
            return 1
        print("CAD export completed successfully.")
        for path in result.artifacts:
            print(f"Written: {path}")
        if result.warning:
            print(result.warning)
        return 0

    model = load_model(args.project)

    if args.command == "validate":
        findings = [*validate_model(model), *validate_visualizations(model)]
        print(f"Objects: {len(model.objects)}")
        print(f"Relations: {len(model.relations)}")
        if not findings:
            print("OK: no validation findings")
            return 0
        for severity, message in findings:
            print(f"{severity}: {message}")
        return 1 if any(severity == "ERROR" for severity, _ in findings) else 0

    if args.command == "view":
        output = args.output or _default_viewer_output(args.project)
        export_viewer(model, output, project_name=args.project.resolve().name)
        print(f"Written: {output}")
        if not args.no_open:
            webbrowser.open(output.resolve().as_uri())
        return 0

    if args.command == "export-mermaid":
        export_mermaid(model, args.output)
    elif args.command == "export-html":
        export_html(model, args.output)
    elif args.command == "export-xlsx":
        export_xlsx(model, args.output)
    else:
        raise AssertionError(f"Unhandled command: {args.command}")

    print(f"Written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
