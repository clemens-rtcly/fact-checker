"""
Stufe 0.8 — Wortlaut-Diff bei nahezu wörtlicher Übernahme.

Fängt die Klasse ab, für die es keine Regel gibt: Ist ein Claim nahezu
wortgleich übernommen, ist jede Ersetzung darin sichtbar, ohne dass die
Pipeline wissen muss, wonach sie sucht.
"""
from __future__ import annotations

import difflib
import re

from konfig import CFG
from kern.segmentierung import Sent

_DIFF_WORT = re.compile(r"[\w\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df]+")


def _wortlaut_diff(claim_text: str, quell_text: str) -> list[dict]:
    """Wort-für-Wort-Vergleich eines nahezu wörtlich übernommenen Claims.

    Gemeldet werden **nur Ersetzungen**, nicht Auslassungen oder
    Einschübe. Das ist die entscheidende Einschränkung: Weglassen ist beim
    Zusammenfassen der Normalfall und würde die Meldung unbrauchbar
    machen. Vertauscht wird dagegen selten aus Versehen — eine Ersetzung
    in einem sonst wortgleichen Satz ist genau die Stelle, an die eine
    Redaktion schauen will.

    `nah` markiert Ersetzungen, deren beide Seiten sich stark ähneln
    (`diff_nah_min`). Das ist die Signatur einer Verfälschung statt einer
    Umformulierung: „XXL" -> „XL", „Langenhorn" -> „Langenharm". Weit
    auseinanderliegende Paare („Gemeinde" -> „Ort") bleiben sichtbar,
    lösen aber kein Flag aus — sie sind meist legitime Wortwahl.

    Verglichen wird gegen den ROHEN Satz. Der angereicherte Satz aus
    `zitate.sprecherkontexte` würde geerbte Sprechernamen als Differenz
    ausweisen, die im Artikel an dieser Stelle gar nicht stehen.
    """
    a = _DIFF_WORT.findall(claim_text)
    b = _DIFF_WORT.findall(quell_text)
    if not a or not b:
        return []
    out: list[dict] = []
    sm = difflib.SequenceMatcher(a=[w.lower() for w in b],
                                 b=[w.lower() for w in a], autojunk=False)
    for op, b1, b2, a1, a2 in sm.get_opcodes():
        if op != "replace":
            continue
        if (a2 - a1) > CFG["diff_max_worte"] or (b2 - b1) > CFG["diff_max_worte"]:
            continue
        claim_teil = " ".join(a[a1:a2])
        quell_teil = " ".join(b[b1:b2])
        aehnlich = difflib.SequenceMatcher(
            a=quell_teil.lower(), b=claim_teil.lower()).ratio()
        out.append({"claim": claim_teil, "quelle": quell_teil,
                    "nah": aehnlich >= CFG["diff_nah_min"],
                    "aehnlichkeit": round(aehnlich, 2)})
        if len(out) >= CFG["diff_max_meldungen"]:
            break
    return out


def pruefe(claim_text: str, primaerquelle: Sent, lex_wert: float
           ) -> tuple[dict | None, list[str], list[str]]:
    """Diff anwenden, wenn der Claim die Fast-Wörtlichkeits-Schwelle reißt.

    Liefert (wortlaut-Block für das JSON oder None, flags, notes) — die
    Schwelle `diff_lex_min` und der Flag-Bau lagen früher direkt in
    align(); die Rechnung selbst ist unverändert `_wortlaut_diff`.
    """
    if lex_wert < CFG["diff_lex_min"]:
        return None, [], []
    aend = _wortlaut_diff(claim_text, primaerquelle.text)
    if not aend:
        return None, [], []
    wortlaut = {"quelle": primaerquelle.id, "aenderungen": aend}
    flags: list[str] = []
    notes: list[str] = []
    nahe = [a for a in aend if a["nah"]]
    if nahe:
        flags.append("wortlaut_abweichung")
        notes.append(
            "Fast wörtlich übernommen, aber abweichend: "
            + "; ".join("\u201e" + a["quelle"] + "\u201c \u2192 \u201e"
                        + a["claim"] + "\u201c" for a in nahe[:3])
            + ".")
    return wortlaut, flags, notes
