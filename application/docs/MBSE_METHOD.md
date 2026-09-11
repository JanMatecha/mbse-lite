# MBSE Lite Method

## Purpose

MBSE Lite is a pragmatic method for small technical projects. It borrows the core ideas of systems engineering and MBSE while keeping the project model readable as plain text.

The method is intentionally not a complete implementation of SysML or any ISO/IEC/IEEE standard. Its vocabulary and relations should, however, remain reasonably mappable to SysML v2 concepts in the future.

## Source of truth

Project Markdown files are authoritative. Generated XLSX, HTML and Mermaid files are views or exchange formats.

A project may organize authoritative Markdown in nested directories. MBSE Lite reads Markdown recursively from the project directory, so engineering and project-management information can be physically separated while remaining part of one traceable project model.

## Recommended project areas

Use two clearly separated areas when a project contains both system engineering and delivery planning:

```text
project/
├── mbse/
│   ├── needs
│   ├── requirements
│   ├── functions
│   ├── architecture / concepts / decisions
│   ├── verification
│   ├── engineering issues and risks
│   └── engineering relations
└── project_management/
    ├── tasks
    ├── milestones
    └── project-management and cross-area relations
```

The separation answers two different questions:

- `mbse/` — what system are we developing, why, and how will we know it is correct?
- `project_management/` — what work must be done, by whom, and when?

Explicit relations may cross the boundary. For example, a task can `resolve` an engineering issue or `produce` a verification result.

## Object types

| Prefix | Object | Primary area | Purpose |
|---|---|---|---|
| NEED | Need | MBSE | Stakeholder/user need or problem to solve |
| REQ | Requirement | MBSE | Verifiable statement the solution shall satisfy |
| FUN | Function | MBSE | What the system must do |
| PART | Part | MBSE | Logical or physical element of the solution |
| CON | Concept | MBSE | Candidate solution or architectural alternative |
| VER | Verification | MBSE | Test, inspection, analysis or demonstration |
| DEC | Decision | MBSE | Recorded technical decision and rationale |
| RISK | Risk | Context-dependent | Technical risk in `mbse/`; delivery/project risk in `project_management/` |
| ISSUE | Issue | Context-dependent | Engineering open point in `mbse/`; delivery/project issue in `project_management/` |
| TASK | Task | Project management | Planned project work |
| MS | Milestone | Project management | Significant project checkpoint |

Folder placement is therefore meaningful for `RISK` and `ISSUE`. Do not move an engineering uncertainty into project management merely because somebody must work on it; instead keep the issue in `mbse/` and link a `TASK` to it.

## Minimum engineering flow

```text
NEED -> REQ -> FUN -> CON/PART -> VER
```

The exact graph does not need to be linear. A need may derive several requirements; a requirement may map to several functions and verification cases; functions may be realized by parts or candidate concepts.

## IDs

Every model object must have a stable and unique ID in the form:

```text
PREFIX-NNN
```

Examples: `REQ-001`, `FUN-004`, `DEC-002`.

IDs are unique across the whole project, including both `mbse/` and `project_management/`, and should not be reused after an object is deleted or deprecated.

## Relations

Relations are stored explicitly in Markdown tables with the columns:

```text
Source | Relation | Target
```

Recommended engineering relations include:

- `derives`
- `satisfied_by`
- `realized_by`
- `verified_by`
- `connects_to`
- `selects`
- `affects`

Recommended project relations include:

- `produces`
- `resolves`
- `evaluates`
- `depends_on`
- `threatens`

Relations may be split across files. A recommended convention is to keep engineering-to-engineering relations under `mbse/` and relations involving project-management objects under `project_management/`.

The vocabulary is deliberately small in the POC. New relation types should be added only when a real project needs them.

## Validation rules in V0.1

The tool checks at least:

1. object IDs are unique across all project areas,
2. relation sources and targets exist,
3. requirements have incoming and outgoing traceability,
4. requirements have verification relations,
5. functions have a realization relation.

Warnings indicate incomplete engineering work; errors indicate an inconsistent model.

## Views

The same model can be represented in different forms:

- Markdown — primary human-readable project model,
- Mermaid — graphical engineering/traceability view,
- HTML — project overview/dashboard,
- XLSX — LibreOffice-compatible table exchange and review format.

Generated views may combine both project areas, but should preserve source paths so the distinction between MBSE and project management remains visible.

## Project management

Project-management information is related to, but distinct from, the engineering model. Tasks and milestones belong in `project_management/`. Technical needs, requirements, functions, architecture, verification and technical decisions belong in `mbse/`.

Technical issues and risks remain in `mbse/`; project/delivery issues and risks may live in `project_management/`. Project-management objects should reference engineering objects where useful rather than duplicating engineering facts.

This lets the project answer separately:

- what and why are we developing?
- what work is required to deliver it?

## POC boundaries

V0.1 intentionally excludes:

- database/server storage,
- concurrent-edit conflict handling,
- graphical editing,
- full SysML v2 parsing,
- PLM/ALM integration,
- automated simulation integration,
- complex workflow/approval management.

These should only be introduced after a real project demonstrates the need.
