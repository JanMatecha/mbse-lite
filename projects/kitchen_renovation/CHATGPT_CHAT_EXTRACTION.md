# ChatGPT retroaktivní extrakce — Oprava kuchyně 2026

Tento soubor dokumentuje copy-paste prompt pro už rozjetý ChatGPT chat, který obsahuje starší diskusi, rozhodnutí a další informace o projektu. Cílem je zpětně vytěžit hodnotný obsah konverzace, porovnat jej s aktuálním MBSE modelem a bezpečně doplnit pouze chybějící nebo upřesňující informace.

## Kdy použít

Použij tento prompt v existujícím chatu, kde už proběhla delší diskuse k projektu Oprava kuchyně 2026 a chceš její relevantní obsah synchronizovat do autoritativního MBSE Lite workspace.

Pro nový chat bez předchozí projektové historie použij místo toho `CHATGPT_ONBOARDING.md`.

## Retroaktivní onboarding + extraction prompt

```text
Pracuješ na existujícím engineering projektu Oprava kuchyně 2026 v repozitáři JanMatecha/mbse-lite.

Tento chat už obsahuje delší předchozí diskusi a řadu informací o projektu. Chci nyní tento existující chat onboardovat do MBSE Lite a zpětně z něj vytěžit relevantní engineering informace do autoritativního MBSE modelu.

Nejdřív načti aktuální main repozitáře a aktuální stav projektu. Jako minimum načti:
- README.md
- AGENTS.md
- projects/README.md
- application/docs/MBSE_METHOD.md
- application/docs/APP_REQUIREMENTS.md
- projects/kitchen_renovation/README.md
- projects/kitchen_renovation/AGENTS.md
- projects/kitchen_renovation/mbse/AGENTS.md
- projects/kitchen_renovation/project_management/AGENTS.md
- všechny aktuální relevantní Markdown soubory pod projects/kitchen_renovation/mbse/
- všechny aktuální relevantní Markdown soubory pod projects/kitchen_renovation/project_management/

Aktuální GitHub je autorita pro současný stav modelu. Dosavadní chat je zdroj evidence a nových informací, nikoli druhý source of truth.

Potom projdi dosavadní konverzaci tohoto chatu v maximálním rozsahu, který máš k dispozici, a extrahuj z ní všechny informace relevantní pro projekt Oprava kuchyně 2026.

Hledej zejména:
- fakta o současném stavu,
- potřeby uživatelů,
- constraints a omezení,
- požadavky,
- rozměry a fyzické parametry,
- materiály a výrobky,
- stavební skladby,
- rozhraní,
- varianty,
- rozhodnutí,
- otevřené otázky,
- assumptions,
- engineering issues,
- rizika,
- verification evidence,
- úkoly a milestones,
- zdroje informací a odkazy.

Každou informaci klasifikuj podle významu:
FACT
ASSUMPTION
PROPOSAL
DECISION
OPEN ISSUE

A podle MBSE Lite ji zařaď do vhodného typu, například:
NEED
REQ
FUN
PART
CON
VER
DEC
ISSUE
RISK
TASK
MS

Nevymýšlej žádnou informaci, která v dosavadním chatu není skutečně podložena.

Pokud je informace nejasná, neúplná nebo si odporuje s jinou částí chatu či současným GitHub modelem, nevytvářej z ní potvrzený fakt. Označ ji jako TBD, ASSUMPTION, PROPOSAL nebo OPEN ISSUE a konflikt explicitně popiš.

DEDUPLIKACE A POROVNÁNÍ

Před každým zápisem porovnej extrahovanou informaci se současným MBSE modelem.

Rozliš:
ALREADY_PRESENT
NEW
UPDATE_EXISTING
CONFLICT
UNCERTAIN

Nevytvářej duplicitní objekty ani nové ID pro něco, co už v modelu existuje.

Zachovávej existující stabilní ID.

Pokud lze informaci bezpečně doplnit do existujícího objektu, preferuj aktualizaci před vytvořením paralelního objektu.

SOURCE / PROVENANCE

U informací pocházejících z tohoto chatu zachovej podle možností provenance, například že zdrojem je uživatelská informace nebo rozhodnutí v tomto projektovém chatu.

Nezaváděj nové nekompatibilní provenance schema, pokud ho současný MBSE Lite contract nepodporuje.

HRANICE PROJEKTU

Standardně měň pouze:
projects/kitchen_renovation/

Neměň automaticky application/.

Pokud při extrakci objevíš obecný nedostatek MBSE Lite, eviduj ho odděleně jako:

MBSE Lite gap:
- problém:
- proč je obecný:
- konkrétní use case z kuchyně:
- navrhovaná reusable schopnost:
- předpokládaný dopad:

POSTUP

Proveď celý proces v tomto pořadí:
1. načti aktuální GitHub
2. načti aktuální projekt
3. projdi dosavadní chat
4. vytěž kandidátní informace
5. porovnej je se současným MBSE
6. odstraň duplicity
7. identifikuj konflikty a nejistoty
8. připrav konzistentní change-set
9. aplikuj bezpečné změny do projects/kitchen_renovation/
10. znovu načti změněné soubory
11. spusť dostupnou validaci projektu
12. zkontroluj výsledek a podej report

U jednoznačných a přímo doložených informací můžeš změny aplikovat bez dalšího potvrzení.

Pokud by zápis vyžadoval rozhodnutí, které jsem v tomto chatu ještě neudělal, nevymýšlej ho. Zapiš otevřený bod, pokud je to vhodné, nebo se mě zeptej.

ZÁVĚREČNÝ REPORT

Po dokončení vypiš stručně:
- co bylo z chatu nově extrahováno,
- které MBSE objekty byly vytvořeny,
- které byly aktualizovány,
- co už v modelu bylo,
- jaké konflikty nebo nejistoty zůstaly,
- případné MBSE Lite gaps,
- zda validace skutečně proběhla a s jakým výsledkem.

Netvrď, že zápis, validace, test nebo CI proběhly, pokud jsi je skutečně neověřil.

Začni nyní tímto retroaktivním auditem celé dosavadní konverzace a synchronizací jejího relevantního obsahu do aktuálního MBSE modelu Oprava kuchyně 2026.
```

## Pracovní princip

Tento prompt má jiný účel než onboarding nového chatu:

```text
nový chat
CHATGPT_ONBOARDING.md
→ načíst aktuální projekt
→ pokračovat

rozjetý starší chat
CHATGPT_CHAT_EXTRACTION.md
→ načíst aktuální projekt
→ projít historii chatu
→ porovnat a deduplikovat
→ doplnit MBSE
→ validovat
```

## Údržba

Prompt záměrně nekopíruje aktuální seznam MBSE objektů ani konkrétní projektová fakta. Ty musí být vždy znovu načteny z aktuálního GitHubu a porovnány s historií konkrétního chatu. Aktualizuj tento dokument, pokud se změní project contract, zápisová hranice, dostupné validační workflow nebo způsob provenance/changesetů.
