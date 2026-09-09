# Codex Instructions — Project Template

## Scope

These instructions apply only inside this project directory. Replace generic statements with project-specific instructions immediately after copying the template.

## Project source of truth

- Markdown files in this project directory are authoritative unless this file explicitly says otherwise.
- Generated Mermaid, HTML and XLSX outputs are views/exchange files, not the master model.
- Preserve assigned IDs.
- Keep relations explicit in `07_relations.md` or another documented relations file.

## Engineering behavior

- Do not invent technical facts, measurements, constraints, requirements or decisions without labeling them as assumptions/proposals.
- Distinguish known facts from assumptions, open questions and candidate concepts.
- Record material decisions with rationale.
- Record unresolved matters as `ISSUE-*` rather than silently guessing.
- Add verification intent for important requirements.

## Project isolation

- Do not introduce content from another project unless explicitly instructed.
- Do not edit the reusable application under `../../application/` while performing ordinary engineering work in this project.
- If a missing application capability is discovered, describe the need first; application implementation is a separate scope.

## Project-specific section — customize this

Document here, for example:

- project objective,
- allowed and forbidden assumptions,
- terminology,
- input documents and trusted sources,
- required outputs,
- naming conventions,
- technical constraints,
- confidentiality rules,
- preferred working sequence.
