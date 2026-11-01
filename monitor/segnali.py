"""Calcolo dei cinque segnali strutturali sugli articoli delle ultime 48 ore.

1. lunghezza anomala        (parole rispetto alla mediana della testata; indizi visibili se c'è paywall)
2. permanenza in homepage   (ore di presenza, rispetto alle abitudini della testata)
3. ripresa da altri locali  (articoli simili su testate di gruppi editoriali diversi)
4. popolarità su Reddit
5. divergenza dal nazionale (la storia non compare sulle testate nazionali)
"""
import csv
import logging
import math
import re
import statistics
from collections import defaultdict
from datetime import timedelta

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config, db

log = logging.getLogger(__name__)
GRUPPI_NON_GRUPPI = {"", "?", "indipendente", "independent", "nonprofit", "non profit"}


def chiave_gruppo(testata):
    g = (testata.get("gruppo") or "").split("/")[0].split("(")[0].strip().lower()
    return g if g not in GRUPPI_NON_GRUPPI else "t:" + testata["chiave"]


def _testo(a):
    return f"{a.get('titolo') or ''}. {a.get('titolo') or ''}. {(a.get('sommario') or '')[:400]}"


def _titolo_norm(t):
    return re.sub(r"[^a-z0-9áéíóúñ ]", "", (t or "").lower()).strip()


