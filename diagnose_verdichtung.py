# -*- coding: utf-8 -*-
"""Diagnose Stufe 1.5: Wie gut trifft die Verdichtung — und wovon hängt es ab?

Wertet vorhandene Gold- und Laufdateien aus, rechnet nichts neu, lädt kein
Modell. Die Ablation hat gezeigt, dass die Primärzuordnung fast nie falsch
liegt (CIP 0,991 ohne Stufe 1.5) und die gesamte Präzisionslast an den
verdichteten Fundstellen hängt. Dieses Skript zerlegt genau diese Menge.

Drei Fragen:

  1. Trefferquote je Gewinnband — steigt sie monoton mit dem Restbeitrag?
     Nur dann ist eine Schwelle überhaupt das richtige Instrument.
  2. Trefferquote nah gegen fern — trägt der Abstands-Prior wirklich?
  3. Wäre der Gewinn RELATIV zum noch ungedeckten Rest das bessere
     Kriterium als der Gewinn absolut zum Gesamtgewicht des Claims?

Dazu eine Schwellensimulation: Was würde ein anderer Wert wegwerfen, was
behalten — getrennt nach richtigen und falschen Fundstellen.

Datenquelle sind die Notizen im Lauf-JSON („s5 erklärt zusätzlich 19 %",
„Fundstellen erklären 87 % des Claims."). Sie sind auf ganze Prozent
gerundet; für Bänder reicht das, für Nachkommastellen nicht.

Aufruf (PowerShell):

    python diagnose_verdichtung.py "gold\\*.json" --lauf "laeufe\\voll\\*.json"
    python diagnose_verdichtung.py "gold\\*.json" --lauf "laeufe\\voll\\*.json" --liste
    python diagnose_verdichtung.py "gold\\*.json" --lauf "laeufe\\voll\\*.json" --test
"""
from __future__ import annotations

import glob
import json
import re
import sys

import eval as E

_GEWINN = re.compile(r"\b(s\d+) erklärt zusätzlich (\d+) %")
_ANKER = re.compile(r"Zahlen-Anker in ([^).;·]+)")
_VERDICHTET = re.compile(r"Verdichtet aus ([^(.·]+)")
_GESAMT = re.compile(r"Fundstellen erklären (\d+) % des Claims")
_SATZ = re.compile(r"s\d+")

# Bänder für den absoluten Gewinn. Die Grenzen liegen um die beiden
# Schwellen herum (residual_min_nah 0,10 / residual_min_fern 0,22),
# damit sichtbar wird, was direkt oberhalb von ihnen passiert.
_BAENDER = [(0.00, 0.12), (0.12, 0.16), (0.16, 0.20), (0.20, 0.25),
            (0.25, 0.35), (0.35, 1.01)]
# Bänder für den relativen Gewinn (Anteil am noch ungedeckten Rest).
_REL_BAENDER = [(0.00, 0.20), (0.20, 0.35), (0.35, 0.50), (0.50, 0.70),
                (0.70, 1.01)]


def _lade(muster: str) -> list[dict]:
    out = []
    for p in sorted(glob.glob(muster)):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def _zerlege_note(note: str) -> tuple[list[str], list[tuple[str, float]],
                                      list[str], float | None]:
    """(Quellen in Auswahlreihenfolge, [(id, gewinn)], Anker-Ids, cov_total)."""
    reihenfolge: list[str] = []
    m = _VERDICHTET.search(note)
    if m:
        reihenfolge = _SATZ.findall(m.group(1))
    gewinne = [(sid, int(pz) / 100.0) for sid, pz in _GEWINN.findall(note)]
    anker: list[str] = []
    for m in _ANKER.finditer(note):
        anker += _SATZ.findall(m.group(1))
    mg = _GESAMT.search(note)
    cov = int(mg.group(1)) / 100.0 if mg else None
    return reihenfolge, gewinne, anker, cov


def _nr(sid: str) -> int:
    return int(sid[1:])


def _klasse(sid: str, notwendig: set[str], erlaubt: set[str]) -> str:
    if sid in notwendig:
        return "notwendig"
    if sid in erlaubt:
        return "zulaessig"
    return "falsch"


