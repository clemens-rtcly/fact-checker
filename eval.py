"""
Gold-Set gegen Läufe stellen: CIP/CIR/F1, Unbelegt-Erkennung, Flags.

Bewertet wird auf **Satzebene** (siehe `gold_entwurf.py`): Jeder Claim
wird auf den Transkriptsatz gemappt, in dem er liegt, die Fundstellen
aller Teil-Claims eines Satzes werden vereinigt und gegen die Annotation
gestellt. Damit überlebt das Gold-Set Änderungen an `claims.py`.

Vier Kennzahlenblöcke, bewusst getrennt:

  **Fundstellen** — CIP/CIR/F1, mikro und makro. Mikro ist die Leitzahl
  (alle Sätze gepoolt), makro mittelt pro Satz und zeigt damit, ob kurze
  Claims systematisch leiden. Richtig ist eine Fundstelle, wenn sie in
  `notwendig ∪ zulaessig` steht; für CIR zählt nur `notwendig`. Sätze
  ohne Gold-Quelle gehen mit in den CIP-Nenner — sonst wären falsch
  vergebene Quellen auf unbelegten Claims unsichtbar.

  **Unbelegt-Erkennung** — eigene 2×2-Matrix. Bei leeren Mengen bricht
  CIP/CIR zusammen, und dies ist die Zahl, an der `t_none` hängt.

  **Relationen** — Konfusionsmatrix. Zeigt, ob `bedeutung_verschoben`
  über- oder unterschießt.

  **Flags** — Präzision und Recall je Flag einzeln. Das ist die Zahl, die
  die Identifier-Prüfung, den Wortlaut-Diff und `widerspruch_wortgleich`
  rechenschaftspflichtig macht.

    python3 eval.py gold/*.json --lauf voll=laeufe/voll/*.json
    python3 eval.py gold/*.json --lauf voll=laeufe/voll/*.json --fehler
    python3 eval.py "gold/*.json" --laeufe laeufe          # alle auf einmal
    python3 eval.py gold/*.json --lauf voll=a/*.json --lauf nurlex=b/*.json
    python3 eval.py gold/*.json --lauf voll=a/*.json --test
    python3 eval.py gold/*.json --lauf voll=a/*.json --protokoll verlauf.jsonl

`--laeufe ORDNER` nimmt jeden Unterordner mit JSON-Dateien als eigenen
Lauf, benannt nach dem Ordner — ein Befehl für alle Varianten, und neue
tauchen ohne Änderung am Aufruf auf. `voll` bzw. `basis` wird nach vorn
sortiert, damit ΔF1 gegen den Basislauf gerechnet wird.

Mehrere `--lauf`-Angaben werden nebeneinander gestellt — so vergleichst du
Baselines (nur lex, nur Embeddings, volle Pipeline) und Ablationen gegen
dieselbe Annotation. `--protokoll` hängt das Ergebnis mit Zeitstempel an
eine Datei an; das ist die Regression über Zeit.

`--fehler` listet zu jeder Fehlerklasse die betroffenen Sätze mit Gold-
und Lauf-Wert auf, bei Fundstellenfehlern zusätzlich den Text der
betroffenen Artikelsätze. Aggregatzahlen sagen nicht, ob ein Fehlalarm
ein bekanntes Muster ist oder etwas Neues — dafür braucht es die Sätze
selbst. `--fehler-max N` hebt die Obergrenze je Klasse (Standard 20).

Standardmäßig wird nur `split: dev` ausgewertet. `--test` schaltet auf die
zurückgehaltene Menge um — die sieht man sich erst an, wenn man glaubt,
fertig zu sein, sonst misst das Gold-Set irgendwann nur noch sich selbst.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time

REL_RANG = ["keine_quelle", "bedeutung_verschoben", "inferiert",
            "aggregiert", "direkt"]
FLAGS = ["zahlkonflikt", "zahl_unbelegt", "ort_konflikt", "kuerzel_konflikt",
         "ident_unbelegt", "wortlaut_abweichung", "widerspruch_wortgleich",
         "bedeutung_verschoben", "nli_widerspruch"]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _satz_index(start: int | None, eintraege: list[dict]) -> int | None:
    if start is None:
        return None
    for i, e in enumerate(eintraege):
        if e["start"] <= start < e["end"]:
            return i
    davor = [i for i, e in enumerate(eintraege) if e["start"] <= start]
    return davor[-1] if davor else None


def lauf_auf_saetze(daten: dict, gold: dict) -> dict[int, dict]:
    """Pipeline-Ausgabe auf die Gold-Satzeinteilung abbilden."""
    proSatz: dict[int, dict] = {}
    for c in daten["transcript"]["claims"]:
        i = _satz_index(c.get("start"), gold["eintraege"])
        if i is None:
            continue
        eintrag = proSatz.setdefault(i, {"quellen": set(), "flags": set(),
                                         "relationen": []})
        for q in c.get("sources") or []:
            eintrag["quellen"].add(q["sentence"])
        eintrag["flags"] |= set(c.get("flags") or [])
        eintrag["relationen"].append(c["relation"])
    for e in proSatz.values():
        e["relation"] = min(
            e["relationen"],
            key=lambda r: REL_RANG.index(r) if r in REL_RANG else len(REL_RANG)
        ) if e["relationen"] else "keine_quelle"
    return proSatz


def bewerte(paare: list[tuple[dict, dict]]) -> dict:
    """`paare` sind (gold, lauf_auf_saetze)-Tupel je Textpaar."""
    tp_p = fp_p = 0                    # für CIP, mikro
    tp_r = fn_r = 0                    # für CIR, mikro
    cip_je_satz: list[float] = []
    cir_je_satz: list[float] = []
    # Unbelegt: (gold_leer, lauf_leer)
    unbelegt = {(True, True): 0, (True, False): 0,
                (False, True): 0, (False, False): 0}
    konfusion: dict[tuple[str, str], int] = {}
    flag_zahlen = {f: {"tp": 0, "fp": 0, "fn": 0} for f in FLAGS}
    ungeprueft = 0
    saetze = 0
    details: list[dict] = []

    for gold, lauf in paare:
        for i, e in enumerate(gold["eintraege"]):
            if not e.get("geprueft"):
                ungeprueft += 1
                continue
            saetze += 1
            g_notwendig = set(e.get("notwendig") or [])
            g_erlaubt = g_notwendig | set(e.get("zulaessig") or [])
            treffer = lauf.get(i, {})
            p_quellen = set(treffer.get("quellen") or ())

            richtig = p_quellen & g_erlaubt
            tp_p += len(richtig)
            fp_p += len(p_quellen - g_erlaubt)
            tp_r += len(p_quellen & g_notwendig)
            fn_r += len(g_notwendig - p_quellen)

            if p_quellen:
                cip_je_satz.append(len(richtig) / len(p_quellen))
            elif g_notwendig:
                cip_je_satz.append(0.0)
            if g_notwendig:
                cir_je_satz.append(len(p_quellen & g_notwendig)
                                   / len(g_notwendig))

            unbelegt[(not g_notwendig, not p_quellen)] += 1

            g_rel = e.get("relation", "keine_quelle")
            p_rel = treffer.get("relation", "keine_quelle")
            konfusion[(g_rel, p_rel)] = konfusion.get((g_rel, p_rel), 0) + 1

            g_flags = set(e.get("flags_erwartet") or [])
            p_flags = set(treffer.get("flags") or ())
            for f in FLAGS:
                if f in p_flags and f in g_flags:
                    flag_zahlen[f]["tp"] += 1
                elif f in p_flags:
                    flag_zahlen[f]["fp"] += 1
                elif f in g_flags:
                    flag_zahlen[f]["fn"] += 1

            details.append({
                "paar": gold.get("paar", "?"),
                "satz": e.get("satz", f"#{i}"),
                "text": e.get("text", ""),
                "artikel": {a["id"]: a["text"]
                            for a in gold.get("artikel_saetze") or []},
                "g_notwendig": g_notwendig, "g_zulaessig": set(e.get("zulaessig") or []),
                "p_quellen": p_quellen,
                "g_rel": g_rel, "p_rel": p_rel,
                "g_flags": g_flags, "p_flags": p_flags,
            })

    def quote(a, b):
        return a / b if b else 0.0

    cip = quote(tp_p, tp_p + fp_p)
    cir = quote(tp_r, tp_r + fn_r)
    f1 = quote(2 * cip * cir, cip + cir)
    cip_makro = quote(sum(cip_je_satz), len(cip_je_satz))
    cir_makro = quote(sum(cir_je_satz), len(cir_je_satz))
    f1_makro = quote(2 * cip_makro * cir_makro, cip_makro + cir_makro)
    return {
        "saetze": saetze, "ungeprueft": ungeprueft,
        "cip": cip, "cir": cir, "f1": f1,
        "cip_makro": cip_makro, "cir_makro": cir_makro, "f1_makro": f1_makro,
        "unbelegt": unbelegt, "konfusion": konfusion, "flags": flag_zahlen,
        "details": details,
    }


def _zeige(name: str, r: dict, ausfuehrlich: bool) -> None:
    print(f"\n=== {name} — {r['saetze']} geprüfte Sätze")
    if r["ungeprueft"]:
        print(f"    ({r['ungeprueft']} Einträge übersprungen: geprueft=false)")
    print(f"  mikro   CIP {r['cip']:.3f}   CIR {r['cir']:.3f}   "
          f"F1 {r['f1']:.3f}")
    print(f"  makro   CIP {r['cip_makro']:.3f}   CIR {r['cir_makro']:.3f}   "
          f"F1 {r['f1_makro']:.3f}")
    if r["cip_makro"] < r["cip"] - 0.05 or r["cir_makro"] < r["cir"] - 0.05:
        print("  Makro deutlich unter Mikro — kurze Claims mit wenigen "
              "Quellen leiden überproportional.")

    u = r["unbelegt"]
    print("\n  Unbelegt-Erkennung        Lauf: keine Quelle | Lauf: Quelle")
    print(f"    Gold: keine Quelle           {u[(True, True)]:>6}"
          f" | {u[(True, False)]:>6}")
    print(f"    Gold: Quelle                 {u[(False, True)]:>6}"
          f" | {u[(False, False)]:>6}")
    treffer = u[(True, True)]
    print(f"    Präzision {treffer / (treffer + u[(False, True)]):.3f}   "
          f"Recall {treffer / (treffer + u[(True, False)]):.3f}"
          if (treffer + u[(False, True)]) and (treffer + u[(True, False)])
          else "    (zu wenige Fälle für Präzision/Recall)")

    if ausfuehrlich:
        rel_gold = sorted({g for g, _p in r["konfusion"]})
        rel_lauf = sorted({p for _g, p in r["konfusion"]})
        if rel_gold:
            breite = max(len(x) for x in rel_gold + rel_lauf) + 2
            print("\n  Relationen (Zeile = Gold, Spalte = Lauf)")
            print("    " + "".join(x[:10].rjust(12) for x in rel_lauf)
                  .rjust(breite))
            for g in rel_gold:
                zellen = "".join(
                    str(r["konfusion"].get((g, p), 0)).rjust(12)
                    for p in rel_lauf)
                print(f"    {g:<{breite}}{zellen}")

    print("\n  Flags                      TP    FP    FN   Präz.  Recall")
    for f in FLAGS:
        z = r["flags"][f]
        if not (z["tp"] or z["fp"] or z["fn"]):
            continue
        p = z["tp"] / (z["tp"] + z["fp"]) if (z["tp"] + z["fp"]) else 0.0
        rc = z["tp"] / (z["tp"] + z["fn"]) if (z["tp"] + z["fn"]) else 0.0
        print(f"    {f:<24}{z['tp']:>4}{z['fp']:>6}{z['fn']:>6}"
              f"{p:>8.2f}{rc:>8.2f}")


def _kuerze(t: str, n: int = 72) -> str:
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _zeige_fehler(name: str, r: dict, grenze: int) -> None:
    """Die betroffenen Sätze je Fehlerklasse — Aggregatzahlen allein sagen
    nicht, ob ein Fehlalarm ein Wortbildungsfall ist oder etwas Neues."""
    d = r["details"]
    print(f"\n########## Fehler im Detail — {name}")

    def block(titel: str, eintraege: list, zeile) -> None:
        if not eintraege:
            return
        print(f"\n--- {titel} ({len(eintraege)})")
        for x in eintraege[:grenze]:
            zeile(x)
        if len(eintraege) > grenze:
            print(f"    … {len(eintraege) - grenze} weitere "
                  "(--fehler-max erhöhen)")

    # 1. Unbelegt-Fehler: die teuerste Klasse, deshalb zuerst
    block("Gold hat Quelle, Lauf sagt keine Quelle (t_none zu scharf)",
          [x for x in d if x["g_notwendig"] and not x["p_quellen"]],
          lambda x: (
              print(f"  {x['paar']}/{x['satz']}  {_kuerze(x['text'])}"),
              [print(f"      erwartet {s}: {_kuerze(x['artikel'].get(s, ''), 62)}")
               for s in sorted(x["g_notwendig"])]))

    block("Lauf vergibt Quelle, Gold sagt keine (Scheinbeleg)",
          [x for x in d if not x["g_notwendig"] and x["p_quellen"]],
          lambda x: print(f"  {x['paar']}/{x['satz']}  "
                          f"vergeben {sorted(x['p_quellen'])}  "
                          f"{_kuerze(x['text'])}"))

    # 2. Fundstellen
    block("Fehlende Fundstellen (CIR)",
          [x for x in d if x["p_quellen"] and (x["g_notwendig"] - x["p_quellen"])],
          lambda x: (
              print(f"  {x['paar']}/{x['satz']}  fehlt "
                    f"{sorted(x['g_notwendig'] - x['p_quellen'])}, "
                    f"gefunden {sorted(x['p_quellen'])}"),
              print(f"      {_kuerze(x['text'])}")))

    block("Falsche Fundstellen (CIP)",
          [x for x in d
           if x["p_quellen"] - (x["g_notwendig"] | x["g_zulaessig"])],
          lambda x: (
              print(f"  {x['paar']}/{x['satz']}  zu viel "
                    f"{sorted(x['p_quellen'] - (x['g_notwendig'] | x['g_zulaessig']))}"),
              print(f"      Claim:  {_kuerze(x['text'])}"),
              [print(f"      {s}: {_kuerze(x['artikel'].get(s, ''), 62)}")
               for s in sorted(x["p_quellen"]
                               - (x["g_notwendig"] | x["g_zulaessig"]))]))

    # 3. Relationen — harmlose Fälle abtrennen
    rel_fehler = [x for x in d if x["g_rel"] != x["p_rel"]]
    harmlos = [x for x in rel_fehler
               if x["g_rel"] == "direkt" and x["p_rel"] == "aggregiert"
               and not (x["p_quellen"] - (x["g_notwendig"] | x["g_zulaessig"]))]
    echt = [x for x in rel_fehler if x not in harmlos]
    block("Relation abweichend",
          echt,
          lambda x: print(f"  {x['paar']}/{x['satz']}  Gold {x['g_rel']} → "
                          f"Lauf {x['p_rel']}  {_kuerze(x['text'], 52)}"))
    if harmlos:
        print(f"\n--- Relation direkt→aggregiert, aber alle Quellen zulässig "
              f"({len(harmlos)})")
        print("    Kein Fundstellenfehler: Die Zusatzquelle steht in "
              "`zulaessig`, CIP zählt sie zu Recht als richtig.\n"
              "    Die Relation wird nur aus der Quellenanzahl abgeleitet "
              "und kippt deshalb mit.")

    # 4. Flags einzeln — das ist die Klasse, für die dieser Modus gebaut ist
    for f in FLAGS:
        block(f"Fehlalarm: {f}",
              [x for x in d if f in x["p_flags"] and f not in x["g_flags"]],
              lambda x: print(f"  {x['paar']}/{x['satz']}  "
                              f"{_kuerze(x['text'])}"))
    for f in FLAGS:
        block(f"Übersehen: {f}",
              [x for x in d if f in x["g_flags"] and f not in x["p_flags"]],
              lambda x: print(f"  {x['paar']}/{x['satz']}  "
                              f"{_kuerze(x['text'])}"))


def _vergleich(ergebnisse: dict[str, dict]) -> None:
    if len(ergebnisse) < 2:
        return
    print("\n=== Vergleich")
    print(f"  {'Lauf':<20}{'CIP':>7}{'ΔCIP':>8}{'CIR':>7}{'ΔCIR':>8}"
          f"{'F1':>7}{'bv-FP':>7}{'unbel.P':>9}")
    basis = None
    for name, r in ergebnisse.items():
        bv = r["flags"]["bedeutung_verschoben"]["fp"]
        u = r["unbelegt"]
        nenner = u[(True, True)] + u[(False, True)]
        up = u[(True, True)] / nenner if nenner else 0.0
        if basis is None:
            basis = r
            d_cip = d_cir = ""
        else:
            d_cip = f"{r['cip'] - basis['cip']:+.3f}"
            d_cir = f"{r['cir'] - basis['cir']:+.3f}"
        print(f"  {name:<20}{r['cip']:>7.3f}{d_cip:>8}{r['cir']:>7.3f}"
              f"{d_cir:>8}{r['f1']:>7.3f}{bv:>7}{up:>9.2f}")
    print("\n  ΔCIP/ΔCIR gegen den ersten Lauf. Bewusst getrennt: Alle "
          "Varianten tauschen\n  Präzision gegen Recall, und F1 versteckt "
          "genau diesen Tausch. Als Faustregel\n  ist eine Änderung gut, "
          "wenn ΔCIR deutlich positiv ist und ΔCIP um weniger als\n  ein "
          "Drittel davon fällt.")
    print("  bv-FP = Fehlalarme `bedeutung_verschoben`. Sie sollte mit "
          "steigendem CIR von\n  allein sinken — das ist gleichzeitig der "
          "Test, ob beide wirklich gekoppelt sind.")
    print("  unbel.P = Präzision der Unbelegt-Erkennung (an dieser Zahl "
          "hängt `t_none`).")


def main(argv: list[str]) -> int:
    laeufe: dict[str, list[str]] = {}
    protokoll = None
    # --laeufe ORDNER: jeder Unterordner mit JSON-Dateien wird ein Lauf,
    # benannt nach dem Ordner. Erspart es, für jeden Vergleich acht
    # --lauf-Angaben zu tippen; neue Varianten tauchen automatisch auf.
    while "--laeufe" in argv:
        k = argv.index("--laeufe")
        wurzel = argv[k + 1]
        del argv[k:k + 2]
        gefunden = []
        for eintrag in sorted(os.listdir(wurzel)) if os.path.isdir(wurzel) else []:
            pfad = os.path.join(wurzel, eintrag)
            if os.path.isdir(pfad) and glob.glob(os.path.join(pfad, "*.json")):
                gefunden.append((eintrag, pfad))
        if not gefunden:
            print(f"[!] {wurzel}: keine Unterordner mit JSON-Dateien.",
                  file=sys.stderr)
        # Basislauf zuerst, damit ΔF1 gegen ihn gerechnet wird.
        gefunden.sort(key=lambda x: (x[0] not in ("voll", "basis"), x[0]))
        for name, pfad in gefunden:
            laeufe.setdefault(name, []).extend(
                sorted(glob.glob(os.path.join(pfad, "*.json"))))
    while "--lauf" in argv:
        k = argv.index("--lauf")
        spec = argv[k + 1]
        del argv[k:k + 2]
        name, _, muster = spec.partition("=")
        if not muster:
            name, muster = "lauf", name
        laeufe.setdefault(name, []).extend(sorted(glob.glob(muster)))
    if "--protokoll" in argv:
        k = argv.index("--protokoll")
        protokoll = argv[k + 1]
        del argv[k:k + 2]
    test = "--test" in argv
    ausfuehrlich = "--kurz" not in argv
    fehler = "--fehler" in argv
    fehler_max = 20
    if "--fehler-max" in argv:
        k = argv.index("--fehler-max")
        fehler_max = int(argv[k + 1])
        del argv[k:k + 2]
        fehler = True
    gold_muster = [a for a in argv if not a.startswith("-")]

    gold_dateien: list[str] = []
    for m in gold_muster:
        gold_dateien += sorted(glob.glob(m))
    if not gold_dateien or not laeufe:
        print(__doc__.strip())
        return 1

    gewuenscht = "test" if test else "dev"
    golds: dict[str, dict] = {}
    andere_splits: dict[str, str] = {}      # Hash -> Paarname im anderen Split
    for pfad in gold_dateien:
        with open(pfad, encoding="utf-8") as f:
            g = json.load(f)
        if g.get("split", "dev") != gewuenscht:
            andere_splits[g.get("transkript_hash", "")] = (
                f"{g['paar']} (Split '{g.get('split', 'dev')}')")
            continue
        golds[g["paar"]] = g
    if not golds:
        print(f"Keine Gold-Dateien im Split '{gewuenscht}'.")
        return 1
    print(f"Gold: {len(golds)} Paar(e) im Split '{gewuenscht}' "
          f"({', '.join(sorted(golds))})")

    ergebnisse: dict[str, dict] = {}
    for name, pfade in laeufe.items():
        paare: list[tuple[dict, dict]] = []
        gesehen: set[str] = set()
        for pfad in pfade:
            with open(pfad, encoding="utf-8") as f:
                daten = json.load(f)
            treffer = [g for g in golds.values()
                       if _hash(daten["transcript"]["text"])
                       == g.get("transkript_hash")]
            if not treffer:
                anderer = andere_splits.get(_hash(daten["transcript"]["text"]))
                if anderer:
                    continue          # gehört zum anderen Split, kein Fehler
                print(f"  [!] {pfad}: kein Gold-Paar mit passendem "
                      "Transkript-Hash — Text nachträglich geändert?",
                      file=sys.stderr)
                continue
            gold = treffer[0]
            gesehen.add(gold["paar"])
            paare.append((gold, lauf_auf_saetze(daten, gold)))
        fehlend = set(golds) - gesehen
        if fehlend:
            print(f"  [!] {name}: kein Lauf für {sorted(fehlend)}",
                  file=sys.stderr)
        if paare:
            ergebnisse[name] = bewerte(paare)
            _zeige(name, ergebnisse[name], ausfuehrlich)
            if fehler:
                _zeige_fehler(name, ergebnisse[name], fehler_max)

    _vergleich(ergebnisse)

    if protokoll and ergebnisse:
        with open(protokoll, "a", encoding="utf-8") as f:
            for name, r in ergebnisse.items():
                f.write(json.dumps({
                    "zeit": time.strftime("%Y-%m-%d %H:%M"),
                    "lauf": name, "split": gewuenscht,
                    "paare": sorted(golds), "saetze": r["saetze"],
                    "cip": round(r["cip"], 4), "cir": round(r["cir"], 4),
                    "f1": round(r["f1"], 4),
                }, ensure_ascii=False) + "\n")
        print(f"\nAn {protokoll} angehängt.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
