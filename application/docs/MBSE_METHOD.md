# MBSE Lite Method

## Purpose

MBSE Lite is a pragmatic method for small technical projects. It borrows the core ideas of systems engineering and MBSE while keeping the project model readable as plain text.

The method is intentionally not a complete implementation of SysML or any ISO/IEC/IEEE standard. Its vocabulary and relations should, however, remain reasonably mappable to SysML v2 concepts in the future.

## Source of truth

Project Markdown files that belong to the declared MBSE Lite model are authoritative. Generated XLSX, HTML, JSON, Mermaid, SVG and glTF/GLB files are views or exchange formats.

A project may organize authoritative Markdown in nested directories. V0.10 reads Markdown recursively from the project directory, so engineering and project-management information can be physically separated while remaining part of one traceable project model.

The target portable project contract will make the authoritative model roots explicit so host metadata can coexist beside the model without being interpreted as engineering content.

## Project root and storage location

The directory passed to MBSE Lite is the project root. Project semantics must not depend on a fixed absolute path, on being stored below this source repository, or on a particular parent-directory name.

Repository-local projects under `../projects/` are valid and currently useful for development, regression and integration testing. They are not the only intended production storage model.

A future real project may live in external domain storage. For the planned Family KB integration, the host pattern is:

```text
<DOMAIN>/
└── <TOPIC>/
    └── <PROJECT>/
        ├── 00_INFO/
        ├── XX_PHOTOS/
        ├── XX_COMMUNICATION/
        ├── XX_DOCUMENTS/
        └── XX_MBSE/              # MBSE Lite project root
            ├── 00_INFO/          # host-side workspace metadata
            ├── README.md
            ├── AGENTS.md
            ├── mbse/
            └── project_management/
```

`XX_MBSE` is an example host-side workspace boundary. The `XX` prefix is ordering owned by the host knowledge base. MBSE Lite must not use that number, the directory name or the absolute path as project identity.

The target architecture introduces a stable `project_id` that survives a project move or rename. The exact metadata format is intentionally not fixed by this method yet.

## Embedded workspace boundary

A host knowledge base may place metadata such as `00_INFO/` inside the MBSE Lite project root. That host metadata describes the workspace boundary and integration contract; it is not engineering model content.

The target parser contract therefore distinguishes explicit model roots, normally including:

```text
mbse/
project_management/
```

from host metadata and other non-model content.

V0.10 does not yet implement explicit model-root filtering: it scans Markdown recursively beneath the supplied project root. Until that capability is implemented, host metadata used with V0.10 must avoid Markdown tables that could be mistaken for model-object tables with an `ID` column or relation tables with `Source | Relation | Target` columns.

## External context and provenance

A real project may need evidence that naturally belongs outside the MBSE workspace, such as photographs, supplier documents, communication, measurements or other domain records.

The target architecture allows explicitly declared external context to be read without making it writable project content. The default rule is:

```text
MBSE project root     = read + controlled write
external context      = read/reference only
```

An MBSE object may reference such an external source as provenance. The reference does not copy the source into the MBSE model and does not grant permission to modify the source.

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

`PREFIX` must be one of the prefixes in the Object types table above. The numeric suffix must contain at least three decimal digits; wider suffixes are valid once a sequence exceeds its existing width. Unknown prefixes, shorter suffixes and non-numeric suffixes are validation errors.

IDs are unique across the whole project, including both `mbse/` and `project_management/`, and should not be reused after an object is deleted or deprecated.

Stable model-object IDs are not ordinary editable attributes. The generic update command will not change an ID because doing so requires a future graph-wide refactoring operation.

A future project-level `project_id` is a separate concept from object IDs. It identifies the MBSE workspace itself and remains stable when the workspace directory moves or is renamed.

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

1. every object ID uses the `PREFIX-NNN` form with at least three suffix digits, uses a documented prefix and is unique across all project areas,
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

## Controlled changes and history

Markdown remains the source of truth even when edits are initiated from a browser or future AI client.

Current controlled writes use provenance, optimistic concurrency, candidate validation and atomic commit/rollback. The target architecture extends that foundation with semantic changesets that can group several related model mutations and record engineering meaning such as actor/client, reason, source evidence, diff and validation result.

Semantic changesets complement underlying file/version history; they do not replace the authoritative Markdown files or storage-provider revision history.

## Current implementation boundary

V0.10 includes:

- a static read-only viewer that works without a running server,
- a loopback-only local editable web application,
- controlled editing of existing provenance-backed scalar attributes,
- controlled creation of one new Requirement in the single discovered authoritative Requirement table,
- optimistic concurrency, candidate validation, atomic writes and rollback for supported mutations.

V0.10 does not yet include:

- generic creation of all model-object types,
- relation creation/editing,
- deletion or duplication of arbitrary objects,
- stable project-level `project_id`,
- explicit model-root configuration that excludes host metadata,
- external read-only context roots and external provenance-reference authoring,
- semantic multi-mutation changesets or approval workflow,
- database-backed project authority,
- full SysML v2 parsing,
- PLM/ALM integration,
- automated simulation integration.

The static `mbse-lite view` path remains read-only. Editable browser operations are available only through `mbse-lite serve` and must route writes through validated application commands rather than generated viewer data.

## Storage migration principle

A real project may remain repository-local while it is useful for application development and regression. When the portable external project contract is ready, migration to external authoritative storage should be an explicit one-time authority switch.

The migration should validate at least project identity, model objects, relations, validation findings and external provenance references before the previous authoritative copy is retired. Long-running bidirectional synchronization of two authoritative copies is intentionally outside the target architecture.
