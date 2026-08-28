"""
Entscheidungsbausteine je Claim: Primärzuordnung, Margin, Confidence.

Reine Funktionen über der fusionierten Matrix — hier wird nichts mehr
gemessen, nur noch entschieden und begründet. Die Reihenfolge der Notizen
und Flags ist Teil des Ausgabevertrags; der Orchestrator ruft die drei
Funktionen exakt in der dokumentierten Abfolge auf.
"""
from __future__ import annotations

from konfig import CFG
from kern.lexik import _covered_weight, _pmean
from kern.segmentierung import Sent


def primaerzuordnung(row: list[float], order: list[int],
                     art_sents: list[Sent]
                     ) -> tuple[str, list[int], list[int], float, bool,
                                list[str]]:
    """Erste Zuordnung auf der Einzelsatz-Rangliste.

    Rückgabe: (relation, srcs, redundant, conf, unter_schwelle, notes).
    `conf` ist nur bei `keine_quelle` endgültig — bei belegten Claims
    wird sie später aus der Abdeckung gesetzt.
    """
    s1, si1 = row[order[0]], order[0]
    notes: list[str] = []
    redundant: list[int] = []
    unter_schwelle = False
    if s1 >= CFG["t_direct"]:
        relation = "direkt"
        srcs = [si1]
        for si in order[1:]:
            if row[si] >= max(CFG["t_direct"], s1 - CFG["redundant_delta"]):
                redundant.append(si)
            else:
                break
        conf = 0.0          # wird später aus der Abdeckung gesetzt
    elif s1 >= CFG["t_none"]:
        relation = "direkt"
        srcs = [si1]
        conf = 0.0          # wird später aus der Abdeckung gesetzt
        unter_schwelle = True
    else:
        relation = "keine_quelle"
        srcs = []
        # Der Wert misst hier etwas ANDERES als bei belegten Claims:
        # nicht „so gut ist der Beleg", sondern „so sicher gibt es
        # keinen". Je weiter der beste Kandidat unter `t_none` liegt,
        # desto höher. Beides in derselben Leiste anzuzeigen ist
        # irreführend — die Oberfläche beschriftet das Feld deshalb
        # abhängig von der Relation um.
        conf = round(min(0.97, 0.55 + (CFG["t_none"] - s1) * 2.2), 2)
        # Der knapp gescheiterte Kandidat gehört genannt. Ein Claim mit
        # top 0,44 bei einer Schwelle von 0,44 ist etwas völlig anderes
        # als einer mit 0,20 — im ersten Fall lohnt der Blick auf den
        # Satz, im zweiten nicht. Ohne diese Angabe steht in beiden
        # Fällen nur „keine ausreichend ähnliche Stelle".
        if s1 >= CFG["t_none"] * CFG["knapp_faktor"]:
            notes.append(
                "Keine ausreichend ähnliche Stelle im Artikel — "
                f"nächster Kandidat {art_sents[si1].id} mit "
                + f"{s1:.2f}".replace(".", ",")
                + " (Schwelle " + f"{CFG['t_none']:.2f}".replace(".", ",")
                + ").")
        else:
            notes.append(
                "Keine ausreichend ähnliche Stelle im Artikel.")
    return relation, srcs, redundant, conf, unter_schwelle, notes


def margin_nach_aggregation(row: list[float], srcs: list[int],
                            n: int) -> float:
    """Margin NACH der Aggregation neu bestimmen.

    Vorher wurde Platz 1 gegen Platz 2 der Einzelsatz-Rangliste
    gemessen. Bei einer Verdichtung ist Platz 2 aber regelmäßig die
    zweite Quelle selbst — die Margin fiel also genau dann auf ~0,
    wenn die Aggregation gut funktionierte, und dämpfte über
    `conf_margin_ref` zusätzlich die Confidence. Mehr Belege zu
    finden machte das System unsicherer. Gemeint war immer: Wie klar
    hebt sich das Gewählte vom Nichtgewählten ab?
    """
    uebrig = [row[si] for si in range(n) if si not in srcs]
    return round(max(max(row[si] for si in srcs)
                     - (max(uebrig) if uebrig else 0.0), 0.0), 2)


def confidence_und_notizen(claim_cvec: dict[str, float],
                           art_cgrams: list[set[str]],
                           emb_zeile: list[float] | None,
                           srcs: list[int], margin: float,
                           unter_schwelle: bool
                           ) -> tuple[float, float, list[str], list[str]]:
    """Confidence aus zwei unabhängigen Signalen.

    Nicht der Mittelwert (ein starkes Signal würde heruntergezogen)
    und kein logisches Oder (zwei mittelmäßige lägen fälschlich im
    sicheren Bereich), sondern das Potenzmittel dazwischen.

    Rückgabe: (conf, cov_total, flags, notes).
    """
    union: set[str] = set()
    for si in srcs:
        union |= art_cgrams[si]
    cov_total = _covered_weight(claim_cvec, union)
    # Embedding-Signal über alle Fundstellen, nicht nur den besten
    # Einzelsatz: Bei einer Verdichtung ähnelt definitionsgemäß
    # kein einzelner Satz dem ganzen Claim, und das schlechteste
    # Glied zog die Confidence nach unten.
    emb_sig = (max(emb_zeile[si] for si in srcs)
               if emb_zeile is not None else None)
    core = _pmean([cov_total, emb_sig], CFG["conf_power"])
    core *= 0.85 + 0.15 * min(1.0, margin / CFG["conf_margin_ref"])
    conf = round(min(0.98, max(0.05, core)), 2)
    flags: list[str] = []
    notes: list[str] = [
        f"Fundstellen erklären {cov_total:.0%}".replace("%", " %")
        + " des Claims."]
    # Der Prüfhinweis gilt dem Ergebnis, nicht dem Zwischenstand:
    # Wenn die Verdichtung den Claim am Ende gut erklärt, war der
    # schwache Einzeltreffer kein Mangel, sondern der Normalfall
    # einer Zusammenfassung.
    if unter_schwelle and cov_total < CFG["agg_cov_ok"]:
        notes.append(
            "Unter der Direkt-Schwelle — zur Prüfung empfohlen.")
    if emb_sig is not None and abs(cov_total - emb_sig) > CFG["dissens_delta"]:
        flags.append("signale_uneinig")
        traeger = "der Wortlaut" if cov_total > emb_sig else "die Bedeutung"
        notes.append(
            f"Signale uneinig — nur {traeger} stützt die Zuordnung.")
    return conf, cov_total, flags, notes
