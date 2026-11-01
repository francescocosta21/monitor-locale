"""Giudizio di Claude sui candidati (una chiamata al giorno) e controllo "già uscito in Italia"."""
import json
import logging
import os
from typing import List

import feedparser
from pydantic import BaseModel

from . import config, estrazione, rete

log = logging.getLogger(__name__)

ISTRUZIONI = """Lavori per un giornalista italiano che racconta gli Stati Uniti a un pubblico italiano \
generalista e colto (lettori di un giornale online come Il Post). Cerca storie locali americane da \
raccontare in Italia prima degli altri media italiani. Cerca STORIE, non notizie: vicende con \
personaggi, una trama, qualcosa di sorprendente o rivelatore dell'America, che reggano un articolo \
lungo o un racconto e che un lettore italiano non ha mai sentito.

Ricevi una lista di articoli di giornali locali americani, già selezionati da segnali strutturali \
(lunghezza, permanenza in homepage, ripresa da altre testate, Reddit, assenza dai media nazionali). \
Solo una piccola parte merita davvero: sii severo, l'asticella è alta.

Scala del voto:
- 9-10: storia straordinaria, originale, con personaggi e trama; la racconteresti subito.
- 7-8: storia originale e raccontabile, che dice qualcosa di non ovvio sugli Stati Uniti.
- 5-6: notizia con qualche spunto, ma prevedibile o poco sviluppabile.
- 1-4: cronaca di routine, sviluppi minori o passaggi procedurali di vicende in corso (udienze, \
rinvii, voti di commissione, raccolte fondi elettorali), campagna elettorale ordinaria, versioni \
locali di temi nazionali già noti, notizie che interessano solo chi vive lì, recensioni, comunicati, \
servizi di consumo, contenuti distribuiti a più testate. Un pezzo che parla di un luogo lontano \
dalla testata che lo pubblica (per esempio la California su un giornale della Pennsylvania) è quasi \
sempre un pezzo d'agenzia: abbassa il voto e dillo nella motivazione.

Per ciascun articolo dai:
- voto (1-10), secondo la scala.
- motivazione: una riga in italiano (massimo 20 parole) che spiega il voto.
- sinossi: in italiano, due o tre frasi discorsive (45-55 parole) che raccontano di cosa parla la \
storia e perché colpisce, come le spiegheresti a un collega. Tono piano, senza enfasi. Usa solo le \
informazioni fornite: se il sommario manca, limitati a ciò che dice il titolo e non inventare dettagli.
- query_italia: una ricerca per Google News in italiano che troverebbe questa storia se fosse \
già uscita su un giornale italiano. Usa i nomi propri più specifici (persone, luoghi, \
organizzazioni) tra virgolette, massimo 3 termini. Esempio: "Storm Lake" giornale.

Valuta ogni articolo in modo indipendente e restituisci una valutazione per ogni id ricevuto."""


def istruzioni():
    """Istruzioni di base più le preferenze espresse dal giornalista (data/preferenze.md)."""
    if config.PREFERENZE.exists():
        preferenze = config.PREFERENZE.read_text(encoding="utf-8").strip()
        if preferenze:
            return f"{ISTRUZIONI}\n\nPreferenze e giudizi espressi dal giornalista su selezioni passate, \
da tenere presenti:\n\n{preferenze}"
    return ISTRUZIONI


class Valutazione(BaseModel):
    id: int
    voto: int
    motivazione: str
    sinossi: str
    query_italia: str


class Esito(BaseModel):
    valutazioni: List[Valutazione]


SCHEMA = {
    "type": "object",
    "properties": {
        "valutazioni": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "voto": {"type": "integer"},
                    "motivazione": {"type": "string"},
                    "sinossi": {"type": "string"},
                    "query_italia": {"type": "string"},
                },
                "required": ["id", "voto", "motivazione", "sinossi", "query_italia"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["valutazioni"],
    "additionalProperties": False,
}


def _scheda(i, a):
    t = a["t"]
    return {
        "id": i,
        "testata": f"{t['nome']} ({t['citta']}, {t['stato']}; {t['tipo']}; lingua {t['lingua']})",
        "titolo": a["titolo"],
        "sommario": (a.get("sommario") or "")[:500],
        "segnali": [s[2] for s in a["segnali"]],
        "altre_testate": [f"{b['t']['nome']}: {b['titolo']}" for b in a.get("ripresa", [])[:4]],
    }


def valuta(candidati):
    """Aggiunge a ogni candidato voto, motivazione, sinossi e query_italia. Se la chiamata fallisce
    il monitor va avanti con i soli segnali strutturali."""
    if not candidati or not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("giudizio saltato (nessun candidato o chiave API assente)")
        return False
    import anthropic

    client = anthropic.Anthropic()
    schede = [_scheda(i, a) for i, a in enumerate(candidati)]
    try:
        with client.messages.stream(
            model=config.MODELLO,
            max_tokens=64000,
            system=istruzioni(),
            messages=[{"role": "user", "content": json.dumps(schede, ensure_ascii=False, indent=1)}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        ) as flusso:
            risposta = flusso.get_final_message()
    except anthropic.APIStatusError as e:
        log.error("giudizio: errore API %s: %s", e.status_code, e.message)
        return False
    except anthropic.APIConnectionError as e:
        log.error("giudizio: connessione non riuscita: %s", e)
        return False
    if risposta.stop_reason != "end_turn":
        log.error("giudizio: risposta non utilizzabile (stop_reason=%s)", risposta.stop_reason)
        return False
    testo = next((b.text for b in risposta.content if b.type == "text"), "")
    try:
        esito = Esito.model_validate_json(testo)
    except ValueError as e:
        log.error("giudizio: JSON non valido: %s", e)
        return False
    log.info("giudizio: %d valutazioni, token %s in / %s out", len(esito.valutazioni),
             risposta.usage.input_tokens, risposta.usage.output_tokens)
    for v in esito.valutazioni:
        if 0 <= v.id < len(candidati):
            candidati[v.id].update(voto=min(10, max(1, v.voto)), motivazione=v.motivazione, sinossi=v.sinossi,
                                   query_italia=v.query_italia)
    return True


def gia_in_italia(a):
    """Cerca la storia su Google News Italia negli ultimi 7 giorni. Solo un'etichetta, nessuna penalità."""
    query = a.get("query_italia")
    if not query:
        return None
    r = rete.scarica_google_news(rete.google_news_url(f"{query} when:7d", lingua="it"))
    if r is None or not r.ok:
        return None
    voci = feedparser.parse(r.content).entries
    if not voci:
        return None
    primo = voci[0]
    return {"titolo": estrazione.testo_pulito(primo.get("title", "")), "url": primo.get("link", ""),
            "fonte": (primo.get("source") or {}).get("title", ""), "quanti": len(voci)}
