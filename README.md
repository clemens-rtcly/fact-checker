# Articly Alignment Lab — Stufe 0–3

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

## NLI (Stufe 3, optional, lokal)

Ein Cross-Encoder prüft je Claim: Folgt er aus seinen Fundstellen
(entailment), widerspricht er ihnen (contradiction) — oder keins von
beidem (neutral)? Der Neutral-Fall ist der dritte Link-Status
**„Bedeutung verschoben"**: richtige Stelle gefunden, Aussage leicht
verschoben („es *könnte* zu Geruchsbelästigung kommen" → „es *kam* zu
Geruchsbelästigung"). In der Penn-Studie betraf das 18 von 159 Links —
gut jeder zehnte; bisher landete so etwas als `direkt` mit etwas
niedrigerer Confidence und fiel niemandem auf. `contradiction` liefert
als Nebenprodukt echte semantische Widerspruchserkennung jenseits der
Zahlkonflikte (Flag **NLI-Widerspruch**).

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install "sentence-transformers>=3.0" sentencepiece protobuf
```

(torch/transformers sind dieselben wie für die lokalen Embeddings;
sentencepiece/protobuf braucht nur der mDeBERTa-/MiniLM-Tokenizer.)
Danach im Dropdown „NLI · Stufe 3" ein Modell wählen.

**Modellwahl** (Rechercheergebnis Anfang 2026): Es gibt kein eindeutig
bestes deutschsprachiges 3-Klassen-NLI — zwei ernsthafte Kandidaten und
eine Schnellstufe, alle drei sind eingebaut und direkt vergleichbar:

| UI-Name | Modell | Größe | Warum |
|---|---|---|---|
| `nli-mdeberta-2mil7` **(Standard)** | MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 | 279M | XNLI-de 82,4 %; als einziges auch auf Fever-NLI-/ANLI-Übersetzungen trainiert (evidenznahe Paare) — Standard der Faktenprüfungsliteratur |
| `nli-gbert-large` | svalabs/gbert-large-zeroshot-nli | 337M | rein deutsch, XNLI-de-Test 85,6 % — bester deutscher Rohwert, aber nur maschinell übersetztes (M)NLI, kein Fever/ANLI |
| `nli-minilm-l6` | MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli | ~110M | mehrfach schneller, spürbar schwächer — für Massendurchläufe |

Neuere Architekturen (ModernBERT/ModernCE, tasksource-NLI) sind bislang
rein englisch; für mmBERT/EuroBERT/ModernGBERT existiert noch kein
etabliertes deutsches 3-Klassen-Finetuning. Ehrliche Erwartung: ~80–85 %
XNLI-Genauigkeit heißt **Hilfssignal, kein Orakel** — die Schwellen
(`nli_entail_min`/`nli_contra_min`) sind wie `t_direct`/`t_none` erst
mit einem Gold-Set seriös kalibrierbar. Schnelltest ohne UI:

```bash
python3 nli.py nli-mdeberta-2mil7        # Selbsttest inkl. Labelprüfung
python3 nli.py nli-gbert-large --debug "Prämisse" "Hypothese"
```

Der Selbsttest ist **kein Ritual, sondern Pflicht vor der ersten
Auswertung**: Trägt ein Checkpoint eine falsche `id2label`, sind
Entailment und Contradiction vertauscht, und jeder korrekt belegte Claim
erscheint als Widerspruch. `nli.py` probt deshalb die Reihenfolge immer
empirisch und warnt bei Abweichung zur Config. Erkennungsmerkmal im
Viewer: `nli` nahe 0,00 bei gleichzeitig hoher Abdeckung und hohem emb.

**Gemessene Schwachstelle des Modells:** Wechselt ein *bildhafter*
Ausdruck die grammatische Form („das *ist* ein wunder Punkt" →
„spricht von *einem wunden Punkt*"), meldet das Modell mit ~0,95
Sicherheit einen Widerspruch, obwohl korrekt verdichtet wurde.
Sachliche Nominalisierungen sind nicht betroffen — das Alltagsmuster
im Radiotext („Die Lage ist angespannt" → „spricht von einer
angespannten Lage") ist sicher. Der Widerspruchs-Chip verlangt deshalb
eine zweite Meinung: Negationsasymmetrie zwischen Fundstelle und Claim
**oder** schwache lex/emb-Stützung. Ohne beides wird der Befund als
„Signale uneinig" geführt statt als Widerspruch. Die Ablationsskripte,
die zu diesem Befund geführt haben, liegen dem Projekt bei.

Ein NLI-Paar je belegtem Claim (Prämisse = Überschrift + Vorspann +
tragende Fundstellen, beide Seiten zahlnormalisiert), gebatcht in einem
Durchlauf — bei ~10 Claims wenige Sekunden auf einem i5. Herabgestuft
wird konservativ: nur wenn Neutral dominiert *und* Entailment unter der
Schwelle liegt, nie bei Zahlkonflikt (hartes Signal hat Vorrang) und nie
bei Teilaussagen mit Rückverweis („ohne sie" — der Prämisse fehlt der
Bezug, Neutral wäre ein Artefakt).

## Was die Stufen tun

| Stufe | Signal | Ergebnis |
|---|---|---|
| 0 | Deutsche Zahlwörter → Normform („sechs Komma acht Millionen Euro" → `6800000 EUR`), Geld/Prozent/Jahre/Verhältnisse | Anker-Boni, **Zahlkonflikt**- und **Zahl-unbelegt**-Flags |
| 0.5 | Personen über NER (`ner.py`), tokenbasierter Namensabgleich | Namens-Anker, **Name-unbelegt**-Meldung |
| 1 | Char-3/4-Gramm-TF-IDF auf zahlnormalisiertem Text + Positionsprior | Kandidatenranking, Margin |
| 1.5 | **Restabdeckung**: weitere Quellen nach ihrem Zusatzbeitrag am Claim | **aggregiert**-Erkennung, auch über Absatzgrenzen hinweg |
| 2 | Embeddings (SAIA oder lokal) + Score-Fusion | robustere Zuordnung bei Umformulierungen |
| 3 | NLI-Cross-Encoder (lokal, `nli.py`) gegen die Fundstellen | **Bedeutung verschoben**, **NLI-Widerspruch** |

### Wie die Aggregation entschieden wird

Die naheliegende Frage „ähnelt Satz X dem Claim?" ist für Verdichtungen die
falsche: ein Member trägt definitionsgemäß nur einen Teil bei und fällt an
jeder Ähnlichkeitsschwelle gegen den *ganzen* Claim durch. Stufe 1.5 fragt
stattdessen „erklärt Satz X etwas, das noch keine Fundstelle erklärt?" und
nimmt gierig weitere Sätze auf, solange ihr Zusatzbeitrag über
`residual_min_nah` (10 %) bzw. `residual_min_fern` (22 %) liegt — je
nachdem, ob der Satz neben einer schon gewählten Fundstelle steht oder
weit entfernt.
Die Notiz im Inspector nennt den gemessenen Beitrag, z. B. „s3 erklärt
zusätzlich 23 %".

Das ersetzt die frühere Fenster-Enumeration benachbarter Sätze. Nebeneffekt:
rund 38 % weniger Embedding-Aufrufe, weil keine Fenstertexte mehr
eingebettet werden.

Relationen: `direkt`, `aggregiert`, `keine_quelle` und — mit NLI —
`bedeutung_verschoben` (der Link bleibt erhalten, nur der Stützstatus
ändert sich; im Viewer als Wellenlinie). Claims zwischen den Schwellen
bleiben `direkt` mit niedriger Confidence und der Notiz „Unter der
Direkt-Schwelle" — sichtbar über den Margin-Chip.

## Im Viewer

- Chips oben: Zahlkonflikt · Zahl unbelegt · Signale uneinig · **Bedeutung
  verschoben** · **NLI-Widerspruch** · ohne Quelle · Margin < 0,10 ·
  Artikel ungenutzt
- Inspector zeigt die Roh-Scores (top/lex/emb/anker/nli) je Claim — zum
  Schwellen-Tuning — sowie die **Attributionsform** („wörtlich" /
  „Paraphrase", aus lex/emb abgeleitet; Design-Space der CHI-Studien zu
  traceable text)
- **Alt gedrückt halten** zeigt alle belegten Artikelstellen auf einmal
  (Modaltaste — momentan statt dauerhaft, sonst wäre der Artikel voller
  Farbe); Hover auf einen Artikelsatz zeigt weiterhin die abhängigen
  Claims (Backlink)
- „Teilspanne" markiert bei Anker-Treffern exakt die Zahlregion im Artikel
- Export erzeugt JSON, das unverändert im ursprünglichen
  Split-View-Prototyp ladbar ist (das Schema ist nur um den Relationswert
  `bedeutung_verschoben`, das Flag `nli_widerspruch` und `scores.nli`
  erweitert — ältere Viewer zeigen solche Claims ohne eigenen Stil)

## Tuning

Alle Schwellen und Gewichte in `pipeline.py` → `CFG` (Fusionsgewichte,
`t_direct`/`t_none`, `residual_min_nah`/`residual_min_fern`, `frage_faktor`, Anker-Boni,
`nli_entail_min`/`nli_contra_min`). Die Restabdeckung ist der
wichtigste Regler für die Aggregation: kleiner = mehr Mehrfachquellen. Sinnvoller
Workflow: 30–50 Paare durchschieben, Fälle mit Margin < 0,10 ansehen,
Schwellen nachziehen.

## Grenzen (bewusst)

- `inferiert` wird weiterhin nicht vergeben. Das NLI liefert zwar das
  nötige Entailment-Signal, aber die saubere Definition (entailt bei
  niedriger lexikalischer Überlappung = Interpretation) braucht erst
  kalibrierte Schwellen aus einem Gold-Set.
- NLI ist ein Hilfssignal (~80–85 % XNLI): `bedeutung_verschoben` ist
  eine Prüfempfehlung, kein Urteil. Der Link bleibt deshalb erhalten.
- Pronomen werden nicht aufgelöst („ohne sie" statt „ohne die AfD");
  Embeddings fangen das nur teilweise ab, die NLI-Prämisse (Überschrift +
  Vorspann) entschärft es, löst es aber nicht.
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
nli.py              NLI (Stufe 3): lokaler Cross-Encoder, 3 Modelle
zitate.py           Zitatblöcke + Sprecherkontext für die Suche
nli_ablation.py     Diagnose: welcher Umbau kippt ein NLI-Urteil?
nli_form_check.py   Gegenprobe: prüft Inhalt oder nur Sprachform?
index.html          Split-View-Frontend mit Eingabe-Panel (wird direkt
                    gepflegt; build_frontend.py ist der historische
                    Generator aus dem Original-Prototyp)
build_frontend.py   erzeugt index.html aus dem Original-Prototyp
```
