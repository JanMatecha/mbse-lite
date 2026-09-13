# Oprava kuchyně 2026

Tento adresář je autoritativní MBSE Lite workspace pro reálný engineering projekt opravy / rekonstrukce kuchyně.

## Stav

Projekt je v inicializační fázi. Engineering fakta budou doplňována pouze z explicitních vstupů a doložených zdrojů. Neznámé údaje se nesmí domýšlet.

## Účel

Projekt slouží současně jako:

1. reálný engineering projekt opravy kuchyně,
2. druhý reálný use case a integrační test obecnosti MBSE Lite mimo doménu garden tool shed.

Aplikační nedostatky zjištěné během projektu se mají evidovat odděleně od engineering modelu a nemají vést k automatickým změnám pod `application/`.

## Struktura

```text
kitchen_renovation/
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

`mbse/` obsahuje technický model a engineering fakta. `project_management/` obsahuje práci, termíny, vlastníky, milestones a delivery tracking. Engineering fakta se do PM nekopírují; PM na ně odkazuje přes stabilní ID.

## Autorita a budoucí migrace

Aktuální autoritativní umístění je tento adresář v repozitáři `JanMatecha/mbse-lite`.

Cílově může být projekt jednorázově migrován do Family KB, kde `XX_MBSE/` bude tvořit MBSE Lite project root. Do té doby se nesmí zakládat druhá autoritativní kopie modelu. Žádný dual-master.

## Engineering tok

Používaný základní tok je:

```text
NEED -> REQ -> FUN -> CON/PART -> VER
```

Podporované typy objektů se řídí aktuální dokumentací MBSE Lite, zejména `NEED`, `REQ`, `FUN`, `PART`, `CON`, `VER`, `DEC`, `RISK`, `ISSUE`, `TASK`, `MS`.

## Evidence a nejistota

Důležitá fakta a rozhodnutí musí být dohledatelná k jejich zdroji, pokud to současný contract umožňuje. Dokud MBSE Lite nemá obecnou strukturovanou external provenance/reference podporu, nebude zde zaváděno vlastní nekompatibilní schema bez předchozí dohody.

Při nejistotě používat `TBD`, vhodný `ISSUE-*`, případně explicitní označení `ASSUMPTION` nebo `PROPOSAL`. Rozlišovat `FACT`, `ASSUMPTION`, `PROPOSAL`, `DECISION` a `OPEN ISSUE`.
