"""Richieste HTTP, normalizzazione degli URL e lettura della lista delle testate."""
import csv
import re
import threading
import time
import warnings
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlparse, urlunparse

import requests

from . import config

warnings.filterwarnings("ignore")

_locale = threading.local()
_google_lock = threading.Lock()
_google_ultimo = [0.0]
PARAMETRI_TRACCIAMENTO = re.compile(r"^(utm_|fbclid|gclid|mc_|cmpid|ref|src|share|taid|smid|output)", re.I)


def sessione():
    if not hasattr(_locale, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": config.UA, "Accept-Language": "en-US,en;q=0.9"})
        _locale.s = s
    return _locale.s


def scarica(url, timeout=config.TIMEOUT):
    """Restituisce la risposta o None. Non solleva eccezioni: una testata che non risponde non ferma il giro."""
    try:
        return sessione().get(url, timeout=timeout)
    except requests.RequestException:
        return None


def scarica_google_news(url):
    """Google News tollera male le raffiche: al massimo una richiesta ogni 0,7 secondi."""
    with _google_lock:
        attesa = 0.7 - (time.time() - _google_ultimo[0])
        if attesa > 0:
            time.sleep(attesa)
        _google_ultimo[0] = time.time()
    return scarica(url)


def google_news_url(query, lingua="en"):
    if lingua == "it":
        return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=it&gl=IT&ceid=IT:it"
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"


def host(url):
    h = urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def chiave_testata(url_homepage):
    """Stessa chiave usata in tools/unisci_testate.py: dominio senza www più percorso."""
    u = urlparse(url_homepage.strip())
    return host(url_homepage) + u.path.rstrip("/").lower()


def normalizza(url, base=None):
    if base:
        url = urljoin(base, url)
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https"):
        return None
    query = [(k, v) for k, v in parse_qsl(u.query) if not PARAMETRI_TRACCIAMENTO.match(k)]
    percorso = u.path.rstrip("/") or "/"
    return urlunparse(("https", host(url), percorso, "", urlencode(query), ""))


def carica_testate():
    with open(config.TESTATE_CSV, newline="", encoding="utf-8") as f:
        righe = [r for r in csv.DictReader(f) if r.get("includi", "si").strip().lower() != "no"]
    for r in righe:
        r["chiave"] = chiave_testata(r["url_homepage"])
        r["dominio"] = host(r["url_homepage"])
    return righe
