# ChatGPT onboarding — Oprava kuchyně 2026

Tento soubor dokumentuje vstupní prompt pro nový ChatGPT chat, který má pokračovat v práci na existujícím projektu `projects/kitchen_renovation/`.

## Jak použít

Zkopíruj následující prompt jako první zprávu do nového chatu v GPT projektu **Oprava kuchyně 2026**.

## Onboarding prompt

```text
Pracuješ na existujícím engineering projektu Oprava kuchyně 2026 v repozitáři JanMatecha/mbse-lite.

Nejdřív načti aktuální main a vytvoř si aktuální obraz projektu. Jako minimum načti:
- README.md
- AGENTS.md
- projects/README.md
- application/docs/MBSE_METHOD.md
- application/docs/APP_REQUIREMENTS.md
- projects/kitchen_renovation/README.md
- projects/kitchen_renovation/AGENTS.md
- projects/kitchen_renovation/mbse/AGENTS.md
- projects/kitchen_renovation/project_management/AGENTS.md
- všechny aktuálně relevantní Markdown soubory v projects/kitchen_renovation/mbse/ a project_management/.

Aktuální soubory repozitáře mají přednost před starými chaty nebo historickou pamětí.

Autoritativní MBSE workspace tohoto projektu je nyní projects/kitchen_renovation/. Projekt může být v budoucnu jednorázově migrován do Family KB jako externí XX_MBSE workspace; do té doby nevytvářej paralelní autoritativní kopii.

Tento chat je primárně engineering projekt kuchyně, nikoli vývoj aplikace MBSE Lite. Pracuj standardně pouze uvnitř projects/kitchen_renovation/. Pokud narazíš na obecně použitelný nedostatek aplikace, popiš jej odděleně jako MBSE Lite gap místo automatické změny application/.

Dodržuj aktuální MBSE Lite metodiku. Zachovávej stabilní ID. Technický model patří do mbse/, projektové plánování do project_management/. Engineering fakta se do PM nekopírují; odkazují se stabilními ID.

Nevymýšlej chybějící fakta. Podle situace používej TBD, ISSUE, ASSUMPTION nebo PROPOSAL a rozlišuj FACT, ASSUMPTION, PROPOSAL, DECISION a OPEN ISSUE.

Pro změny používej workflow:
read current project -> reason -> propose change -> validate -> apply -> re-read -> report.

Před zápisem načti aktuální relevantní soubory. Po zápisu změněné soubory znovu načti a ověř výsledek. Netvrď, že změna, validace, test nebo CI proběhly úspěšně, pokud to nebylo skutečně ověřeno.

Projekt už existuje; neinicializuj jej znovu. Pokračuj od současného stavu. Při sběru nových vstupů postupuj typicky po jedné otázce a nepřeskakuj k řešení, dokud chybí důležitá fakta nebo rozhodovací kritéria.

Projekt kuchyně je současně reálný test obecnosti MBSE Lite. Pokud odhalí obecný problém v objektovém modelu, relations, variants, interfaces, provenance, vieweru, authoringu nebo project managementu, reportuj jej odděleně jako:
MBSE Lite gap:
- problém
- proč je obecný
- konkrétní use case z kuchyně
- navrhovaná reusable schopnost
- předpokládaný dopad

V první odpovědi po onboardingu stručně uveď:
1. jaký aktuální stav repozitáře jsi načetl,
2. současný stav projektu kuchyně,
3. hlavní otevřené body a existující rozhodnutí,
4. případné MBSE Lite gaps,
5. nejlogičtější další krok.

Potom pokračuj v mém aktuálním požadavku. Pokud žádný konkrétní požadavek ještě není, polož jednu nejvhodnější další otázku.
```

## Údržba

Prompt záměrně nekopíruje aktuální seznam objektů, rozhodnutí ani issues. Ty má nový chat pokaždé načíst z aktuálního projektu. Aktualizuj tento soubor pouze tehdy, když se změní project contract, autorita projektu, hranice zápisu nebo základní AI workflow.
