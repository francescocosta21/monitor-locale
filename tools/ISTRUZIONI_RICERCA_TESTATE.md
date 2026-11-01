# Istruzioni per la ricerca delle testate (per area geografica)

Stiamo costruendo un monitor di storie locali americane per un giornalista italiano che vuole trovare storie locali USA da raccontare in Italia prima degli altri media italiani. Il monitor scarica ogni 2 ore homepage e feed RSS di ~400 testate locali. Il tuo compito: compilare la lista delle testate per UNA area geografica.

## Tipi di testata da includere (mescolali, non solo quotidiani)
- `quotidiano_metro`: grandi quotidiani metropolitani (Boston Globe, Philadelphia Inquirer…). Vanno inclusi TUTTI quelli rilevanti: sono grandi fonti di storie.
- `quotidiano_locale`: quotidiani di città medie/piccole
- `nonprofit`: nonprofit locali/statali (membri INN, Report for America, es. Texas Tribune, CalMatters, Spotlight PA, VTDigger)
- `settimanale_alt`: settimanali alternativi (Village Voice-style: Chicago Reader, Riverfront Times…)
- `tv_locale`: siti delle TV locali (affiliate ABC/CBS/NBC/Fox nelle città principali)
- `citta_contea`: giornali e giornalini di città e di contea, testate piccole e iper-locali (settimanali di contea, siti comunali indipendenti)
- Testate in **spagnolo** (colonna lingua=es): quotidiani, settimanali, TV locali Univision/Telemundo dove esistono con siti propri
- ESCLUSI: aggregatori (Patch, NewsBreak, Ground News…), siti di soli comunicati, blog personali, testate nazionali.

## Criteri
- Almeno 2-3 testate per ogni stato, più peso agli stati popolosi e a quelli in bilico (PA, MI, WI, GA, AZ, NV, NC).
- Preferisci testate che pubblicano ogni giorno e che fanno giornalismo originale.
- Verifica che la testata sia ANCORA ATTIVA nel 2026 (molte hanno chiuso o ridotto; alcune sono diventate solo digitali).
- Varia i gruppi editoriali, e annota sempre il gruppo: serve per non contare come "ripresa" un pezzo ripubblicato dentro lo stesso gruppo. Valori tipici: Gannett, Lee, McClatchy, Alden/MediaNews, Advance, Hearst, CNHI, Adams, Carpenter, Paxton, Ogden, Gray, Nexstar, Sinclair, TEGNA, Scripps, Hearst TV, Cox Media Group, Allen Media, Graham Media, Univision/TelevisaUnivision, Telemundo/NBCU, Axios Local, American Journalism Project, indipendente.

## Verifica tecnica (obbligatoria)
Per ogni testata esegui lo script di verifica (puoi passare molti URL in una volta):

```
.venv/bin/python tools/verifica_testata.py https://www.a.com https://www.b.com 2>/dev/null
```

Restituisce una riga JSON per URL con status HTTP, url finale e feed RSS trovati (con numero di elementi). Se non trova un feed, prova a cercarlo tu (WebFetch sulla homepage, WebSearch "<testata> rss feed", percorsi come /rss/, /feeds/, /category/news/feed/). Uno status 403 sulla homepage NON è un problema di per sé (protezione anti-bot), ma annotalo. Se la testata non ha feed funzionante, tienila solo se è davvero importante e annota "senza feed".

## Output
Scrivi un CSV UTF-8 con intestazione esattamente:

```
nome,url_homepage,feed_rss,stato,citta,tipo,gruppo,lingua,paywall,homepage_status,note
```

- `stato`: sigla a due lettere (DC per Washington)
- `tipo`: uno dei valori sopra
- `lingua`: en o es
- `paywall`: si / no / misto / ?
- `homepage_status`: lo status HTTP restituito dallo script
- `note`: breve, in italiano (es. "forte su politica statale", "chiusa la versione cartacea nel 2024", "senza feed")

Metti tra virgolette i campi che contengono virgole. Scrivi il file con lo strumento Write nel percorso indicato nel prompt. Alla fine rispondi con: numero di testate, distribuzione per stato e per tipo, e le testate escluse perché chiuse o senza feed (breve).

## Nota sui blocchi (aggiunta dopo il primo giro)
La verifica gira da un Mac in Italia, il monitor girerà su server GitHub negli USA. Status 451 (geoblocco UE), 402, 403, 429 e timeout NON sono motivi di esclusione: includere con nota "da verificare da USA" + codice. Escludere solo testate chiuse o inattive.
