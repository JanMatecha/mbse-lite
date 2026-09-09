# Application Development Rules

## Purpose

MBSE Lite is developed use-case first. A real project should demonstrate the need for a new feature before the toolkit grows substantially.

## Change categories

### Application change

Examples: parser behavior, validation rule, CLI command, export format, import behavior, model schema support.

Application changes belong under `application/` and should include tests.

### Project change

Examples: new requirement, changed concept, technical decision, risk, task, milestone, relation.

Project changes belong only under the relevant `projects/<project>/` directory.

## Model contract changes

Any change to supported object types, required columns, ID rules, relation semantics or parsing conventions must be documented in `MBSE_METHOD.md` and covered by tests.

## POC design constraints

Prefer:

- Python standard library where practical,
- small focused dependencies,
- deterministic transformations,
- human-readable generated artifacts,
- explicit validation messages,
- reviewable imports.

Avoid until demonstrated necessary:

- databases,
- long-running backend services,
- complex GUI frameworks,
- concurrency/synchronization infrastructure,
- full SysML v2 parsing,
- project-specific logic in reusable application code.

## Definition of done

For code changes:

1. tests pass,
2. demo project validates,
3. relevant documentation is updated,
4. no unrelated project engineering data is modified.
