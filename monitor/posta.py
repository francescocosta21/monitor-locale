"""Composizione e invio dell'email del mattino."""
import html
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import VOTO_MINIMO, VOTO_PREFERITO

log = logging.getLogger(__name__)

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
ETICHETTE = {"lunghezza": "Lunghezza", "homepage": "Homepage", "ripresa": "Ripresa",
             "reddit": "Reddit", "nazionale": "Non sui nazionali"}

STILE = """
body{margin:0;background:#f4f1ea;font-family:Georgia,'Times New Roman',serif;color:#1d1d1b}
.pagina{max-width:680px;margin:0 auto;background:#fffdf8;padding:28px 26px}
h1{font-size:22px;margin:0 0 4px}
.sotto{font-family:Helvetica,Arial,sans-serif;font-size:13px;color:#6b665c;margin:0 0 24px}
.storia{border-top:1px solid #e3ddd0;padding:18px 0}
.num{font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#9a9385;font-weight:bold}
.sinossi{font-size:17px;line-height:1.45;margin:4px 0 8px}
.titolo{font-family:Helvetica,Arial,sans-serif;font-size:14px;margin:0 0 4px}
.titolo a{color:#1f4e79;text-decoration:none}
.fonte{font-family:Helvetica,Arial,sans-serif;font-size:12.5px;color:#6b665c;margin:0 0 8px}
.segnali{font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#3d3a33;margin:0 0 6px;line-height:1.7}
.chip{display:inline-block;background:#eee8da;border-radius:3px;padding:1px 7px;margin:0 4px 3px 0}
.giudizio{font-family:Helvetica,Arial,sans-serif;font-size:12.5px;color:#3d3a33;margin:0 0 4px}
.avviso{font-family:Helvetica,Arial,sans-serif;font-size:12.5px;margin:4px 0 0;padding:6px 9px;border-radius:3px}
.italia{background:#fbeaea;color:#8a1f1f}
.segue{background:#e8f0f8;color:#1f4e79}
.anche{font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#6b665c;margin:6px 0 0}
.anche a{color:#6b665c}
.piede{font-family:Helvetica,Arial,sans-serif;font-size:11.5px;color:#9a9385;border-top:1px solid #e3ddd0;padding-top:14px;margin-top:8px;line-height:1.6}
"""


def _e(testo):
    return html.escape(str(testo or ""))


def data_italiana(d):
    return f"{d.day} {MESI[d.month - 1]} {d.year}"


def componi(storie, statistiche, giorno):
    blocchi = []
    for n, a in enumerate(storie, 1):
        t = a["t"]
        chip = "".join(f'<span class="chip"><b>{_e(ETICHETTE[s[0]])}</b> · {_e(s[2])}</span>' for s in a["segnali"])
        giudizio = (f'<p class="giudizio"><b>Giudizio {a["voto"]}/10</b> · {_e(a.get("motivazione"))}</p>'
                    if a.get("voto") else "")
        avvisi = ""
        if a.get("italia"):
            i = a["italia"]
            fonte = f" ({_e(i['fonte'])})" if i.get("fonte") else ""
            avvisi += (f'<p class="avviso italia">Già uscito in Italia? {i["quanti"]} risultati negli ultimi 7 giorni, '
                       f'per esempio: <a href="{_e(i["url"])}">{_e(i["titolo"])}</a>{fonte}</p>')
        if a.get("segue"):
            s = a["segue"]
            avvisi += (f'<p class="avviso segue">Sviluppo di una storia già segnalata il {_e(s.get("data"))}: '
                       f'<a href="{_e(s.get("url"))}">{_e(s.get("titolo"))}</a></p>')
        anche = ""
        if a.get("ripresa"):
            link = ", ".join(f'<a href="{_e(b["url"])}">{_e(b["t"]["nome"])}</a>' for b in a["ripresa"][:6])
            anche = f'<p class="anche">Ne scrivono anche: {link}</p>'
        sinossi = a.get("sinossi") or a["titolo"]
        blocchi.append(f"""
<div class="storia">
  <div class="num">{n}</div>
  <p class="sinossi">{_e(sinossi)}</p>
  <p class="titolo"><a href="{_e(a['url'])}">{_e(a['titolo'])}</a></p>
  <p class="fonte">{_e(t['nome'])} · {_e(t['citta'])}, {_e(t['stato'])} · {_e(t['tipo'].replace('_', ' '))}{' · in spagnolo' if t.get('lingua') == 'es' else ''}</p>
  <p class="segnali">{chip}</p>
  {giudizio}{avvisi}{anche}
</div>""")

    s = statistiche
    note = []
    if not s.get("giudizio_ok"):
        note.append("Il giudizio di Claude oggi non è disponibile: l'ordine si basa solo sui segnali strutturali.")
    piede = (f"{s.get('testate', 0)} testate monitorate · {s.get('finestra', 0)} articoli nelle ultime 48 ore · "
             f"{s.get('con_segnali', 0)} con almeno due segnali · {s.get('candidati', 0)} valutati da Claude"
             f" ({s.get('scartate_voto', 0)} escluse per voto sotto {VOTO_MINIMO})."
             + "".join(f"<br>{_e(x)}" for x in note))
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><style>{STILE}</style></head>
<body><div class="pagina">
<h1>Storie locali americane</h1>
<p class="sotto">{data_italiana(giorno)} · {len(storie)} storie: prima quelle con voto da {VOTO_PREFERITO} in su, poi le migliori subito sotto; dentro ogni fascia, per punteggio (60% segnali, 40% giudizio)</p>
{''.join(blocchi)}
<p class="piede">{piede}</p>
</div></body></html>"""


def invia(oggetto, corpo_html):
    # split() senza argomenti toglie ogni tipo di spazio, compresi quelli unificatori che Google
    # inserisce quando mostra la password per app
    utente = "".join((os.environ.get("GMAIL_UTENTE") or "").split())
    password = "".join((os.environ.get("GMAIL_APP_PASSWORD") or "").split())
    destinatario = "".join((os.environ.get("EMAIL_DESTINATARIO") or "").split()) or utente
    if not (utente and password):
        log.warning("credenziali Gmail assenti: email non inviata")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = oggetto, f"Monitor locale <{utente}>", destinatario
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(utente, password)
        s.sendmail(utente, [destinatario], msg.as_string())
    log.info("email inviata")
    return True
