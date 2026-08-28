# Befehle (PowerShell)

Alle Befehle im Projektordner ausführen, dort wo `pipeline.py` liegt.
Unter Windows heißt der Interpreter meist `python`, nicht `python3`. Die
Fortsetzungszeile in PowerShell ist das Backtick `` ` ``, nicht `\`.

---

## Einmalig einrichten

```powershell
# API-Schlüssel für die aktuelle Sitzung
$env:SAIA_API_KEY = "dein-key"

# … oder dauerhaft für deinen Benutzer (danach PowerShell neu öffnen)
[Environment]::SetEnvironmentVariable("SAIA_API_KEY", "dein-key", "User")

# prüfen
$env:SAIA_API_KEY

# Ordner anlegen
New-Item -ItemType Directory -Force -Path laeufe\voll, gold
```

---

## Der übliche Ablauf

```powershell
# 1. Alle Paare neu durchrechnen (Läufe liegen in laeufe\voll)
python batch.py laeufe\voll -o laeufe\voll --neu

# 2. Entwurfs-Annotationen erzeugen (überspringt vorhandene Dateien)
python gold_entwurf.py laeufe\voll -o gold\

# 3. annotate.html im Browser öffnen, gold\<paar>.json hineinziehen,
#    durchklicken, herunterladen, Datei in gold\ ersetzen

# 4. Messen
python eval.py "gold\*.json" --lauf voll="laeufe\voll\*.json"
```

Nach einer Codeänderung reichen Schritt 1 und 4.

---

## `batch.py` — Paare durchrechnen

```powershell
# Standard: SAIA-Embeddings + NLI, überspringt vorhandene Zieldateien
python batch.py laeufe\voll -o laeufe\voll

# Auch vorhandene Dateien neu rechnen
python batch.py laeufe\voll -o laeufe\voll --neu

# Kleinere Blöcke gegen HTTP-500-Fehler (Standard 8)
python batch.py laeufe\voll -o laeufe\voll --neu --batch 4

# Ohne Embeddings / ohne NLI — schnell, für reine Schwellenversuche
python batch.py laeufe\voll -o laeufe\test --emb ohne --nli ohne

# Komplett lokal, wenn SAIA instabil ist
python batch.py laeufe\voll -o laeufe\lokal --emb local-multilingual-e5-large-instruct

# Lokalen Rückfall abschalten (erzwingt reine SAIA-Läufe)
python batch.py laeufe\voll -o laeufe\voll --neu --kein-fallback

# Weniger Ausgabe
python batch.py laeufe\voll -o laeufe\voll --still

# Einzelne Stufen abschalten (Nummern oder Namen, Komma-Liste)
python batch.py laeufe\voll -o laeufe\ohne05 --ohne 0.5
python batch.py laeufe\voll -o laeufe\test --ohne 0.5,wortlaut --emb ohne --nli ohne
```

Nach Abbruch (Strg-C, Netz, Kontingent) denselben Befehl **ohne `--neu`**
wiederholen — fertige Dateien werden übersprungen.

---

## Stufen abschalten — was trägt eine Stufe bei?

Je abgeschalteter Stufe ein Ordner, dann alles mit einem Befehl messen:

```powershell
python batch.py laeufe\voll -o laeufe\abl\voll --neu
python batch.py laeufe\voll -o laeufe\abl\ohne_0   --neu --ohne 0
python batch.py laeufe\voll -o laeufe\abl\ohne_05  --neu --ohne 0.5
python batch.py laeufe\voll -o laeufe\abl\ohne_15  --neu --ohne 1.5

python eval.py "gold\*.json" --laeufe laeufe\abl
```

Kürzel laut `konfig.STUFEN`: `0` (= `0_anker` **und** `0_verifikation`),
`0.5`/`personen`, `0.6`/`identifier`, `0.8`/`wortlaut`,
`1.2`/`teilaussagen`, `1.5`/`restabdeckung`, `2`/`embeddings`,
`3`/`nli`. Stufe 1 ist nicht abschaltbar. Bei Abweichung vom Standard
steht die Schalterstellung als `meta.stufen` in jeder Ergebnisdatei.
Unbekannte Kürzel brechen mit einer Liste der erlaubten ab.

---

## `varianten.py` — Experimente

```powershell
# Welche Varianten gibt es?
python varianten.py --liste

# Alle Varianten in eigene Ordner rechnen
python varianten.py laeufe\voll -o laeufe\exp

