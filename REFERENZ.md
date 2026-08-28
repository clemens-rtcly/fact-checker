# Alignment Lab — Funktionsreferenz

Stand: Stufen 0, 0.5, 0.6, 0.8, 1, 1.2, 1.5, 2 und 3. Diese Datei
erklärt, was im Code passiert und wie die Anzeigen im Split-View zu
lesen sind. Der Code ist nach Stufen geordnet: je Stufe ein Ordner
(`stufe0/` … `stufe3/`), quer dazu `kern/` (Text, Segmentierung,
Lexik, Fusion, Entscheidung, Ausgabe) und `konfig.py` (CFG, STUFEN,
VARIANTE). §4 folgt dieser Ordnung.

---

## 1. Die Kennzeichnungen: s1, c1, §, Blocks

### `s1`, `s2`, `s3` … — Sätze im **Originalartikel**

Fortlaufend über das ganze Dokument nummeriert, beginnend bei 1. Die
Zählung läuft **absatzübergreifend weiter** — s1 ist immer der erste
Satz des Artikels, unabhängig davon, in welchem Absatz ein Satz steht.

```
Stadtrat beschließt Rekordinvestitionen        -> s1   (§0, headline)

Die Stadt investiert 5,3 Millionen Euro.       -> s2   (§1, lead)
Der Gemeinderat stimmte mit 28 zu 11 zu.       -> s3   (§1, lead)

Es ist die höchste Summe seit 2019.            -> s4   (§2, body)
```

### `c1`, `c2`, `c3` … — Claims im **Transkript**

Gleiches Prinzip — mit einer Einschränkung: Ein Transkriptsatz kann in
**mehrere Claims zerfallen**, wenn er an einem Konnektor teilbar ist
(Stufe 1.2). Aus einem Satz werden dann c5 und c6, jeder mit eigener
Relation, eigener Confidence und eigenem Urteil.

```
„Kraft sprach von einem Kraftakt, während die Opposition kritisierte."
 └── c5 ──────────────────────┘  └── c6 ─────────────────────────┘
        direkt → s7                      direkt → s9
```

Die Claim-Nummerierung zählt über die **Teilaussagen**, nicht über die
Sätze. Elf Claims können also aus neun Transkriptsätzen stammen.

### `block` — die Rolle eines Artikelsatzes

Wird allein aus der Absatzposition abgeleitet, nicht aus dem Inhalt:

| Wert | Herkunft | Darstellung |
|---|---|---|
| `headline` | erster Absatz (§0) | groß, fett |
| `lead` | zweiter Absatz (§1) | leicht hervorgehoben |
| `body` | alle weiteren Absätze | normal |

Praktische Konsequenz: **Leerzeilen sind bedeutungstragend.** Wer den
Artikel ohne Leerzeile zwischen Überschrift und Text einfügt, bekommt
keine erkannte Überschrift.

### `§0`, `§1` … — Absatzindex

Interne Nummer des Absatzes, beginnend bei 0. Wird für die
Block-Zuordnung und für die Nachbarschaftssuche bei der
Zahlenprüfung benutzt.

---

## 2. Die Anzeigen im Viewer

### Relationen (Linienstil zwischen den Spalten)

| Relation | Bedeutung | Wann vergeben |
|---|---|---|
| `direkt` | Claim geht auf **eine** Artikelstelle zurück | Top-Score ≥ `t_direct`, keine weitere Quelle nötig |
| `aggregiert` | Claim verdichtet **mehrere** Artikelstellen | mehr als eine tragende Fundstelle nach Stufe 1.5 |
| `bedeutung_verschoben` | richtige Stelle gefunden, Aussage aber **leicht verschoben** („es *könnte*" → „es *kam*"; „Rhinopharyngitis" → „Halsschmerzen und Husten") — der Link bleibt erhalten | nur mit NLI (Stufe 3): Neutral dominiert und Entailment < `nli_entail_min`; Wellenlinie im Viewer |
| `keine_quelle` | keine ausreichend ähnliche Stelle gefunden | Top-Score < `t_none` |
| `inferiert` | im Schema vorgesehen, **wird weiterhin nie vergeben** | Definition (entailt bei niedriger lexikalischer Überlappung) steht, braucht aber kalibrierte Schwellen aus einem Gold-Set |

Zur Einordnung von `bedeutung_verschoben`: In der Penn-Studie
(Kambhamettu et al.) hatten 18 von 159 Links „semantische Probleme" —
weder Treffer noch Fehler. Vorher landete so etwas hier als `direkt` mit
etwas niedrigerer Confidence und fiel niemandem auf. Die Fundstellen
bleiben absichtlich erhalten: verschoben heißt „richtig verlinkt, nicht
sauber belegt", nicht „falsch verlinkt".

### Rollen einer Fundstelle

| Rolle | Bedeutung |
|---|---|
| `primaer` | **tragend** — diese Stelle erklärt einen Teil des Claims, der sonst unerklärt bliebe |
| `redundant` | sagt inhaltlich dasselbe wie eine andere Fundstelle, wird nur zur Information mitgeführt |

Wichtig für die Lesart: Bei `aggregiert` sind **alle** tragenden Quellen
`primaer`. Es gibt keine Rangfolge unter ihnen — s2 ist nicht „wichtiger"
als s3, beide erklären verschiedene Teile.

### Kennzahlen im Inspector

| Anzeige | Bedeutung | Faustregel |
|---|---|---|
| **Sicherheit · ohne Quelle** | Bei `keine_quelle` misst das Feld etwas ANDERES: nicht die Güte eines Belegs, sondern die Sicherheit, dass keiner existiert (`0,55 + (t_none − top) × 2,2`). Je weiter der beste Kandidat unter der Schwelle liegt, desto höher. Die Oberfläche beschriftet es deshalb um und zeigt daneben den Abstand zur Schwelle statt der bedeutungslosen Margin | hoch = klarer Fehlschlag; **niedrig = knapp gescheitert und einen Blick wert** |
| **Confidence** | Potenzmittel aus Gesamtabdeckung und Embedding, gedämpft durch die Margin | < 0,50 = ansehen |
| **Margin** | Abstand der besten Fundstelle zum besten NICHT gewählten Satz — nach der Aggregation gemessen | klein = es gab gleichwertige Alternativen außerhalb der Auswahl |
| **Margin zu Top-2 (alt)** | Abstand zwischen bestem und zweitbestem Artikelsatz | < 0,10 = die Zuordnung war knapp, Verwechslungsgefahr |
| **Scores → top** | fusionierter Gesamtscore des besten Satzes | Basis aller Schwellen |
| **Scores → lex** | rein lexikalische Ähnlichkeit (Stufe 1) | hoch bei wörtlicher Übernahme |
| **Scores → emb** | Embedding-Ähnlichkeit (Stufe 2), `—` im Offline-Modus | hoch bei Umformulierung |
| **Scores → anker** | Bonus aus Zahlen- und Namenstreffern (Stufe 0/0.5) | > 0 = harte Evidenz vorhanden |
| **Scores → nli** | Entailment-Wahrscheinlichkeit der Fundstellen für den Claim (Stufe 3), fehlt ohne NLI | < `nli_entail_min` (0,60) = Stützung fraglich |

