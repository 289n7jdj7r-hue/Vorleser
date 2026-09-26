# Vorleser

PDFs vorlesen lassen — im Browser, auf dem iPhone, oder als fertige MP3.

| | Was es ist | Wo es läuft |
|---|---|---|
| **`docs/`** | Web-App, installierbar auf dem Home-Bildschirm | Browser, iPhone, iPad |
| **`cli/`** | Python-Werkzeug, macht MP3-Dateien | Rechner |

Der Text wird lokal aus der PDF gelöst. Es wird nichts hochgeladen — nur der fertige
Text geht an den gewählten Sprachdienst.

---

## Schnellstart

1. `docs/index.html` herunterladen und in **Microsoft Edge** oder **Chrome** öffnen
2. **Einstellungen** → ganz unten **Cloud-Stimme**
3. Anbieter **ElevenLabs**, API-Schlüssel einfügen, **Verbinden**
4. **Probe hören** — wenn das gut klingt, PDF reinziehen und Play

Ohne Cloud-Schlüssel läuft die App mit den Stimmen deines Betriebssystems. Die klingen
deutlich schlechter; die App ist dafür sofort und kostenlos nutzbar.

---

## Bedienung

| Element | Bedeutung |
|---|---|
| **Deutsch / English** | schaltet Stimme *und* Abkürzungslogik um |
| **Stimme A / B** | zwei Systemstimmen je Sprache, live wechselbar |
| **Cloud-Chip** | erscheint bei verbundener Cloud-Stimme; antippen schaltet durch |
| **1× / 1,25× / 1,5×** | Tempo |
| **Lesezeichen** | merkt den laufenden Satz — Taste `M` |
| **Sammlung** | alle gemerkten Sätze, nach Buch gruppiert, mit Export |

Tastatur: `Leertaste` vorlesen/anhalten · `←` `→` Satz zurück/vor · `M` merken · `Esc` stoppen

Beim Sprachwechsel wird der laufende Satz noch in der alten Stimme zu Ende gelesen.
Das ist Absicht — mitten im Satz umzuschalten klingt abgehackt.

---

## Cloud-Stimmen

Vier Anbieter stehen zur Wahl. Der Schlüssel wird **nur lokal im Browser** gespeichert
und geht ausschließlich an den jeweiligen Anbieter.

| Anbieter | gratis pro Monat | Bemerkung |
|---|---|---|
| **ElevenLabs** | 10.000 Zeichen (~4 Seiten) | beste Qualität; Voice Library erst ab Starter (6 $/Monat) |
| **Azure** | 500.000 Zeichen | Dragon HD; Studenten-Abos können regional gesperrt sein |
| **Google** | 1.000.000 Zeichen | Chirp 3 HD; kein Tempo, dafür größtes Gratiskontingent |
| **System** | unbegrenzt | Stimmen des Betriebssystems, deutlich schwächer |

### ElevenLabs einrichten

1. Konto auf elevenlabs.io
2. **Entwickler → API-Schlüssel → Schlüssel erstellen**
3. Berechtigungen: **Text zu Sprache = Zugriff**, **Stimmen = Gelesen**, Rest *Kein Zugang*
4. „Bei Leaks automatisch deaktivieren" eingeschaltet lassen
5. Optional unter *Nutzungslimits* ein Credit-Limit setzen

Gewünschte Stimmen müssen unter **Meine Stimmen** liegen, sonst findet die API sie nicht.

**Der Schlüssel gehört niemals in eine Datei oder ins Repository.** Er wird pro Gerät
einmal in der App eingegeben und dort gespeichert.

---

## Auf dem iPhone

SideStore und `.ipa`-Dateien brauchst du nicht. Die App läuft als Web-App vom
Home-Bildschirm — kein Zertifikat, kein 7-Tage-Ablauf.

1. Repo auf GitHub hochladen
2. **Settings → Pages → Branch `main`, Ordner `/docs`**
3. Adresse **in Safari** öffnen (nur Safari kann das), Teilen → **Zum Home-Bildschirm**
4. App öffnen, Schlüssel einmal eintragen

