# Project Template

Copy this directory to `projects/<project_name>/`, then customize it before adding real engineering data.

## Structure

```text
<project_name>/
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

## Starting a new project

1. Rename the copied directory.
2. Replace this README with project purpose, scope, stakeholders and status.
3. Customize the root and nested `AGENTS.md` files.
4. Remove unused sections only when you are sure they are not needed.
5. Add project-specific engineering files under `mbse/` as useful.
6. Preserve stable IDs and explicit relations when automation is desired.

The file names are a recommended convention, not a rigid schema.
