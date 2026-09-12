# MBSE Lite Method

## Purpose

MBSE Lite is a pragmatic method for small technical projects. It borrows the core ideas of systems engineering and MBSE while keeping the project model readable as plain text.

The method is intentionally not a complete implementation of SysML or any ISO/IEC/IEEE standard. Its vocabulary and relations should, however, remain reasonably mappable to SysML v2 concepts in the future.

## Source of truth

Project Markdown files are authoritative. Generated XLSX, HTML, JSON, Mermaid, SVG and glTF/GLB files are views or exchange formats.

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

`PREFIX` must be one of the prefixes in the Object types table above and `NNN` must be exactly three decimal digits. Unknown prefixes and any other ID format are validation errors.

IDs are unique across the whole project, including both `mbse/` and `project_management/`, and should not be reused after an object is deleted or deprecated.

Stable IDs are not ordinary editable attributes. The generic update command will not change an ID because doing so requires a future graph-wide refactoring operation.

## Structured engineering quantities

When a numeric engineering value is intended to drive geometry or another generator, keep it in a dedicated object-table attribute instead of relying on prose extraction. Put the unit in the column header, for example `Target Length [m]`, and keep the cell value numeric, for example `4.0`. The parser retains the value as text for backward compatibility; the geometry layer converts it to a deterministic decimal `Quantity` only after validating that the value exists, is numeric, finite and positive and that its source object and unit match the generator contract.

Human-readable requirement prose may refer to the structured dimensions without repeating their authoritative numbers. Unresolved geometry remains `TBD`. Visualization-only placeholders are ordinary renderer settings, not typed engineering quantities, and must never be written back as project facts.

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

## Validation rules

The tool checks at least:

1. every object ID has the exact `PREFIX-NNN` format, uses a documented prefix and is unique across all project areas,
2. relation sources and targets exist and relation types are not empty,
3. every requirement has an incoming `derives` relation whose source is a Need,
4. every requirement has at least one outgoing `satisfied_by` relation,
5. every requirement has at least one outgoing `verified_by` relation,
6. every function has at least one outgoing `realized_by` relation.

An activated geometry profile can add generator-specific structural checks. The garden-shed profile, for example, maps an explicit `footprint` role to a Requirement and requires positive decimal `Target Length [m]` and `Target Depth [m]` values. It does not search prose or substitute default engineering dimensions when these inputs are invalid.

ID format, prefix, uniqueness and broken relation-reference findings are errors because they make the model structurally inconsistent. Missing semantic traceability from rules 3–6 is a warning because it can represent incomplete engineering work. Relation names are matched exactly; a different or generic relation does not satisfy these checks.

## Views

The same model can be represented in different forms:

- Markdown — primary human-readable project model,
- Mermaid — graphical engineering/traceability view,
- HTML and generated JSON — interactive project viewer and its manifest/model payload,
- SVG — derived 2D engineering view,
- glTF/GLB — derived 3D engineering view,
- XLSX — LibreOffice-compatible table exchange and review format.

Generated views may combine both project areas, but should preserve source paths so the distinction between MBSE and project management remains visible. Visualization elements should reference existing stable model IDs instead of defining an independent identity system. For example, an SVG element may use `data-mbse-id="PART-012"`, and a glTF node may use `extras.mbse_id` with the same value.

The generated viewer manifest and renderer/selection contracts are documented in `VIEW_ARCHITECTURE.md`. Visualization output is always derived: it must not silently add requirements, decisions, geometry facts or other authoritative engineering content.

## Project management

Project-management information is related to, but distinct from, the engineering model. Tasks and milestones belong in `project_management/`. Technical needs, requirements, functions, architecture, verification and technical decisions belong in `mbse/`.

Technical issues and risks remain in `mbse/`; project/delivery issues and risks may live in `project_management/`. Project-management objects should reference engineering objects where useful rather than duplicating engineering facts.

This lets the project answer separately:

- what and why are we developing?
- what work is required to deliver it?

## POC boundaries

The current POC intentionally excludes:

- database/server storage,
- graphical editing,
- full SysML v2 parsing,
- PLM/ALM integration,
- automated simulation integration,
- complex workflow/approval management.

The local `update-attribute` command provides optimistic stale-write detection and atomic validation as the foundation for a future editor; the browser remains read-only and no web backend is included.
