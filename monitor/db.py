"""Database SQLite con lo storico degli articoli, delle homepage e dei nazionali."""
import sqlite3
from datetime import datetime, timedelta, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS articoli (
    url TEXT PRIMARY KEY,
    testata TEXT NOT NULL,          -- chiave della testata (dominio + percorso della homepage)
    titolo TEXT,
    sommario TEXT,
    autori TEXT,
    n_autori INTEGER,
    sezione TEXT,
    pubblicato TEXT,
    prima_vista TEXT NOT NULL,
    fonte TEXT,                      -- feed / sitemap / homepage / google_news
    parole INTEGER,
    parole_fonte TEXT,               -- wordCount / articleBody / testo / feed
    immagini INTEGER,
    paywall INTEGER DEFAULT 0,
    ap INTEGER DEFAULT 0,            -- lancio Associated Press
    dettagli INTEGER DEFAULT 0       -- 1 se la pagina dell'articolo è stata letta
);
CREATE INDEX IF NOT EXISTS articoli_testata ON articoli(testata, prima_vista);
CREATE INDEX IF NOT EXISTS articoli_vista ON articoli(prima_vista);

CREATE TABLE IF NOT EXISTS homepage (
    url TEXT PRIMARY KEY,
    testata TEXT NOT NULL,
    avvistamenti INTEGER DEFAULT 0,
    avvistamenti_top INTEGER DEFAULT 0,
    posizione_migliore INTEGER,
    prima TEXT,
    ultima TEXT
);
CREATE INDEX IF NOT EXISTS homepage_testata ON homepage(testata, ultima);

CREATE TABLE IF NOT EXISTS giri (
    ts TEXT NOT NULL,
    testata TEXT NOT NULL,
    metodo TEXT,
    articoli INTEGER,
    homepage_ok INTEGER,
    errore TEXT
);
CREATE INDEX IF NOT EXISTS giri_ts ON giri(ts);

CREATE TABLE IF NOT EXISTS nazionali (
    url TEXT PRIMARY KEY,
    fonte TEXT,
    titolo TEXT,
    sommario TEXT,
    prima_vista TEXT
);

CREATE TABLE IF NOT EXISTS reddit (
    id TEXT PRIMARY KEY,
    url TEXT,
    dominio TEXT,
    titolo TEXT,
    subreddit TEXT,
    punteggio INTEGER,
    commenti INTEGER,
    creato TEXT,
    aggiornato TEXT
);
CREATE INDEX IF NOT EXISTS reddit_url ON reddit(url);
CREATE INDEX IF NOT EXISTS reddit_dominio ON reddit(dominio);
"""


def adesso():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def connetti():
    config.STATO.mkdir(exist_ok=True)
    con = sqlite3.connect(config.DB, timeout=60)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def pulisci(con, giorni=15):
    """Tiene il database piccolo: oltre due settimane non servono né per le finestre né per le mediane."""
    limite = iso(adesso() - timedelta(days=giorni))
    con.execute("DELETE FROM articoli WHERE prima_vista < ?", (limite,))
    con.execute("DELETE FROM homepage WHERE ultima < ?", (limite,))
    con.execute("DELETE FROM giri WHERE ts < ?", (limite,))
    con.execute("DELETE FROM nazionali WHERE prima_vista < ?", (limite,))
    con.execute("DELETE FROM reddit WHERE creato < ?", (limite,))
    con.commit()
