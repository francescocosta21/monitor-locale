"""Costanti e percorsi del monitor. Le soglie dei segnali stanno qui per poterle ritoccare."""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATI = BASE / "data"
TESTATE_CSV = DATI / "testate.csv"
INVIATI_CSV = DATI / "inviati.csv"
PREFERENZE = DATI / "preferenze.md"   # giudizi del giornalista, letti da Claude ogni mattina
ARCHIVIO = DATI / "archivio"
STATO = BASE / "stato"          # cartella non versionata: il database vive nella cache di GitHub Actions
DB = STATO / "monitor.db"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
TIMEOUT = 12
WORKERS = 48
MAX_PAGINE_ARTICOLO_PER_TESTATA = 25   # pagine di articoli nuovi scaricate per testata a ogni giro
DURATA_MASSIMA_GIRO = 900              # secondi: oltre, le testate rimaste passano al giro dopo

# Finestra e selezione
FINESTRA_ORE = 48
STORIE_EMAIL = 10
CANDIDATI_GIUDIZIO = 70
PESO_STRUTTURALE = 0.6
PESO_GIUDIZIO = 0.4
SEGNALI_MINIMI = 2
VOTO_PREFERITO = 7              # prima le storie da qui in su...
VOTO_MINIMO = 5                 # ...poi, per arrivare a STORIE_EMAIL, i voti immediatamente inferiori; mai sotto questo

# Soglie dei segnali
LUNGHEZZA_RAPPORTO = 1.8        # parole / mediana della testata
LUNGHEZZA_CAMPIONE_MINIMO = 10
HOMEPAGE_ORE_MINIME = 12
HOMEPAGE_TOP = 10               # posizione considerata "in alto"
INTERVALLO_ORE = 2
SIMILARITA_STESSA_STORIA = 0.40
SIMILARITA_NAZIONALE = 0.25
SIMILARITA_DOPPIONE_EMAIL = 0.28   # più larga: nell'email due pezzi sulla stessa vicenda non devono comparire entrambi
SIMILARITA_COPIA = 0.85            # stesso articolo ripubblicato: non conta come ripresa indipendente
LUNGHEZZA_RAPPORTO_MASSIMO = 10    # oltre: elenchi e raccolte automatiche, non pezzi lunghi
STATI_PER_NAZIONALE = 3            # ripresa in almeno 3 altri stati: la storia è nazionale
RIPRESA_ALTRE_TESTATE = 2       # testate di gruppi diversi oltre a quella dell'articolo
REDDIT_PUNTEGGIO = 80           # upvote + 2 × commenti

# Esclusioni per sezione (necrologi, meteo, sponsorizzati)
ESCLUSIONI_URL = (r"/(obituar\w*|obits?|necrolog\w*|death-notices|weather|meteo|el-tiempo|clima|"
                  r"sponsored|sponsor-content|paid-?post|partner-?content|branded-?content|"
                  r"brandavestudio|advertorial|native-ad)(/|$|-)")
ESCLUSIONI_TITOLO = r"^(obituary|obituaries|sponsored|paid content|weather forecast|pronóstico)\b"

# Fonti nazionali per il segnale "divergenza dal nazionale"
NAZIONALI_FEED = {
    "NYT": "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
    "NYT home": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "NPR": "https://feeds.npr.org/1003/rss.xml",
    "Fox News": "https://moxie.foxnews.com/google-publisher/us.xml",
    "NBC News": "https://feeds.nbcnews.com/nbcnews/public/news",
    "CBS News": "https://www.cbsnews.com/latest/rss/us",
}
NAZIONALI_GOOGLE_NEWS = ["apnews.com", "cnn.com", "washingtonpost.com", "usatoday.com",
                         "abcnews.go.com", "wsj.com", "axios.com", "reuters.com"]

# Giudizio
MODELLO = "claude-sonnet-5"   # dal 2026-10-30: circa il 70% in meno rispetto a Opus 5 con 100 candidati