def sammle(golds: dict, nach_hash: dict) -> tuple[list[dict], dict]:
    """Alle verdichteten Fundstellen mit ihren Merkmalen einsammeln."""
    posten: list[dict] = []
    referenz = {"primaer": 0, "primaer_falsch": 0,
                "anker": 0, "anker_falsch": 0,
                "redundant": 0, "redundant_falsch": 0,
                "ohne_lauf": []}

    for paar, gold in sorted(golds.items()):
        d = nach_hash.get(gold.get("transkript_hash", ""))
        if d is None:
            referenz["ohne_lauf"].append(paar)
            continue

        for c in d["transcript"]["claims"]:
            i = E._satz_index(c.get("start"), gold["eintraege"])
            if i is None:
                continue
            e = gold["eintraege"][i]
            if not e.get("geprueft"):
                continue
            notwendig = set(e.get("notwendig") or [])
            erlaubt = notwendig | set(e.get("zulaessig") or [])
            if not notwendig:
                continue          # Gold sagt „unbelegt" — kein Maßstab

            quellen = c.get("sources") or []
            redundant = [q["sentence"] for q in quellen
                         if q.get("role") == "redundant"]
            reihenfolge, gewinne, anker, cov_ges = _zerlege_note(
                c.get("note") or "")
            gewinn_ids = [sid for sid, _g in gewinne]

            # Primärquelle: erste in der Verdichtungsliste, sonst die
            # einzige nicht-redundante Fundstelle.
            if reihenfolge:
                primaer = reihenfolge[0]
            else:
                rest = [q["sentence"] for q in quellen
                        if q.get("role") != "redundant"]
                primaer = rest[0] if rest else None
            if primaer:
                referenz["primaer"] += 1
                if _klasse(primaer, notwendig, erlaubt) == "falsch":
                    referenz["primaer_falsch"] += 1
            for sid in redundant:
                referenz["redundant"] += 1
                if _klasse(sid, notwendig, erlaubt) == "falsch":
                    referenz["redundant_falsch"] += 1
            for sid in anker:
                if sid in gewinn_ids:
                    continue
                referenz["anker"] += 1
                if _klasse(sid, notwendig, erlaubt) == "falsch":
                    referenz["anker_falsch"] += 1

            if not gewinne or primaer is None:
                continue

            # Abdeckung vor der ersten Ergänzung: Gesamtabdeckung minus
            # der Summe aller Restbeiträge. Die Gewinne sind marginal und
            # in Auswahlreihenfolge, deshalb ist die Rückrechnung
            # zulässig — bis auf die Rundung auf ganze Prozent.
            cov_vor = (cov_ges - sum(g for _s, g in gewinne)
                       if cov_ges is not None else None)
            nachbarn = [_nr(primaer)] + [_nr(s) for s in redundant]

            for schritt, (sid, gewinn) in enumerate(gewinne):
                d_min = min((abs(_nr(sid) - x) for x in nachbarn), default=99)
                rest_vor = (max(0.0, 1.0 - cov_vor)
                            if cov_vor is not None else None)
                relativ = (gewinn / rest_vor
                           if rest_vor and rest_vor > 0.01 else None)
                posten.append({
                    "paar": paar, "claim": c["id"], "satz": i,
                    "quelle": sid, "gewinn": gewinn, "abstand": d_min,
                    "schritt": schritt + 1,
                    "rest_vor": rest_vor, "relativ": relativ,
                    "klasse": _klasse(sid, notwendig, erlaubt),
                    "text": c["text"],
                })
                nachbarn.append(_nr(sid))
                if cov_vor is not None:
                    cov_vor += gewinn
    return posten, referenz


def _quote(gruppe: list[dict]) -> tuple[int, int, int, float]:
    n = len(gruppe)
    notw = sum(1 for p in gruppe if p["klasse"] == "notwendig")
    fal = sum(1 for p in gruppe if p["klasse"] == "falsch")
    return n, notw, fal, (n - fal) / n if n else 0.0


def _tabelle(titel: str, zeilen: list[tuple[str, list[dict]]]) -> None:
    print(f"\n{titel}")
    print(f"  {'Band':<16}{'n':>5}{'notw.':>7}{'zul.':>6}{'falsch':>8}"
          f"{'Trefferquote':>14}")
    print("  " + "-" * 56)
    for name, gruppe in zeilen:
        n, notw, fal, q = _quote(gruppe)
        zul = n - notw - fal
        if not n:
            print(f"  {name:<16}{0:>5}{'—':>7}{'—':>6}{'—':>8}{'—':>14}")
            continue
        print(f"  {name:<16}{n:>5}{notw:>7}{zul:>6}{fal:>8}{q:>13.0%}")


def _simuliere(posten: list[dict], schluessel: str,
               werte: list[float], titel: str) -> None:
    brauchbar = [p for p in posten if p[schluessel] is not None]
    if not brauchbar:
        print(f"\n{titel}\n  (keine Daten — fehlt die Abdeckungsnotiz?)")
        return
    print(f"\n{titel}")
    print(f"  {'Schwelle':<10}{'behalten':>10}{'davon falsch':>14}"
          f"{'verworfen':>11}{'davon richtig':>15}{'CIP*':>8}")
    print("  " + "-" * 68)
    for w in werte:
        behalten = [p for p in brauchbar if p[schluessel] >= w]
        verworfen = [p for p in brauchbar if p[schluessel] < w]
        b_fal = sum(1 for p in behalten if p["klasse"] == "falsch")
        v_richtig = sum(1 for p in verworfen if p["klasse"] != "falsch")
        cip = (len(behalten) - b_fal) / len(behalten) if behalten else 1.0
        print(f"  {w:<10.2f}{len(behalten):>10}{b_fal:>14}"
              f"{len(verworfen):>11}{v_richtig:>15}{cip:>7.0%}")
    print("  * CIP nur über die verdichteten Fundstellen, nicht über den Lauf.")
    print("  Näherung erster Ordnung: Fällt eine frühe Ergänzung weg,\n"
          "  ändern sich für die späteren Abstand und Rest.")


