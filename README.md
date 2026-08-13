# Articly Alignment Lab — Stufe 0–2

Testwerkzeug für die Informationszuordnung Transkript ⇄ Originalartikel.
Eigenes Paar einfügen, analysieren, im Split-View prüfen: Welche Aussage
stammt woher, wo weichen Zahlen ab, was ist unbelegt.

## Start

Keine Installation, keine Abhängigkeiten — nur Python ≥ 3.10:

```bash
python3 app.py            # http://127.0.0.1:8765
python3 app.py 8080       # anderer Port
```

Browser öffnen, Artikel + Transkript einfügen (oder „Beispiel laden"),
Modell wählen, **Analysieren**. Strg+Enter in den Textfeldern startet
ebenfalls.

## Embeddings (Stufe 2)

Zwei Backends, gleiche Schnittstelle und gleiche Präfix-Konvention — die
Ergebnisse sind daher direkt vergleichbar.

### Personenerkennung (Stufe 0.5, optional)

```bash
pip install spacy && python3 -m spacy download de_core_news_sm
```

Ohne spaCy läuft ein regelbasierter Rückfall, der konservativ arbeitet:
Er verwirft Kandidaten mit Artikel am Anfang („Die Bauarbeiten") und
bekannte Nicht-Namen-Wörter, findet dafür weniger echte Namen.
`ner.backend()` zeigt, welcher Pfad aktiv ist. Der Abgleich ist in beiden
Fällen tokenbasiert, „Kraft" gilt also durch „Sabine Kraft" als belegt.

### Lokal auf der CPU (kein Key, kein Netz nach dem ersten Lauf)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "sentence-transformers>=3.0"
```

Der CPU-Wheel-Index spart rund 2 GB CUDA-Ballast, den eine Iris Xe
ohnehin nicht nutzt. Danach im Dropdown ein `local · …`-Modell wählen.

| Modell | Größe | Anmerkung |
|---|---|---|
| `local-multilingual-e5-large-instruct` | 560M, ~2,2 GB | dasselbe Modell wie auf SAIA — für den 1:1-Vergleich |
| `local-multilingual-e5-base` | 278M, ~1,1 GB | schneller, spürbar schwächer |
| `local-bge-m3` | 568M, ~2,2 GB | zweite Meinung, unabhängig von der E5-Familie |

Der erste Lauf lädt die Gewichte nach `~/.cache/huggingface` (mit
`ALIGNMENT_LAB_MODELS=/pfad` umlenkbar) und dauert entsprechend; danach
liegt das Modell im Prozessspeicher und jede weitere Analyse startet
sofort. Auf einem i5 mit 16 GB braucht `e5-large-instruct` für ein
typisches Paar (~20 Sätze) einige Sekunden. Schnelltest ohne UI:

```bash
python3 saia.py local-multilingual-e5-large-instruct
```

### SAIA-API (GWDG / Academic Cloud / KISSKI)

OpenAI-kompatibler Endpunkt `https://chat-ai.academiccloud.de/v1/embeddings`.

- API-Key über den [KISSKI LLM Service](https://kisski.gwdg.de/en/leistungen/2-02-llm-service) buchen („Book"),
  dieselbe Mailadresse wie im Academic-Cloud-Konto verwenden.
- Key im Formular eintragen (bleibt im Browser-localStorage) **oder**
  `export SAIA_API_KEY=…` vor dem Start.
- Modelle: `multilingual-e5-large-instruct`, `qwen3-embedding-4b`,
  `e5-mistral-7b-instruct`.
- Bei HTTP 401: Key ungültig, noch nicht freigeschaltet oder mit
  Leerzeichen eingefügt — der Key wird serverseitig getrimmt.

### Ohne Embeddings

Option „ohne — nur Stufe 0+1" nutzt rein lexikalische Zuordnung, komplett
offline und ohne Installation. Für zahlenlastige Lokalnachrichten bereits
erstaunlich brauchbar.

Claims werden mit Instruct-Präfix als Queries eingebettet, Artikelsätze
roh als Dokumente (asymmetrische E5-/Qwen-Konvention; `e5-base` nutzt
stattdessen `query:`/`passage:`, `bge-m3` gar kein Präfix). Die
Kosinuswerte werden robust normalisiert (P10–P95), weil E5-Modelle auch
für Unverwandtes hohe Rohwerte liefern.

## Was die Stufen tun

| Stufe | Signal | Ergebnis |
|---|---|---|
| 0 | Deutsche Zahlwörter → Normform („sechs Komma acht Millionen Euro" → `6800000 EUR`), Geld/Prozent/Jahre/Verhältnisse | Anker-Boni, **Zahlkonflikt**- und **Zahl-unbelegt**-Flags |
| 0.5 | Personen über NER (`ner.py`), tokenbasierter Namensabgleich | Namens-Anker, **Name-unbelegt**-Meldung |
| 1 | Char-3/4-Gramm-TF-IDF auf zahlnormalisiertem Text + Positionsprior | Kandidatenranking, Margin |
| 1.5 | **Restabdeckung**: weitere Quellen nach ihrem Zusatzbeitrag am Claim | **aggregiert**-Erkennung, auch über Absatzgrenzen hinweg |
| 2 | Embeddings (SAIA oder lokal) + Score-Fusion | robustere Zuordnung bei Umformulierungen |

### Wie die Aggregation entschieden wird

Die naheliegende Frage „ähnelt Satz X dem Claim?" ist für Verdichtungen die
falsche: ein Member trägt definitionsgemäß nur einen Teil bei und fällt an
jeder Ähnlichkeitsschwelle gegen den *ganzen* Claim durch. Stufe 1.5 fragt
stattdessen „erklärt Satz X etwas, das noch keine Fundstelle erklärt?" und
nimmt gierig weitere Sätze auf, solange ihr Zusatzbeitrag über
`residual_min` liegt (Anteil am TF-IDF-Gewicht des Claims, Standard 13 %).
Die Notiz im Inspector nennt den gemessenen Beitrag, z. B. „s3 erklärt
zusätzlich 23 %".

Das ersetzt die frühere Fenster-Enumeration benachbarter Sätze. Nebeneffekt:
rund 38 % weniger Embedding-Aufrufe, weil keine Fenstertexte mehr
eingebettet werden.

Relationen: `direkt`, `aggregiert`, `keine_quelle`. Claims zwischen den
Schwellen bleiben `direkt` mit niedriger Confidence und der Notiz
„Unter der Direkt-Schwelle" — sichtbar über den Margin-Chip.

## Im Viewer

- Chips oben: Zahlkonflikt · Zahl unbelegt · ohne Quelle · Margin < 0,10 · Artikel ungenutzt
- Inspector zeigt zusätzlich die Roh-Scores (top/lex/emb/anker) je Claim — zum Schwellen-Tuning
- „Teilspanne" markiert bei Anker-Treffern exakt die Zahlregion im Artikel
- Export erzeugt JSON, das unverändert im ursprünglichen
  Split-View-Prototyp ladbar ist (gleiches Schema)

## Tuning

Alle Schwellen und Gewichte in `pipeline.py` → `CFG` (Fusionsgewichte,
`t_direct`/`t_none`, `residual_min`, Anker-Boni). `residual_min` ist der
wichtigste Regler für die Aggregation: kleiner = mehr Mehrfachquellen. Sinnvoller
Workflow: 30–50 Paare durchschieben, Fälle mit Margin < 0,10 ansehen,
Schwellen nachziehen.

## Grenzen (bewusst)

- `inferiert` wird nicht vergeben — dafür braucht es NLI (Stufe 3).
- Pronomen werden nicht aufgelöst („ohne sie" statt „ohne die AfD");
  Embeddings fangen das nur teilweise ab.
- Claims = Transkriptsätze; feineres Claim-Splitting kommt später.
- Teilspannen nur über Zahlen-Anker, kein Token-Alignment.
- Personenprüfung ist heuristisch (kapitalisierte Namensfolgen).

## Dateien

```
app.py              Server (nur Standardbibliothek), /api/align
pipeline.py         Stufen 0–2: Segmentierung, Fusion, Entscheidung
german_numbers.py   Zahlwort-Parser + numerische Entities
ner.py              Personenerkennung (spaCy o. Rückfall) + Namensabgleich
saia.py             Embeddings: SAIA-API + lokales CPU-Backend
static/index.html   Split-View-Frontend mit Eingabe-Panel
build_frontend.py   erzeugt index.html aus dem Original-Prototyp
```
