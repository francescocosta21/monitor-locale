"""Punto d'ingresso.

    python -m monitor giro       raccolta (testate, homepage, nazionali, Reddit)
    python -m monitor mattina    segnali, giudizio, email  [--prova: non invia e non registra]
    python -m monitor auto       quello che serve adesso: giro se l'ultimo è vecchio, email se è mattina
"""
import argparse
import csv
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, db, giudizio, posta, raccolta, reddit, rete, segnali

log = logging.getLogger("monitor")
ROMA = ZoneInfo("Europe/Rome")


def giro():
    esito = raccolta.giro()
    con = db.connetti()
    # Senza credenziali Reddit blocca i server di GitHub: inutile consumare minuti
    if reddit.Reddit().ufficiale:
        esito["reddit"] = reddit.aggiorna(con, rete.carica_testate(), scadenza=time.time() + 180)
    return esito


def mattina(prova=False):
    oggi = datetime.now(ROMA).date()
    con = db.connetti()
    testate = rete.carica_testate()
    finestra, stat = segnali.calcola(con, testate)
    inviati = segnali.carica_inviati()
    candidati = segnali.scegli_candidati(finestra, {r["url"] for r in inviati})
    stat.update(testate=len(testate), candidati=len(candidati))
    stat["giudizio_ok"] = giudizio.valuta(candidati)
    for a in candidati:
        voto = a.get("voto")
        a["punteggio"] = (config.PESO_STRUTTURALE * a["strutturale"] + config.PESO_GIUDIZIO * voto / 10
                          if voto else a["strutturale"])
    ammesse = [a for a in candidati if not a.get("voto") or a["voto"] >= config.VOTO_MINIMO]
    stat["scartate_voto"] = len(candidati) - len(ammesse)
    # Prima i voti da VOTO_PREFERITO in su, poi a scalare (6, poi 5) finché non si arriva a STORIE_EMAIL
    storie = sorted(ammesse, key=lambda a: (min(a.get("voto") or 0, config.VOTO_PREFERITO), a["punteggio"]),
                    reverse=True)[:config.STORIE_EMAIL]
    for a in storie:
        a["italia"] = giudizio.gia_in_italia(a)

    corpo = posta.componi(storie, stat, oggi)
    config.ARCHIVIO.mkdir(parents=True, exist_ok=True)
    if prova:
        percorso = config.ARCHIVIO / f"prova-{oggi.isoformat()}.html"
        percorso.write_text(corpo, encoding="utf-8")
        log.info("prova salvata in %s (%d storie)", percorso, len(storie))
        return storie
    oggetto = f"Storie locali USA · {posta.data_italiana(oggi)}"
    if not posta.invia(oggetto, corpo):
        raise SystemExit("invio non riuscito")
    (config.ARCHIVIO / f"{oggi.isoformat()}.html").write_text(corpo, encoding="utf-8")
    nuovo = not config.INVIATI_CSV.exists()
    with open(config.INVIATI_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuovo:
            w.writerow(["data", "url", "titolo", "sommario", "testata", "voto", "punteggio"])
        for a in storie:
            w.writerow([oggi.isoformat(), a["url"], a["titolo"], (a.get("sommario") or "")[:300],
                        a["t"]["nome"], a.get("voto", ""), f"{a['punteggio']:.3f}"])
    return storie


def auto(forza_email=False):
    con = db.connetti()
    ultimo = con.execute("SELECT MAX(ts) FROM giri").fetchone()[0]
    con.close()
    if not ultimo or db.adesso() - datetime.fromisoformat(ultimo) > timedelta(minutes=90):
        giro()
    else:
        log.info("ultimo giro %s: salto la raccolta", ultimo)
    ora = datetime.now(ROMA)
    gia_inviata = (config.ARCHIVIO / f"{ora.date().isoformat()}.html").exists()
    if forza_email or (5 <= ora.hour < 13 and not gia_inviata):   # GitHub a volte ritarda di ore i giri programmati
        mattina()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("comando", choices=["giro", "mattina", "auto"])
    p.add_argument("--prova", action="store_true")
    p.add_argument("--forza-email", action="store_true")
    args = p.parse_args()
    if args.comando == "giro":
        giro()
    elif args.comando == "mattina":
        mattina(prova=args.prova)
    else:
        auto(forza_email=args.forza_email)
