# MBSE Lite Method

## Purpose

MBSE Lite is a pragmatic method for small technical projects. It borrows the core ideas of systems engineering and MBSE while keeping the project model readable as plain text.

The method is intentionally not a complete implementation of SysML or any ISO/IEC/IEEE standard. Its vocabulary and relations should, however, remain reasonably mappable to SysML v2 concepts in the future.

## Source of truth

Project Markdown files are authoritative. Generated XLSX, HTML and Mermaid files are views or exchange formats.

## Object types

| Prefix | Object | Purpose |
|---|---|---|
| NEED | Need | Stakeholder/user need or problem to solve |
| REQ | Requirement | Verifiable statement the solution shall satisfy |
| FUN | Function | What the system must do |
| PART | Part | Logical or physical element of the solution |
| CON | Concept | Candidate solution or architectural alternative |
| VER | Verification | Test, inspection, analysis or demonstration |
| DEC | Decision | Recorded technical/project decision and rationale |
| RISK | Risk | Uncertain event that may affect project objectives |
| ISSUE | Issue | Open problem, question or unresolved item |
| TASK | Task | Planned project work |
| MS | Milestone | Significant project checkpoint |

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

IDs should not be reused after an object is deleted or deprecated.

## Relations

Relations are stored explicitly in a Markdown table with the columns:

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

The vocabulary is deliberately small in the POC. New relation types should be added only when a real project needs them.

## Validation rules in V0.1

The tool checks at least:

1. every object ID has the exact `PREFIX-NNN` format, uses a documented prefix and is unique,
2. relation sources and targets exist and relation types are not empty,
3. every requirement has an incoming `derives` relation whose source is a Need,
4. every requirement has at least one outgoing `satisfied_by` relation,
5. every requirement has at least one outgoing `verified_by` relation,
6. every function has at least one outgoing `realized_by` relation.

ID format, prefix, uniqueness and broken relation-reference findings are errors because they make the model structurally inconsistent. Missing semantic traceability from rules 3–6 is a warning because it can represent incomplete engineering work. Relation names are matched exactly; a different or generic relation does not satisfy these checks.

## Views

The same model can be represented in different forms:

- Markdown — primary human-readable project model,
- Mermaid — graphical engineering/traceability view,
- HTML — project overview/dashboard,
- XLSX — LibreOffice-compatible table exchange and review format.

## Project management

Project-management information is related to, but distinct from, the engineering model. Tasks, risks, issues and milestones should reference engineering objects where useful, so that the project can answer both:

- what and why are we developing?
- who is doing what, when, and with which open risks/issues?

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