# Nur bestimmte
python varianten.py laeufe\voll -o laeufe\exp --nur basis --nur A_ident_saat

# Schnelldurchlauf ohne Modelle (nur für Schwellenvarianten sinnvoll)
python varianten.py laeufe\voll -o laeufe\exp --emb ohne --nli ohne
```

Schalter wie `--batch`, `--neu`, `--emb`, `--nli` werden an `batch.py`
durchgereicht.

---

## `eval.py` — Messen

```powershell
# Ein Lauf gegen Gold
python eval.py "gold\*.json" --lauf voll="laeufe\voll\*.json"

# Alle Variantenordner auf einmal
python eval.py "gold\*.json" --laeufe laeufe\exp

# Mit Fehlerliste (welche Sätze, welche Artikelsätze)
python eval.py "gold\*.json" --lauf voll="laeufe\voll\*.json" --fehler

# Mehr Zeilen je Fehlerklasse
python eval.py "gold\*.json" --lauf voll="laeufe\voll\*.json" --fehler-max 50

# Der zurückgehaltene Test-Split — erst ansehen, wenn du fertig bist
python eval.py "gold\*.json" --laeufe laeufe\test --test

# Ergebnis mit Zeitstempel protokollieren
python eval.py "gold\*.json" --laeufe laeufe\exp --protokoll verlauf.jsonl

# Kürzere Ausgabe (ohne Relationsmatrix)
python eval.py "gold\*.json" --laeufe laeufe\exp --kurz

# Mehrere Läufe von Hand nebeneinander
python eval.py "gold\*.json" `
    --lauf voll="laeufe\voll\*.json" `
    --lauf A="laeufe\exp\A_ident_saat\*.json"
```

Die Anführungszeichen um `"gold\*.json"` sind wichtig — sonst löst
PowerShell das Muster selbst auf.

---

## `gold_entwurf.py` — Annotationsentwürfe

```powershell
# Alle Läufe, dev/test wird automatisch zugeteilt
python gold_entwurf.py laeufe\voll -o gold\

# Anteil der Testmenge ändern (Standard 0,25)
python gold_entwurf.py laeufe\voll -o gold\ --test-anteil 0.3

# Einzelnes Paar, Split erzwingen
python gold_entwurf.py laeufe\voll\az_CHIO.json -o gold\az_CHIO.json --split test

# Nach geänderter Satzsegmentierung: neue Sätze anhängen,
# geprüfte Einträge bleiben unangetastet
python gold_entwurf.py laeufe\voll -o gold\ --aktualisieren
```

---

## `inferiert_ablation.py` — Messskript

```powershell
python inferiert_ablation.py --kontrolle
python inferiert_ablation.py --reichweite laeufe\voll\az_CHIO.json
python inferiert_ablation.py laeufe\voll\az_CHIO.json --alle
```

---

## Kleinkram

```powershell
# Server für das Frontend
python app.py

# Selbsttest der Identifier-Prüfung (braucht kein Modell)
python -m stufe0.identifier

# Prüfen, ob eine Änderung an der Satztrennung greift
python -c "from kern import segmentierung as S; t='Programm Progress.NRW wurde gefördert. Danach kam mehr.'; print([t[a:b] for a,b in S._split_sentences_in(t,0,len(t))])"

# Wie viele Paare sind schon annotiert?
Get-ChildItem gold\*.json | ForEach-Object {
    $d = Get-Content $_ -Raw | ConvertFrom-Json
    $offen = ($d.eintraege | Where-Object { -not $_.geprueft }).Count
    "$($_.Name): $offen von $($d.eintraege.Count) offen"
}
```

---

## Kennzahlen kurz erklärt

| Zahl | Bedeutung |
| --- | --- |
| **CIP** | Anteil der vergebenen Fundstellen, die richtig sind |
| **CIR** | Anteil der notwendigen Fundstellen, die gefunden wurden |
| **mikro / makro** | alle Sätze gepoolt / pro Satz gemittelt. Makro deutlich niedriger heißt: kurze Claims leiden |
| **bv-FP** | Fehlalarme `bedeutung_verschoben` |
| **unbel.P** | Präzision der Unbelegt-Erkennung — daran hängt `t_none` |

**Faustregel für Varianten:** gut, wenn ΔCIR deutlich positiv ist und
ΔCIP um weniger als ein Drittel davon fällt. Bei 104 Sätzen entspricht
0,005 etwa einer einzigen Fundstelle — das ist Rauschen, keine Messung.
