#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_vorlesen.py  v3 — macht aus einer PDF ein Hörbuch.

Zwei Stimmen:
    --sprache de   deutsch (Standard)
    --sprache en   amerikanisch

Vier Sprachdienste:
    --engine edge      gratis, kein Konto                     (Standard)
    --engine azure     Dragon HD, 500.000 Zeichen/Monat gratis
    --engine openai    Betonung per Anweisung steuerbar
    --engine google    Chirp 3 HD, 1.000.000 Zeichen/Monat gratis
    --engine eleven    ElevenLabs, höchste Qualität

Installieren:
    pip install pymupdf edge-tts
    pip install pytesseract pillow      (nur für eingescannte PDFs)

Beispiele:
    python pdf_vorlesen.py skript.pdf
    python pdf_vorlesen.py skript.pdf --engine azure
    python pdf_vorlesen.py paper.pdf --sprache en --engine openai
    python pdf_vorlesen.py skript.pdf --engine openai --anweisung "Sehr ruhig, langsam."
    python pdf_vorlesen.py skript.pdf --alles-vorlesen
"""

import argparse
import asyncio
import base64
import io
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        sys.exit("Fehlt: PyMuPDF.  Installieren mit:  pip install pymupdf")

try:
    import edge_tts
except ImportError:
    sys.exit("Fehlt: edge-tts.  Installieren mit:  pip install edge-tts")


# ══════════════════════════════════════════════════════════════
#  Genau zwei Stimmen
# ══════════════════════════════════════════════════════════════

SPRACHEN = {
    "de": {
        "locale": "de-DE",
        "name": "Deutsch",
        "edge": "de-DE-KatjaNeural",
        "hd_wunsch": ["de-DE-Katja:DragonHDLatestNeural",
                      "de-DE-Seraphina:DragonHDLatestNeural"],
        "hd_ersatz": "de-DE-KatjaNeural",
        "openai": "cedar",
        "kapitel": "Kapitel",
    },
    "en": {
        "locale": "en-US",
        "name": "Amerikanisches Englisch",
        "edge": "en-US-AriaNeural",
        "hd_wunsch": ["en-US-Aria:DragonHDLatestNeural",
                      "en-US-Ava:DragonHDLatestNeural"],
        "hd_ersatz": "en-US-AriaNeural",
        "openai": "marin",
        "kapitel": "Chapter",
    },
}


# ══════════════════════════════════════════════════════════════
#  Abkürzungen: schützen (kein falscher Satzbruch) + ausschreiben
# ══════════════════════════════════════════════════════════════

SP = "\x01"

ABBR_DE = [
    "z.B.", "u.a.", "d.h.", "i.d.R.", "u.U.", "z.T.", "v.a.", "o.g.", "u.g.", "s.o.", "s.u.",
    "a.a.O.", "z.Zt.", "bzw.", "ggf.", "inkl.", "exkl.", "usw.", "etc.", "vgl.", "ca.", "bspw.",
    "evtl.", "sog.", "einschl.", "entspr.", "ggü.", "zzgl.", "abzgl.", "bzgl.", "lt.", "ebd.",
    "ff.", "Nr.", "Abs.", "Art.", "Abb.", "Tab.", "Kap.", "Bd.", "Aufl.", "Hrsg.", "Prof.", "Dr.",
    "Mio.", "Mrd.", "Tsd.", "Jh.", "Str.", "geb.", "max.", "min.", "St.", "Pkt.", "Anl.", "Ziff.",
    "Rz.", "Tz.", "o.ä.", "u.ä.", "i.V.m.", "i.S.d.", "i.S.v.", "i.H.v.", "u.v.m.", "gem.", "rd.",
    "insb.", "zit.", "Anm.", "Anh.", "Rn.", "Fn.",
]

ABBR_EN = [
    "e.g.", "i.e.", "etc.", "cf.", "vs.", "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Jr.", "Sr.",
    "St.", "Inc.", "Ltd.", "Co.", "Corp.", "Fig.", "Ch.", "Vol.", "No.", "pp.", "p.", "ed.",
    "eds.", "al.", "approx.", "est.", "min.", "max.", "Ave.", "Dept.", "Univ.", "Sec.", "Art.",
]

SPACED_DE = [("z. B.", "z.B."), ("u. a.", "u.a."), ("d. h.", "d.h."), ("i. d. R.", "i.d.R."),
             ("u. U.", "u.U."), ("z. T.", "z.T."), ("v. a.", "v.a."), ("o. g.", "o.g."),
             ("s. o.", "s.o."), ("s. u.", "s.u."), ("a. a. O.", "a.a.O."), ("z. Zt.", "z.Zt."),
             ("i. V. m.", "i.V.m."), ("i. H. v.", "i.H.v."), ("i. S. d.", "i.S.d.")]

SPACED_EN = [("e. g.", "e.g."), ("i. e.", "i.e.")]

SAG_DE = [
    (r"\bz\.B\.", "zum Beispiel"), (r"\bu\.a\.", "unter anderem"), (r"\bd\.h\.", "das heißt"),
    (r"\bi\.d\.R\.", "in der Regel"), (r"\bu\.U\.", "unter Umständen"), (r"\bz\.T\.", "zum Teil"),
    (r"\bv\.a\.", "vor allem"), (r"\bo\.g\.", "oben genannt"), (r"\bu\.v\.m\.", "und vieles mehr"),
    (r"\bi\.V\.m\.", "in Verbindung mit"), (r"\bi\.S\.d\.", "im Sinne des"),
    (r"\bi\.S\.v\.", "im Sinne von"), (r"\bi\.H\.v\.", "in Höhe von"), (r"\bgem\.", "gemäß"),
    (r"\binsb\.", "insbesondere"), (r"\bbzw\.", "beziehungsweise"), (r"\bggf\.", "gegebenenfalls"),
    (r"\binkl\.", "inklusive"), (r"\bexkl\.", "exklusive"), (r"\busw\.", "und so weiter"),
    (r"\betc\.", "et cetera"), (r"\bvgl\.", "vergleiche"), (r"\bca\.", "circa"),
    (r"\bbspw\.", "beispielsweise"), (r"\bevtl\.", "eventuell"), (r"\bsog\.", "sogenannt"),
    (r"\beinschl\.", "einschließlich"), (r"\bzzgl\.", "zuzüglich"), (r"\babzgl\.", "abzüglich"),
    (r"\bbzgl\.", "bezüglich"), (r"\bggü\.", "gegenüber"), (r"\brd\.(?=\s*\d)", "rund"),
    (r"\bNr\.", "Nummer"), (r"\bAbs\.", "Absatz"), (r"\bArt\.(?=\s*\d)", "Artikel"),
    (r"\bAbb\.", "Abbildung"), (r"\bTab\.", "Tabelle"), (r"\bKap\.", "Kapitel"),
    (r"\bAufl\.", "Auflage"), (r"\bHrsg\.", "Herausgeber"), (r"\bProf\.", "Professor"),
    (r"\bDr\.", "Doktor"), (r"\bMio\.", "Millionen"), (r"\bMrd\.", "Milliarden"),
    (r"\bTsd\.", "Tausend"), (r"\bS\.(?=\s*\d)", "Seite "), (r"\bTz\.", "Textziffer"),
    (r"\bZiff\.", "Ziffer"), (r"\bRn\.", "Randnummer"), (r"\bFn\.", "Fußnote"),
    (r"§§", "Paragrafen "), (r"§", "Paragraf "), (r"%", " Prozent"), (r"€", " Euro"),
    (r"\$", " Dollar"), (r"&", " und "),
]

SAG_EN = [
    (r"\be\.g\.", "for example"), (r"\bi\.e\.", "that is"), (r"\betc\.", "et cetera"),
    (r"\bcf\.", "compare"), (r"\bvs\.", "versus"), (r"\bapprox\.", "approximately"),
    (r"\bFig\.", "Figure"), (r"\bCh\.", "Chapter"), (r"\bVol\.", "Volume"), (r"\bNo\.", "Number"),
    (r"\bpp?\.(?=\s*\d)", "page "), (r"%", " percent"), (r"€", " euros"), (r"\$", " dollars"),
    (r"&", " and "),
]

SAG_ALLE = [
    (r"https?://\S+", "Link"), (r"\bwww\.\S+", "Link"),
    (r"(\d)\s*[–-]\s*(\d)", r"\1 – \2"),
    (r"[•▪●◦‣]", " "), (r"[→←↑↓⇒]", " "),
    (r"\.{3,}", " "), (r"_{2,}", " "),
]

LIGATUREN = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
             "\u2018": "'", "\u2019": "'", "\u201b": "'", "\u201c": '"', "\u201d": '"',
             "\u201e": '"', "\u2013": "–", "\u2014": "–",
             "\u00a0": " ", "\u2007": " ", "\u202f": " "}

HOCHGESTELLT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def bau_sprache(code):
    k = dict(SPRACHEN[code])
    abbr = ABBR_DE if code == "de" else ABBR_EN
    alle = set()
    for a in abbr:
        alle.add(a)
        alle.add(a[0].upper() + a[1:])
    k["abbr"] = sorted(alle, key=len, reverse=True)
    k["spaced"] = SPACED_DE if code == "de" else SPACED_EN
    waehrung = ([(r"\$\s*(\d+(?:[.,]\d+)?)", r"\1 Dollar"), (r"€\s*(\d+(?:[.,]\d+)?)", r"\1 Euro")]
                if code == "de" else
                [(r"\$\s*(\d+(?:[.,]\d+)?)", r"\1 dollars"), (r"€\s*(\d+(?:[.,]\d+)?)", r"\1 euros")])
    roh = waehrung + (SAG_DE if code == "de" else SAG_EN) + SAG_ALLE
    k["sag"] = [(re.compile(p, re.I if p.startswith(r"\b") and p[2].islower() else 0), r)
                for p, r in roh]
    return k


# ══════════════════════════════════════════════════════════════
#  Text säubern und trennen
# ══════════════════════════════════════════════════════════════

def saeubern(s):
    s = s.replace("\u00ad", "")
    for k, v in LIGATUREN.items():
        s = s.replace(k, v)
    return re.sub(r"[ \t]{2,}", " ", s)


def schuetzen(t, k):
    for src, dst in k["spaced"]:
        t = t.replace(src, dst)
        t = t.replace(src[0].upper() + src[1:], dst[0].upper() + dst[1:])
    for a in k["abbr"]:
        t = t.replace(a, a.replace(".", SP))
    t = re.sub(r"(\d)\.(?=\d)", r"\1" + SP, t)
    t = re.sub(r"(^|[\s(])(\d{1,3})\.(?=\s)", r"\1\2" + SP, t)
    t = re.sub(r"\b([A-ZÄÖÜ])\.(?=\s*[A-ZÄÖÜ])", r"\1" + SP, t)
    t = re.sub(r"\b([A-ZÄÖÜ][a-zäöü]{0,2})\.(?=\s*[\dIVX])", r"\1" + SP, t)
    return t


def saetze(text, k):
    t = schuetzen(text, k)
    out, start, i, n = [], 0, 0, len(t)
    while i < n:
        if t[i] not in ".!?…":
            i += 1
            continue
        j = i + 1
        while j < n and t[j] in '"»”’)]':
            j += 1
        if j >= n:
            out.append(t[start:])
            start = n
            break
        m = re.match(r"\s+", t[j:])
        if not m:
            i += 1
            continue
        p = j + len(m.group(0))
        nach = t[p] if p < n else None
        if nach is None or re.match(r'["»„(\[A-ZÄÖÜ0-9§]', nach):
            out.append(t[start:j])
            start = i = p
        else:
            i += 1
    if start < n:
        out.append(t[start:])
    return [s.replace(SP, ".").strip() for s in out if s.strip()]


def aussprechen(s, k):
    for rx, rep in k["sag"]:
        s = rx.sub(rep, s)
    return re.sub(r"\s{2,}", " ", s).strip()


# ══════════════════════════════════════════════════════════════
#  Der Hörbuch-Filter: Belege, Fußnoten, Bildunterschriften raus
# ══════════════════════════════════════════════════════════════

BELEG_KLAMMER = re.compile(
    r"\(\s*(?:vgl\.|siehe|s\.|see|cf\.)?\s*[A-ZÄÖÜ][\w.\-äöüß]*"
    r"(?:\s*(?:et\s+al\.|u\.\s*a\.|&|und|and)\s*[A-ZÄÖÜ][\w.\-äöüß]*)*"
    r"[,;]?\s*\d{4}[a-z]?"
    r"(?:\s*[,;:]\s*(?:S\.|p{1,2}\.)?\s*\d+(?:\s*f{1,2}\.)?(?:\s*[–-]\s*\d+)?)?\s*\)",
    re.I)
BELEG_ECKIG = re.compile(r"\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]")
BELEG_SATZ = re.compile(r"^(?:vgl\.|siehe|cf\.|see)\b.{0,110}$", re.I)
BELEG_ANHANG = re.compile(r"[\s;,(]+(?:vgl\.|siehe|cf\.|see)\s.{0,110}$", re.I)
UNTERSCHRIFT = re.compile(
    r"^(?:abbildung|abb\.|tabelle|tab\.|grafik|schaubild|figure|fig\.|table|chart)"
    r"\s*\d+\s*[.:–-]", re.I)
QUELLE_ZEILE = re.compile(r"^(?:quelle|source|eigene\s+darstellung)\s*[:.]", re.I)
LITERATUR = re.compile(
    r"^(?:literatur|literaturverzeichnis|quellenverzeichnis|quellen|bibliografie|"
    r"bibliographie|referenzen|references|bibliography|works\s+cited)\b", re.I)


def belege_raus(t):
    t = BELEG_KLAMMER.sub("", t)
    t = BELEG_ECKIG.sub("", t)
    t = re.sub(r"\s+([,.;:])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


# ══════════════════════════════════════════════════════════════
#  PDF auslesen
# ══════════════════════════════════════════════════════════════

def seiten_zeilen(page, spalten, filtern):
    d = page.get_text("dict")
    breite, hoehe = page.rect.width, page.rect.height
    roh = []
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            groessen = [sp.get("size", 10) for sp in spans]
            roh.append({"spans": spans, "bbox": line["bbox"],
                        "size": max(groessen), "smin": min(groessen)})
    if not roh:
        return [], breite

    koerper = statistics.median([r["size"] for r in roh])
    zeilen = []
    for r in roh:
        teile = []
        for sp in r["spans"]:
            txt = sp.get("text", "")
            # hochgestellte Fußnotenziffern wegwerfen
            if filtern and sp.get("size", 10) < koerper * 0.82 \
               and re.fullmatch(r"[\d,\s⁰¹²³⁴⁵⁶⁷⁸⁹]+", txt or " "):
                continue
            teile.append(txt)
        txt = saeubern("".join(teile)).strip()
        if not txt:
            continue
        x0, y0, x1, y1 = r["bbox"]
        fett = any(sp.get("flags", 0) & 16 for sp in r["spans"])
        # Fußnotenzone: kleiner Satz im unteren Seitendrittel
        if filtern and r["size"] < koerper * 0.88 and y0 > hoehe * 0.70:
            continue
        zeilen.append({"text": txt, "x0": x0, "x1": x1, "y": y0,
                       "size": r["size"], "fett": fett, "koerper": koerper})

    if not zeilen:
        return [], breite

    zwei = spalten == "2"
    if spalten == "auto" and len(zeilen) > 12:
        m = breite / 2
        L = [z for z in zeilen if z["x1"] < m + breite * 0.03]
        R = [z for z in zeilen if z["x0"] > m - breite * 0.03]
        zwei = (len(L) + len(R) > len(zeilen) * 0.9
                and len(L) > len(zeilen) * 0.25 and len(R) > len(zeilen) * 0.25)
    if zwei:
        m = breite / 2
        L = sorted([z for z in zeilen if z["x0"] <= m], key=lambda z: z["y"])
        R = sorted([z for z in zeilen if z["x0"] > m], key=lambda z: z["y"])
        return L + R, breite

    zeilen.sort(key=lambda z: (round(z["y"] / 2), z["x0"]))
    return zeilen, breite


def ist_ueberschrift(z):
    t = z["text"]
    if len(t) > 110:
        return False
    if z["size"] > z["koerper"] * 1.13:
        return True
    if z["fett"] and len(t) < 85 and not re.search(r"[.!?;]$", t):
        return True
    if re.match(r"^\d{1,2}(\.\d{1,2}){0,3}\.?\s+[A-ZÄÖÜ]", t) and len(t) < 85 \
       and not re.search(r"[.!?]$", t):
        return True
    return False


def wiederkehrend(seiten):
    z = {}
    for zeilen, _ in seiten:
        for l in zeilen[:2] + zeilen[-2:]:
            if len(l["text"]) > 90:
                continue
            key = re.sub(r"\d+", "#", l["text"]).strip()
            if len(key) >= 3:
                z[key] = z.get(key, 0) + 1
    noetig = max(3, round(len(seiten) * 0.5))
    return {k for k, v in z.items() if v >= noetig}


def bloecke_bauen(zeilen, raus, filtern):
    """Liefert [('h'|'p', Text), ...] — Überschriften getrennt von Absätzen."""
    if not zeilen:
        return []
    rechts = max(z["x1"] for z in zeilen)
    out, buf = [], ""

    def spuelen():
        nonlocal buf
        if buf.strip():
            out.append(("p", buf.strip()))
        buf = ""

    for z in zeilen:
        t = z["text"]
        if re.fullmatch(r"[\s\d/–\-|]+", t):
            continue
        if re.sub(r"\d+", "#", t).strip() in raus:
            continue
        if re.fullmatch(r"[.\u2022\-–_]{4,}", t):
            continue
        if filtern and (UNTERSCHRIFT.match(t) or QUELLE_ZEILE.match(t)):
            continue
        t = re.sub(r"\s*\.{4,}\s*\d*$", "", t).strip()
        if not t:
            continue

        if ist_ueberschrift(z):
            spuelen()
            out.append(("h", t))
            continue

        if not buf:
            buf = t
        elif re.search(r"[a-zäöüß]-$", buf) and re.match(r"^[a-zäöüß]", t):
            buf = buf[:-1] + t
        elif re.match(r"^([-–•▪●]|\(?\d{1,2}[.)]\s|[a-z]\)\s)", t):
            spuelen()
            buf = t
        else:
            buf += " " + t

        if z["x1"] < rechts - max(24, rechts * 0.13) and re.search(r'[.!?:»"”]$', buf):
            spuelen()
    spuelen()
    return out


def ocr_seite(page, sprache, dpi=300):
    import pytesseract
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))),
                                       lang="deu" if sprache == "de" else "eng")


def text_holen(pfad, von, bis, spalten, ocr, filtern, k, sprache):
    doc = pymupdf.open(pfad)
    gesamt = doc.page_count
    von = max(1, min(gesamt, von or 1))
    bis = max(von, min(gesamt, bis or gesamt))

    ocr_da = False
    if ocr != "aus":
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
            ocr_da = True
        except ImportError:
            pass

    seiten, leer = [], []
    for n in range(von, bis + 1):
        page = doc[n - 1]
        zeilen, breite = seiten_zeilen(page, spalten, filtern)
        if sum(len(z["text"]) for z in zeilen) < 40:
            if ocr_da:
                print(f"    Seite {n}: kein Text — OCR läuft …", flush=True)
                try:
                    roh = ocr_seite(page, sprache)
                    zeilen = [{"text": saeubern(l).strip(), "x0": 0, "x1": breite,
                               "y": i, "size": 10, "fett": False, "koerper": 10}
                              for i, l in enumerate(roh.splitlines()) if l.strip()]
                except Exception as e:
                    print(f"    Seite {n}: OCR fehlgeschlagen ({e})")
                    leer.append(n)
            else:
                leer.append(n)
        seiten.append((zeilen, n))
        if (n - von) % 15 == 0 and n > von:
            print(f"    … Seite {n}", flush=True)

    doc.close()
    raus = wiederkehrend(seiten)

    einheiten, geschnitten, im_anhang = [], 0, False
    for zeilen, nr in seiten:
        for art, txt in bloecke_bauen(zeilen, raus, filtern):
            if filtern and art == "h" and LITERATUR.match(txt):
                im_anhang = True
            if im_anhang:
                geschnitten += 1
                continue
            if art == "h":
                einheiten.append((nr, "h", txt.rstrip(".") + "."))
                continue
            vorher = txt
            if filtern:
                txt = belege_raus(txt)
            if not re.search(r"[a-zA-ZäöüÄÖÜß0-9]", txt):
                continue
            for s in saetze(txt, k):
                if filtern and BELEG_SATZ.match(s):
                    geschnitten += 1
                    continue
                if filtern and BELEG_ANHANG.search(s):
                    s = BELEG_ANHANG.sub("", s).rstrip(" ,;(")
                    if s and not re.search(r"[.!?]$", s):
                        s += "."
                    geschnitten += 1
                if re.search(r"[a-zA-ZäöüÄÖÜß]", s):
                    einheiten.append((nr, "p", s))
            if filtern and len(txt) < len(vorher):
                geschnitten += 1

    return einheiten, leer, ocr_da, gesamt, geschnitten, im_anhang


# ══════════════════════════════════════════════════════════════
#  In Sprechblöcke bündeln
# ══════════════════════════════════════════════════════════════

def paketieren(einheiten, k, max_zeichen):
    """Bündelt zu Blöcken. Jeder Block: Liste von ('h'|'p', gesprochener Text)."""
    pakete, akt, laenge = [], [], 0
    for _, art, txt in einheiten:
        gesprochen = aussprechen(txt, k)
        if not gesprochen:
            continue
        if akt and laenge + len(gesprochen) > max_zeichen:
            pakete.append(akt)
            akt, laenge = [], 0
        akt.append((art, gesprochen))
        laenge += len(gesprochen)
    if akt:
        pakete.append(akt)
    return pakete


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ssml_bauen(paket, stimme, locale, tempo):
    teile, vorher_h = [], False
    for i, (art, txt) in enumerate(paket):
        if i and not vorher_h:
            teile.append('<break time="900ms"/>' if art == "h"
                         else '<break time="550ms"/>')
        teile.append(xml_escape(txt))
        if art == "h":
            teile.append('<break time="700ms"/>')
        vorher_h = (art == "h")
    inhalt = " ".join(teile)
    rate = f' rate="{tempo}"' if tempo and tempo != "+0%" else ""
    if rate:
        inhalt = f"<prosody{rate}>{inhalt}</prosody>"
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{locale}"><voice name="{stimme}">{inhalt}</voice></speak>')


def klartext(paket):
    """Für edge-tts: Pausen nur über Satzzeichen andeutbar."""
    teile = []
    for art, txt in paket:
        teile.append(txt if art == "p" else txt.rstrip(".") + ".")
    return "  ".join(teile)


# ══════════════════════════════════════════════════════════════
#  Sprechanweisung — das Stellrad für die Betonung
# ══════════════════════════════════════════════════════════════

ANWEISUNG = {
    "de": ("Lies wie ein professioneller Hörbuchsprecher. Ruhiges, gleichmäßiges "
           "Tempo. Betone Fachbegriffe und Schlüsselwörter deutlich, aber ohne zu "
           "übertreiben. Setze echte Pausen an Satz- und Absatzgrenzen. Trage "
           "Nebensätze tiefer und ruhiger vor als Hauptsätze. Sachlicher, warmer "
           "Ton. Keine werbliche Begeisterung, keine künstliche Fröhlichkeit."),
    "en": ("Read like a professional audiobook narrator. Calm, even pace. Clearly "
           "emphasize technical terms and key words without overdoing it. Take real "
           "pauses at sentence and paragraph boundaries. Deliver subordinate clauses "
           "lower and quieter than main clauses. Measured, warm tone. No promotional "
           "enthusiasm, no artificial cheerfulness."),
}

ENGINES = {
    "edge":   "edge-tts — gratis, kein Konto",
    "azure":  "Azure Dragon HD — 500.000 Zeichen/Monat gratis",
    "openai": "OpenAI steuerbar — Betonung per Anweisung",
    "eleven": "ElevenLabs — höchste Qualität, teuer",
    "google": "Google Chirp 3 HD — 1 Mio. Zeichen/Monat gratis",
}


# ══════════════════════════════════════════════════════════════
#  edge-tts
# ══════════════════════════════════════════════════════════════

async def edge_sprechen(text, stimme, tempo, lautstaerke, tonhoehe, versuche=3):
    letzter = None
    for v in range(versuche):
        try:
            c = edge_tts.Communicate(text, stimme, rate=tempo,
                                     volume=lautstaerke, pitch=tonhoehe)
            buf = bytearray()
            async for msg in c.stream():
                if msg["type"] == "audio":
                    buf += msg["data"]
            if buf:
                return bytes(buf)
            raise RuntimeError("keine Audiodaten")
        except Exception as e:
            letzter = e
            if v < versuche - 1:
                await asyncio.sleep(1.5 * (v + 1))
    raise RuntimeError(f"Sprachdienst antwortet nicht: {letzter}")


# ══════════════════════════════════════════════════════════════
#  Gemeinsamer HTTP-Helfer
# ══════════════════════════════════════════════════════════════

def post(url, daten, kopf, versuche=3, timeout=120):
    letzter = None
    for v in range(versuche):
        try:
            req = urllib.request.Request(url, data=daten, headers=kopf)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                antwort = r.read()
            if antwort:
                return antwort
            raise RuntimeError("leere Antwort")
        except urllib.error.HTTPError as e:
            leib = e.read().decode("utf-8", "replace")[:220]
            if e.code in (401, 403):
                raise RuntimeError(f"Zugang abgelehnt ({e.code}): {leib}")
            if e.code == 400:
                raise RuntimeError(f"Anfrage abgelehnt (400): {leib}")
            if e.code == 429:
                letzter = RuntimeError("Ratenlimit (429)")
                time.sleep(6 * (v + 1))
                continue
            letzter = RuntimeError(f"HTTP {e.code}: {leib}")
        except Exception as e:
            letzter = e
        if v < versuche - 1:
            time.sleep(2 * (v + 1))
    raise RuntimeError(str(letzter))


def hole(url, kopf, timeout=30):
    req = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ══════════════════════════════════════════════════════════════
#  Azure Dragon HD
# ══════════════════════════════════════════════════════════════

def azure_url(region, pfad):
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/{pfad}"


def azure_stimme_waehlen(key, region, k):
    try:
        alle = hole(azure_url(region, "voices/list"),
                    {"Ocp-Apim-Subscription-Key": key})
    except Exception as e:
        print(f"  Stimmenliste nicht abrufbar ({e}) — nehme {k['hd_ersatz']}")
        return k["hd_ersatz"], False
    namen = {v.get("ShortName", "") for v in alle}
    for w in k["hd_wunsch"]:
        if w in namen:
            return w, True
    hd = sorted(n for n in namen if n.startswith(k["locale"]) and "DragonHD" in n)
    return (hd[0], True) if hd else (k["hd_ersatz"], False)


def azure_sprechen(ssml, key, region):
    return post(azure_url(region, "v1"), ssml.encode("utf-8"),
                {"Ocp-Apim-Subscription-Key": key,
                 "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-48khz-192kbitrate-mono-mp3",
                 "User-Agent": "pdf-vorlesen"})


# ══════════════════════════════════════════════════════════════
#  OpenAI — steuerbare Betonung
# ══════════════════════════════════════════════════════════════

def openai_sprechen(text, key, stimme, anweisung, modell="gpt-4o-mini-tts"):
    leib = json.dumps({"model": modell, "voice": stimme, "input": text,
                       "instructions": anweisung, "response_format": "mp3"}
                      ).encode("utf-8")
    return post("https://api.openai.com/v1/audio/speech", leib,
                {"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})


# ══════════════════════════════════════════════════════════════
#  ElevenLabs
# ══════════════════════════════════════════════════════════════

def eleven_stimme_waehlen(key, wunsch):
    try:
        daten = hole("https://api.elevenlabs.io/v1/voices", {"xi-api-key": key})
    except Exception as e:
        raise RuntimeError(f"Stimmenliste nicht abrufbar: {e}")
    stimmen = daten.get("voices", [])
    if not stimmen:
        raise RuntimeError("keine Stimmen im Konto")
    if wunsch:
        for v in stimmen:
            if v.get("name", "").lower() == wunsch.lower() or v.get("voice_id") == wunsch:
                return v["voice_id"], v.get("name", wunsch)
        print(f"  '{wunsch}' nicht gefunden. Verfügbar: "
              + ", ".join(v.get("name", "?") for v in stimmen[:12]))
    return stimmen[0]["voice_id"], stimmen[0].get("name", "?")


def eleven_sprechen(text, key, voice_id, modell="eleven_multilingual_v2"):
    leib = json.dumps({
        "text": text, "model_id": modell,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                           "style": 0.15, "use_speaker_boost": True}
    }).encode("utf-8")
    return post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", leib,
                {"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"})


# ══════════════════════════════════════════════════════════════
#  Google Chirp 3 HD
# ══════════════════════════════════════════════════════════════

GOOGLE_BASIS = "https://texttospeech.googleapis.com/v1"


def google_stimme_waehlen(key, locale, wunsch=None):
    try:
        daten = hole(f"{GOOGLE_BASIS}/voices?languageCode={locale}&key={key}", {})
    except urllib.error.HTTPError as e:
        leib = e.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"Google lehnt den Schlüssel ab ({e.code}): {leib}")
    except Exception as e:
        raise RuntimeError(f"Stimmenliste nicht abrufbar: {e}")

    alle = [v.get("name", "") for v in daten.get("voices", [])]
    hd = sorted(n for n in alle if "Chirp3-HD" in n)
    if wunsch:
        for n in alle:
            if n == wunsch or n.endswith("-" + wunsch):
                return n, "Chirp3-HD" in n
        print(f"  '{wunsch}' nicht gefunden.")
        if hd:
            print("  Verfügbare HD-Stimmen: "
                  + ", ".join(n.split("-")[-1] for n in hd[:14]))
    if hd:
        return hd[0], True
    andere = sorted(n for n in alle if "Neural2" in n) or sorted(alle)
    if andere:
        return andere[0], False
    raise RuntimeError(f"keine Stimme für {locale} gefunden")


def ssml_google(paket):
    """Chirp 3 HD kennt kein <break>, aber <p> und <s>.
       Das Modell setzt die Pausen dann selbst — meist natürlicher."""
    out, puffer = [], []
    for art, txt in paket:
        satz = "<s>" + xml_escape(txt) + "</s>"
        if art == "h":
            if puffer:
                out.append("<p>" + "".join(puffer) + "</p>")
                puffer = []
            out.append("<p>" + satz + "</p>")
        else:
            puffer.append(satz)
    if puffer:
        out.append("<p>" + "".join(puffer) + "</p>")
    return "<speak>" + "".join(out) + "</speak>"


def google_sprechen(ssml, key, stimme, locale):
    leib = json.dumps({
        "input": {"ssml": ssml},
        "voice": {"languageCode": locale, "name": stimme},
        "audioConfig": {"audioEncoding": "MP3"}
    }).encode("utf-8")
    antwort = post(f"{GOOGLE_BASIS}/text:synthesize?key={key}", leib,
                   {"Content-Type": "application/json; charset=utf-8"})
    roh = json.loads(antwort.decode("utf-8")).get("audioContent")
    if not roh:
        raise RuntimeError("Google liefert kein Audio zurück")
    return base64.b64decode(roh)


# ══════════════════════════════════════════════════════════════
#  Kosten
# ══════════════════════════════════════════════════════════════

def kosten(engine, zeichen, minuten):
    """Grobe Schätzung in US-Dollar. Preise Stand August 2026."""
    if engine == "edge":
        return 0.0, "gratis"
    if engine == "azure":
        frei = 500_000
        if zeichen <= frei:
            return 0.0, f"im Gratiskontingent ({zeichen:,}/{frei:,} Zeichen)".replace(",", ".")
        return (zeichen - frei) / 1_000_000 * 22, "über dem Gratiskontingent"
    if engine == "openai":
        return minuten * 0.018, "rund 1,8 Cent pro Audiominute"
    if engine == "eleven":
        return zeichen / 1000 * 0.10, "10 Cent pro 1.000 Zeichen"
    if engine == "google":
        frei = 1_000_000
        if zeichen <= frei:
            rest = f"{frei - zeichen:,}".replace(",", ".")
            return 0.0, f"im Gratiskontingent — {rest} Zeichen bleiben diesen Monat"
        return (zeichen - frei) / 1_000_000 * 30, "über dem Gratiskontingent (30 $/Mio.)"
    return 0.0, ""


# ══════════════════════════════════════════════════════════════
#  Hauptlauf
# ══════════════════════════════════════════════════════════════

def datei_waehlen():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        p = filedialog.askopenfilename(title="PDF auswählen",
                                       filetypes=[("PDF", "*.pdf")])
        root.destroy()
        return p or None
    except Exception:
        return None


def dauer(zeichen, tempo):
    f = 1.0
    m = re.match(r"([+-]?\d+)%", tempo or "+0%")
    if m:
        f = 1 + int(m.group(1)) / 100
    return max(1, round(zeichen / (900 * max(0.3, f))))


def balken(i, n):
    a = i / n
    return "█" * int(a * 28) + "·" * (28 - int(a * 28))


def schluessel(engine, args):
    umgebung = {"azure": "AZURE_SPEECH_KEY", "openai": "OPENAI_API_KEY",
                "eleven": "ELEVENLABS_API_KEY", "google": "GOOGLE_TTS_KEY"}
    if engine == "edge":
        return ""
    key = args.key or os.environ.get(umgebung[engine], "")
    if not key:
        print(f"\n  Für --engine {engine} brauche ich einen Schlüssel.")
        print(f"    Windows:  setx {umgebung[engine]} dein-schluessel")
        print(f"    macOS:    export {umgebung[engine]}=dein-schluessel")
        print(f"    oder:     --key dein-schluessel")
        return None
    return key


async def lauf(args):
    pfad = args.pdf or datei_waehlen()
    if not pfad:
        print("Keine Datei ausgewählt.")
        return 1
    pfad = Path(pfad).expanduser()
    if not pfad.is_file():
        print(f"Nicht gefunden: {pfad}")
        return 1

    von = bis = None
    if args.seiten:
        m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", args.seiten)
        if not m:
            print("--seiten erwartet etwas wie  12-40  oder  7")
            return 1
        von = int(m.group(1))
        bis = int(m.group(2)) if m.group(2) else von

    k = bau_sprache(args.sprache)
    filtern = not args.alles_vorlesen
    engine = args.engine

    key = schluessel(engine, args)
    if key is None:
        return 1
    region = args.region or os.environ.get("AZURE_SPEECH_REGION", "westeurope")
    anweisung = args.anweisung or ANWEISUNG[args.sprache]

    if engine == "azure":
        stimme, echt = azure_stimme_waehlen(key, region, k)
        zeigename = stimme + ("" if echt else "  (kein HD verfügbar)")
        max_zeichen = 1700
    elif engine == "openai":
        stimme = args.stimme or k["openai"]
        zeigename = f"{stimme} (OpenAI)"
        max_zeichen = 1400
    elif engine == "google":
        try:
            stimme, echt = google_stimme_waehlen(key, k["locale"], args.stimme)
        except RuntimeError as e:
            print(f"  {e}")
            return 1
        zeigename = stimme + ("" if echt else "   (kein Chirp 3 HD — ausgewichen)")
        max_zeichen = 1600
        if args.tempo != "+0%":
            print("  Hinweis: Chirp 3 HD kennt kein Tempo — --tempo wird ignoriert.")
    elif engine == "eleven":
        try:
            stimme, name = eleven_stimme_waehlen(key, args.stimme)
        except RuntimeError as e:
            print(f"  {e}")
            return 1
        zeigename = f"{name} (ElevenLabs)"
        max_zeichen = 2400
    else:
        stimme = k["edge"]
        zeigename = stimme
        max_zeichen = 2200

    print(f"\n  Datei    {pfad.name}")
    print(f"  Sprache  {k['name']}")
    print(f"  Engine   {ENGINES[engine]}")
    print(f"  Stimme   {zeigename}")
    print(f"  Filter   {'an' if filtern else 'aus'}\n")

    print("  Text wird ausgelesen …")
    t0 = time.time()
    einheiten, leer, ocr_da, gesamt, geschnitten, anhang = text_holen(
        str(pfad), von, bis, args.spalten, args.ocr, filtern, k, args.sprache)

    if not einheiten:
        print("\n  In dieser PDF steckt kein lesbarer Text.")
        if not ocr_da:
            print("  Vermutlich ein Scan. Für OCR zusätzlich:")
            print("    pip install pytesseract pillow   + Tesseract-Programm")
        return 1

    ueber = sum(1 for _, a, _ in einheiten if a == "h")
    zeichen = sum(len(t) for _, _, t in einheiten)
    pakete = paketieren(einheiten, k, max_zeichen)
    minuten = dauer(zeichen, args.tempo)

    print(f"  {len(einheiten)-ueber} Sätze, {ueber} Überschriften, "
          f"{format(zeichen, ',').replace(',', '.')} Zeichen")
    print(f"  Hördauer ~{minuten} min in {len(pakete)} Blöcken")
    if filtern and geschnitten:
        print(f"  {geschnitten} Belege, Fußnoten und Verweise entfernt"
              + (" (inkl. Literaturverzeichnis)" if anhang else ""))
    if leer:
        print("  Ohne Text übersprungen: Seite "
              + ", ".join(str(x) for x in leer[:8]) + (" …" if len(leer) > 8 else ""))
    print(f"  Gelesen in {time.time()-t0:.1f} s")

    preis, erklaerung = kosten(engine, zeichen, minuten)
    if preis > 0:
        print(f"\n  Geschätzte Kosten: ~{preis:.2f} USD  ({erklaerung})")
        if preis >= args.limit and not args.ja:
            antwort = input("  Weitermachen? [j/N] ").strip().lower()
            if antwort not in ("j", "ja", "y", "yes"):
                print("  Abgebrochen.")
                return 0
    elif engine == "azure":
        print(f"  Kosten: {erklaerung}")
    print()

    if args.txt:
        ziel_txt = Path(args.txt) if isinstance(args.txt, str) else pfad.with_suffix(".txt")
        with open(ziel_txt, "w", encoding="utf-8") as f:
            for _, art, t in einheiten:
                f.write(("\n\n## " + t + "\n\n") if art == "h" else (t + " "))
        print(f"  Text gesichert: {ziel_txt}")

    ziel = Path(args.ausgabe) if args.ausgabe else pfad.with_suffix(".mp3")
    print("  Sprachausgabe läuft …")
    t1 = time.time()
    audio = bytearray()

    for i, paket in enumerate(pakete, 1):
        try:
            if engine == "azure":
                audio += azure_sprechen(
                    ssml_bauen(paket, stimme, k["locale"], args.tempo), key, region)
            elif engine == "openai":
                audio += openai_sprechen(klartext(paket), key, stimme, anweisung)
            elif engine == "google":
                audio += google_sprechen(ssml_google(paket), key, stimme, k["locale"])
            elif engine == "eleven":
                audio += eleven_sprechen(klartext(paket), key, stimme)
            else:
                audio += await edge_sprechen(klartext(paket), stimme, args.tempo,
                                             args.lautstaerke, args.tonhoehe)
        except RuntimeError as e:
            print(f"\n\n  Abbruch bei Block {i} von {len(pakete)}: {e}")
            if audio:
                notfall = ziel.with_name(ziel.stem + "_unvollstaendig.mp3")
                notfall.write_bytes(bytes(audio))
                print(f"  Das bereits Gesprochene: {notfall}")
            return 1
        print(f"\r  [{balken(i, len(pakete))}] {i}/{len(pakete)}", end="", flush=True)

    ziel.write_bytes(bytes(audio))
    print(f"\n\n  Fertig in {time.time()-t1:.0f} s — {len(audio)/1048576:.1f} MB")
    print(f"  {ziel.resolve()}\n")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="Macht aus einer PDF ein Hörbuch.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ohne Argumente öffnet sich ein Dateidialog.")
    p.add_argument("pdf", nargs="?", help="Pfad zur PDF")
    p.add_argument("--sprache", choices=["de", "en"], default="de",
                   help="de = Deutsch (Standard), en = amerikanisches Englisch")
    p.add_argument("--engine", choices=["edge", "azure", "openai", "eleven", "google"],
                   default="edge", help="Sprachdienst (Standard: edge)")
    p.add_argument("--anweisung",
                   help="eigene Sprechanweisung (nur --engine openai)")
    p.add_argument("--stimme", help="Stimme überschreiben (openai / eleven / google)")
    p.add_argument("--key", help="API-Schlüssel (sonst aus Umgebungsvariable)")
    p.add_argument("--region", help="Azure-Region (Standard westeurope)")
    p.add_argument("--tempo", default="+0%", help="z. B. +10%% (edge und azure)")
    p.add_argument("--lautstaerke", default="+0%", help="nur edge")
    p.add_argument("--tonhoehe", default="+0Hz", help="nur edge")
    p.add_argument("--seiten", help="Seitenbereich, z. B. 12-40")
    p.add_argument("--ausgabe", help="Zieldatei (Standard: gleicher Name als .mp3)")
    p.add_argument("--spalten", choices=["auto", "1", "2"], default="auto")
    p.add_argument("--ocr", choices=["auto", "aus"], default="auto")
    p.add_argument("--txt", nargs="?", const=True, default=False,
                   help="bereinigten Text zusätzlich als .txt sichern")
    p.add_argument("--alles-vorlesen", action="store_true",
                   help="Fußnoten, Belege und Bildunterschriften mitlesen")
    p.add_argument("--limit", type=float, default=0.50,
                   help="ab diesen Kosten in USD wird nachgefragt (Standard 0.50)")
    p.add_argument("--ja", action="store_true", help="Kostenrückfrage überspringen")
    args = p.parse_args()

    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except AttributeError:
            pass
    try:
        sys.exit(asyncio.run(lauf(args)))
    except KeyboardInterrupt:
        print("\n  Abgebrochen.")
        sys.exit(130)


if __name__ == "__main__":
    main()
