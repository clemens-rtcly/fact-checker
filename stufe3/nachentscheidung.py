"""
Stufe 3 — NLI-Nachentscheidung über den fertigen Claims.

Prämisse = Überschrift + Vorspann + tragende Fundstellen; Hypothese =
Claim. Drei Ausgänge:

  contradiction dominant  -> Flag `nli_widerspruch` (Relation bleibt —
                             der Link ist richtig, der Inhalt kollidiert;
                             gleiche Semantik wie beim Zahlkonflikt)
  neutral dominant und    -> Relation `bedeutung_verschoben`: richtige
  Entailment unter der       Stelle, Aussage leicht verschoben („es
  Schwelle                   könnte" -> „es kam"). Penn-Studie: 18 von
                             159 Links — gut jeder zehnte.
  sonst                   -> nur Score, keine Änderung

Nicht herabgestuft wird bei Teilaussagen mit offenem Rückverweis
(`geschuetzt`, siehe stufe3/praemisse.py) und bei bereits gemeldetem
Zahlkonflikt — das harte Signal hat Vorrang, ein zweiter Status auf
demselben Befund wäre Doppelmeldung.
"""
from __future__ import annotations

from konfig import CFG
from stufe3.praemisse import _negation_asymmetry


def anwenden(claims_json: list[dict],
             nli_jobs: list[tuple[int, str, str, bool, str]],
             nli_fn) -> None:
    """NLI in EINEM Batch laufen lassen und Urteile eintragen (in place)."""
    if not nli_jobs:
        return
    probs = nli_fn([(p, h) for _idx, p, h, _g, _q in nli_jobs])
    for (idx, _p, _h, geschuetzt, quelltext), pr in zip(nli_jobs, probs):
        cj = claims_json[idx]
        ent, neu, con = (pr["entailment"], pr["neutral"],
                         pr["contradiction"])
        cj["scores"]["nli"] = round(ent, 3)
        zusatz: list[str] = []
        # Neben der Schwelle ein echter Abstand zu entailment. Ein
        # bloßes `con > ent` wäre wirkungslos: Bei con ≥ 0,55 ist ent
        # zwangsläufig ≤ 0,45, die Bedingung also immer erfüllt.
        if (con >= CFG["nli_contra_min"]
                and con - ent >= CFG["nli_contra_margin"]):
            # Zweite Meinung verlangen. Gemessener Fehlermodus: Wechselt
            # ein BILDHAFTER Ausdruck die grammatische Form (Kopulasatz
            # <-> Prädikatsnomen, „das ist ein wunder Punkt" ->
            # „spricht von einem wunden Punkt"), meldet das Modell mit
            # ~0,95 Sicherheit einen Widerspruch, wo eine korrekte
            # Verdichtung steht. Sachliche Nominalisierungen sind davon
            # nicht betroffen (gemessen: 0 von 8).
            #
            # Deshalb wird der rote Chip nur vergeben, wenn das Urteil
            # unabhängig gestützt ist — durch eine Negationsasymmetrie
            # oder dadurch, dass lex/emb den Claim ohnehin nicht klar
            # tragen. Ein Claim mit sehr hoher Wortlaut- UND
            # Bedeutungsübereinstimmung, in dem nichts verneint wird,
            # ist mit hoher Wahrscheinlichkeit korrekt verdichtet.
            if (_negation_asymmetry(quelltext, _h)
                    or cj["scores"]["top"] < CFG["nli_contra_support_max"]):
                cj["flags"].append("nli_widerspruch")
                zusatz.append("NLI: Fundstelle widerspricht dem Claim "
                              f"(contradiction {con:.2f}).")
            else:
                # Nicht verschweigen, aber auch nicht als Widerspruch
                # ausrufen: Der Befund landet bei den uneinigen Signalen.
                if "signale_uneinig" not in cj["flags"]:
                    cj["flags"].append("signale_uneinig")
                zusatz.append(
                    f"NLI meldet Widerspruch (contradiction {con:.2f}), "
                    "Wortlaut und Bedeutung stützen den Claim aber "
                    "stark und es wird nichts verneint — nicht als "
                    "Widerspruch gemeldet, siehe Signale uneinig.")
        elif ent < CFG["nli_entail_min"] and neu >= ent and neu >= con:
            if "zahlkonflikt" in cj["flags"]:
                pass                        # hartes Signal hat Vorrang
            elif geschuetzt:
                zusatz.append(
                    "NLI unter der Entailment-Schwelle "
                    f"({ent:.2f}), aber Teilaussage mit Rückverweis — "
                    "nicht herabgestuft.")
            else:
                cj["relation"] = "bedeutung_verschoben"
                cj["flags"].append("bedeutung_verschoben")
                zusatz.append(
                    "Bedeutung verschoben — die Fundstelle widerspricht "
                    "dem Claim nicht, stützt ihn aber auch nicht "
                    f"vollständig (entailment {ent:.2f}, "
                    f"neutral {neu:.2f}).")
        # ---------------- Widerspruch bei Wortgleichheit
        # Unabhängig von der Verzweigung oben und ohne Einfluss auf die
        # Relation — deshalb ein eigenes `if` statt eines weiteren
        # `elif`. Die Logik ist der Safeguard genau entgegengesetzt und
        # das mit Absicht: Hohe lexikalische Stützung entschärft dort
        # den Widerspruch, weil ein bildhafter Formwechsel dahinter
        # stehen kann. Bei Wortgleichheit gibt es keinen Formwechsel —
        # dann muss der Widerspruch in der Differenz sitzen, und die
        # ist klein und benennbar. Vorerst nur Zählmaterial: Wie oft
        # feuert die Kombination auf dem Gold-Set, und wie oft zu
        # Recht? Erst danach ist ein eigener Status begründbar.
        lexw = (cj["scores"] or {}).get("lex")
        if (con >= CFG["nli_wortgleich_contra"] and lexw is not None
                and lexw >= CFG["nli_wortgleich_lex"]):
            if "widerspruch_wortgleich" not in cj["flags"]:
                cj["flags"].append("widerspruch_wortgleich")
            zusatz.append(
                f"Widerspruch bei Wortgleichheit: contradiction {con:.2f} "
                f"bei lex {lexw:.2f} — die Abweichung muss in dem "
                "wenigen liegen, das sich unterscheidet (siehe Wortlaut).")
        if zusatz:
            cj["note"] = " · ".join(
                ([cj["note"]] if cj["note"] else []) + zusatz)
