"""Giro di raccolta (ogni 2 ore): articoli nuovi, fotografia delle homepage, nazionali.

Nessun modello coinvolto: solo richieste HTTP e lettura di metadati.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import config, db, estrazione, rete

log = logging.getLogger(__name__)


def leggi_data(testo):
    if not testo:
        return None
    testo = str(testo).strip()
    try:
        d = datetime.fromisoformat(testo.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(testo)
        except (TypeError, ValueError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _google_news(t):
    dominio = t["dominio"]
    r = rete.scarica_google_news(rete.google_news_url(f"site:{dominio} when:2d"))
    if r is None or not r.ok:
        return []
    return estrazione.da_feed(r.content, "google_news")


def _completa_articolo(a):
    """Aggiunge all'articolo i dettagli letti dalla sua pagina (lunghezza, foto, firme, paywall)."""
    r = rete.scarica(a["url"])
    if r is None or not r.ok:
        return
    try:
        d = estrazione.dettagli_articolo(r.text)
    except Exception as e:  # pagina malformata: si tiene quello che si sa dal feed
        log.debug("dettagli %s: %s", a["url"], e)
        return
    if a.get("parole_fonte") == "feed" and (d["parole"] or 0) < a.get("parole", 0):
        d["parole"], d["parole_fonte"] = a["parole"], "feed"
    for k, v in d.items():
        if v not in (None, ""):
            if k in ("titolo", "sommario") and a.get(k) and len(a[k]) >= len(str(v)):
                continue
            a[k] = v
        else:
            a.setdefault(k, v)
    data = leggi_data(a.get("pubblicato"))
    a["pubblicato"] = data.isoformat() if data else None
    a["dettagli"] = 1
    # Pagina che dichiara come originale un altro sito (NPR, AP, CalMatters...): è un pezzo ripubblicato
    canonico, proprio = a.pop("canonico", ""), rete.host(a["url"])
    if canonico and canonico != proprio and not canonico.endswith("." + proprio) \
            and not proprio.endswith("." + canonico):
        a["ap"] = 1


def raccogli_testata(t, conosciuti, scadenza=None):
    esito = {"testata": t["chiave"], "articoli": [], "homepage": [], "homepage_ok": 0,
             "metodo": t.get("metodo", ""), "errore": ""}
    if scadenza and time.time() > scadenza:
        esito["errore"] = "rimandata"
        return esito
    articoli = []
    metodo = t.get("metodo", "")
    if metodo in ("feed", "feed_scoperto") and t.get("feed_ok"):
        r = rete.scarica(t["feed_ok"])
        if r is not None and r.ok:
            articoli = estrazione.da_feed(r.content, "feed", base=t["url_homepage"])
    elif metodo == "sitemap" and t.get("sitemap_news"):
        r = rete.scarica(t["sitemap_news"])
        if r is not None and r.ok:
            articoli = estrazione.da_sitemap(r.content)

    # Homepage: fotografia per il segnale di permanenza, e fonte di articoli per chi non ha feed
    if metodo != "google_news":
        r = rete.scarica(t["url_homepage"])
        if r is not None and r.ok and len(r.text) > 2000:
            esito["homepage_ok"] = 1
            esito["homepage"] = estrazione.link_homepage(r.text, r.url, t["dominio"])
    per_url = {a["url"]: a for a in articoli}
    for url, testo in esito["homepage"]:
        if url not in per_url:
            per_url[url] = {"url": url, "titolo": testo, "fonte": "homepage"}
        elif testo and not per_url[url].get("titolo"):
            per_url[url]["titolo"] = testo

    # Ripiego su Google News per le testate bloccate o con feed rotto
    if not articoli and (metodo == "google_news" or not esito["homepage_ok"]):
        for a in _google_news(t):
            per_url.setdefault(a["url"], a)
        esito["metodo"] = "google_news"
        if not per_url:
            esito["errore"] = "nessun articolo"

    limite = datetime.now(timezone.utc) - timedelta(hours=72)
    nuovi = []
    for a in per_url.values():
        d = leggi_data(a.get("pubblicato"))
        if d and d < limite:
            continue
        a["pubblicato"] = d.isoformat() if d else None
        if a["url"] not in conosciuti:
            nuovi.append(a)

    # Pagine dei nuovi articoli: prima quelli in homepage, poi il resto nell'ordine del feed
    in_homepage = {u for u, _ in esito["homepage"]}
    nuovi.sort(key=lambda a: a["url"] not in in_homepage)
    da_leggere = [a for a in nuovi[:config.MAX_PAGINE_ARTICOLO_PER_TESTATA] if a["fonte"] != "google_news"]
    if scadenza and time.time() > scadenza:
        da_leggere = []   # tempo finito: si salvano gli articoli senza leggerne le pagine
    with ThreadPoolExecutor(max_workers=4) as pool:   # al massimo 4 richieste contemporanee per testata
        list(pool.map(_completa_articolo, da_leggere))
    esito["articoli"] = nuovi
    return esito


