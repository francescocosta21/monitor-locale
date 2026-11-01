"""Estrazione di articoli da feed, sitemap, homepage e pagine degli articoli."""
import html
import json
import re
import time
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from . import rete

RE_PAROLE = re.compile(r"\w+", re.UNICODE)
# Agenzie e contenuti distribuiti a più testate: non sono storie della testata che li pubblica
RE_DATELINE_AP = re.compile(r"\((AP|Reuters)\)\s*[—–-]")
RE_AP = re.compile(r"(\bAssociated Press\b|^AP$|\bReuters\b|\bCNN Newsource\b|\bNPR\b|"
                   r"\bStateline\b|\bKFF Health News\b|\bThe Conversation\b|\bScripps News\b|\bGray News\b|"
                   r"\bNexstar Media Wire\b|\bStacker\b|\bBloomberg\b|\bThe Washington Post\b|\bNew York Times\b)", re.I)
SEGMENTI_NON_ARTICOLO = {
    "tag", "tags", "topic", "topics", "author", "authors", "category", "categories", "section",
    "search", "video", "videos", "podcast", "podcasts", "newsletter", "newsletters", "subscribe",
    "about", "contact", "privacy", "terms", "advertise", "account", "login", "e-edition", "eedition",
    "weather", "obituaries", "classifieds", "jobs", "events", "calendar", "games", "puzzles", "shop",
    "services", "members-only", "correction", "corrections", "gallery", "galleries", "photos", "sponsored",
}


def parole(testo):
    return len(RE_PAROLE.findall(testo or ""))


def testo_pulito(frammento):
    return html.unescape(BeautifulSoup(frammento or "", "lxml").get_text(" ", strip=True))


def data_iso(struttura):
    if not struttura:
        return None
    try:
        return datetime.fromtimestamp(time.mktime(struttura), tz=timezone.utc).isoformat()
    except (OverflowError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------- feed e Google News

def da_feed(contenuto, fonte, base=None):
    feed = feedparser.parse(contenuto)
    articoli = []
    for e in feed.entries:
        url = rete.normalizza(e.get("link", ""), base)
        if not url:
            continue
        titolo = testo_pulito(e.get("title", ""))
        if fonte == "google_news":
            titolo = re.sub(r"\s+[-–|]\s+[^-–|]+$", "", titolo)  # toglie " - Nome testata"
        sommario = testo_pulito(e.get("summary", ""))[:600]
        corpo = " ".join(testo_pulito(c.get("value", "")) for c in e.get("content", []) or [])
        autori = [a.get("name", "") for a in e.get("authors", []) if a.get("name")] or \
                 ([e.get("author")] if e.get("author") else [])
        a = {
            "url": url, "titolo": titolo, "sommario": sommario if fonte != "google_news" else "",
            "autori": ", ".join(autori), "n_autori": len(autori),
            "sezione": ", ".join(t.get("term", "") for t in e.get("tags", [])[:3]),
            "pubblicato": data_iso(e.get("published_parsed") or e.get("updated_parsed")),
            "fonte": fonte, "ap": int(bool(RE_AP.search(", ".join(autori)) or RE_DATELINE_AP.search(sommario[:200]))),
        }
        n = parole(corpo)
        if n > 150:
            a["parole"], a["parole_fonte"] = n, "feed"
        articoli.append(a)
    return articoli


# ---------------------------------------------------------------- sitemap news

def da_sitemap(xml):
    soup = BeautifulSoup(xml, "xml")
    articoli = []
    for u in soup.find_all("url"):
        loc = u.find("loc")
        url = rete.normalizza(loc.get_text(strip=True)) if loc else None
        if not url:
            continue
        titolo = u.find(["news:title", "title"])
        data = u.find(["news:publication_date", "publication_date", "lastmod"])
        articoli.append({
            "url": url, "titolo": titolo.get_text(strip=True) if titolo else "",
            "pubblicato": data.get_text(strip=True) if data else None, "fonte": "sitemap",
        })
    return articoli


# ---------------------------------------------------------------- homepage

def sembra_articolo(url, dominio):
    u = rete.urlparse(url)
    if rete.host(url) != dominio and not rete.host(url).endswith("." + dominio):
        return False
    segmenti = [s for s in u.path.lower().split("/") if s]
    if not segmenti or segmenti[0] in SEGMENTI_NON_ARTICOLO:
        return False
    if re.search(r"/(image|video|gallery|collection)_[0-9a-f-]{8,}", u.path):
        return False
    ultimo = segmenti[-1]
    ha_slug = ultimo.count("-") >= 3
    ha_numero = bool(re.search(r"\d{4,}", u.path)) or bool(re.search(r"/20\d\d/", u.path))
    return (ha_slug or ha_numero) and len(segmenti) >= 1


def link_homepage(pagina, base, dominio):
    """Link agli articoli nell'ordine in cui compaiono nella pagina, con il testo del link come titolo."""
    soup = BeautifulSoup(pagina, "lxml")
    for rimuovi in soup.select("nav, footer, header [role=navigation]"):
        rimuovi.decompose()
    visti, risultato = set(), []
    for a in soup.find_all("a", href=True):
        url = rete.normalizza(a["href"], base)
        if not url or url in visti or not sembra_articolo(url, dominio):
            continue
        testo = html.unescape(a.get_text(" ", strip=True))
        if len(testo) < 20:
            testo = ""
        visti.add(url)
        risultato.append((url, testo))
    return risultato


# ---------------------------------------------------------------- pagina dell'articolo

def _json_ld(soup):
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            dati = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        coda = dati if isinstance(dati, list) else [dati]
        while coda:
            d = coda.pop()
            if isinstance(d, list):
                coda.extend(d)
                continue
            if not isinstance(d, dict):
                continue
            if "@graph" in d:
                coda.extend(d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]])
            tipo = d.get("@type", "")
            tipi = tipo if isinstance(tipo, list) else [tipo]
            if any("Article" in str(t) or "Posting" in str(t) for t in tipi):
                return d
    return {}


