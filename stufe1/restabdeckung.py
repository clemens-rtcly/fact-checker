"""
Stufe 1.5 — Restabdeckung: Verdichtungen über mehrere Fundstellen.

Nicht „ähnelt Satz X dem Claim?", sondern „erklärt Satz X etwas, das noch
keine Fundstelle erklärt?". Ein Member einer Verdichtung trägt
definitionsgemäß nur einen Teil bei und wäre an einer Ähnlichkeitsschwelle
gegen den ganzen Claim gescheitert.

Hier greifen drei der Varianten-Aushänge (konfig.VARIANTE): `gewinn`
formt den Restbeitrag, `max_quellen` die Obergrenze, `zusatzquellen`
ergänzt nach der gierigen Auswahl.
"""
from __future__ import annotations

import konfig
from konfig import CFG
from kern.lexik import _ngrams, _prep
from kern.segmentierung import Sent
from stufe1.abdeckung import Lexikalisch


def residual_gain(lexi: Lexikalisch, ci: int, c_text: str,
                  art_sents: list[Sent], chosen: list[int], cand: int,
                  min_traeger: int | None = None) -> float:
    """Anteil des Claims, den `cand` zusätzlich zu `chosen` erklärt.

    Dieselbe Rechnung wie das A aus `_coverage_score`, nur mit den
    bereits erklärten n-Grammen als Ausschluss.

    Zusätzlich muss der Beitrag von mindestens `residual_min_carriers`
    verschiedenen Inhaltswörtern getragen werden. Gemessen: echte
    Verdichtungen werden von zwei bis sieben Wörtern getragen — meist
    Eigennamen, Zahlen oder Sachbegriffe. Scheinbelege hängen dagegen
    an einem einzigen Wort. Einzelne Zahlen-Anker fallen dadurch nicht
    durchs Raster: für die gibt es den eigenen Pfad über
    `stufe0.anker.komplementaere`.
    """
    # Asymmetrisch, und zwar mit Absicht:
    #   bereits erklärt  -> ANGEREICHERTE Sicht. Was der Sprecherkontext
    #       einer Fundstelle abdeckt, gilt als erklärt; sonst holt ein
    #       ferner Satz Punkte für einen Namen, den der Block ohnehin
    #       trägt (gemessen: s39 rutschte so zu c11 hinein).
    #   Zusatzbeitrag   -> ROHE Sicht. Ein geerbter Kontext ist per
    #       Definition nichts Neues; er ist ja mit dem ganzen Block
    #       geteilt. Zählte er als Beitrag, würde jeder weitere Satz
    #       desselben Zitats als Verdichtung erscheinen (gemessen:
    #       s34 und s36 drängten sich so zu c19).
    covered: set[str] = set()
    for si in chosen:
        covered |= lexi.art_cgrams_a[si]
    rest = {g: w for g, w in lexi.claim_cvecs[ci].items()
            if g not in covered and g in lexi.art_cgrams[cand]}
    if not rest:
        return 0.0
    total = sum(lexi.claim_cvecs[ci].values()) or 1.0
    gewinn = sum(rest.values()) / total

    traeger = 0
    for w, _p in lexi.claim_ctoks[ci]:
        wg = set(_ngrams(_prep(w)))
        if wg and sum(v for g, v in rest.items() if g in wg) / total > 0.01:
            traeger += 1
            if traeger >= (CFG["residual_min_carriers"]
                           if min_traeger is None else min_traeger):
                formen = konfig.VARIANTE.get("gewinn")
                return (gewinn if formen is None
                        else formen(gewinn, art_sents[cand].text, c_text))
    return 0.0


