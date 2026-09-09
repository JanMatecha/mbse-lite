# MBSE Lite

A lightweight, text-first MBSE proof of concept for small technical projects.

## Goal

The project explores whether the core principles of Model-Based Systems Engineering can be used effectively without a heavyweight MBSE tool. The source of truth is plain Markdown; Python validates the model and generates alternative views and exports.

## Core principles

- Markdown is the source of truth.
- Every model object has a unique ID.
- Relations are explicit and machine-readable.
- One model can generate multiple views.
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

The Python tool is intended to provide:

- model validation,
- reference and traceability checks,
- Mermaid diagrams,
- LibreOffice-compatible `.xlsx` export,
- static HTML project overview.

## Repository layout

```text
mbse-lite/
├── docs/
├── projects/
│   └── demo_project/
├── src/
│   └── mbse_lite/
├── tests/
├── pyproject.toml
└── README.md
```

## Quick start

```bash
uv sync
uv run mbse-lite validate projects/demo_project
uv run mbse-lite export-mermaid projects/demo_project generated/traceability.md
uv run mbse-lite export-html projects/demo_project generated/index.html
uv run mbse-lite export-xlsx projects/demo_project generated/model.xlsx
```

The demo project is intentionally generic and only demonstrates the mechanics of the MBSE-lite model.