def _autori(ld, soup):
    a = ld.get("author")
    nomi = []
    for x in (a if isinstance(a, list) else [a]):
        if isinstance(x, dict) and x.get("name"):
            nomi.append(str(x["name"]))
        elif isinstance(x, str):
            nomi.append(x)
    if not nomi:
        nomi = [m.get("content", "") for m in soup.find_all("meta", attrs={"name": "author"}) if m.get("content")]
    return [n for n in nomi if n and len(n) < 80]


def dettagli_articolo(pagina):
    """Legge ciò che è visibile anche sotto paywall: metadati, sommario, testo in chiaro, foto, firme."""
    soup = BeautifulSoup(pagina, "lxml")
    ld = _json_ld(soup)
    meta = lambda **k: (soup.find("meta", attrs=k) or {}).get("content")  # noqa: E731

    corpo = soup.find("article") or soup.find(attrs={"itemprop": "articleBody"}) or soup.find("main") or soup
    paragrafi = [p.get_text(" ", strip=True) for p in corpo.find_all("p")]
    visibili = parole(" ".join(p for p in paragrafi if len(p) > 40))

    conteggio, fonte = None, None
    wc = ld.get("wordCount")
    try:
        wc = int(str(wc).replace(",", "")) if wc else None
    except ValueError:
        wc = None
    if wc and wc > 100:
        conteggio, fonte = wc, "wordCount"
    elif ld.get("articleBody") and parole(ld["articleBody"]) > 100:
        conteggio, fonte = parole(ld["articleBody"]), "articleBody"
    elif visibili > 100:
        conteggio, fonte = visibili, "testo"

    gratuito = str(ld.get("isAccessibleForFree", "")).lower()
    paywall = gratuito in ("false", "0") or bool(soup.select_one(
        "[class*=paywall], [id*=paywall], [class*=meter-], [class*=subscriber-only], [class*=piano-]"))
    if paywall and fonte == "testo":
        fonte = "visibile"   # testo troncato dal paywall: il conteggio è un minimo

    immagini = len(corpo.find_all("figure")) or len(corpo.find_all("img"))
    canonico = (soup.find("link", rel="canonical") or {}).get("href") or meta(property="og:url") or ""
    autori = _autori(ld, soup)
    sezione = ld.get("articleSection") or meta(property="article:section") or ""
    if isinstance(sezione, list):
        sezione = ", ".join(map(str, sezione[:3]))
    return {
        "titolo": html.unescape(str(ld.get("headline") or meta(property="og:title") or "")),
        "sommario": html.unescape(str(ld.get("description") or meta(property="og:description")
                                      or meta(name="description") or ""))[:600],
        "autori": ", ".join(autori), "n_autori": len(autori),
        "sezione": str(sezione)[:120],
        "pubblicato": ld.get("datePublished") or meta(property="article:published_time"),
        "parole": conteggio, "parole_fonte": fonte, "immagini": immagini,
        "paywall": int(paywall),
        "ap": int(bool(any(RE_AP.search(n) for n in autori) or RE_DATELINE_AP.search(" ".join(paragrafi[:2])))),
        "canonico": rete.host(canonico) if canonico.startswith("http") else "",
    }
