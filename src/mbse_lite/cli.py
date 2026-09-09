from __future__ import annotations

import argparse
from pathlib import Path

from .core import (
    export_html,
    export_mermaid,
    export_xlsx,
    import_xlsx_to_markdown,
    load_model,
    validate_model,
)


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project", type=Path, help="Path to a project directory containing Markdown files")


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

    xlsx = sub.add_parser("export-xlsx", help="Generate a LibreOffice-compatible XLSX workbook")
    _add_project_argument(xlsx)
    xlsx.add_argument("output", type=Path)

    xlsx_import = sub.add_parser(
        "import-xlsx",
        help="Convert an edited MBSE-lite XLSX workbook to normalized Markdown for review",
    )
    xlsx_import.add_argument("input", type=Path)
    xlsx_import.add_argument("output_dir", type=Path)

    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "import-xlsx":
        written = import_xlsx_to_markdown(args.input, args.output_dir)
        for path in written:
            print(f"Written: {path}")
        print("Review the imported Markdown before replacing source-of-truth project files.")
        return 0

    model = load_model(args.project)

    if args.command == "validate":
        findings = validate_model(model)
        print(f"Objects: {len(model.objects)}")
        print(f"Relations: {len(model.relations)}")
        if not findings:
            print("OK: no validation findings")
            return 0
        for severity, message in findings:
            print(f"{severity}: {message}")
        return 1 if any(severity == "ERROR" for severity, _ in findings) else 0

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