Zusätzlich zeigt der Inspector neben der Relation die **Attributionsform**
(aus dem Design-Space der CHI-Studien zu „traceable text"): `wörtlich`
bei hohem lex, `Paraphrase` bei niedrigem lex und hohem emb. Reine
Anzeigelogik ohne Einfluss auf die Entscheidung — die Scores tragen die
Unterscheidung ohnehin, sie war nur nirgends sichtbar.

Die Kombination ist aussagekräftiger als jeder Einzelwert: **lex niedrig,
emb hoch** heißt „stark umformuliert, inhaltlich getroffen" — genau der
Fall, für den Stufe 2 existiert. **lex hoch, anker 0** bei einem Satz mit
Zahlen ist dagegen ein Warnsignal.

### Befund-Chips über den Spalten

| Chip | Auslöser |
|---|---|
| Zahlkonflikt | Zahl im Transkript weicht von der Zahl im Artikel ab (`flags: zahlkonflikt`) |
| Zahl unbelegt | Zahl im Transkript kommt im Artikel gar nicht vor (`flags: zahl_unbelegt`) |
| Name/Kürzel abweichend | `flags: ort_konflikt` oder `kuerzel_konflikt` — ein Ortsname, eine Organisation oder ein Kürzel kommt im Artikel nicht wörtlich vor, hat dort aber einen sehr nahen Nachbarn („Langenharm" gegen „Langenhorn", „XL" gegen „XXL") |
| Name/Kürzel unbelegt | `flags: ident_unbelegt` — kein wörtlicher Treffer und kein naher Nachbar im Artikel |
| Wortlaut abweichend | `flags: wortlaut_abweichung` — ein fast wörtlich übernommener Claim (lex ≥ `diff_lex_min`) enthält eine Ersetzung, deren beide Seiten sich stark ähneln |
| Widerspruch bei Wortgleichheit | `flags: widerspruch_wortgleich` — NLI meldet contradiction ≥ `nli_wortgleich_contra` bei lex ≥ `nli_wortgleich_lex`. Die aussagekräftigste Konstellation überhaupt: Sind zwei Sätze fast wortgleich, muss der Widerspruch in der kleinen Differenz sitzen |
| Signale uneinig | Abdeckung und Embedding weichen um mehr als `dissens_delta` ab (`flags: signale_uneinig`) — entweder Paraphrase ohne Wortlaut oder Wortlaut ohne Bedeutung. Hier landen zusätzlich die **nicht gestützten NLI-Widersprüche** (siehe Stufe 3) |
| Bedeutung verschoben | Relation `bedeutung_verschoben` — NLI: Fundstelle widerspricht nicht, stützt aber auch nicht vollständig |
| NLI-Widerspruch | `flags: nli_widerspruch` — contradiction über der Schwelle **und** unabhängig gestützt; semantischer Widerspruch jenseits der Zahlkonflikte („der Turm wird *nicht* verkleidet") |
| ohne Quelle | Relation `keine_quelle` |
| inferiert | derzeit immer 0 |
| Margin < 0,10 | knappe Entscheidung, Verwechslungsgefahr |
| Artikel ungenutzt | Artikelsätze, auf die kein Claim verweist |

„Artikel ungenutzt" ist kein Fehler — Zusammenfassungen lassen naturgemäß
weg. Auffällig wird es, wenn ein Satz mit harten Fakten ungenutzt bleibt.

### Rückrichtung und Modaltaste

Hover auf einen Artikelsatz hebt die Claims hervor, die ihn benutzen
(Backlink). **Alt gedrückt halten** zeigt zusätzlich alle belegten
Artikelstellen auf einmal; loslassen blendet sie wieder aus. Momentan
statt dauerhaft, weil der Artikel sonst voller Farbe und nicht mehr
lesbar wäre — die Empfehlung aus den CHI-Studien: fünf von 21
Teilnehmern lasen quellenfirst, der Chip „Artikel ungenutzt" ist die
Zahl dazu, die Modaltaste das Bild.

### Entitäten-Status

| Status | Zeichen | Bedeutung |
|---|---|---|
| `match` | `=` | im Artikel belegt |
| `konflikt` | `≠` | Artikel nennt einen **anderen** Wert (wird mitangezeigt) |
| `unbelegt` | `?` | im Artikel nicht auffindbar |

Das Feld `type` sagt, welcher Kanal den Befund erzeugt hat: `zahl`,
`geld`, `prozent`, `datum` aus Stufe 0, `person` aus Stufe 0.5, `ort`
und `kuerzel` aus Stufe 0.6. Identifier tragen keine Normform, die von
der Oberfläche abweicht — der Inspector zeigt sie deshalb ohne `→`.

---

## 3. Der Ablauf einer Analyse

```
Artikeltext + Transkripttext
        │
        ├─ kern/text        strip_html()            Markup → Klartext + Absätze
        ├─ kern/segmentierung  segment()             Absätze → Sätze → s1…sN
        ├─ Stufe 1.2  stufe1/teilaussagen.waehle_claims()   Sätze → c1…cM
        │
        ├─ Stufe 0    stufe0/zahlen.extract_entities()   Zahlen, Geld, %, Jahre
        ├─ Stufe 0.5  stufe0/personen (ner.persons())    Personennamen
        │                                  ↓ stufe0/anker: Anker-Boni
        ├─ Stufe 1    stufe1/abdeckung        lexikalische Matrizen (TfIdf,
        │                                     Abdeckung, Ko-Lokalität, Zitate)
        ├─ Stufe 2    stufe2/skalierung       Embedding-Matrix (optional)
        │                                  ↓
        ├─ kern/fusion.matrix()           ein Score je Claim×Satz
        ├─ kern/entscheidung              Primärzuordnung, Margin, Confidence
        ├─ Stufe 1.5  stufe1/restabdeckung    weitere tragende Quellen
        ├─ Stufe 0    stufe0/anker.komplementaere()   Zahlen-Anker als Zusatzquellen
        ├─ Stufe 0    stufe0/verifikation     Zahlen / Personen / Identifier
        ├─ Stufe 0.8  stufe0/wortlaut         Wort-für-Wort-Diff
        ├─ Stufe 1    stufe1/spannen          Belegspannen für den Viewer
        ├─ Stufe 3    stufe3/praemisse + nachentscheidung   NLI in einem Batch
        │                                ↓ bedeutung_verschoben / nli_widerspruch
        └─ kern/ausgabe.assemble()        JSON im Viewer-Schema
```

`pipeline.py` enthält nur noch diese Reihenfolge — jede Rechnung liegt in
ihrem Stufen-Modul. Die Reihenfolge ist Teil des Ausgabevertrags: Notizen
und Flags erscheinen im JSON in Aufrufreihenfolge.

---

## 4. Der Code, nach Stufen geordnet

### `pipeline.py` — der Orchestrator

**`align(article_text, transcript_text, embed_fn=None, model_label=..., nli_fn=None, stufen=None)`**
Die einzige Funktion, die von außen aufgerufen wird. Führt alle Stufen
aus und liefert das fertige JSON. `embed_fn` ist optional — fehlt sie,
läuft alles ohne Embeddings, und die Fusionsgewichte werden automatisch
neu normalisiert. `nli_fn` ist ebenfalls optional (Stufe 3) — fehlt sie,
bleibt `scores.nli` leer und `bedeutung_verschoben` wird nie vergeben.
`stufen` überschreibt einzelne `STUFEN`-Schalter für diesen Lauf
(siehe §5); nur bei Abweichung vom Standard erscheint die
Schalterstellung als `meta.stufen` im Ergebnis — Läufe mit allen
Stufen bleiben byte-identisch zu vorher.

### `konfig.py` — CFG, STUFEN, VARIANTE

Alle Schwellen und Gewichte (`CFG`, §5), die Stufen-Schalter (`STUFEN`,
§5) und die benannten Aushänge (`VARIANTE`), über die `varianten.py`
Verhalten austauscht, ohne Module zu patchen — derzeit `gewinn`,
`max_quellen`, `zusatzquellen` und `tfidf_klasse`. Alles wird zur
**Laufzeit** gelesen; wer `CFG` oder `STUFEN` ändert, wirkt sofort auf
den nächsten `align`-Aufruf. `pipeline.py` exportiert `CFG`, `STUFEN`,
`VARIANTE`, `align`, `segment`, `Sent`, `strip_html` und `TfIdf`
weiterhin — bestehende Skripte und Notizen bleiben gültig.

### `kern/` — was mehrere Stufen teilen

#### `kern/text.py`

**`strip_html(text)`**
Entfernt HTML- **und Markdown**-Auszeichnung und stellt Absatzgrenzen
wieder her. Blocktags (`<p>`, `</p>`, `<h3>`, `<br>`, `<li>`) werden zu
Leerzeilen, damit die Absatzlogik greift; übrige Tags entfallen, Entities
werden aufgelöst. Markdown-Überschriften verlieren ihre Rautezeichen,
bleiben aber als Text erhalten — Zwischenüberschriften tragen Inhalt
(„19 Gelege von Bodenbrütern") und dürfen als Fundstelle dienen.
Läuft automatisch am Anfang von `align()` und nur, wenn überhaupt Markup
gefunden wird. Ohne diesen Schritt verklebt aus dem Redaktionssystem
kopierter Text die Überschrift mit dem ersten Fließtextsatz, und
Zwischenüberschriften zählen als Artikelsätze.

#### `kern/segmentierung.py`

**`segment(text, kind, id_prefix)`**
Zerlegt in Absätze (Leerzeile) und Sätze. Kennt eine Abkürzungsliste
(`z.B.`, `Mio.`, `ca.` …) und schützt Ordnungszahlen („3. Platz"), damit
dort keine Satzgrenze entsteht. Liefert exakte Zeichen-Offsets — davon
hängt die gesamte Markierung im Viewer ab.

**`strip_html(text)` / `_ueberschrift(...)` — Überschriften**
Auszeichnung wird auf Markdown normalisiert (`<h2>` wird `##`) statt
gelöscht; `segment` erkennt daraus echte Überschriften und liefert
`block='heading'` mit der Ebene in `level`. Die frühere Dreiteilung
headline/lead/body kam aus der **Absatzposition** — erster Absatz gleich
Überschrift, zweiter gleich Vorspann. Das war eine Annahme über die
Textgestalt und lag falsch, sobald ein Text keine Überschrift hatte,
direkt mit dem Vorspann begann oder mehrere Zwischentitel trug. Erkannt
werden Markdown (`#` bis `######`), Setext (`===`, `---`) und HTML
(`<h1>`–`<h6>`); die Auszeichnungszeichen fallen aus den Satz-Offsets
heraus, die Offsets selbst bleiben exakt.

#### `kern/lexik.py` — TF-IDF, Abdeckung, Ko-Lokalität

Neu gebaut wird ein TF-IDF überall über `erzeuge_tfidf(docs)` — der
Umweg existiert, damit `VARIANTE["tfidf_klasse"]` die Klasse an allen
drei Verwendungsstellen (Stufe 1, Teilaussagen-Probe, Varianten-Helfer)
gleichzeitig austauschen kann.

**`TfIdf` / `.vec(text)`**
Char-3/4-Gramm-TF-IDF über alle Sätze und Claims. Zeichen-n-Gramme statt
Wörter, weil sie mit deutscher Komposition und Flexion umgehen
(„Gewerbesteuereinnahmen" ↔ „Gewerbesteuer") ohne Stemming.

**`_coverage_score(...)`** — das Hauptsignal von Stufe 1
Asymmetrisch, weil „belegt sein" asymmetrisch ist: Es zählt, wie viel des
*Claims* der Satz erklärt, nicht wie ähnlich sich beide Texte sind. Drei
Bestandteile, die verschiedene Fehler abfangen:

```
A  Anteil des CLAIMS, den der Satz abdeckt          (Hauptsignal)
B  Anteil des SATZES, den der Claim abdeckt         (milder Dämpfer)
K  Ko-Lokalität benachbarter Wörter                 (Nähe-Bonus)

score = A · (0,75 + 0,25 · min(1, B/0,30)) + 0,30 · K
```

**Zwei Wortklassen werden gefiltert.** Funktionswörter (Artikel,
Hilfsverben, Präpositionen) und Hedges — quantifizierende oder abtönende
Adverbien wie „insgesamt", „rund", „bereits", „allerdings". Beide sind
geschlossene Klassen ohne nennenswerten Informationsgehalt, tauchen aber
in beliebigen Sätzen auf und stiften dadurch Scheinbelege. In einem Fall
trug „insgesamt" allein 13,1 % Restbeitrag und löste damit eine falsche
Verdichtung mit einem inhaltlich unbeteiligten Satz aus.

**A und B laufen nur über Inhaltswörter.** Funktionswörter tragen gemessen
15 bis 18 Prozent des Claim-Gewichts, im Einzelfall über 35 — genug, um
falsche Verdichtungen auszulösen. In einem Fall stützte sich eine
Verdichtung auf die Überlappung von „diese … sind" und kam damit auf
13,7 % Restbeitrag, knapp über der Schwelle; nach der Filterung bleiben
1,3 %. Zahlen werden nie gefiltert, auch wenn sie kurz sind — sie sind
die härtesten Anker.

Warum B nur dämpft und nicht gleichberechtigt eingeht: Lange Sätze decken
kurze Claims zufällig leichter ab (gemessene Korrelation Satzlänge zu A:
+0,40), das gehört bestraft. Aber bei echter Zusammenfassung ist B
naturgemäß klein, ohne dass die Zuordnung schlechter wäre. Gemessen an 26
Claims mit bekannter Quelle: A allein trennt Platz 1 von Platz 2 im Mittel
mit 0,363, eine symmetrische Verrechnung (F1) verschlechtert das auf 0,259,
der milde Dämpfer verbessert es auf 0,384.

**`_colocality(...)`** — der Nähe-Bonus K
Stehen Wörter, die im Artikelsatz nah beieinanderliegen, auch im Claim nah
beieinander? Gezählt werden Paare übereinstimmender Tokens, die in beiden
Texten höchstens `_COLOC_W` (8) Tokens auseinanderliegen, geteilt durch die
Paare, die im Claim nah beieinanderliegen. Bei weniger als `_COLOC_MIN` (5)
Treffern wird gedämpft — aus zwei zufällig passenden Wörtern lässt sich
keine Struktur ablesen.

**Reihenfolgefrei**, und das ist der Punkt: Beim Zusammenfassen für Audio
wird die Wortstellung regelmäßig gedreht. Ein reihenfolgetreues Maß (zuvor
die längste gemeinsame Wortfolge) bestraft das zu Unrecht und lieferte bei
umgestellten Sätzen nur Bruchstücke — bei einem Beispiel blieb von einem
klaren Treffer nur das Wort „in" übrig.

Gemessen an 25 Claims mit bekannter Quelle, Abstand zwischen Platz 1 und 2:

| | Trennung |
|---|---|
| ungefiltert + Wortfolge (reihenfolgeabhängig) | 0,472 |
| gefiltert + Wortfolge | 0,509 |
| gefiltert + bestes Satzfenster | 0,532 |
| **gefiltert + Ko-Lokalität** | **0,562** |

**`_pmean(values, p)`** — Potenzmittel für die Confidence
`p=1` ist der Mittelwert, `p→∞` das Maximum. Bei `p=3` bleiben zwei
mittelmäßige Signale mittelmäßig, ein einzelnes starkes zieht aber hoch.
Der Mittelwert würde ein starkes Signal herunterziehen; ein logisches Oder
(noisy-OR) hübe zwei mittelmäßige fälschlich in den sicheren Bereich
(0,50 und 0,55 ergäben dort 0,78).

#### `kern/fusion.py` — ein Score je Claim×Satz

**`fused_at(ci, si)`** (`kern/fusion.py`)
Der Gesamtscore eines Paars:

```
basis = w_cov·abdeckung + w_emb·embedding + w_lex·kosinus + w_pos·position
score = basis + anker · (1 − basis)
```

Der Kosinus bleibt neben der Abdeckung, weil er die Gegenrichtung
mitmisst — er ist ein Korrektiv gegen sehr lange Sätze, die per Zufall
viel abdecken.

Der Positionsprior nutzt aus, dass Zusammenfassungen der Artikelreihenfolge
folgen — der dritte Claim wird eher in der Artikelmitte fündig.

Die Anker werden in den verbleibenden Spielraum skaliert statt addiert.
Additiv überschritten Basis plus Anker regelmäßig 1,0 und wurden
abgeschnitten; dann lagen Platz 1 und Platz 2 gleichauf und die Margin
fiel fälschlich auf 0.

#### `kern/entscheidung.py` — Primärzuordnung, Margin, Confidence

Die Schwellenlogik hinter den Relationen (§2): `primaerzuordnung`
vergleicht den Topscore gegen `t_direct`/`t_none` und sammelt
`redundant`-Kandidaten, `margin_nach_aggregation` misst den Abstand des
Gewählten zum besten Nichtgewählten **nach** Stufe 1.5 (sonst wäre die
zweite Quelle ihr eigener Konkurrent), `confidence_und_notizen` bildet
das Potenzmittel aus Abdeckung und Embedding-Signal und meldet
`signale_uneinig` ab `dissens_delta`.

#### `kern/ausgabe.py`

`assemble()` baut das Ergebnis-JSON. Feldnamen
und Reihenfolge sind der Vertrag mit `index.html` und `eval.py`.

### `stufe0/` — harte Signale vor aller Ähnlichkeit

#### `stufe0/zahlen.py` — Zahlwörter und numerische Entities (vormals `german_numbers.py`)

**`parse_number_word(word)`**
Deutsches Zahlwort → Zahl. Beherrscht zusammengesetzte Formen
(`achtundzwanzig` → 28), Tausender (`zweitausendneunzehn` → 2019),
Hunderter (`neunzehnhundertvierundachtzig` → 1984) und die gesprochene
Jahres-Lesart (`zwanzigsiebenundzwanzig` → 2027).

**`extract_entities(text)`**
Findet alle numerischen Entitäten mit exakten Offsets und normalisiert
sie. Erkennt zusätzlich Dezimalstellen über „Komma", Skalenwörter
(Millionen, Mrd.), Einheiten (Euro, Prozent) und Verhältnisse („28 zu 11"
→ `28:11`).

| Typ | Beispiel | Normform |
|---|---|---|
| `geld` | fünf Komma drei Millionen Euro | `5300000 EUR` |
| `prozent` | rund drei Prozent | `3 %` |
| `zahl` | achtundzwanzig zu elf **oder** 28:11 | `28:11` |
| `zahl` | acht bis zehn **oder** 8 bis 10 | `8-10` |
| `zahl` | zwischen 30 und 45 | `30-45` |
| `zahl` mit Einheit | dreißigjähriger / 30-Jährige | `30 Jahre` |
| `datum` | zweitausendneunzehn | `2019` |

Einheiten-Suffixe verschmelzen im Deutschen mit dem Zahlwort. Ohne
Behandlung findet die Pipeline im Artikel „30-Jährige" die Zahl 30, im
Transkript „dreißigjähriger" aber gar nichts — der Anker greift dann
einseitig. `_split_unit_suffix` zerlegt solche Komposita (jährig, tägig,
stündig, monatig, köpfig, stellig, prozentig …), `_unit_of_token` erkennt
die Ziffernform mit nachgestellter Einheit. Beide Schreibweisen erhalten
dieselbe Normform.

Ziffern, die unmittelbar an Buchstaben kleben, sind keine Mengenangaben:
`CO2`, `NO2`, `H2O` erzeugen keine Zahl-Entität mehr.

Die Ziffernform eines Verhältnisses („0:0") wurde früher als zwei
unabhängige Zahlen gelesen, weil der Doppelpunkt nicht in `_TOKEN_RE`
steht und deshalb kein Token wird. Die Normalisierung war damit
einseitig: Das Transkript sagt „null zu null" und liefert `0:0`, der
Artikel schreibt „0:0" und liefert zwei Nullen — der Anker griff nicht,
und die Konfliktprüfung meldete einen Unterschied, wo keiner war.
`_ist_uhrzeit` trennt die Ziffernform gegen Uhrzeiten ab: „14:30 Uhr"
über das nachgestellte „Uhr", zusätzlich gilt ein zweistelliger zweiter
Wert über 12 ohne führende Null als Zeitindiz. `0:0` bis `12:59` bleiben
damit Spielstände — in Lokalnachrichten die häufigere Lesart, aber eine
echte Ambiguität: „12:10" ohne „Uhr" wird als Verhältnis gelesen.

**Spannen.** `NUM bis NUM` wird zu einer Entität `8-10` zusammengefasst.
Zwei kleine Einzelzahlen liegen beide unter der Ankerschwelle
(`_anchorworthy`, ab 10) und sind im Artikel selten eindeutig — der Satz,
der sie enthält, wurde deshalb nicht als zweite Fundstelle ergänzt, wenn
sein Wortbeitrag unter `residual_min_fern` lag. Als Spanne ist der Wert
distinktiv genug für einen Anker und praktisch immer eindeutig.

`_spanne_ok` hält den Zweig bewusst eng; wo eine Bedingung scheitert,
bleibt es beim bisherigen Verhalten (zwei unabhängige Zahlen), der Zweig
kann also nichts verschlechtern. Ausgeschlossen sind Datumsspannen
(„vom 8. bis 10. Juli", erkannt am Ordnungspunkt hinter dem Token),
Uhrzeiten, Spannen mit Skala oder Einheit („1,6 bis 1,8 Millionen",
„acht bis zehn Jahre" — die Skala gälte für beide Endpunkte und müsste
mitgerechnet werden), nicht ganzzahlige Endpunkte und absteigende Paare.
Die reine Bindestrichform („8-10") wird **nicht** erkannt: Sie ist in
manchen Häusern auch die Schreibweise für Spielstände und würde dort mit
dem Verhältniszweig kollidieren.

**Spannenformen und Typbezeichnungen.** `NUM bis NUM` und
`zwischen NUM und NUM` ergeben beide `30-45`. „und" gilt **nur** nach
„zwischen", sonst würde jede Aufzählung („2 und 3 Prozent") zur Spanne.
Ohne die „zwischen"-Form war die Normalisierung wieder einseitig: Artikel
„zwischen 30 und 45", Transkript „von 30 bis 45" ergab einen
Zahlkonflikt, wo keiner ist — derselbe Fehler wie bei `0:0` vor der
Ziffernform, nur für die andere Schreibweise.

**Ausgeschriebene Ziffernketten.** „zwei-eins-zwei-C-D" ist die
gesprochene Form von „212CD". Ohne eigene Behandlung zerfällt sie in drei
kleine Zahlen (2, 1, 2), die im Artikel irgendwo anders ebenfalls
vorkommen — und erzeugen dort einen Zahlkonflikt gegen eine völlig
unbeteiligte Stelle. `_kette_aufloesen` erkennt Ketten aus mindestens
drei Gliedern, in denen jedes Glied entweder ein Ziffernwort oder ein
Einzelbuchstabe ist und mindestens ein Ziffernwort vorkommt. Zwei Glieder
wären zu wenig („S-Bahn"), gewöhnliche Komposita scheitern schon am
Gliedtest („Baden-Württemberg", „Nord-Ostsee-Kanal"). Beide Formen sind
damit als Menge unterdrückt; den Abgleich übernimmt `_codes` in `stufe0/identifier.py`,
das die Kette zur Ziffernform auflöst und auf exakter Gleichheit besteht.
Im Inspector erscheint dabei die aufgelöste Form („213CD"), nicht die
gesprochene — für die Meldung „steht so nicht im Artikel — dort 212CD"
ist das die brauchbarere Angabe, weicht aber vom Wortlaut des Transkripts
ab.

Zahlen, denen **ohne Leerzeichen Buchstaben folgen**, werden gar nicht
erst als Menge geführt: „212CD", „A7", „5G" sind Typbezeichnungen. Als
Zahl geführt erzeugten sie einen Zahlkonflikt gegen jede beliebige andere
Zahl im Artikel. Inhaltlich prüft sie die Kürzelprüfung in
`stufe0/identifier.py`, die auf exakter Gleichheit besteht statt auf numerischer
Nähe. Nur wenn die Zahl allein steht (keine Skala, keine Einheit) — „5
Grad" bleibt eine Messung.

**`normalize_numbers(text)`**
Ersetzt alle numerischen Entitäten durch ihre Normform. Wird vor der
TF-IDF-Berechnung angewandt — dadurch ähneln sich ausgeschriebene und
ziffernhafte Schreibweise auch *lexikalisch*, nicht nur über die Anker.

#### `stufe0/anker.py` — eindeutige Werte als Wegweiser

`matrix()` vergibt die Boni aus §5 (`anchor_unique`, `anchor_multi`,
`anchor_name_unique`, `anchor_name`, gedeckelt mit `anchor_cap`):
Eine Zahl oder ein Name, der in genau einem Artikelsatz steht,
lokalisiert den Beleg fast von allein. `komplementaere()` läuft nach der
Restabdeckung und ergänzt Fundstellen für eindeutige Zahlen-Anker
außerhalb der bisherigen Quellen, auch wenn deren Wortbeitrag klein ist.

**`_anchorworthy(entity)`**
Entscheidet, ob eine Zahl als Anker und als Teilspanne taugt. Bloße kleine
Zahlen unter 10 („zwei Ministerpräsidenten") kommen überall vor,
unterscheiden nichts und erzeugten als Teilspanne vierstellige Schnipsel.
Geldbeträge, Prozentwerte, Jahreszahlen und Verhältnisse bleiben
vollwertig. Für die Konfliktprüfung zählen kleine Zahlen weiterhin mit.

#### `stufe0/verifikation.py` — Zahlen, Personen, Identifier gegen den Artikel

Die drei Prüfungen hinter den Chips (§2): `pruefe_zahlen` (match /
konflikt / unbelegt gegen alle numerischen Entities, Nachbarschaft über
den Absatz), `pruefe_personen` (tokenbasierter Namensabgleich über
`ner.matches`), `pruefe_identifier` (Befunde aus `stufe0/identifier.py`
in Entities, Flags und Notizen übersetzen).

**Währungsellipse.** Im Deutschen wird die wiederholte Einheit
weggelassen: „20 Milliarden Euro … rund 62 Milliarden". Der zweite Betrag
erbt die Währung aus dem Kontext, wird aber als `zahl` geparst. Deshalb
gelten `{zahl, geld}` und `{zahl, prozent}` in `_values_equal` als
vergleichbar, analog zum bestehenden `{zahl, datum}`. Ohne das fand ein
`geld`-Claim seinen gleichwertigen `zahl`-Beleg nicht und meldete
stattdessen einen Konflikt gegen den nächstbesten anderen Geldbetrag im
Artikel.

**Vergleichbarkeit vor Konflikt.** Ein Verhältnis trägt als Wert eine
Zeichenkette (`"0:0"`), ein Skalar eine Zahl (`0.0`) — beide mit Typ
`zahl`, aber nicht auf einer Skala vergleichbar. Strukturierte Werte
gleicher Form sind untereinander sehr wohl vergleichbar: Der Abstand wird
komponentenweise gebildet, damit die Meldung „8-12 weicht ab — Artikel
nennt 8-10" lautet statt nur „unbelegt". Die Konfliktprüfung in
`stufe0/verifikation.py` verwirft deshalb Kandidaten mit unendlichem Abstand, statt
`min` den erstbesten wählen zu lassen. Ohne diese Prüfung lautete die
Meldung „0:0 weicht ab — Artikel nennt 0".

**`_values_equal(a, b)`**
Vergleicht zwei numerische Entitäten über ihren **Normwert**, nicht über
die Schreibweise. Dadurch gilt „fünf Komma drei Millionen Euro" als
identisch mit „5,3 Millionen Euro".

#### `stufe0/personen.py` — Stufe 0.5, Personen (vormals `ner.py`)

Importiert wird das Modul überall als `personen as ner` — die
Aufrufe heißen also weiterhin `ner.persons()`, `ner.entities()`,
`ner.backend()`.

**`persons(text)`**
Personennamen mit Offsets. Nutzt spaCy `de_core_news_sm`, falls
installiert, sonst einen konservativen regelbasierten Rückfall.

Der Rückfall verwirft Kandidaten mit Artikel am Anfang („Die
Bauarbeiten") und bekannte Nicht-Namen-Wörter. Hintergrund: Im Deutschen
werden alle Substantive großgeschrieben, „zwei großgeschriebene Wörter
nebeneinander" ist deshalb **kein** Namenssignal — „im Osten Regierungen"
sieht sonst aus wie ein Name.

**`matches(claim_name, article_names, article_text=None)`**
Tokenbasierter Abgleich statt Zeichenkettensuche. Belegt ist ein Name,
wenn die Tokenmengen ineinander enthalten sind — in beide Richtungen.
„Kraft" gilt damit durch „Sabine Kraft" als belegt, was in Transkripten
die Regel ist.

Scheitert das, greift eine Prüfung gegen den Rohtext: Kommen alle
Namensbestandteile als eigenständige Wörter im Artikel vor, gilt der Name
als belegt. Das fängt den Regex-Rückfall ab, der Einzelnamen wie „Merz"
nicht als Entität erkennt. Ein abweichender Name („Ehrler" statt „Ehrle")
fällt weiterhin durch.

**`backend()`**
Gibt `'spacy'` oder `'regex'` zurück — zeigt, welcher Pfad aktiv ist.

#### `stufe0/identifier.py` — Stufe 0.6, Orte, Organisationen, Kürzel

Der einzige Kanal mit **umgekehrter Logik**. Alle anderen Stufen lesen
Ähnlichkeit als Belegtheit; hier ist Fast-Identität ein Verdacht.

Der Grund ist eine Eigenschaft der Zeichen-n-Gramme, nicht ein Fehler:
Sie sind absichtlich kompositionstolerant, damit
„Gewerbesteuereinnahmen" auf „Gewerbesteuer" passt. Dieselbe Toleranz
macht „Langenharm" zu einem sehr guten Treffer für „Langenhorn".
Gemessen an einem absichtlich verfälschten Satz („XXL" → „XL",
„Langenhorn" → „Langenharm"): Abdeckung 1,00 bei lex 0,90. Die
Verfälschung *erhöht* den Score; über Schwellen ist sie nicht erreichbar.

**`pruefe(claim_text, artikel_text)`**
Liefert Befunde als `{"art", "surface", "status", "quelle_surface"?}`.
`status` ist `konflikt` (nicht wörtlich im Artikel, aber ein naher
Nachbar dort) oder `unbelegt` (nichts Vergleichbares).

**Zwei Klassen, zwei Verfahren.** Für Namen (LOC/ORG aus
`ner.entities`) wird morphologisch verglichen; für Kürzel über
Editierdistanz, weil ein zwei- bis vierstelliges Kürzel keinen Stamm
hat, an dem sich etwas ablesen ließe.

**`_variante(a, b)`** — der eigentliche Diskriminator
Drei Ausgänge: Flexionsvariante (kein Befund), gemeinsamer Stamm mit
abweichender Fortsetzung (Verdacht), zu wenig gemeinsam (kein Paar).
Drei Regeln in dieser Reihenfolge:

1. **Präfix.** Ist ein Wort echter Präfix des anderen, nie ein Konflikt.
   Deckt Komposition („Nord" aus „Nord- und Ostsee" gegen „Nordsee"),
   Ableitung („Münsteraner" gegen „Münster") und Genitiv mit einer Regel
   ab. Verfälschungen *tauschen* Zeichen, sie kürzen nicht.
2. **Alle Trennstellen** (`_teilbar`), nicht nur die maximale. Der gierige
   Präfix frisst sonst den Anfang der Endung: „grünen"/„grüner" teilt
   gierig „grüne", übrig bleiben „n" und „r" — und „r" allein ist keine
   Endung. Bei Trennstelle 4 bleiben „en" und „er".
3. **Umlautfaltung, aber nur mit echter Ableitung** und gegen
   `_ENDUNGEN | _ABLEITUNGEN`. „Lippstädter"/„Lippstadt" und
   „Münchner"/„München" sind ohne Faltung nicht lösbar. Unterscheiden
   sich zwei Wörter dagegen *ausschließlich* im Umlaut
   („Munster"/„Münster"), bleibt der Befund — das ist ein
   Transkriptionsfehler, kein Wortbildungsmuster.

**Beurteilt wird nur der ähnlichste Kandidat**, nicht die Disjunktion
über alle Artikelwörter. Die Disjunktion hatte ein Loch: „Langenharm"
gegen „Länge" ergibt nach Umlautfaltung „lange", und das ist ein Präfix
von „langenharm" — ein zufälliges Wort irgendwo im Artikel hob damit den
echten Konflikt gegen „Langenhorn" auf. „Langenhorn"/„Langenharm" teilt „langenh", die Reste
„orn"/„arm" sind keine Endungen. „Nordfriesland"/„Nordfrieslands"
teilt alles bis auf ein `s`.

Warum nicht einfach ein Ähnlichkeitsmaß mit Schwelle: Das trennt nicht.
Gemessene n-Gramm-Deckung von Claim-Wort durch Artikel-Wort —
`Gewerbesteuereinnahmen ← Gewerbesteuer` 0,53,
`Bauleitverfahrens ← Bauleitplanung` 0,33, `Bürgerverein ← Verein` 0,39,
und der Rauschfall `endgültige ← nachhaltige` 0,37. Die echten
Kompositionsbeziehungen und das Rauschen liegen ineinander; nur die
Frage „ist der Rest eine Endung?" trennt sie.

**Geprüft wird gegen den ganzen Artikel**, nicht gegen die Fundstellen.
Ortsnamen stehen in Lokalnachrichten in fast jedem Absatz; eine Prüfung
gegen die Fundstelle allein würde bei jeder Verdichtung Fehlalarme
erzeugen, ohne einen echten Fehler zu finden. Dieselbe Wahl trifft
`ner.matches` für Personen.

**Personen sind ausgeschlossen** (`labels=("LOC", "ORG")`), sonst stünde
jeder Name doppelt im Inspector — Stufe 0.5 prüft sie schon. Im
Regex-Rückfall von `ner` sind die Klassen nicht trennbar; dann liefert
`_namen` bewusst nichts und nur die Kürzelprüfung läuft.

#### `stufe0/wortlaut.py` — Stufe 0.8, Wort-für-Wort-Diff

`pruefe(claim_text, primaerquelle, lex_wert)` läuft erst ab
`diff_lex_min` (0,85) lexikalischer Übereinstimmung mit der
Primärfundstelle — darunter ist ein Wortvergleich sinnlos, weil die
Texte ohnehin verschieden formuliert sind. Gemeldet werden **nur
Ersetzungen** (`diff_max_worte`, `diff_max_meldungen`); eine Ersetzung
mit Zeichenähnlichkeit ab `diff_nah_min` (0,55) gilt als Vertauschung
(„XXL" → „XL") und löst das Flag `wortlaut_abweichung` aus, alles
darunter ist Wortwahl und bleibt reine Anzeige.

### `stufe1/` — das lexikalische Rückgrat (nicht abschaltbar)

#### `stufe1/abdeckung.py` — die Matrizen des Laufs

`berechne(art_sents, claims_raw)` bündelt alles Lexikalische in einem
`Lexikalisch`-Objekt: TF-IDF-Vektoren, Kosinus- und Abdeckungsmatrix,
Inhaltswort-Sichten und die Zitat-Kontexte. Die Stufen 1.5, die
Entscheidung und die Spannen lesen daraus — gerechnet wird alles genau
einmal.

#### Zwei Wortmengen je Artikelsatz

Der Kontext darf nur beeinflussen, **was gefunden wird**, nie **was
berichtet wird**:

| | Sicht | wofür |
|---|---|---|
| `art_cgrams_a` | angereichert | A-Term der Abdeckung, Kandidatensuche, „bereits erklärt" in der Restabdeckung |
| `art_cgrams` | roh | B-Dämpfer, Zusatzbeitrag eines Kandidaten, `cov_total`, Confidence, Belegspannen |

Die Trennung ist an drei Stellen nötig, jede aus einem gemessenen
Fehler: Liefe der Kontext in den **B-Dämpfer**, machte er den Satz
künstlich lang und bestrafte genau die Sätze, denen er helfen soll
(0,479 fiel auf 0,461). Zählte er als **Zusatzbeitrag**, erschiene jeder
weitere Satz desselben Zitats als Verdichtung (s34 und s36 drängten sich
so zu c19). Fehlte er beim **bereits Erklärten**, holte ein ferner Satz
Punkte für einen Namen, den der Block ohnehin trägt (s39 zu c11).

#### `stufe1/zitate.py` — Zitatblöcke und Sprecherkontext

**`bloecke(sents)`** gruppiert Sätze, die durch Anführungszeichen
zusammengehalten werden, je Absatz. Absatzgrenzen beenden einen Block,
Eigennamen ausdrücklich **nicht**: „Anders sei das beim Pink-Pop-Festival
in Landgraaf" steht mitten in der Rede einer Hotelsprecherin — würde der
Name den Block beenden, erbte der Folgesatz den falschen Sprecher.

**Attribution ohne Verbliste.** Der Sprecher wird strukturell bestimmt:
Trennzeichen, ein bis zwei Wörter, Eigenname. Was dazwischen steht, muss
nicht bekannt sein — geprüft wird nur, dass dort kein Funktionswort steht
(`_NICHT_VERB`). Eine Positivliste von Redeverben wäre prinzipiell
unvollständig („fügt hinzu", „räumt ein", „zufolge") und müsste jede
Flexionsform führen; Funktionswörter sind dagegen eine geschlossene
Klasse, und ein finites Verb gehört nie dazu. Das Deutsche invertiert
nach einem Zitat, deshalb trägt die Struktur.

**Eigennamen kommen aus `stufe0/personen.py`**, nicht aus der Großschreibung — dem
Modul, das die Personenerkennung der Stufe 0.5 leistet und die Heuristik
„zwei großgeschriebene Wörter" schon einmal abgelöst hat. `ner.entities()`
liefert dafür auch Organisationen, weil „so eine Sprecherin" auf das
City-Hotel verweist und nicht auf eine Person.

**`sprecherkontexte(sents)`** liefert je Satz den geerbten Kontextstring.
Zwei Bestandteile, die nachweislich unterschiedlich wirken: der
Sprechername (half c11 mit +0,175, bei c5 wirkungslos) und die
Gruppenwörter aus Possessivphrasen der 1. Person — „meine Kollegen aus
dem Kreis", „unsere Buchungen" (halfen c5 mit +0,29 und c7 mit +0,13).
Angereichert wird nur, wo der Satz zu einem Block gehört, ein Pronomen
der 1. Person oder ein Zitat trägt **und** seinen Bezug nicht selbst
nennt.

Pronomen werden bewusst **nicht** aufgelöst. „wir" wird nicht durch
„Wolfgang Wahl und die Betriebe im Kreis" ersetzt — das wäre
Koreferenzanalyse, im Deutschen unzuverlässig, und ein Fehler wirkte
still. Gesammelt werden nur Wörter, die im Block ohnehin stehen.

Sprechernamen werden auf die **reichste im Text belegte Form** normiert:
„sagt Mandele" wird zu „Hoteldirektor Eugene Mandele", weil die volle
Form die Wörter mitbringt, die eine Zusammenfassung aufgreift.

Bekannte Grenzen: verschachtelte und absatzübergreifende Zitate; im
Regex-Rückfall von `stufe0/personen.py` einwortige Namen („sagt Mandele" ohne
Vornamen) — mit spaCy kein Problem; und `GRUPPEN_UEBER_BLOECKE` — die Verteilung der Gruppenwörter
über Blockgrenzen hinweg ist gemessen leicht schlechter (F1 0,84 statt
0,86) und deshalb aus.

#### `stufe1/spannen.py` — Belegspannen für den Viewer

**`_evidence_spans(claim_grams, sent_text, anchor_spans)`**
Bestimmt, welcher Ausschnitt eines Artikelsatzes im Viewer kräftig
markiert wird (`source.start/end`).

Die frühere Regel lautete „Ankerregion, sonst ganzer Satz" und war in
beide Richtungen falsch: Eine Zahl im Satz schrumpfte die Anzeige auf die
Ziffern zusammen — bei „19 PFAS-haltige Substanzen will Goldschmidt …
verbieten" blieb sichtbar nur `19`, der eigentliche Beleg verschwand.
Umgekehrt wurde ein Satz ohne Zahl vollständig markiert, auch wenn er nur
ein Wort beitrug. Optisch kehrte das die Gewichtung um: Die Nebenquelle
leuchtete, die Hauptquelle zeigte zwei Ziffern.

Jetzt gilt ein Satz-Token als stützend, wenn mindestens 60 % seiner
Zeichen-3-Gramme im Claim vorkommen. Zeichen statt Wörter, weil
Transkripte Eigennamen phonetisch verformen („Pfass" für PFAS,
„Schlehswig" für Schleswig). Reihenfolge bleibt unberücksichtigt, weil
Zusammenfassungen umstellen — eine reihenfolgetreue Suche lieferte bei
umgestellten Sätzen nur Bruchstücke.

Entscheidend ist die Unterscheidung dreier Token-Zustände:

| Zustand | Bedeutung | Wirkung |
|---|---|---|
| `treffer` | im Claim belegt | trägt die Region |
| `abgelehnt` | geprüft, nicht gefunden | **trennt** zwei Regionen |
| `übersprungen` | gar nicht geprüft (Funktionswort, sehr kurz) | durchlässig |

Zwei Trefferregionen werden **nur** über übersprungene Tokens verbunden.
Ein einziges abgelehntes Wort dazwischen trennt sie. Eine Quelle besteht
deshalb aus einer *Liste* von Regionen (`source.spans`), nicht aus einer
einzelnen Spanne — `start`/`end` bleiben als Hülle erhalten, damit ältere
Viewer weiter funktionieren.

An den Rändern wächst eine Region über übersprungene Tokens hinaus, aber
nur, wenn bis zur Satzgrenze nichts Abgelehntes mehr folgt.

Beide Regeln adressieren je einen realen Fehler:

| Satz im Artikel | vorher markiert | jetzt |
|---|---|---|
| „… nicht verfügbar **waren**." (1:1 übernommen) | endete vor „waren" | vollständig |
| „… die Geschäfte, **der** erst zwei Jahre zuvor …" | Relativpronomen mit markiert | endet nach „Geschäfte" |
| „Laut Feuerwehr **konnte es zu einer** Geruchsbelästigung …" | eine Region über alles | vier getrennte Inseln |

Gemessen an 42 Quellen: 55 % bleiben eine einzige Insel, 29 % zwei, im
Mittel 1,71. Die Anzeige zersplittert also nicht — sie zeigt nur nicht
mehr Belege an, wo keine sind. Alle Inseln einer Quelle teilen sich im
Viewer denselben Schlüssel, es wird weiterhin nur *eine* Verbindungslinie
gezeichnet.

**`waehle_claims(transcript_text, art_sents, aktiv=True)`** — Stufe 1.2
Entscheidet, ob ein Transkriptsatz als Ganzes oder in Teilaussagen
verarbeitet wird. Ruft `split_sentence()` im selben Modul und nimmt eine Zerlegung
**zurück**, wenn ein Teil im Artikel nichts findet *und* einen Rückverweis
enthält.

Diese Doppelbedingung ist der Kern: Ein Teil ohne Rückverweis, der im
Artikel nichts findet, bleibt bewusst getrennt — das ist der Fall der
erfundenen zweiten Satzhälfte, und die soll als `keine_quelle` auffallen,
statt in der Zuordnung der ersten Hälfte zu verschwinden. Die Prüfung
läuft rein lexikalisch und kostet keine Embeddings.

#### `stufe1/teilaussagen.py` — Stufe 1.2, Teilaussagen (vormals `claims.py`)

**`split_sentence(text, base=0)`**
Zerlegt einen Satz an Konnektoren und liefert `[(teiltext, start, end), …]`
mit absoluten Offsets. Gibt immer mindestens ein Element zurück, die
Aufrufseite braucht also keinen Sonderfall.

Geschnitten wird an: Komma + Konnektor (deshalb, während, weil, obwohl,
außerdem, aber …), Semikolon, Gedankenstrich zwischen zwei Aussagen.

Nicht geschnitten wird:

| Fall | Grund |
|---|---|
| innerhalb von „…" oder ( ) | Zitate bleiben zusammen |
| `, dass …` | sonst bleibt „X sagte," als Fragment |
| `, der/die/das …` | Relativsätze modifizieren nur |
| `, und zwar/das/dabei …` | leitet keinen eigenen Satz ein |
| Teil kürzer als `MIN_PART_LEN` (25) | zu wenig Inhalt zum Zuordnen |
| nach Gedankenstrich kürzer als 35 oder mit Präposition beginnend | dort stehen Zusätze, keine Aussagen |
| `sodass`, `damit`, `wenn`, `falls`, `nachdem`, `bevor`, `sobald`, `solange` | Folge, Zweck, Bedingung, Zeit — gehört zur selben Aussage |
| alle Teile treffen denselben Artikelsatz | die Trennung wäre folgenlos |
| `weil`/`sondern`/`denn` bei offener Verneinung davor | **Sinnumkehr** — siehe unten |
| mehr als `MAX_PARTS` (3) Teile | Übersplitting |

**Die Negationsklammer.** „Nicht, weil X, sondern weil Y" ist *eine*
Aussage. Ein Schnitt bei „weil" macht aus dem verneinten X eine behauptete
Aussage und kehrt den Sinn um — aus „das sicher nicht, weil sie alle Nazis
geworden seien" würde der eigenständige Claim „weil sie alle Nazis
geworden seien", der dann auch noch als belegt gilt. `_has_open_negation()`
prüft deshalb vor jedem Schnitt an einem dieser Konnektoren, ob im
Vorderteil eine Verneinung offen ist.

**`has_anaphor(text)`**
Prüft auf Rückverweise (sie, ihn, dies, dabei, dadurch, deren …). Ein Teil
mit solchem Marker ist ohne seinen Vorgänger nicht sinnvoll prüfbar und
darf nicht allein als unbelegt gelten.

#### `stufe1/restabdeckung.py` — Stufe 1.5, Verdichtung

**`residual_gain(ci, chosen, cand)`** — Kern von Stufe 1.5
Beantwortet: *Welchen Anteil des Claims erklärt Satz `cand` zusätzlich zu
den bereits gewählten Sätzen?* Gerechnet auf den TF-IDF-Gewichten des
Claims, sodass Inhaltswörter zählen und Funktionswörter praktisch nicht.
Das Ergebnis ist direkt als Prozentanteil lesbar und steht so in der
Notiz („s3 erklärt zusätzlich 23 %").

Der Grund für diese Konstruktion: Die naheliegende Frage „ähnelt Satz X
dem Claim?" ist für Verdichtungen die falsche. Ein Member trägt
definitionsgemäß nur einen Teil bei und fällt an jeder Ähnlichkeitsschwelle
gegen den *ganzen* Claim durch.

**Redundante Fundstellen zählen für den Abstand mit.** Die
abstandsabhängige Schwelle misst zu `srcs` **und** `redundant`. Ohne das
hing das Ergebnis daran, wie ein Satz eingestuft wurde, statt daran, was
er beiträgt: Im Aachen-Paar lag der Restbeitrag von s61 zu c12 in beiden
Fällen bei 0,191 — nur der Abstand kippte von 2 (nah, Schwelle 0,10) auf
3 (fern, Schwelle 0,22), weil s63 einmal als zweite Quelle und einmal als
redundant galt. Redundante Sätze werden dem Nutzer angezeigt und stehen
in der NLI-Prämisse; ein Satz, der für beides gut genug ist, besetzt auch
eine Position in der Nachbarschaft. Als *Kandidat* bleibt er
ausgeschlossen — sein Beitrag ist ja schon verbucht.

### `stufe2/` — Embeddings (optional)

#### `stufe2/saia.py` — die Embedding-Backends

**`embed(texts, model, api_key=None, is_query=False)`**
Einzige Schnittstelle nach außen. Der Modellname entscheidet das Backend:
Namen mit Präfix `local-` rechnen auf der CPU, alle anderen gehen an die
SAIA-API.

`is_query` steuert die Präfix-Konvention: Claims werden als Anfragen mit
Instruct-Präfix eingebettet, Artikelsätze roh als Dokumente. Diese
Asymmetrie ist die von den E5- und Qwen-Autoren vorgesehene Verwendung
und macht beide Backends untereinander vergleichbar.

**`load_local(model)`**
Lädt ein lokales Modell einmalig und hält es im Prozessspeicher — jede
weitere Analyse startet ohne Ladezeit.

#### `stufe2/skalierung.py` — Matrix-Normalisierung

**`_normalize_matrix(rows)`**
Spreizt die Embedding-Kosinuswerte von P10 bis zum Maximum, global über
alle Paare. Nötig, weil E5-artige Modelle auch für völlig unverwandte
Satzpaare Werte um 0,7 liefern.

Global und nicht zeilenweise, damit das absolute Niveau erhalten bleibt —
sonst hätte auch ein Claim ohne jede Fundstelle einen Topwert von 1,0 und
`keine_quelle` würde nie vergeben. Der obere Anker ist bewusst das
Maximum: Mit P95 lagen bei längeren Dokumenten sämtliche Zeilenmaxima
darüber und wurden auf 1,0 geklemmt, womit das Embedding am oberen Ende
gar nichts mehr unterschied.

### `stufe3/` — NLI (optional)

#### `stufe3/nli.py` — die NLI-Modelle

**`classify(pairs, model)`**
Einzige Schnittstelle nach außen. Bekommt (Prämisse, Hypothese)-Paare
und liefert je Paar `{"entailment", "neutral", "contradiction"}` als
Softmax-Wahrscheinlichkeiten, gebatcht (8 Paare je Vorwärtsdurchlauf).
Gekürzt wird nur die Prämisse (`truncation="only_first"`) — die
Hypothese ist der Claim und muss vollständig im Fenster bleiben, sonst
beurteilt das Modell einen anderen Satz als den, der geprüft werden
soll.

**`load_nli(model)`**
Lädt das Modell einmalig und hält es im Prozessspeicher. Drei Modelle
in `NLI_MODELS` (Rechercheergebnis: kein eindeutiger Sieger):
`nli-mdeberta-2mil7` (Standard; XNLI-de 82,4 %, als einziges auf
Fever-NLI-/ANLI-Übersetzungen trainiert), `nli-gbert-large` (rein
deutsch, XNLI-de 85,6 %, aber nur übersetztes (M)NLI) und
`nli-minilm-l6` (Schnellstufe für Massendurchläufe).

**`_label_order(model, tokenizer)`**
Die Label-Reihenfolge im Logit-Vektor variiert je Checkpoint
(roberta-large-mnli: contradiction/neutral/entailment, mDeBERTa:
entailment/neutral/contradiction) — und manche Checkpoints tragen eine
*falsche* `id2label`. Deshalb wird **immer** empirisch geprobt
(`_order_from_probe`: Identitätspaar → Entailment-Dimension,
Negationspaar → Contradiction-Dimension; zwei Vorwärtsdurchläufe,
einmalig beim Laden) und das Ergebnis gegen `_order_from_config`
gehalten. Bei Abweichung gewinnt die Probe — eine Messung schlägt eine
Behauptung — und es erscheint eine laute Warnung.

Der Config allein zu vertrauen wäre fahrlässig: Sind die Label
vertauscht, kommt **jeder klar gestützte Claim als Widerspruch heraus**,
und zwar lautlos, weil das Ergebnis wie ein inhaltliches Urteil
aussieht. Erkennungsmerkmal im Viewer: `nli` nahe 0,00 bei gleichzeitig
hoher Abdeckung und hohem emb.

**`selftest(model)` / `debug_pair(model, premise, hypothesis)`**
Diagnose von der Kommandozeile:

```bash
python nli.py nli-mdeberta-2mil7                    # vier Testfälle + Labelcheck
python nli.py nli-gbert-large --debug "Prämisse" "Hypothese"   # Rohwerte
```

Der Selbsttest prüft entailment, neutral, contradiction und einen
schweren Fall (Redewiedergabe mit Personenwechsel) und meldet, ob die
Zuordnung plausibel ist; Exitcode 1 bei Verdacht. `debug_pair` zeigt
Logits, Wahrscheinlichkeiten je Index und die Tokenanzahl — Letzteres
deckt auf, ob die Prämisse am 512-Token-Limit gekürzt wurde.

#### `stufe3/praemisse.py` — Prämissenbau und Auftragssammlung

**`_nli_premise(primary, art_sents)`** — Stufe 3, Prämissenbau
Prämisse = Überschrift + erster Vorspann-Satz + tragende Fundstellen, in
Artikelreihenfolge und dedupliziert; beide Seiten (auch die Hypothese an
der Aufrufstelle) zahlnormalisiert.

Die Prämissenkonstruktion ist wichtiger als die Modellwahl: Der
Cross-Encoder kann nur auflösen, was in seiner Eingabe steht. Für
„St. Barbara" ↔ „Die Kirche in Pannesheide" liegt die verbindende
Evidenz in der Überschrift, die Aussage aber im Fließtext — Überschrift
und Vorspann führen in Nachrichtentexten fast immer die Hauptentität ein
und sind billig mitzugeben. Der volle Absatz bleibt bewusst draußen: Er
könnte Entailment aus Sätzen liefern, auf die der Link gar nicht zeigt —
dann wäre der Claim „belegt", ohne dass die *angezeigte* Fundstelle ihn
trägt.

Die Zahlnormalisierung beider Seiten folgt der TracSum-Fehleranalyse:
NLI-Modelle scheitern an unterschiedlichen Zahlschreibweisen („zwölf
Millionen" vs. „12 Millionen"); nach `normalize_numbers` sind
übereinstimmende Werte zeichengleich.

`auftrag()` sammelt je belegtem Claim (Prämisse, Hypothese,
Downgrade-Schutz, Quelltext) ein; gelaufen wird erst nach der
Claim-Schleife, damit alle Paare in **einem** Batch durchs Modell gehen.
Der Quelltext (nur die Fundstellen, ohne Überschrift und Vorspann) dient
der Negationsprüfung — Überschriften bringen häufig sachfremde
Verneinungen mit („finden keine Auszubildenden").

**Die NLI-Nachentscheidung** (`stufe3/nachentscheidung.py`)
Alle Paare gehen in **einem** Batch durchs Modell (ein Paar je belegtem
Claim). Drei Ausgänge auf den Softmax-Wahrscheinlichkeiten:

| Befund | Wirkung |
|---|---|
| contradiction ≥ `nli_contra_min`, ≥ entailment + `nli_contra_margin` **und** unabhängig gestützt (siehe unten) | Flag `nli_widerspruch`, Relation bleibt — der Link ist richtig, der Inhalt kollidiert (gleiche Semantik wie beim Zahlkonflikt) |
| dasselbe, aber **nicht** unabhängig gestützt | kein roter Chip; Flag `signale_uneinig` und eine erklärende Notiz |
| Neutral dominiert und entailment < `nli_entail_min` | Relation → `bedeutung_verschoben`, Fundstellen bleiben erhalten |
| sonst | nur `scores.nli`, keine Änderung |

**Der Widerspruch braucht eine zweite Meinung.** Gemessener Fehlermodus
des Modells (Ablationsreihe `nli_ablation.py` → `nli_form_check.py` →
`nli_minimalpaare.py` → `nli_nominalphrase.py`): Wechselt ein
**bildhafter** Ausdruck die grammatische Form — Kopulasatz gegen
Prädikatsnomen, „das *ist* ein wunder Punkt" gegen „spricht von *einem
wunden Punkt*" —, meldet das Modell mit ~0,95 Sicherheit einen
Widerspruch, wo eine korrekte Verdichtung steht. Entscheidend ist die
Kombination: sachliche Nominalisierungen sind nicht betroffen (gemessen
0 von 8), gleiche Form bei bildhaftem Inhalt ebenfalls nicht (0 von 2),
nur die Kreuzung kippt (2 von 2). Das Alltagsmuster im Radiotext („Die
Lage ist angespannt" → „spricht von einer angespannten Lage") ist also
sicher.

Der rote Chip wird deshalb nur vergeben, wenn das NLI-Urteil unabhängig
gestützt ist:

* **Negationsasymmetrie** (`_negation_asymmetry`) zwischen den tragenden
  Fundstellen und dem Claim — der weitaus häufigste echte Widerspruch
  entsteht durch Verneinung, und solche Paare haben fast identischen
  Wortlaut. Ohne diese Prüfung würde die Stützungsregel ausgerechnet die
  Fälle unterdrücken, für die der Chip existiert. Geprüft wird bewusst
  nur gegen die Fundstellen, nicht gegen die ganze Prämisse: Überschrift
  und Vorspann bringen häufig sachfremde Verneinungen mit („finden keine
  Auszubildenden").
* **oder** schwache Stützung durch lex/emb (`scores.top` <
  `nli_contra_support_max`). Ein Claim mit sehr hoher Wortlaut- und
  Bedeutungsübereinstimmung, in dem nichts verneint wird, ist eher
  korrekt verdichtet als widersprüchlich.

Fällt beides aus, wird der Befund nicht verschwiegen, sondern als
`signale_uneinig` geführt — mit einer Notiz, die den Contradiction-Wert
nennt. Bewusste Einschränkung: Antonym-Widersprüche ohne Negationswort
bei sehr hohem Wortlaut („Die Zahl stieg" / „Die Zahl sank") rutschen
damit in die schwächere Kategorie. Das ist der Preis dafür, dass der
rote Chip verlässlich bleibt.

Zwei Schutzregeln gegen falsche Herabstufungen: Bei bereits gemeldetem
**Zahlkonflikt** passiert nichts — das harte Signal hat Vorrang, ein
zweiter Status auf demselben Befund wäre Doppelmeldung. Und
**Teilaussagen mit Rückverweis** („deshalb müsse es ohne sie gehen",
`Sent.part` + `has_anaphor` aus `stufe1/teilaussagen.py`) werden nie herabgestuft: Der
Prämisse fehlt der Bezug, Neutral wäre dort ein Artefakt. Wichtig ist
die Einschränkung auf Teilaussagen — `has_anaphor` kennt auch „es", und
auf ganze Sätze angewandt würde der Schutz ausgerechnet das Paradebeispiel
blocken („**Es** kam zu einer Geruchsbelästigung": expletives „es", kein
Rückverweis).

### `app.py` — Server

**`POST /api/align`** mit `{article, transcript, model, nli, api_key}`
liefert das Ergebnis-JSON plus `meta.statistik` (Sätze, Claims,
Embedding-Anzahl, NLI-Paare, Dauer). Leerer `model` = Offline-Modus,
leeres `nli` = ohne Stufe 3.

Statuscodes: `400` fehlerhafte Eingabe oder unbekanntes NLI-Modell,
`502` Embedding- oder NLI-Backend (Präfix sagt, welches), `500`
Pipelinefehler.

---

## 5. Stellschrauben in `CFG`

| Parameter | Standard | Wirkung |
|---|---|---|
| `w_emb` / `w_cov` / `w_lex` / `w_pos` | 0,40 / 0,28 / 0,20 / 0,12 | Fusionsgewichte; ohne Embeddings auf dieselbe Summe renormalisiert, damit die Schwellen in beiden Modi gleich bedeuten |
| `cov_contig` | 0,30 | Gewicht der Ko-Lokalität im Abdeckungsscore |
| `cov_b_floor` / `cov_b_ref` | 0,75 / 0,30 | Stärke und Einsatzpunkt des Rückabdeckungs-Dämpfers |
| `conf_power` | 3,0 | Potenzmittel für die Confidence |
| `dissens_delta` | 0,45 | ab hier gelten Abdeckung und Embedding als uneinig |
| `t_direct` | 0,60 | ab hier gilt eine Zuordnung als sicher |
| `t_none` | 0,44 | darunter `keine_quelle`; dazwischen `direkt` mit niedriger Confidence und Prüfhinweis |
| **`residual_min_nah`** | **0,10** | Restbeitrag, den ein **benachbarter** Satz (Abstand ≤ `residual_nah_abstand`) beisteuern muss |
| **`residual_min_fern`** | **0,22** | dasselbe für **entfernte** Sätze — höhere Hürde gegen Scheinbelege |
| `residual_nah_abstand` | 2 | bis zu diesem Satzabstand gilt ein Kandidat als benachbart |
| `frage_faktor` | 0,55 | Abschlag für Fragesätze — sie behaupten nichts, ziehen aber Themenvokabular an |
| `residual_max_sources` | 3 | Obergrenze der tragenden Fundstellen je Claim |
| `residual_min_carriers` | 2 | so viele Inhaltswörter müssen den Zusatzbeitrag tragen |
| `agg_min_claim_len` | 55 | sehr kurze Claims werden nicht aggregiert |
| `anchor_unique` | 0,30 | Bonus für eine im Artikel eindeutige Zahl |
| `anchor_multi` | 0,12 | Bonus für eine Zahl mit 2–3 Fundstellen |
| `anchor_name_unique` | 0,20 | Eigenname, der in genau einem Artikelsatz steht — spiegelt `anchor_unique`, bleibt aber darunter: Namen wiederholen sich in Nachrichtentexten von Natur aus, und `ner.matches` ist heuristisch |
| `anchor_name` | 0,10 | Eigenname in genau zwei Artikelsätzen. Unverändert, damit die Stufung rein additiv bleibt und keinen Claim schlechter stellt. Ab drei Fundstellen kein Bonus — ein über den Text verteilter Name lokalisiert nichts |
| `anchor_cap` | 0,38 | Deckel über alle Anker-Boni |
| `redundant_delta` | 0,07 | wie nah ein Satz am Top-Score liegen muss, um als `redundant` mitzulaufen |
| `split_min_lex` | 0,16 | darunter gilt ein Teil als „findet nichts" (nur mit Rückverweis wird zurückgeführt) |
| `nli_entail_min` | 0,60 | darunter gilt der Claim als nicht gestützt — zusammen mit dominantem Neutral wird `bedeutung_verschoben` vergeben |
| `nli_contra_min` | 0,55 | darüber Flag `nli_widerspruch` … |
| `nli_contra_support_max` | 0,75 | oberhalb dieser lex/emb-Stützung wird ein Widerspruch nur noch bei Negationsasymmetrie als solcher gemeldet |
| `nli_wortgleich_contra` | 0,90 | ab hier gilt ein Widerspruch bei fast wortgleichem Claim als Befund — **unabhängig** von `nli_contra_support_max` und ohne Einfluss auf die Relation |
| `nli_wortgleich_lex` | 0,92 | so hoch muss die lexikalische Übereinstimmung dafür sein |
| `diff_lex_min` | 0,85 | ab dieser lexikalischen Übereinstimmung wird Wort für Wort gegen die Primärfundstelle verglichen |
| `diff_nah_min` | 0,55 | ab dieser Zeichenähnlichkeit der beiden Seiten gilt eine Ersetzung als Vertauschung statt als Wortwahl — nur diese lösen das Flag aus |
| `diff_max_worte` | 5 | längere Ersetzungen sind Umformulierung und werden nicht gemeldet |
| `diff_max_meldungen` | 6 | Obergrenze je Claim |
| `nli_contra_margin` | 0,25 | … aber nur mit diesem Abstand zu entailment. Ein bloßes „contradiction > entailment" wäre wirkungslos: Bei c ≥ 0,55 ist e zwangsläufig ≤ 0,45. Gemeint ist der Fall e = 0,44 / c = 0,55 — dort ist das Modell praktisch unentschieden |

Die beiden NLI-Schwellen sind vorläufig gesetzt und — wie
`t_direct`/`t_none` — erst mit einem Gold-Set seriös kalibrierbar.
Richtung beim Nachziehen: `nli_entail_min` höher = mehr Herabstufungen
(mehr Recall auf verschobene Bedeutungen, mehr Fehlalarme bei lockeren
Paraphrasen).

Nicht in `CFG`: `MIN_PART_LEN` (25), `MIN_PART_LEN_DASH` (35),
`MAX_PARTS` (3) in `stufe1/teilaussagen.py`; `_COLOC_W` (8),
`_COLOC_MIN` (5) und `_FUNC_WORDS` in `kern/lexik.py`; `_SPAN_FUZZ`
(0,6) in `stufe1/spannen.py`.
In `stufe0/identifier.py`: `_ENDUNGEN`, `_ABLEITUNGEN`, `_MIN_STAMM` (4), `_CODE_DIST` (2).

Beim Kalibrieren gilt: Solange nur gegen Einzelbeispiele getestet wird,
ist jede Schwellenänderung Raten. Ein Gold-Set von 30–50 selbst markierten
Paaren ist die Voraussetzung für sinnvolles Tuning.

---

### Die `STUFEN`-Schalter (`konfig.py`)

Einzelne Mechanismen lassen sich je Lauf abschalten — zur Messung, was
eine Stufe beiträgt, oder um Kosten zu sparen. Was früher die
CFG-Schlüssel `split_claims` und `ident_pruefen` waren, sind jetzt die
Schalter `1.2_teilaussagen` und `0.6_identifier`.

| Schalter | Kürzel | schaltet ab |
|---|---|---|
| `0_anker` | `0`, `anker` | Anker-Boni und komplementäre Zahlen-Anker |
| `0_verifikation` | `0`, `verifikation` | Zahlkonflikt-/Unbelegt-Prüfung |
| `0.5_personen` | `0.5`, `personen` | Personen-NER, Namens-Anker, Namensabgleich (spart die spaCy-Aufrufe) |
| `0.6_identifier` | `0.6`, `identifier` | Orte/Organisationen/Kürzel |
| `0.8_wortlaut` | `0.8`, `wortlaut` | Wort-für-Wort-Diff |
| `1.2_teilaussagen` | `1.2`, `teilaussagen` | Zerlegung an Konnektoren |
| `1.5_restabdeckung` | `1.5`, `restabdeckung` | Verdichtung (mehrere Quellen) |
| `2_embeddings` | `2`, `embeddings` | Stufe 2 trotz gewähltem Modell |
| `3_nli` | `3`, `nli` | Stufe 3 trotz gewähltem Modell |

Das Kürzel `0` schaltet **beide** 0er-Schalter. Stufe 1 (lexikalisches
Alignment) ist bewusst nicht abschaltbar — sie ist das Rückgrat, auf dem
alle Schwellen kalibriert sind.

Nutzung: `batch.py --ohne 0.5,wortlaut` (Komma-Liste aus Nummern oder
Namen), programmatisch `align(..., stufen={"0.5_personen": False})`, in
Varianten als Bündel `"stufen": {...}`. Nur bei Abweichung vom Standard
schreibt die Pipeline die Schalterstellung als `meta.stufen` ins
Ergebnis — Läufe mit allen Stufen bleiben byte-identisch zu vorher.
Unbekannte Kürzel brechen mit einer Liste der erlaubten ab.

---

## 6. Bekannte Grenzen

- **Die Identifier-Prüfung erreicht nur benannte Klassen.** Orte,
  Organisationen, Kürzel, Zahlen, Personen. Eine Verfälschung, die keine
  davon berührt und semantisch plausibel bleibt („Bürgermeister" →
  „Amtsdirektor" in einer Zuschreibung, ein gedrehtes Modalverb), fällt
  hier nicht auf. Dafür ist NLI das einzige Instrument.
- **Umlautkorruptionen werden als `unbelegt` gemeldet, nicht als
  Konflikt.** „Munster" gegen „Münster" teilt nur ein Zeichen am Anfang,
  fällt damit unter `_MIN_STAMM` und erreicht die Konfliktregel nie. Der
  Befund erscheint trotzdem — nur mit der unschärferen Meldung.
- **`_ABLEITUNGEN` macht gegen Endungsvertauschungen blind.** „Münsterer"
  statt „Münster" liefe als Ableitung durch. Der Preis dafür, dass
  „Lippstädter" und „Münchner" keine Fehlalarme mehr auslösen.
- **`_ENDUNGEN` ist eine geschlossene Klasse.** Was fehlt, erzeugt einen
  Fehlalarm; was zu viel darin steht, macht die Prüfung blind. Gemessen
  an einem Paar (10 Claims): 0 Fehlalarme, beide eingebauten
  Verfälschungen gefunden. Das ist keine Validierung — es ist eine
  Hypothese, die einen ersten Test überlebt hat.
- **Der Wortlaut-Diff meldet nur Ersetzungen.** Auslassungen sind beim
  Zusammenfassen der Normalfall; sie mitzumelden würde die Spalte
  unbrauchbar machen. Ein weggelassener Nebensatz fällt nicht auf.
- **Unterhalb `diff_lex_min` gibt es keinen Diff.** Eine Verfälschung in
  einem stark umformulierten Claim bleibt unsichtbar.
- **`widerspruch_wortgleich` ist vorerst nur Zählmaterial.** Das Flag
  widerspricht der Safeguard-Logik bewusst, ändert aber keine Relation.
  Die offene Frage: Wie oft feuert die Kombination auf dem Gold-Set, und
  wie oft zu Recht? Erst danach ist ein eigener Status begründbar.

- **`inferiert`: Messung vor Entscheidung.** `inferiert_ablation.py`
  prüft die Richtungsasymmetrie in drei Varianten je Claim — V
  (Quelle→Claim), R_satz (Claim→ganzer Satz), R_span (Claim→Evidenz-Spans).
  Die Kennzahl ist der Anteil gesättigter Werte in der Rückrichtung:
  Liegt alles in den äußeren Bändern und fällt nicht mit der Erwartung
  zusammen, trägt die Rückrichtung kein Signal und Methode E fällt aus.
  R_span gegen R_satz misst den Materialüberschuss langer Artikelsätze.
  Methode C (Abdeckung ≤ 0,80 **und** Entailment ≥ 0,50) läuft als
  Vorfilter, damit die doppelten Aufrufe begrenzt bleiben; `--alle`
  schaltet ihn ab. Der Kontrollsatz (`--kontrolle`) ist nötig, weil in
  den eigenen Paaren womöglich gar keine Ableitungen vorkommen. Ein
  `V_MIN`-Gate (0,70) schließt Fälle aus, bei denen schon die
  Vorwärtsrichtung nicht trägt — sonst zieht ein einzelner gescheiterter
  Vorwärtsfall die ganze Lückenmessung nach unten, ohne zur eigentlichen
  Frage (Richtungsasymmetrie) etwas beizutragen. Beim ersten Testlauf
  bestand der Kontrollsatz aus nur 3+3 Fällen; zwei davon waren
  irreführend — einer mit gescheitertem `V`, einer mit einer fälschlich
  als „direkt" etikettierten Generalisierung, die selbst eine
  Informationsreduktion war. Beide wurden korrigiert, der Satz auf 4+3
  erweitert.
- **`inferiert` wird weiterhin nie vergeben.** Das Entailment-Signal
  existiert jetzt, aber die saubere Definition (entailt bei niedriger
  lexikalischer Überlappung = Interpretation) braucht erst kalibrierte
  Schwellen aus einem Gold-Set — sonst wäre jede lockere Paraphrase eine
  „Interpretation".
- **NLI ist ein Hilfssignal, kein Orakel.** ~80–85 % XNLI-Genauigkeit
  heißt: `bedeutung_verschoben` ist eine Prüfempfehlung. Deshalb bleiben
  die Fundstellen erhalten, die Confidence unangetastet und die
  Herabstufung konservativ (Neutral muss dominieren, Zahlkonflikt und
  geschützte Teilaussagen sind ausgenommen).
- **Die Zerlegung ist rein oberflächlich.** Sie kennt Konnektoren, aber
  keine Syntax — Sätze ohne Konnektor bleiben ungeteilt, auch wenn sie
  zwei Behauptungen enthalten.
- **Teilspannen sind eine Wortmengen-Heuristik.** Sie erkennen keine
  Syntax; ein zufällig ähnliches Wort kann die Region verschieben.
- **Keine Pronomenauflösung.** „ohne sie" statt „ohne die AfD" ist
  lexikalisch unsichtbar; Embeddings fangen das nur teilweise ab.
- **Der Rückfall-NER findet weniger Namen als spaCy** — bewusst, um
  Fehlalarme zu vermeiden.