def main(argv: list[str]) -> int:
    if not argv or "--hilfe" in argv or "-h" in argv:
        print(__doc__)
        return 0
    split = "test" if "--test" in argv else "dev"
    zeige_liste = "--liste" in argv
    argv = [a for a in argv if a not in ("--test", "--liste")]
    if "--lauf" not in argv:
        print("[!] --lauf <muster> fehlt", file=sys.stderr)
        return 1
    k = argv.index("--lauf")
    lauf_muster = argv[k + 1]
    gold_muster = argv[0] if k != 0 else argv[2]

    golds = {g["paar"]: g for g in _lade(gold_muster)
             if g.get("split", "dev") == split}
    if not golds:
        print(f"[!] keine Gold-Dateien im Split '{split}'", file=sys.stderr)
        return 1
    nach_hash = {}
    for d in _lade(lauf_muster):
        try:
            nach_hash[E._hash(d["transcript"]["text"])] = d
        except Exception:
            pass

    posten, ref = sammle(golds, nach_hash)
    print(f"Split '{split}' — {len(golds)} Paar(e)"
          + (f", ohne Lauf: {', '.join(ref['ohne_lauf'])}"
             if ref["ohne_lauf"] else ""))

    if not posten:
        print("\nKeine verdichteten Fundstellen gefunden. Lief der Lauf mit "
              "Stufe 1.5?")
        return 0

    # ---------------------------------------------------- Referenzwerte
    print("\nZum Vergleich — die nicht verdichteten Fundstellen:")
    for name, n_s, f_s in (("Primärquellen", "primaer", "primaer_falsch"),
                           ("redundante", "redundant", "redundant_falsch"),
                           ("Zahlen-Anker", "anker", "anker_falsch")):
        n, f = ref[n_s], ref[f_s]
        if n:
            print(f"  {name:<16}{n:>4}   davon falsch {f:>3}   "
                  f"Trefferquote {(n - f) / n:>4.0%}")

    n, notw, fal, q = _quote(posten)
    print(f"\nVerdichtete Fundstellen: {n}   notwendig {notw}   "
          f"zulässig {n - notw - fal}   falsch {fal}   Trefferquote {q:.0%}")

    # ---------------------------------------------------------- Bänder
    _tabelle("Nach absolutem Gewinn (Anteil am ganzen Claim):",
             [(f"{lo:.2f}–{hi:.2f}",
               [p for p in posten if lo <= p["gewinn"] < hi])
              for lo, hi in _BAENDER])

    _tabelle("Nach Abstand zur nächsten schon gewählten Fundstelle:",
             [("nah (≤2)", [p for p in posten if p["abstand"] <= 2]),
              ("mittel (3–7)", [p for p in posten if 3 <= p["abstand"] <= 7]),
              ("fern (≥8)", [p for p in posten if p["abstand"] >= 8])])

    _tabelle("Nach Reihenfolge der gierigen Auswahl:",
             [("2. Quelle", [p for p in posten if p["schritt"] == 1]),
              ("3. Quelle", [p for p in posten if p["schritt"] == 2]),
              ("4. und weiter", [p for p in posten if p["schritt"] >= 3])])

    mit_rel = [p for p in posten if p["relativ"] is not None]
    if mit_rel:
        _tabelle("Nach relativem Gewinn (Anteil am noch ungedeckten Rest):",
                 [(f"{lo:.2f}–{hi:.2f}",
                   [p for p in mit_rel if lo <= p["relativ"] < hi])
                  for lo, hi in _REL_BAENDER])

    # ------------------------------------------------------ Simulation
    _simuliere(posten, "gewinn", [0.10, 0.14, 0.18, 0.22, 0.26, 0.30],
               "Simulation: eine EINHEITLICHE absolute Schwelle")
    _simuliere(posten, "relativ", [0.20, 0.30, 0.40, 0.50, 0.60],
               "Simulation: eine relative Schwelle (Gewinn / Rest)")

    if zeige_liste:
        falsche = [p for p in posten if p["klasse"] == "falsch"]
        print(f"\n--- Falsche Verdichtungen ({len(falsche)})")
        for p in sorted(falsche, key=lambda x: -x["gewinn"]):
            rel = f"{p['relativ']:.2f}" if p["relativ"] is not None else "—"
            print(f"  {p['paar']} · {p['claim']} -> {p['quelle']}   "
                  f"Gewinn {p['gewinn']:.2f}   rel {rel}   "
                  f"Abstand {p['abstand']}   Schritt {p['schritt']}")
            print(f"      {p['text'][:96]}")
    else:
        print(f"\n  (`--liste` zeigt die {fal} falschen Verdichtungen "
              "einzeln)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
