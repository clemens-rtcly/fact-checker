"""
Stufenübergreifender Kern: Text, Segmentierung, Lexik, Fusion,
Entscheidung, Ausgabe.

Alles hier wird von mehreren Stufen gelesen und gehört keiner allein.
Einzige bewusste Aufwärtskante: kern.lexik importiert stufe0.zahlen
(normalize_numbers) — zahlen.py ist ein abhängigkeitsfreies Blatt,
ein Zirkel kann so nicht entstehen.
"""
