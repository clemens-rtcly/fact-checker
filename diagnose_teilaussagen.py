# -*- coding: utf-8 -*-
"""Diagnose: Wie viel der Unbelegt- und Recall-Fehler geht auf Stufe 1.2?

Wertet vorhandene Gold- und Laufdateien aus — rechnet nichts neu, lädt
kein Modell, braucht keine API. Beantwortet eine einzige Frage:

    Sind die Sätze, bei denen der Lauf `keine_quelle` meldet oder
    notwendige Fundstellen verfehlt, überproportional solche, die
    Stufe 1.2 in Teilaussagen zerlegt hat?

Falls ja, liegt ein Teil des `t_none`-Befunds gar nicht an `t_none`,
sondern eine Stufe früher — und die billige Reparatur wäre die
Rückverweis-Liste (`has_anaphor`) oder `split_min_lex`, nicht die
Schwelle.

Ein Gold-Satz gilt hier als **zerlegt**, wenn der Lauf mehr als einen
Claim auf ihn abbildet. Das ist genau das, was Stufe 1.2 erzeugt.

Aufruf (PowerShell):

    python diagnose_teilaussagen.py "gold\\*.json" --lauf "laeufe\\voll\\*.json"
    python diagnose_teilaussagen.py "gold\\*.json" --lauf "laeufe\\voll\\*.json" --test
    python diagnose_teilaussagen.py "gold\\*.json" --lauf "laeufe\\voll\\*.json" --liste
"""
from __future__ import annotations

import glob
import json
import sys

import eval as E


def _lade(muster: str) -> list[dict]:
    dateien = sorted(glob.glob(muster))
    out = []
    for p in dateien:
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


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
        print(f"[!] keine Gold-Dateien im Split '{split}' gefunden",
              file=sys.stderr)
        return 1

    laeufe = {}
    for d in _lade(lauf_muster):
        name = (d.get("meta", {}).get("paar")
                or d.get("meta", {}).get("titel", ""))
        laeufe[name] = d
    # Zuordnung über den Transkript-Hash, wie in eval.py
    nach_hash = {}
    for d in laeufe.values():
        try:
            nach_hash[E._hash(d["transcript"]["text"])] = d
        except Exception:
            pass

    # Zähler: [zerlegt][kategorie]
    zahl = {True: {"saetze": 0, "kq_fp": 0, "fn": 0, "notwendig": 0,
                   "fp_quellen": 0, "quellen": 0},
            False: {"saetze": 0, "kq_fp": 0, "fn": 0, "notwendig": 0,
                    "fp_quellen": 0, "quellen": 0}}
    faelle: list[str] = []
    ohne_lauf = []

    for paar, gold in sorted(golds.items()):
        d = nach_hash.get(gold.get("transkript_hash", ""))
        if d is None:
            ohne_lauf.append(paar)
            continue
        # Claims je Gold-Satz sammeln (wie eval.lauf_auf_saetze, aber
        # ohne die Vereinigung — die Anzahl ist hier die Information)
        proSatz: dict[int, list[dict]] = {}
        for c in d["transcript"]["claims"]:
            i = E._satz_index(c.get("start"), gold["eintraege"])
            if i is not None:
                proSatz.setdefault(i, []).append(c)

        for i, e in enumerate(gold["eintraege"]):
            if not e.get("geprueft"):
                continue
            claims = proSatz.get(i, [])
            zerlegt = len(claims) > 1
            z = zahl[zerlegt]
            z["saetze"] += 1

            g_notwendig = set(e.get("notwendig") or [])
            g_erlaubt = g_notwendig | set(e.get("zulaessig") or [])
            p_quellen = set()
            for c in claims:
                for q in c.get("sources") or []:
                    p_quellen.add(q["sentence"])

            z["notwendig"] += len(g_notwendig)
            z["quellen"] += len(p_quellen)
            z["fn"] += len(g_notwendig - p_quellen)
            z["fp_quellen"] += len(p_quellen - g_erlaubt)
            if g_notwendig and not p_quellen:
                z["kq_fp"] += 1

            if zerlegt and (g_notwendig - p_quellen):
                leer = [c for c in claims if not c.get("sources")]
                faelle.append(
                    f"{paar} · Satz {i} · {len(claims)} Teile, "
                    f"{len(leer)} davon ohne Quelle · "
                    f"fehlend {sorted(g_notwendig - p_quellen)}\n"
                    + "".join(f"      [{c['relation']}] {c['text'][:88]}\n"
                              for c in claims))

    # ---------------------------------------------------------- Ausgabe
    print(f"Split '{split}' — {len(golds)} Paar(e)"
          + (f", ohne Lauf: {', '.join(ohne_lauf)}" if ohne_lauf else ""))
    print()
    kopf = f"{'':<22}{'zerlegt':>10}{'ganz':>10}"
    print(kopf)
    print("-" * len(kopf))

    def zeile(titel: str, schluessel: str) -> None:
        print(f"{titel:<22}{zahl[True][schluessel]:>10}"
              f"{zahl[False][schluessel]:>10}")

    zeile("geprüfte Sätze", "saetze")
    zeile("davon ohne Quelle*", "kq_fp")
    zeile("notwendige Quellen", "notwendig")
    zeile("davon verfehlt (FN)", "fn")
    zeile("falsche Quellen (FP)", "fp_quellen")
    print("\n  * Gold nennt notwendige Quellen, der Lauf findet keine.")

    print()
    for zerlegt, name in ((True, "zerlegt"), (False, "ganz")):
        z = zahl[zerlegt]
        if not z["saetze"]:
            continue
        cir = (z["notwendig"] - z["fn"]) / z["notwendig"] if z["notwendig"] else 0.0
        cip = ((z["quellen"] - z["fp_quellen"]) / z["quellen"]
               if z["quellen"] else 0.0)
        print(f"  {name:<8} CIR {cir:.3f}   CIP {cip:.3f}   "
              f"ohne Quelle {z['kq_fp']}/{z['saetze']} "
              f"({z['kq_fp'] / z['saetze']:.0%})")

    ges_kq = zahl[True]["kq_fp"] + zahl[False]["kq_fp"]
    ges_fn = zahl[True]["fn"] + zahl[False]["fn"]
    ges_s = zahl[True]["saetze"] + zahl[False]["saetze"]
    if ges_s:
        print(f"\n  Anteil zerlegter Sätze insgesamt: "
              f"{zahl[True]['saetze'] / ges_s:.0%}")
    if ges_kq:
        print(f"  Anteil der Unbelegt-Fehler auf zerlegten Sätzen: "
              f"{zahl[True]['kq_fp'] / ges_kq:.0%}")
    if ges_fn:
        print(f"  Anteil der verfehlten Quellen auf zerlegten Sätzen: "
              f"{zahl[True]['fn'] / ges_fn:.0%}")

    print("\n  Lesart: Liegen die letzten beiden Prozentsätze deutlich über\n"
          "  dem Anteil zerlegter Sätze, trägt Stufe 1.2 überproportional\n"
          "  zum Fehler bei — dann lohnt sich `has_anaphor`/`split_min_lex`\n"
          "  vor jeder Änderung an `t_none`.")

    if zeige_liste and faelle:
        print(f"\n--- Zerlegte Sätze mit verfehlten Quellen ({len(faelle)})")
        for f in faelle:
            print("  " + f)
    elif faelle:
        print(f"\n  ({len(faelle)} zerlegte Sätze mit verfehlten Quellen — "
              "`--liste` zeigt sie im Wortlaut)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
