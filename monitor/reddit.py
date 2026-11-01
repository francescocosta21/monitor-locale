"""Segnale social: post su Reddit che linkano gli articoli delle testate.

Con credenziali (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET) usa le API ufficiali e legge upvote e commenti.
Senza credenziali usa i feed RSS pubblici, lenti e senza numeri: sa solo che un articolo è
fra i più votati della settimana per quel dominio.
"""
import logging
import os
import time
from datetime import datetime, timezone

import feedparser
from bs4 import BeautifulSoup

from . import db, rete

log = logging.getLogger(__name__)
UA = "monitor-locale/1.0 (storie locali USA)"


class Reddit:
    def __init__(self):
        self.id = os.environ.get("REDDIT_CLIENT_ID")
        self.segreto = os.environ.get("REDDIT_CLIENT_SECRET")
        self.token = None
        self.pausa = 0.7 if self.id else 6.0

    @property
    def ufficiale(self):
        return bool(self.id and self.segreto)

    def _token(self):
        r = rete.sessione().post("https://www.reddit.com/api/v1/access_token",
                                 auth=(self.id, self.segreto), data={"grant_type": "client_credentials"},
                                 headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def dominio(self, dominio):
        """Post più votati della settimana che linkano il dominio: lista di dict."""
        try:
            return self._api(dominio) if self.ufficiale else self._rss(dominio)
        except Exception as e:
            log.info("reddit %s: %s", dominio, e)
            return None

    def _api(self, dominio):
        if not self.token:
            self._token()
        r = rete.sessione().get(f"https://oauth.reddit.com/domain/{dominio}/top",
                                params={"t": "week", "limit": 50},
                                headers={"User-Agent": UA, "Authorization": f"bearer {self.token}"}, timeout=20)
        if r.status_code == 401:
            self.token = None
            return self._api(dominio)
        r.raise_for_status()
        post = []
        for c in r.json()["data"]["children"]:
            d = c["data"]
            post.append({"id": d["id"], "url": rete.normalizza(d.get("url", "")), "titolo": d.get("title", ""),
                         "subreddit": d.get("subreddit", ""), "punteggio": d.get("score", 0),
                         "commenti": d.get("num_comments", 0),
                         "creato": datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc).isoformat()})
        return post

    def _rss(self, dominio):
        r = rete.sessione().get(f"https://www.reddit.com/domain/{dominio}/top/.rss",
                                params={"t": "week"}, headers={"User-Agent": UA}, timeout=20)
        if r.status_code == 429:
            raise RuntimeError("429")
        r.raise_for_status()
        post = []
        for pos, e in enumerate(feedparser.parse(r.content).entries):
            html = e.content[0].value if e.get("content") else ""
            link = next((a["href"] for a in BeautifulSoup(html, "lxml").find_all("a", href=True)
                         if a.get_text(strip=True) == "[link]"), "")
            sub = next((t.term for t in e.get("tags", [])), "")
            # Senza numeri: la posizione nella classifica settimanale fa da indicatore (1° → 100)
            post.append({"id": e.get("id", e.link).split("/")[-1], "url": rete.normalizza(link) if link else "",
                         "titolo": e.title, "subreddit": sub, "punteggio": max(0, 100 - 20 * pos), "commenti": 0,
                         "creato": e.get("published", "")})
        return post


def aggiorna(con, testate, quota=None, scadenza=None):
    """Interroga una parte dei domini a ogni giro, a rotazione: in un giorno li copre tutti."""
    client = Reddit()
    domini = sorted({t["dominio"] for t in testate})
    if quota is None:
        quota = max(1, len(domini) // 12 + 1) if client.ufficiale else 15
    ultimo = {r["dominio"]: r["m"] for r in con.execute("SELECT dominio, MAX(aggiornato) m FROM reddit GROUP BY dominio")}
    domini.sort(key=lambda d: ultimo.get(d, ""))
    ts, fatti, bloccato = db.iso(db.adesso()), 0, 0
    for d in domini[:quota]:
        if scadenza and time.time() > scadenza:
            break
        post = client.dominio(d)
        time.sleep(client.pausa)
        if post is None:
            bloccato += 1
            if bloccato >= 3 and fatti == 0:
                log.warning("reddit non raggiungibile in questo giro")
                break
            continue
        fatti += 1
        con.execute("INSERT INTO reddit (id, dominio, aggiornato) VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                    (f"_segnaposto_{d}", d, ts))
        con.execute("UPDATE reddit SET aggiornato = ? WHERE id = ?", (ts, f"_segnaposto_{d}"))
        for p in post:
            con.execute("""INSERT INTO reddit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET punteggio = excluded.punteggio, commenti = excluded.commenti,
                aggiornato = excluded.aggiornato""",
                        (p["id"], p["url"], d, p["titolo"], p["subreddit"], p["punteggio"], p["commenti"],
                         p["creato"], ts))
    con.commit()
    log.info("reddit: %d domini aggiornati (%s)", fatti, "API" if client.ufficiale else "RSS")
    return {"domini": fatti, "modo": "API" if client.ufficiale else "RSS"}