def carica_inviati():
    """Tutti i link già inviati: servono per la regola "nessun link due volte"."""
    if not config.INVIATI_CSV.exists():
        return []
    with open(config.INVIATI_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def calcola(con, testate):
    per_chiave = {t["chiave"]: t for t in testate}
    ora = db.adesso()
    inizio = db.iso(ora - timedelta(hours=config.FINESTRA_ORE))
    primo_giro = {r["testata"]: r["t"] for r in con.execute("SELECT testata, MIN(ts) t FROM giri GROUP BY testata")}
    esclusi_url = re.compile(config.ESCLUSIONI_URL, re.I)
    esclusi_titolo = re.compile(config.ESCLUSIONI_TITOLO, re.I)

    # ------------------------------------------------------------ articoli nella finestra
    finestra = []
    for r in con.execute("SELECT * FROM articoli WHERE prima_vista >= ? OR pubblicato >= ?", (inizio, inizio)):
        a = dict(r)
        t = per_chiave.get(a["testata"])
        if not t or not a.get("titolo"):
            continue
        if a["pubblicato"] and a["pubblicato"] < inizio:
            continue
        if not a["pubblicato"] and a["prima_vista"] == primo_giro.get(a["testata"]):
            continue  # visto al primo giro della testata senza data: non sappiamo se è recente
        if a["ap"] or esclusi_url.search(a["url"]) or esclusi_titolo.search(a["titolo"]):
            continue
        a["t"] = t
        finestra.append(a)
    log.info("articoli nella finestra: %d", len(finestra))
    if not finestra:
        return [], {}

    # ------------------------------------------------------------ 1. lunghezza
    mediane = defaultdict(list)
    for r in con.execute("SELECT testata, parole, parole_fonte FROM articoli WHERE parole IS NOT NULL"):
        mediane[(r["testata"], r["parole_fonte"] == "visibile")].append(r["parole"])
    mediane = {k: statistics.median(v) for k, v in mediane.items() if len(v) >= config.LUNGHEZZA_CAMPIONE_MINIMO}

    # ------------------------------------------------------------ 2. homepage
    home = {r["url"]: dict(r) for r in con.execute("SELECT * FROM homepage")}
    soglie_home = {}
    per_testata = defaultdict(list)
    for h in home.values():
        per_testata[h["testata"]].append(h["avvistamenti"])
    for k, v in per_testata.items():
        v.sort()
        soglie_home[k] = v[int(len(v) * 0.8)] if len(v) >= 20 else None

    # ------------------------------------------------------------ 3 e 5. somiglianze
    inizio_naz = db.iso(ora - timedelta(hours=72))
    nazionali = [dict(r) for r in con.execute("SELECT * FROM nazionali WHERE prima_vista >= ?", (inizio_naz,))]
    inviati = carica_inviati()
    limite_inviati = (ora - timedelta(days=14)).date().isoformat()
    recenti = [i for i in inviati if i.get("data", "") >= limite_inviati]
    testi = [_testo(a) for a in finestra] + [_testo(n) for n in nazionali] + [_testo(i) for i in recenti]
    vett = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, max_df=0.05, min_df=1)
    X = vett.fit_transform(testi)
    nL, nN = len(finestra), len(nazionali)
    XL, XN, XI = X[:nL], X[nL:nL + nN], X[nL + nN:]
    vicini = [[] for _ in range(nL)]
    max_naz = np.zeros(nL)
    segue = [None] * nL
    for s in range(0, nL, 1000):
        blocco = XL[s:s + 1000]
        sim = (blocco @ XL.T).toarray()
        for i, riga in enumerate(sim):
            idx = np.where(riga >= config.SIMILARITA_DOPPIONE_EMAIL)[0]
            vicini[s + i] = [(int(j), float(riga[j])) for j in idx if j != s + i]
        if nN:
            max_naz[s:s + 1000] = (blocco @ XN.T).toarray().max(axis=1)
        if XI.shape[0]:
            simi = (blocco @ XI.T).toarray()
            for i, riga in enumerate(simi):
                j = int(riga.argmax())
                if riga[j] >= config.SIMILARITA_STESSA_STORIA:
                    segue[s + i] = {**recenti[j], "somiglianza": float(riga[j])}

    # ------------------------------------------------------------ 4. Reddit
    reddit_url, reddit_titolo = {}, {}
    for r in con.execute("SELECT * FROM reddit WHERE id NOT LIKE '_segnaposto_%'"):
        valore = (r["punteggio"] or 0) + 2 * (r["commenti"] or 0)
        voce = (valore, r["subreddit"], r["punteggio"], r["commenti"])
        if r["url"] and valore > reddit_url.get(r["url"], (0,))[0]:
            reddit_url[r["url"]] = voce
        tn = _titolo_norm(r["titolo"])
        if len(tn) > 25 and valore > reddit_titolo.get(tn, (0,))[0]:
            reddit_titolo[tn] = voce

    # ------------------------------------------------------------ segnali per articolo
    for i, a in enumerate(finestra):
        t = a["t"]
        segnali = []

        # 1. lunghezza
        troncato = a.get("parole_fonte") == "visibile"
        med = mediane.get((a["testata"], troncato))
        if a.get("parole") and med:
            rapporto = a["parole"] / med
            if config.LUNGHEZZA_RAPPORTO <= rapporto <= config.LUNGHEZZA_RAPPORTO_MASSIMO:
                forza = 0.5 + 0.5 * min(1, (rapporto - config.LUNGHEZZA_RAPPORTO) / 1.7)
                nota = " (parte visibile)" if troncato else ""
                segnali.append(("lunghezza", forza, f"lungo ×{rapporto:.1f} rispetto al solito{nota} ({a['parole']} parole)"))
        if not any(s[0] == "lunghezza" for s in segnali) and a.get("paywall") and \
                (a.get("n_autori") or 0) >= 2 and (a.get("immagini") or 0) >= 4:
            segnali.append(("lunghezza", 0.5, f"indizi di pezzo importante sotto paywall "
                                              f"({a['n_autori']} firme, {a['immagini']} foto)"))

        # 2. homepage
        h = home.get(a["url"])
        if h:
            ore = h["avvistamenti"] * config.INTERVALLO_ORE
            soglia = soglie_home.get(a["testata"])
            if ore >= config.HOMEPAGE_ORE_MINIME and (soglia is None or h["avvistamenti"] >= soglia):
                forza = 0.5 + 0.5 * min(1, (ore - config.HOMEPAGE_ORE_MINIME) / 24)
                if h["avvistamenti_top"] >= 3:
                    forza = min(1, forza + 0.2)
                in_alto = f", in alto per {h['avvistamenti_top'] * config.INTERVALLO_ORE}h" if h["avvistamenti_top"] else ""
                segnali.append(("homepage", forza, f"{ore}h in homepage{in_alto}"))

        # 3. ripresa
        mio_gruppo = chiave_gruppo(t)
        altri = {}
        for j, s in vicini[i]:
            if s < config.SIMILARITA_STESSA_STORIA or s >= config.SIMILARITA_COPIA:
                continue  # troppo diverso, oppure lo stesso articolo ripubblicato
            b = finestra[j]
            g = chiave_gruppo(b["t"])
            if g != mio_gruppo and g not in altri:
                altri[g] = b
        a["ripresa"] = list(altri.values())
        altri_stati = {b["t"]["stato"] for b in altri.values()} - {t["stato"]}
        if len(altri) >= config.RIPRESA_ALTRE_TESTATE:
            forza = 0.5 + 0.5 * min(1, (len(altri) - config.RIPRESA_ALTRE_TESTATE) / 4)
            stati = sorted({b["t"]["stato"] for b in altri.values()} - {t["stato"]})
            fuori = f", anche fuori stato ({', '.join(stati[:4])})" if stati else ""
            segnali.append(("ripresa", forza, f"ripresa da {len(altri)} testate indipendenti{fuori}"))

        # 4. Reddit
        voce = reddit_url.get(a["url"]) or reddit_titolo.get(_titolo_norm(a["titolo"]))
        if voce and voce[0] >= config.REDDIT_PUNTEGGIO:
            forza = 0.5 + 0.5 * min(1, (math.log10(voce[0]) - math.log10(config.REDDIT_PUNTEGGIO)) / 1.2)
            numeri = f"{voce[2]} upvote, {voce[3]} commenti" if voce[3] else "fra i più votati della settimana"
            segnali.append(("reddit", forza, f"Reddit r/{voce[1]}: {numeri}"))

        # 5. divergenza dal nazionale
        if nN and max_naz[i] < config.SIMILARITA_NAZIONALE and len(altri_stati) < config.STATI_PER_NAZIONALE:
            forza = 1.0 if any(s[0] == "ripresa" for s in segnali) else 0.5
            segnali.append(("nazionale", forza, "assente dai nazionali"))

        a["segnali"] = segnali
        a["strutturale"] = min(1.0, sum(s[1] for s in segnali) / 3)
        a["segue"] = segue[i]
        a["vicini"] = vicini[i]

    statistiche = {"finestra": nL, "nazionali": nN,
                   "con_segnali": sum(len(a["segnali"]) >= config.SEGNALI_MINIMI for a in finestra)}
    return finestra, statistiche


