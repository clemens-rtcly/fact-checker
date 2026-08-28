"""
Stufe 3 — Prämissenbau und Auftragssammlung für die NLI-Prüfung.

Die Prämissenkonstruktion ist wichtiger als die Modellwahl: Der
Cross-Encoder kann nur auflösen, was in seiner Eingabe steht. Gelaufen
wird erst nach der Claim-Schleife, damit alle Paare in EINEM Batch durchs
Modell gehen (stufe3/nachentscheidung.py).
"""
from __future__ import annotations

import re

from kern.segmentierung import Sent
from stufe0.zahlen import normalize_numbers
from stufe1 import teilaussagen

_NEGATION = re.compile(
    r"\b(nicht|nichts|kein\w*|nie|niemals|niemand|ohne|weder|kaum|"
    r"nirgend\w*|aufgehoben|abgesagt|gestrichen)\b", re.I)


def _negation_asymmetry(premise: str, hypothesis: str) -> bool:
    """True, wenn Negation nur auf EINER Seite steht.

    Der weitaus häufigste echte Widerspruch entsteht durch Negation:
    „Der Turm wird verkleidet" gegen „Der Turm wird nicht verkleidet".
    Solche Paare haben naturgemäß fast identischen Wortlaut — lex und emb
    stützen also stark, obwohl der Inhalt kollidiert. Ohne diese Prüfung
    würde die Stützungsregel in der Nachentscheidung ausgerechnet die
    Fälle unterdrücken, für die der Widerspruchs-Chip existiert.

    Bewusst grob: Es geht nicht um korrekte Skopusanalyse, sondern um die
    Frage, ob es überhaupt einen Anhaltspunkt für eine Verneinung gibt,
    der das NLI-Urteil unabhängig stützt.
    """
    return bool(_NEGATION.search(premise)) != bool(_NEGATION.search(hypothesis))


def _nli_premise(primary: list[int], art_sents: list[Sent]) -> str:
    """Prämisse für die NLI-Prüfung eines Claims.

    Für „St. Barbara" <-> „Die Kirche in Pannesheide" liegt die
    verbindende Evidenz in der Überschrift, die Aussage aber im
    Fließtext. Deshalb werden Überschrift und erster Vorspann-Satz
    vorangestellt — in Nachrichtentexten führen sie fast immer die
    Hauptentität ein und sind billig mitzugeben. Der volle Absatz bleibt
    draußen: Er verlängert die Eingabe und könnte Entailment aus Sätzen
    liefern, auf die der Link gar nicht zeigt.

    Beide Seiten (auch die Hypothese, siehe Auftragsstelle) laufen durch
    `normalize_numbers` — die TracSum-Fehleranalyse zeigt, dass NLI-Modelle
    an unterschiedlichen Zahlschreibweisen scheitern („zwölf Millionen"
    vs. „12 Millionen"); nach der Normalisierung sind übereinstimmende
    Werte zeichengleich.
    """
    # Kopf = die Überschriften vor der ersten Fundstelle plus der erste
    # Fließtextsatz. Überschriften führen die Hauptentität ein („St.
    # Barbara"), der erste Satz nennt sie meist ausgeschrieben. Früher
    # hingen beide an der Absatzposition; jetzt an der Auszeichnung, und
    # gibt es keine Überschrift, entfällt sie einfach.
    kopf: list[int] = []
    grenze = min(primary) if primary else len(art_sents)
    for si, s in enumerate(art_sents):
        if si >= grenze:
            break
        if s.block == "heading":
            kopf.append(si)
    for si, s in enumerate(art_sents):
        if s.block == "body":
            kopf.append(si)
            break
    reihenfolge = sorted(set(kopf) | set(primary))
    return " ".join(normalize_numbers(art_sents[si].text)
                    for si in reihenfolge)


def auftrag(claim_index: int, c: Sent, srcs: list[int],
            art_sents: list[Sent]) -> tuple[int, str, str, bool, str]:
    """NLI-Auftrag für einen belegten Claim zusammenstellen.

    Rückgabe: (Index, Prämisse, Hypothese, Downgrade-Schutz, Quelltext).
    """
    # Downgrade-Schutz nur für Teilaussagen mit Rückverweis: Einem
    # Fragment wie „deshalb müsse es ohne sie gehen" fehlt der Bezug
    # in der Prämisse, Neutral wäre dort ein Artefakt. Auf ganze
    # Sätze angewandt würde derselbe Schutz aber fast alles blocken
    # — has_anaphor kennt auch „es", und „Es kam zu einer
    # Geruchsbelästigung" ist genau der Fall, den die Stufe finden
    # soll (expletives „es", kein Rückverweis).
    geschuetzt = c.part and teilaussagen.has_anaphor(c.text)
    # Für die Negationsprüfung nur die tragenden Fundstellen, nicht
    # die ganze Prämisse: Überschrift und Vorspann bringen häufig
    # sachfremde Verneinungen mit („finden keine Auszubildenden"),
    # die eine Asymmetrie vortäuschen würden, die mit dem Claim
    # nichts zu tun hat.
    quelltext = " ".join(art_sents[si].text for si in sorted(set(srcs)))
    # Redundante Fundstellen gehören in die Prämisse. Sie sind
    # „redundant" nur im Sinne der Anzeige — inhaltlich sind es
    # Sätze, die fast so gut passen wie der Primärtreffer, und
    # nicht selten stehen genau dort die tragenden Worte. Gemessen
    # an einem realen Paar: Zweimal war der wörtliche Beleg
    # („Wir sind komplett ausgebucht", „Das ist bei uns immer so")
    # als redundant eingestuft und fehlte damit in der Prämisse —
    # das NLI meldete folgerichtig neutral, und der Claim wurde als
    # „Bedeutung verschoben" markiert, obwohl der Beleg im Artikel
    # steht und sogar verlinkt war.
    nli_quellen = sorted(set(srcs))
    return (claim_index, _nli_premise(nli_quellen, art_sents),
            normalize_numbers(c.text), geschuetzt, quelltext)
