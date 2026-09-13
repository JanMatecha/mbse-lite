# Codex Instructions — Oprava kuchyně 2026

## Scope

Tyto instrukce platí pouze pro projekt `projects/kitchen_renovation/`.

Projekt je rozdělen na:

- `mbse/` — system engineering a technický model,
- `project_management/` — plánování a tracking práce.

Používej i vnořené `AGENTS.md` pro pravidla jednotlivých oblastí.

## Project rules

- Markdown model content je autoritativní, pokud projekt výslovně nestanoví jinak.
- Preserve stable IDs.
- Nevymýšlej technická fakta, rozměry, constraints, requirements, decisions, spotřebiče ani řešení.
- Neznámé hodnoty označ `TBD`, případně založ engineering `ISSUE-*`.
- Vždy rozlišuj `FACT`, `ASSUMPTION`, `PROPOSAL`, `DECISION`, `OPEN ISSUE`.
- Technická fakta patří do `mbse/`; práce, termíny, owners, milestones a delivery tracking do `project_management/`.
- PM nesmí kopírovat engineering fakta; má na ně odkazovat přes stabilní ID.
- Zachovávej informaci o původu důležitých vstupů a rozhodnutí v mezích současného MBSE Lite contractu.
- Nezaváděj vlastní schema pro external provenance/reference bez explicitní dohody.
- Nekopíruj fakta z `garden_tool_shed`, `demo_project` ani jiného projektu.
- Tento adresář je jediný aktuální autoritativní MBSE workspace pro projekt. Nevytvářej paralelní autoritativní kopii ve Family KB.
- Budoucí migrace do Family KB je jednorázový switch autority po splnění readiness kritérií.

## Boundary vůči MBSE Lite application

Tento projekt je primárně engineering projekt kuchyně, ne vývoj MBSE Lite.

Pokud narazíš na chybějící schopnost, nejdřív rozhodni, zda jde o:

A) vlastnost/problém konkrétního projektu kuchyně — řeš v projektu,

B) obecně použitelný gap MBSE Lite — neměň automaticky `application/`; nahlas jej odděleně ve formátu:

```text
MBSE Lite gap:
- problém:
- proč je obecný:
- konkrétní use case z kuchyně:
- navrhovaná reusable schopnost:
- předpokládaný dopad:
```

## AI-first workflow

Pro změny používej:

```text
read current project
      ↓
reason
      ↓
propose change
      ↓
validate
      ↓
apply
      ↓
re-read
      ↓
report
```

Před zápisem načti relevantní aktuální soubory. Po zápisu je znovu načti a ověř výsledek. Nikdy netvrď, že soubor byl změněn, model validuje, test prošel nebo CI je zelené, pokud to nebylo skutečně ověřeno.

## Intake order

Engineering fakta sbírej postupně, vždy po jedné otázce:

```text
současný stav
→ problém / motivace rekonstrukce
→ stakeholders a jejich potřeby
→ scope
→ fyzická omezení
→ rozhraní
→ varianty
→ requirements
→ verification
→ plán realizace
```

Nepřeskakuj předčasně k řešení.