def _forza(a, nome):
    return max((s[1] for s in a["segnali"] if s[0] == nome), default=0)


def scegli_candidati(finestra, gia_inviati):
    """Candidati per il giudizio: almeno 2 segnali, mai un link già inviato, una sola voce per storia.

    Le liste si alternano: punteggio complessivo, lunghezza e permanenza in homepage. La ripresa da
    altre testate premia spesso la cronaca e gli sviluppi minori; lunghezza e homepage indicano
    più spesso un lavoro di racconto."""
    idonei = [a for a in finestra
              if len(a["segnali"]) >= config.SEGNALI_MINIMI and a["url"] not in gia_inviati
              # stesso articolo già inviato sotto un altro indirizzo: non è uno sviluppo, è un doppione
              and not (a["segue"] and a["segue"]["somiglianza"] >= config.SIMILARITA_COPIA)]
    classifiche = [
        sorted(idonei, key=lambda a: a["strutturale"], reverse=True),
        sorted((a for a in idonei if _forza(a, "lunghezza")),
               key=lambda a: (_forza(a, "lunghezza"), a["strutturale"]), reverse=True),
        sorted((a for a in idonei if _forza(a, "homepage")),
               key=lambda a: (_forza(a, "homepage"), a["strutturale"]), reverse=True),
    ]
    posizione = {id(a): k for k, a in enumerate(finestra)}
    scelti, coperti = [], set()
    cursori = [0] * len(classifiche)
    while len(scelti) < config.CANDIDATI_GIUDIZIO and any(c < len(l) for c, l in zip(cursori, classifiche)):
        for n, lista in enumerate(classifiche):
            while cursori[n] < len(lista):
                a = lista[cursori[n]]
                cursori[n] += 1
                k = posizione[id(a)]
                if k in coperti:
                    continue
                scelti.append(a)
                coperti.add(k)
                coperti.update(j for j, _ in a["vicini"])   # stessa vicenda, anche raccontata con altre parole
                break
            if len(scelti) >= config.CANDIDATI_GIUDIZIO:
                break
    return scelti
