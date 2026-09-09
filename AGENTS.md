# Codex Instructions

## Repository purpose

This repository contains both:

1. the development of the `mbse-lite` Python toolkit,
2. example/private technical projects that use the MBSE-lite method.

## Core architecture

- Markdown project files are the source of truth.
- Python reads and validates Markdown tables.
- Relations between model objects are explicit.
- Mermaid, HTML and XLSX are generated views/exchange formats.
- Keep the implementation intentionally small and transparent.

## Model vocabulary

Use these stable ID prefixes:

- `NEED-` stakeholder/user need
- `REQ-` requirement
- `FUN-` function/action
- `PART-` logical/physical part
- `CON-` candidate concept
- `VER-` verification/test
- `DEC-` decision
- `RISK-` risk
- `ISSUE-` open issue/question
- `TASK-` project task
- `MS-` milestone

Typical engineering traceability:

```text
NEED -> REQ -> FUN -> CON/PART -> VER
```

## Development rules

- Do not silently invent project requirements or technical facts.
- Preserve existing IDs once assigned.
- Prefer explicit simple data structures over complex abstractions.
- Generated files must never become the authoritative project model.
- Add automated tests for parser or validation behavior changes.
- Do not add databases, web frameworks, or heavy dependencies unless a real use case requires them.
- Keep future SysML v2 mapping in mind, but do not implement a full SysML parser in the POC.

## Private project rule

Do not introduce references to unrelated customer projects, prior commercial use cases, or confidential examples into this repository unless explicitly requested for that repository.