**Mit Cloud-Stimme läuft die Wiedergabe bei gesperrtem Bildschirm weiter**, inklusive
Titel und Steuerung auf dem Sperrbildschirm und über AirPods. Der erste Ton braucht eine
Berührung — einmal Play drücken, dann sperren.

Ohne Cloud-Stimme pausiert iOS beim Sperren. Das ist eine Grenze der Web-Sprachausgabe;
die App hält deshalb bewusst an, statt stumm weiterzulaufen.

---

## Python-Werkzeug

Für ganze Bücher als MP3 — läuft durch, auch wenn der Rechner sonst nichts tut.

```bash
cd cli
pip install -r requirements.txt

python pdf_vorlesen.py buch.pdf                          # gratis, kein Konto
python pdf_vorlesen.py buch.pdf --engine google          # Chirp 3 HD
python pdf_vorlesen.py paper.pdf --sprache en --engine eleven
python pdf_vorlesen.py buch.pdf --seiten 20-40 --ausgabe kapitel2.mp3
```

Schlüssel als Umgebungsvariable: `ELEVENLABS_API_KEY`, `GOOGLE_TTS_KEY`,
`AZURE_SPEECH_KEY`, `OPENAI_API_KEY`.

Vor jedem kostenpflichtigen Lauf kommt eine Kostenschätzung mit Rückfrage.

| Option | Bedeutung |
|---|---|
| `--sprache de\|en` | Deutsch oder amerikanisches Englisch |
| `--engine edge\|azure\|openai\|eleven\|google` | Sprachdienst |
| `--stimme NAME` | Stimme überschreiben |
| `--anweisung "…"` | Sprechanweisung (nur `openai`) |
| `--seiten 12-40` | nur diesen Bereich |
| `--tempo +10%` | schneller/langsamer (`edge`, `azure`) |
| `--txt` | bereinigten Text zusätzlich sichern |
| `--alles-vorlesen` | Filter aus |
| `--limit 2.00` | ab wie viel USD nachgefragt wird |

Die MP3 kommt per iCloud aufs iPhone. Zum Hören eignet sich **Apple Books** am besten —
merkt sich die Stelle, Hintergrundwiedergabe, Sperrbildschirm-Steuerung.

---

## Was mit dem Text passiert

Damit es nach Vortrag klingt und nicht nach vorgelesenem Dokument:

- Silbentrennung über Zeilenumbrüche wird zusammengesetzt
- Kopf- und Fußzeilen, Seitenzahlen, Inhaltsverzeichnis-Punkte fliegen raus
- Zweispaltige Layouts werden erkannt und in Lesereihenfolge gebracht
- Überschriften bekommen eigene Pausen
- Abkürzungen werden ausgeschrieben: „z. B." → „zum Beispiel", „i. V. m." → „in Verbindung
  mit", „§" → „Paragraf", „Tz." → „Textziffer"; im Englischmodus „e.g." → „for example"
- Der Satztrenner stolpert nicht über „Abs. 4", „S. 42" oder „Mr."
- Belege, eckige Nummernverweise, hochgestellte Fußnotenziffern, der Fußnotenapparat,
  Bildunterschriften und ab „Literaturverzeichnis" der Rest werden weggelassen

Alles hören: `--alles-vorlesen` beziehungsweise den Filter in der App ausschalten.

---

## Eingescannte PDFs

Die meisten PDFs enthalten den Text bereits. Test: Lässt sich der Text im Reader mit der
Maus markieren? Dann braucht es kein OCR.

Falls doch: `pip install pytesseract pillow` plus das Tesseract-Programm mit deutschem
Sprachpaket. Das Werkzeug erkennt Seiten ohne Textebene dann selbst — offline.

Die Browser-App kann kein OCR.

---

## Nach Änderungen an der Web-App

In `docs/sw.js` die Zeile `const VERSION = 'vorleser-vN'` hochzählen. Sonst liefern
installierte Geräte weiter die alte Fassung aus dem Zwischenspeicher.

## Lizenz

MIT
