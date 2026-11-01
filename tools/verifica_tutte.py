"""Verifica tutte le testate di data/testate.csv e scrive data/verifica_usa.csv.

Per ogni testata controlla, in ordine: il feed indicato, i feed scopribili dalla homepage,
la sitemap news (da robots.txt). Pensato per girare su GitHub Actions (IP USA).

Uso: python tools/verifica_tutte.py
"""
import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verifica_testata import UA, conta_elementi, verifica  # noqa: E402

BASE = Path(__file__).resolve().parent.parent


def sitemap_news(homepage):
    """Cerca in robots.txt una sitemap che contenga 'news'; restituisce (url, n. url) o None."""
    try:
        r = requests.get(urljoin(homepage, "/robots.txt"), headers={"User-Agent": UA}, timeout=15)
    except requests.RequestException:
        return None
    if not r.ok:
        return None
    for riga in r.text.splitlines():
        if riga.lower().startswith("sitemap:") and "news" in riga.lower():
            url = riga.split(":", 1)[1].strip()
            try:
                s = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            except requests.RequestException:
                continue
            n = len(re.findall(r"<loc>", s.text)) if s.ok else 0
            if n:
                return url, n
    return None


def verifica_riga(r):
    esito = {"nome": r["nome"], "url_homepage": r["url_homepage"], "status_usa": "",
             "feed_ok": "", "elementi": "", "sitemap_news": "", "metodo": "nessuno"}
    if r.get("feed_rss"):
        n = conta_elementi(r["feed_rss"])
        if n:
            esito.update(feed_ok=r["feed_rss"], elementi=n, metodo="feed")
    v = verifica(r["url_homepage"])
    esito["status_usa"] = v.get("status") or v.get("errore", "")
    if esito["metodo"] == "nessuno" and v["feed"]:
        esito.update(feed_ok=v["feed"][0]["url"], elementi=v["feed"][0]["elementi"], metodo="feed_scoperto")
    s = sitemap_news(v.get("url_finale") or r["url_homepage"])
    if s:
        esito["sitemap_news"] = s[0]
        if esito["metodo"] == "nessuno":
            esito.update(elementi=s[1], metodo="sitemap")
    if esito["metodo"] == "nessuno" and esito["status_usa"] == 200:
        esito["metodo"] = "homepage"
    return esito


if __name__ == "__main__":
    with open(BASE / "data" / "testate.csv", newline="", encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    with ThreadPoolExecutor(max_workers=16) as pool:
        esiti = list(pool.map(verifica_riga, righe))
    campi = list(esiti[0].keys())
    with open(BASE / "data" / "verifica_usa.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campi)
        w.writeheader()
        w.writerows(esiti)
    from collections import Counter
    print(Counter(e["metodo"] for e in esiti))
