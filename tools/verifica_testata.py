"""Verifica una o più testate: homepage raggiungibile e feed RSS/Atom disponibile.

Uso: .venv/bin/python tools/verifica_testata.py https://www.example.com [altri url...]
Stampa una riga JSON per URL: status, url finale, feed trovati (con numero di elementi).
"""
import json
import sys
import warnings
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
PERCORSI_FEED = [
    "/feed/", "/rss", "/rss.xml", "/feed.xml", "/index.rss",
    "/arc/outboundfeeds/rss/?outputType=xml",          # Arc (WaPo, Alden, molti TV)
    "/search/?f=rss&t=article&l=50&s=start_time&sd=desc",  # BLOX / TownNews (Lee, molti locali)
    "/news/index.rss",
]


def conta_elementi(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if r.status_code != 200:
            return 0
        return len(feedparser.parse(r.content).entries)
    except requests.RequestException:
        return 0


def verifica(url):
    esito = {"url": url, "status": None, "url_finale": None, "feed": []}
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    except requests.RequestException as e:
        esito["errore"] = type(e).__name__
        return esito
    esito["status"] = r.status_code
    esito["url_finale"] = r.url
    candidati = []
    if r.ok:
        soup = BeautifulSoup(r.text, "lxml")
        for link in soup.find_all("link", rel="alternate"):
            if "rss" in (link.get("type") or "") or "atom" in (link.get("type") or ""):
                candidati.append(urljoin(r.url, link.get("href")))
    candidati += [urljoin(r.url, p) for p in PERCORSI_FEED]
    visti = set()
    for c in candidati:
        if c in visti:
            continue
        visti.add(c)
        n = conta_elementi(c)
        if n > 0:
            esito["feed"].append({"url": c, "elementi": n})
            if len(esito["feed"]) >= 2:
                break
    return esito


if __name__ == "__main__":
    for u in sys.argv[1:]:
        print(json.dumps(verifica(u), ensure_ascii=False), flush=True)
