# Project Template

Copy this directory to the chosen MBSE Lite project root, then customize it before adding real engineering data. The destination may be under this repository's `projects/` directory or in external project storage.

MBSE Lite project semantics must not depend on the absolute path, parent directory name or a repository-relative location.

## Native project structure

```text
<project_root>/
├── README.md
├── AGENTS.md
├── mbse/
│   ├── AGENTS.md
│   ├── 01_needs.md
│   ├── 02_requirements.md
│   ├── 03_functions.md
│   ├── 04_architecture_and_concepts.md
│   ├── 05_verification.md
│   ├── 06_engineering_issues_and_risks.md
│   └── 07_relations.md
└── project_management/
    ├── AGENTS.md
    ├── 01_tasks.md
    ├── 02_milestones.md
    └── 03_relations.md
```

## Separation rule

Use `mbse/` for the technical/system model: needs, requirements, functions, architecture, concepts, technical decisions, verification, engineering issues/risks and supporting technical data.

Use `project_management/` for execution planning: tasks, owners, estimates, deadlines, progress, milestones and relations from work items to engineering objects.

Do not duplicate engineering facts into project-management files. Reference stable IDs instead.

## Portable project root

The project root is the directory passed to MBSE Lite commands. Project instructions and model content should therefore avoid assumptions such as `../../application/` or any other fixed relative path to the MBSE Lite source repository.

A reusable application change belongs to the MBSE Lite application project, not inside this engineering project. If the application capability is unavailable, record or request that change separately rather than modifying an assumed neighboring source tree.

## Embedding in a host knowledge base

An external host may wrap the MBSE Lite project root in its own domain hierarchy. For example, the planned Family KB pattern is:

```text
<DOMAIN>/
└── <TOPIC>/
    └── <PROJECT>/
        ├── 00_INFO/
        ├── XX_DOCUMENTS/
        └── XX_MBSE/              # this MBSE Lite project root
            ├── 00_INFO/          # host-side workspace metadata
            ├── README.md
            ├── AGENTS.md
            ├── mbse/
            └── project_management/
```

`XX` is host ordering only. MBSE Lite must not infer project identity from that number or directory name.

The target project contract allows host metadata such as `00_INFO/` to coexist at the project root while explicit model roots determine what is parsed as MBSE data. This is guiding architecture; V0.10 still scans Markdown recursively below the project root. Until explicit model-root support is implemented, host metadata used with V0.10 must avoid Markdown tables that could be mistaken for model objects (`ID` columns) or relations (`Source | Relation | Target`).

## External context

The target architecture also allows explicitly declared files outside the MBSE workspace to be used as read-only project context and provenance sources. Such references do not grant permission to modify the external source and should not duplicate the source as a second authoritative copy.

## Starting a new project

1. Copy the template to the chosen project root.
2. Replace this README with project purpose, scope, stakeholders and status.
3. Customize the root and nested `AGENTS.md` files.
4. Remove unused sections only when you are sure they are not needed.
5. Add project-specific engineering files under `mbse/` as useful.
6. Preserve stable IDs and explicit relations when automation is desired.
7. When stable project identity support is available, assign a `project_id` that does not change when the project directory moves or is renamed.

The file names are a recommended convention, not a rigid schema.
