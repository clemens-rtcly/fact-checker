# Alignment Lab — Funktionsreferenz

Stand: Stufen 0, 0.5, 1, 1.2, 1.5, 2 und 3. Diese Datei erklärt, was im
Code passiert und wie die Anzeigen im Split-View zu lesen sind.

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

---

## 3. Der Ablauf einer Analyse

```
Artikeltext + Transkripttext
        │
        ├─ segment()              Absätze → Sätze → s1…sN
        ├─ Stufe 1.2  _choose_claims()     Sätze → Teilaussagen c1…cM
        │
        ├─ Stufe 0    extract_entities()   Zahlen, Geld, Prozent, Jahre
        ├─ Stufe 0.5  ner.persons()        Personennamen
        │                                  ↓ Anker-Boni
        ├─ Stufe 1    TfIdf + _cos_sparse()   lexikalische Matrix
        ├─ Stufe 2    embed() + _cos_dense()  Embedding-Matrix (optional)
        │                                  ↓
        ├─ fused_at()             Fusion zu einem Score je Claim×Satz
        ├─ Primärzuordnung        bester Satz + Schwellenvergleich
        ├─ Stufe 1.5  residual_gain()      weitere tragende Quellen
        ├─ Zahlen-Anker           eindeutige Zahlen außerhalb der Quellen
        ├─ Entity-Verifikation    match / konflikt / unbelegt
        ├─ Stufe 3    nli.classify()     Entailment Claim <- Fundstellen
        │                                ↓ bedeutung_verschoben / nli_widerspruch
        └─ _assemble()            JSON im Viewer-Schema
```

---

## 4. Funktionen nach Modul

### `pipeline.py` — Steuerung und Entscheidungen

**`align(article_text, transcript_text, embed_fn=None, model_label=..., nli_fn=None)`**
Die einzige Funktion, die von außen aufgerufen wird. Führt alle Stufen
aus und liefert das fertige JSON. `embed_fn` ist optional — fehlt sie,
läuft alles ohne Embeddings, und die Fusionsgewichte werden automatisch
neu normalisiert. `nli_fn` ist ebenfalls optional (Stufe 3) — fehlt sie,
bleibt `scores.nli` leer und `bedeutung_verschoben` wird nie vergeben.

**`segment(text, kind, id_prefix)`**
Zerlegt in Absätze (Leerzeile) und Sätze. Kennt eine Abkürzungsliste
(`z.B.`, `Mio.`, `ca.` …) und schützt Ordnungszahlen („3. Platz"), damit
dort keine Satzgrenze entsteht. Liefert exakte Zeichen-Offsets — davon
hängt die gesamte Markierung im Viewer ab.

**`_choose_claims(transcript_text, art_sents)`** — Stufe 1.2
Entscheidet, ob ein Transkriptsatz als Ganzes oder in Teilaussagen
verarbeitet wird. Ruft `claims.split_sentence()` und nimmt eine Zerlegung
**zurück**, wenn ein Teil im Artikel nichts findet *und* einen Rückverweis
enthält.

Diese Doppelbedingung ist der Kern: Ein Teil ohne Rückverweis, der im
Artikel nichts findet, bleibt bewusst getrennt — das ist der Fall der
erfundenen zweiten Satzhälfte, und die soll als `keine_quelle` auffallen,
statt in der Zuordnung der ersten Hälfte zu verschwinden. Die Prüfung
läuft rein lexikalisch und kostet keine Embeddings.

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

**`fused_at(ci, si)`** (lokal in `align`)
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

**Die NLI-Nachentscheidung** (Ende von `align`)
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
`Sent.part` + `claims.has_anaphor`) werden nie herabgestuft: Der
Prämisse fehlt der Bezug, Neutral wäre dort ein Artefakt. Wichtig ist
die Einschränkung auf Teilaussagen — `has_anaphor` kennt auch „es", und
auf ganze Sätze angewandt würde der Schutz ausgerechnet das Paradebeispiel
blocken („**Es** kam zu einer Geruchsbelästigung": expletives „es", kein
Rückverweis).

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

**`_evidence_span(claim_grams, sent_text, anchor_spans)`**
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