def verdichte(lexi: Lexikalisch, ci: int, c_text: str,
              art_sents: list[Sent], srcs: list[int], redundant: list[int],
              ist_frage: list[bool],
              emb_zeile: list[float] | None) -> list[tuple[int, float]]:
    """Gierige Quellenwahl nach Restbeitrag; erweitert `srcs` in place.

    Rückgabe sind die `gains` [(satzindex, beitrag), …] für die Notiz.
    """
    n = len(art_sents)
    gains: list[tuple[int, float]] = []

    def schwelle(si: int) -> float:
        """Nötiger Restbeitrag, abhängig vom Abstand zur nächsten
        bereits gewählten Fundstelle.

        Gemessen an einem realen Paar (21 Claims): Die fehlenden
        zweiten Quellen lagen im Abstand 1 bis 2, die fälschlich
        aufgenommenen im Abstand 8 bis 20. Verdichtung führt in
        Nachrichtentexten fast immer benachbarte Sätze zusammen —
        ein Zitat und seine Fortsetzung, eine Aussage und ihre
        Einordnung. Ein Satz aus einem ganz anderen Abschnitt
        erklärt selten wirklich etwas; meist teilt er nur ein
        Allerweltswort („verzeichnen", „besonders", „Kreis").

        Der Abstand ist also ein Prior auf die Wahrscheinlichkeit,
        dass es sich um eine echte Verdichtung handelt — deshalb
        niedrigere Hürde in der Nachbarschaft, höhere in der Ferne.
        """
        # Redundante Fundstellen zählen für den Abstand mit.
        # Sie werden dem Nutzer angezeigt und stehen in der
        # NLI-Prämisse — ein Satz, der gut genug für beides ist,
        # besetzt auch eine Position in der Nachbarschaft. Ohne
        # sie hing das Ergebnis daran, ob ein Satz als zweite
        # Quelle oder als redundant eingestuft wurde: Bei c12 des
        # Aachen-Paars war der Restbeitrag von s61 in beiden
        # Fällen 0,191 — nur der Abstand kippte von 2 (nah,
        # Schwelle 0,10) auf 3 (fern, Schwelle 0,22), weil s63
        # einmal als Quelle und einmal als redundant galt.
        nachbarn = list(srcs) + list(redundant)
        d = min((abs(si - s) for s in nachbarn), default=99)
        if d <= CFG["residual_nah_abstand"]:
            return CFG["residual_min_nah"]
        return CFG["residual_min_fern"]

    grenze = CFG["residual_max_sources"]
    if konfig.VARIANTE.get("max_quellen"):
        grenze = konfig.VARIANTE["max_quellen"](c_text, grenze)
    while len(srcs) < grenze:
        # In der Nachbarschaft genügt ein einziges Trägerwort: Die
        # Fortsetzung eines Zitats steuert oft genau einen Begriff
        # bei („… sie blieben konstant" -> „Die sind bei uns
        # konstant"). In der Ferne bleibt es bei der strengeren
        # Regel, die Scheinbelege an Allerweltswörtern abfängt.
        #
        # Fragesätze auch hier aussortieren. Der Abschlag in
        # `fusion` hält sie von Platz 1 fern, die Restabdeckung
        # sah sie aber weiter — und weil eine Teaserfrage das
        # Themenvokabular des ganzen Textes trägt, erklärt sie
        # scheinbar immer noch etwas. Ein Fragesatz kann nie Beleg
        # sein, weder als erste noch als zweite Quelle.
        cands = [(si, residual_gain(
                      lexi, ci, c_text, art_sents, srcs, si,
                      min_traeger=1 if min(
                          (abs(si - s) for s in srcs), default=99)
                          <= CFG["residual_nah_abstand"] else None))
                 for si in range(n)
                 if si not in srcs and si not in redundant
                 and not ist_frage[si]]
        cands = [(si, g) for si, g in cands if g >= schwelle(si)]
        if not cands:
            break
        best_si, best_gain = max(cands, key=lambda t: t[1])
        srcs.append(best_si)
        gains.append((best_si, best_gain))

    zusatz_fn = konfig.VARIANTE.get("zusatzquellen")
    if zusatz_fn and len(srcs) < grenze:
        for si in zusatz_fn(c_text, [a.text for a in art_sents],
                            list(srcs), emb_zeile, grenze - len(srcs)):
            if si not in srcs and si not in redundant:
                srcs.append(si)
                gains.append((si, 0.0))
    return gains
