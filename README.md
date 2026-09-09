# MBSE Lite

A lightweight, text-first MBSE proof of concept for small technical projects.

## Goal

The project explores whether the core principles of Model-Based Systems Engineering can be used effectively without a heavyweight MBSE tool. The source of truth is plain Markdown; Python validates the model and generates alternative views and exports.

The home/private workflow is designed around **Git + Codex + Python + Markdown + Mermaid + LibreOffice + HTML**.

## Core principles

- Markdown is the source of truth.
- Every model object has a unique ID.
- Relations are explicit and machine-readable.
- One model can generate multiple views.
- LibreOffice/XLSX is an exchange and collaboration view, not the master model.
- XLSX changes are imported to a separate normalized Markdown directory for review before replacing source files.
- The POC stays intentionally small and understandable.
- The data model should remain reasonably mappable to SysML v2 concepts later.

## Initial object types

- `NEED` — stakeholder or user need
- `REQ` — requirement
- `FUN` — function / action
- `PART` — system part / component
- `CON` — concept / alternative
- `VER` — verification / test
- `DEC` — decision
- `RISK` — risk
- `ISSUE` — open issue / question
- `TASK` — project task
- `MS` — milestone

## Typical engineering chain

```text
NEED -> REQ -> FUN -> CON/PART -> VER
```

Project-management objects such as `TASK`, `RISK`, `ISSUE` and `MS` can be related to the engineering model.

## POC outputs

The Python tool provides:

- model validation,
- reference and traceability checks,
- Mermaid diagrams,
- LibreOffice-compatible `.xlsx` export,
- safe `.xlsx` -> Markdown import for review,
- static HTML project overview with Mermaid visualization.

## Repository layout

```text
mbse-lite/
├── .github/workflows/
├── docs/
├── projects/
│   └── demo_project/
├── src/
│   └── mbse_lite/
├── tests/
├── AGENTS.md
├── pyproject.toml
└── README.md
```

`AGENTS.md` contains repository-level instructions for Codex.

## Quick start

```bash
uv sync --extra dev

uv run mbse-lite validate projects/demo_project
uv run mbse-lite export-mermaid projects/demo_project generated/traceability.md
uv run mbse-lite export-html projects/demo_project generated/index.html
uv run mbse-lite export-xlsx projects/demo_project generated/model.xlsx
```

After editing `generated/model.xlsx` in LibreOffice Calc, convert it back to a **review directory**:

```bash
uv run mbse-lite import-xlsx generated/model.xlsx imported_from_calc
uv run mbse-lite validate imported_from_calc
```

Review the imported Markdown before using it as the new source-of-truth project model.

## Development checks

```bash
uv run pytest -q
```

GitHub Actions also runs the tests and validates the demo project on each push and pull request.

The demo project is intentionally generic and only demonstrates the mechanics of the MBSE-lite model.