**`_anchorworthy(entity)`**
Entscheidet, ob eine Zahl als Anker und als Teilspanne taugt. Bloße kleine
Zahlen unter 10 („zwei Ministerpräsidenten") kommen überall vor,
unterscheiden nichts und erzeugten als Teilspanne vierstellige Schnipsel.
Geldbeträge, Prozentwerte, Jahreszahlen und Verhältnisse bleiben
vollwertig. Für die Konfliktprüfung zählen kleine Zahlen weiterhin mit.

**`_values_equal(a, b)`**
Vergleicht zwei numerische Entitäten über ihren **Normwert**, nicht über
die Schreibweise. Dadurch gilt „fünf Komma drei Millionen Euro" als
identisch mit „5,3 Millionen Euro".

### `german_numbers.py` — Stufe 0, rein numerisch

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
| `zahl` | achtundzwanzig zu elf | `28:11` |
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

**`normalize_numbers(text)`**
Ersetzt alle numerischen Entitäten durch ihre Normform. Wird vor der
TF-IDF-Berechnung angewandt — dadurch ähneln sich ausgeschriebene und
ziffernhafte Schreibweise auch *lexikalisch*, nicht nur über die Anker.

### `ner.py` — Stufe 0.5, Personen

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

### `claims.py` — Stufe 1.2, Teilaussagen

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

### `saia.py` — Stufe 2, Embeddings

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

### `nli.py` — Stufe 3, NLI

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

### `zitate.py` — Zitatblöcke und Sprecherkontext

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

**Eigennamen kommen aus `ner.py`**, nicht aus der Großschreibung — dem
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
Regex-Rückfall von `ner.py` einwortige Namen („sagt Mandele" ohne
Vornamen) — mit spaCy kein Problem; und `GRUPPEN_UEBER_BLOECKE` — die Verteilung der Gruppenwörter
über Blockgrenzen hinweg ist gemessen leicht schlechter (F1 0,84 statt
0,86) und deshalb aus.

### Zwei Wortmengen je Artikelsatz

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
| `anchor_name` | 0,10 | Bonus für einen Personennamen |
| `anchor_cap` | 0,38 | Deckel über alle Anker-Boni |
| `redundant_delta` | 0,07 | wie nah ein Satz am Top-Score liegen muss, um als `redundant` mitzulaufen |
| `split_claims` | True | Stufe 1.2 an/aus — auf `False` verhält sich alles wie vorher |
| `split_min_lex` | 0,16 | darunter gilt ein Teil als „findet nichts" (nur mit Rückverweis wird zurückgeführt) |
| `nli_entail_min` | 0,60 | darunter gilt der Claim als nicht gestützt — zusammen mit dominantem Neutral wird `bedeutung_verschoben` vergeben |
| `nli_contra_min` | 0,55 | darüber Flag `nli_widerspruch` … |
| `nli_contra_support_max` | 0,75 | oberhalb dieser lex/emb-Stützung wird ein Widerspruch nur noch bei Negationsasymmetrie als solcher gemeldet |
| `nli_contra_margin` | 0,25 | … aber nur mit diesem Abstand zu entailment. Ein bloßes „contradiction > entailment" wäre wirkungslos: Bei c ≥ 0,55 ist e zwangsläufig ≤ 0,45. Gemeint ist der Fall e = 0,44 / c = 0,55 — dort ist das Modell praktisch unentschieden |

Die beiden NLI-Schwellen sind vorläufig gesetzt und — wie
`t_direct`/`t_none` — erst mit einem Gold-Set seriös kalibrierbar.
Richtung beim Nachziehen: `nli_entail_min` höher = mehr Herabstufungen
(mehr Recall auf verschobene Bedeutungen, mehr Fehlalarme bei lockeren
Paraphrasen).

Nicht in `CFG`: `MIN_PART_LEN` (25), `MIN_PART_LEN_DASH` (35),
`MAX_PARTS` (3) in `claims.py`; `_COLOC_W` (8), `_COLOC_MIN` (5),
`_FUNC_WORDS` und `_SPAN_FUZZ` (0,6) in `pipeline.py`.

Beim Kalibrieren gilt: Solange nur gegen Einzelbeispiele getestet wird,
ist jede Schwellenänderung Raten. Ein Gold-Set von 30–50 selbst markierten
Paaren ist die Voraussetzung für sinnvolles Tuning.

---

## 6. Bekannte Grenzen

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
