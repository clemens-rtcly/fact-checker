"""
Stufe 0 — harte Signale vor aller Ähnlichkeit.

  zahlen.py        deutsche Zahl-/Währungs-/Datums-Normalisierung + Entitäten
  anker.py         eindeutige Zahlen/Namen als Score-Bonus und Zusatzquellen
  verifikation.py  Zahlen, Personen, Identifier gegen den Artikel prüfen
  personen.py      Personen-NER (spaCy oder Regex-Rückfall)   [Stufe 0.5]
  identifier.py    Orte, Organisationen, Kürzel — Fast-Identität ist
                   Verdacht, nicht Beleg                      [Stufe 0.6]
  wortlaut.py      Wort-für-Wort-Diff bei Fast-Wörtlichkeit   [Stufe 0.8]
"""
