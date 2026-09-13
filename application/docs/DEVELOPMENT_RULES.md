# Application Development Rules

## Purpose

MBSE Lite is developed use-case first. A real project should demonstrate the need for a new feature before the toolkit grows substantially.

## Change categories

### Application change

Examples: parser behavior, validation rule, CLI command, export format, import behavior, model schema support.

Application changes belong under `application/` and should include tests.

### Project change

Examples: new requirement, changed concept, technical decision, risk, task, milestone, relation.

Project changes belong only under the relevant project root. For current repository-local projects and fixtures that root is typically `../projects/<project>/`; future real projects may use an external authoritative project root.

Do not make an application change by reaching from an external project into a repository-relative `application/` path, and do not make a project-data change inside reusable application code.

## Model contract changes

Any change to supported object types, required columns, ID rules, relation semantics, project-root semantics or parsing conventions must be documented in `MBSE_METHOD.md` and covered by tests.

Changes to future location-independent project storage must also preserve the distinction between:

- authoritative model roots,
- host/workspace metadata,
- read-only external context,
- generated/disposable artifacts.

## POC design constraints

Prefer:

- Python standard library where practical,
- small focused dependencies,
- deterministic transformations,
- human-readable generated artifacts,
- explicit validation messages,
- reviewable imports,
- serialized local mutations and optimistic concurrency for controlled writes,
- explicit boundaries instead of implicit filesystem access.

Avoid until demonstrated necessary:

- database-backed project authority,
- remotely exposed long-running backend services,
- complex GUI frameworks,
- distributed two-master synchronization,
- full SysML v2 parsing,
- project-specific logic in reusable application code.

## Definition of done

For code changes:

1. tests pass,
2. demo/integration fixtures validate,
3. relevant documentation is updated,
4. no unrelated project engineering data is modified,
5. portability is not reduced by adding assumptions about a project's repository-relative path.