def salva(con, esito, ts):
    campi = ["url", "testata", "titolo", "sommario", "autori", "n_autori", "sezione", "pubblicato",
             "prima_vista", "fonte", "parole", "parole_fonte", "immagini", "paywall", "ap", "dettagli"]
    for a in esito["articoli"]:
        a = {**a, "testata": esito["testata"], "prima_vista": ts}
        con.execute(f"INSERT OR IGNORE INTO articoli ({','.join(campi)}) VALUES ({','.join('?' * len(campi))})",
                    [a.get(c) for c in campi])
    for pos, (url, _) in enumerate(esito["homepage"]):
        top = int(pos < config.HOMEPAGE_TOP)
        con.execute("""
            INSERT INTO homepage (url, testata, avvistamenti, avvistamenti_top, posizione_migliore, prima, ultima)
            VALUES (?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET avvistamenti = avvistamenti + 1,
                avvistamenti_top = avvistamenti_top + excluded.avvistamenti_top,
                posizione_migliore = MIN(posizione_migliore, excluded.posizione_migliore),
                ultima = excluded.ultima""", (url, esito["testata"], top, pos, ts, ts))
    con.execute("INSERT INTO giri VALUES (?, ?, ?, ?, ?, ?)",
                (ts, esito["testata"], esito["metodo"], len(esito["articoli"]), esito["homepage_ok"], esito["errore"]))


def raccogli_nazionali(con, ts):
    fonti = [(nome, url) for nome, url in config.NAZIONALI_FEED.items()]
    fonti += [(d, rete.google_news_url(f"site:{d} when:2d")) for d in config.NAZIONALI_GOOGLE_NEWS]
    n = 0
    for nome, url in fonti:
        r = rete.scarica_google_news(url) if "news.google" in url else rete.scarica(url)
        if r is None or not r.ok:
            log.warning("nazionale non raggiungibile: %s", nome)
            continue
        fonte = "google_news" if "news.google" in url else "feed"
        for a in estrazione.da_feed(r.content, fonte):
            n += con.execute("INSERT OR IGNORE INTO nazionali VALUES (?, ?, ?, ?, ?)",
                             (a["url"], nome, a["titolo"], a.get("sommario", ""), ts)).rowcount
    return n


def giro(limite_testate=None):
    con = db.connetti()
    ts = db.iso(db.adesso())
    testate = rete.carica_testate()[:limite_testate]
    # Prima le testate lette meno di recente: quelle rimandate dal giro precedente passano davanti
    ultima = {r["testata"]: r["t"] for r in con.execute(
        "SELECT testata, MAX(ts) t FROM giri WHERE errore != 'rimandata' GROUP BY testata")}
    testate.sort(key=lambda t: ultima.get(t["chiave"], ""))
    scadenza = time.time() + config.DURATA_MASSIMA_GIRO
    conosciuti = {}
    for riga in con.execute("SELECT testata, url FROM articoli"):
        conosciuti.setdefault(riga["testata"], set()).add(riga["url"])

    totale, ok_home, errori, rimandate = 0, 0, 0, 0
    with ThreadPoolExecutor(max_workers=config.WORKERS) as pool:
        futuri = {pool.submit(raccogli_testata, t, conosciuti.get(t["chiave"], set()), scadenza): t for t in testate}
        for f in as_completed(futuri):
            try:
                esito = f.result()
            except Exception as e:
                log.warning("errore su %s: %s", futuri[f]["nome"], e)
                errori += 1
                continue
            if esito["errore"] == "rimandata":
                rimandate += 1
                continue
            salva(con, esito, ts)
            totale += len(esito["articoli"])
            ok_home += esito["homepage_ok"]
    naz = raccogli_nazionali(con, ts)
    db.pulisci(con)
    con.commit()
    log.info("giro %s: %d testate (%d rimandate), %d articoli nuovi, %d homepage lette, %d errori, %d nazionali",
             ts, len(testate), rimandate, totale, ok_home, errori, naz)
    return {"articoli_nuovi": totale, "homepage_lette": ok_home, "errori": errori, "nazionali": naz}
