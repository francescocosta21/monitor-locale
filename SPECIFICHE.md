# Monitor storie locali americane — specifiche concordate

Ultimo aggiornamento: 2026-09-25

## Scopo
Trovare storie locali americane da raccontare a un pubblico italiano, prima degli altri media italiani.

## Output
- Email ogni mattina alle **6:00 ora italiana** all'indirizzo nel segreto EMAIL_DESTINATARIO
- **10 storie** (dal 2026-09-27): prima quelle con voto da 7 in su, poi a completare le migliori con 6 e 5; mai sotto 5. Titolo, testata (con luogo), link, sinossi discorsiva in italiano (2-3 frasi, 45-55 parole), segnali scattati, voto con motivazione.
- Claude valuta 100 candidati, scelti alternando punteggio complessivo, lunghezza e permanenza in homepage.
- I giudizi del giornalista sulle selezioni vanno in `data/preferenze.md`, che Claude legge ogni mattina.
- **Nessun link segnalato due volte.** La stessa storia può tornare con link diversi se se ne continua a parlare o ci sono sviluppi.

## Testate (~400)
Lista in `data/testate.xlsx` (da rivedere con l'utente prima di costruire il resto).

- Quotidiani storici, grandi metropolitani inclusi (peso pieno: sono grandi fonti di storie)
- Nonprofit locali
- Settimanali alternativi
- Siti delle TV locali
- Giornali e giornalini di città e di contea
- Testate in spagnolo
- Esclusi: aggregatori (Patch ecc.)
- Copertura: almeno 2-3 per stato, più peso a stati grandi e in bilico

## Segnali strutturali (misurati da script, zero token)
1. **Lunghezza anomala** rispetto alla media della testata. Con paywall: stima da ciò che è visibile (metadati wordCount, sommario, numero foto, firme multiple, ecc.). I pezzi sotto paywall si considerano comunque.
2. **Permanenza in homepage**: snapshot ogni 2 ore.
3. **Ripresa da altri locali**: contano solo testate indipendenti fra loro (escluse riprese interne allo stesso gruppo editoriale e lanci AP).
4. **Popolarità social**: Reddit. **Sospeso dal 2026-09-27**: Reddit blocca le richieste senza credenziali e l'API richiede un'app che non è stata attivata. Il codice resta (`monitor/reddit.py`) e si riattiva da solo se si aggiungono i segreti REDDIT_CLIENT_ID e REDDIT_CLIENT_SECRET.
5. **Divergenza dal nazionale**: la storia non compare sui nazionali (NYT, WaPo, AP, CNN, Fox…).

Soglia: almeno 2 segnali su 5 per entrare fra i candidati.

## Giudizio (Claude, una volta al giorno sui ~50-60 candidati)
- Voto su interesse per pubblico italiano e originalità, con una riga di motivazione.
- Punteggio finale: **60% segnali strutturali, 40% giudizio**.

## Etichetta "già uscito in Italia"
Controllo su Google News in italiano (Il Post, Repubblica, Corriere, ANSA…). Solo etichetta, **nessuna penalizzazione**.

## Contenuti esclusi (per sezione/URL)
Necrologi, meteo, contenuti sponsorizzati. Lo sport resta.

## Finestra
Ultime 48 ore, con segnalazione "ancora viva" se la storia continua a crescere.

## Infrastruttura
- GitHub Actions: snapshot ogni 2 ore + job mattutino
- API Anthropic per giudizio e sinossi
- Invio via Gmail (password per app)
- Segreti impostati dall'utente

## Nota tecnica
Molte testate bloccano gli IP europei (errore 451, GDPR) o i bot. La verifica definitiva dei feed va fatta dal primo giro su GitHub Actions (server USA).
Gannett ha dismesso quasi tutti gli RSS, e alcune testate (AJC, Univision locali) non ne hanno. La raccolta deve quindi usare, in ordine: feed RSS → sitemap news (Google News sitemap) → link estratti dalla homepage. Nessuna testata "senza feed" va esclusa solo per questo.
Verifica da USA (2026-09-25, 618 testate): feed 457, sitemap 18, homepage 54, bloccate anche da USA 89 (Gannett, McClatchy, TEGNA). Per queste si usa Google News RSS (`site:dominio`): niente segnali di permanenza in homepage e lunghezza, restano ripresa, Reddit, divergenza e giudizio.

## Come funziona (implementazione)
- `monitor/raccolta.py` — giro ogni 2 ore: feed/sitemap/Google News, fotografia homepage (ordine dei link), pagine dei nuovi articoli (JSON-LD wordCount, testo visibile, foto, firme, paywall), fonti nazionali.
- `monitor/reddit.py` — domini interrogati a rotazione (API ufficiale se ci sono REDDIT_CLIENT_ID/SECRET, altrimenti RSS pubblico lento e senza numeri).
- `monitor/segnali.py` — i cinque segnali, soglie in `monitor/config.py`. Punteggio strutturale = somma delle forze / 3 (max 1). Somiglianza tra articoli: TF-IDF su titolo e sommario (soglia 0,40 stessa storia, 0,33 nazionale).
- `monitor/giudizio.py` — una chiamata a Claude Opus 5 sui ~60 candidati (voto, motivazione, sinossi, query per Google News Italia), con ripiego automatico su un altro modello in caso di rifiuto.
- `monitor/posta.py` — email HTML via Gmail.
- `.github/workflows/monitor.yml` — cron ogni 2 ore + 03:20 e 04:20 UTC; l'email parte fra le 5 e le 8 ora di Roma se non è già partita. Database SQLite nella cache di GitHub Actions; `data/inviati.csv` e `data/archivio/` versionati nel repository.
- Avvio manuale da GitHub → Actions → Monitor → Run workflow: `giro`, `prova` (anteprima dell'email scaricabile, senza invio), `email-subito`.

## Costi (2026-10-30)
Giudizio con Claude Sonnet 5 su 70 candidati (prima Opus 5 su 100): circa 0,16-0,17 $ al giorno per newsletter. Dal 2026-11-01 repository pubblico (minuti GitHub illimitati e gratuiti): giro ogni 2 ore, tetto di 15 minuti, fino a 25 pagine di articoli per testata.
