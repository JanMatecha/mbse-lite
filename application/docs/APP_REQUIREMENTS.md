# MBSE Lite Application Requirements

Application requirements are intentionally separated from the engineering requirements of projects under `../projects/`.

| ID | Requirement | Status |
|---|---|---|
| APP-REQ-001 | The application shall treat project Markdown files as the authoritative project model. | Implemented |
| APP-REQ-002 | The application shall detect duplicate model object IDs. | Implemented |
| APP-REQ-003 | The application shall validate relation source and target references. | Implemented |
| APP-REQ-004 | The application shall provide basic requirement traceability checks. | Implemented |
| APP-REQ-005 | The application shall generate Mermaid traceability output. | Implemented |
| APP-REQ-006 | The application shall generate a static HTML project overview. | Implemented |
| APP-REQ-007 | The application shall export project data to a LibreOffice-compatible XLSX workbook. | Implemented |
| APP-REQ-008 | XLSX import shall create reviewable Markdown output and shall not silently overwrite the authoritative project model. | Implemented |
| APP-REQ-009 | The application shall remain usable without a database or continuously running server in the POC phase. | Implemented |
| APP-REQ-010 | The application model shall remain reasonably mappable to SysML v2 concepts in future versions. | Guiding |

## Rule for adding requirements

Add an `APP-REQ-*` only for a reusable toolkit capability or constraint. Do not add a one-project technical requirement here.
