# Relations

This file contains the explicit graph edges of the MBSE-lite model.

| Source | Relation | Target |
|---|---|---|
| NEED-001 | derives | REQ-001 |
| NEED-001 | derives | REQ-003 |
| NEED-002 | derives | REQ-002 |
| REQ-001 | satisfied_by | FUN-001 |
| REQ-001 | satisfied_by | FUN-002 |
| REQ-001 | verified_by | VER-001 |
| REQ-002 | satisfied_by | FUN-003 |
| REQ-002 | verified_by | VER-002 |
| REQ-003 | satisfied_by | FUN-004 |
| REQ-003 | verified_by | VER-003 |
| FUN-001 | realized_by | PART-001 |
| FUN-002 | realized_by | CON-001 |
| FUN-003 | realized_by | PART-002 |
| FUN-004 | realized_by | PART-003 |
| DEC-001 | selects | PART-002 |
| RISK-001 | threatens | REQ-002 |
| ISSUE-001 | affects | REQ-002 |
| TASK-001 | resolves | ISSUE-001 |
| TASK-002 | evaluates | CON-001 |
| TASK-002 | evaluates | CON-002 |
| MS-001 | depends_on | TASK-002 |
