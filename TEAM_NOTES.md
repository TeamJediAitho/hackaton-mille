# Team Notes

## Problema 1

- **Problema:** Il tempo della prima ingestion con Docling risulta enorme, soprattutto per documenti scannerizzati e non digitali. Docling gira in locale ed è molto lento: worst case di ingestion misurato a 37,18 s.
- **Com'è stato risolto:** l'ingest processava i file in sequenza, uno alla volta (`ingest_corpus`). Ora i file vengono parssati in parallelo con un `ThreadPoolExecutor`: ogni worker tiene le proprie pipeline (il `DocumentConverter` di Docling non è thread-safe, quindi ogni thread ha il suo parser con/senza OCR), mentre le scritture su Qdrant restano sul thread main per evitare upsert concorrenti sul client locale. La concorrenza è `INGEST_WORKERS` (default 4, cap al numero di file e core); `INGEST_WORKERS=1` ripristina esattamente il comportamento sequenziale, utile per gli A/B.
- **Cosa ho imparato:** la parallelizzazione è gratis—zero dipendenze, cache di parsing invariata (chiave sempre sha256+engine), contratti intatti. Il guadagno reale dipende da quanti file pesanti ci sono nel lotto: su act 1 (6 file, 2 con OCR) il parse fresco passa da 151,0 s a 105,9 s (-30%); su un lotto con più scansioni il beneficio è più marcato. Il collo di bottiglia resta il documento più lento del pool (garib_d08, 5,2 MB, da solo oltre i 4 minuti di OCR fresco): per quello la leva giusta è cambiare engine OCR (vedi sotto).

### Misurazione (act 1, parse fresco senza cache)

```bash
# cache spostata via, entrambe le run con --rebuild --act 1
INGEST_WORKERS=1 python baseline_naive_rag.py --questions <q> --round-id timing --output /tmp/seq.json --rebuild --act 1
INGEST_WORKERS=4 python baseline_naive_rag.py --questions <q> --round-id timing --output /tmp/par.json --rebuild --act 1
```

| Config | Tempo ingest | Lettura |
| --- | --- | --- |
| sequenziale (1 worker) | 151,0 s | baseline |
| **parallelo (4 worker)** | **105,9 s** | -30%, 6 file di cui 2 OCR |

**Prossimi passi aperti:** Tesseract al posto di EasyOCR (il repo Docling supporta `OCREngine.TESSERACT`, ma servono il wheel `tesserocr` self-contained e i tessdata `ita`/`eng`/`osd` via `TESSDATA_PREFIX`): sbloccherebbe il collo di bottiglia *per documento* e si combina con la parallelizzazione. Inoltre la latenza di parsing dipende fortemente dalla macchina: 37,18 s misurati all'inizio non valgono per garib_d08, che da solo supera i 4 minuti di OCR fresco.

---

Copiate il blocco per aggiungere un nuovo problema, tranquilli che anche il coding agent lo sa gestire

## Problema 2 — La baseline gira, ma nessuno sa quanto vale

- **Problema:** dopo il primo giro end-to-end (`outputs/round1/submission_round_1_pre_opt.json`) non
  esisteva alcun modo di dire se il retrieval fosse buono: nel repo non c'era uno scorer, e per le 8
  domande del round 1 non c'erano annotazioni. Senza un numero, ogni modifica successiva sarebbe
  stata un'ipotesi non verificabile — esattamente ciò che la Fase 1 della guida vieta.
- **Com'è stato risolto:** `eval/annotations_round_1.json` (fonti attese, fatti richiesti, domande
  di astensione — **etichette nostre, non ufficiali**) e `score_submission.py`, che misura senza
  chiamare nessuna API: recall@5, precision@5, hit@5, MRR, `dont_know_rate`, latenza, costo e una
  diagnosi per domanda che separa gli errori di retrieval da quelli di generation.
  Taratura: sulle annotazioni ufficiali `eval/sample_annotations.json` lo scorer dà recall@5 = 1.000
  e hit@5 = 1.000, quindi legge correttamente la submission.
- **Cosa ho imparato:** una risposta ben scritta non dice nulla sul retrieval. Q003 e Q006 hanno
  risposte convincenti *e* la fonte decisiva solo al rank 3, con tre contesti su cinque fuori tema:
  senza misura sembravano due successi.

### Baseline misurata (pre-opt, corpus completo, 15 documenti)

```bash
python score_submission.py \
  --submission outputs/round1/submission_round_1_pre_opt.json \
  --annotations eval/annotations_round_1.json
```

| Metrica | Valore | Lettura |
| --- | --- | --- |
| recall@5 | 0,952 | quasi tutte le fonti attese entrano nei 5 contesti |
| precision@5 | **0,571** | il punto debole: 5 slot riempiti sempre, anche quando non servono |
| hit@5 | 1,000 | almeno una fonte utile c'è sempre |
| MRR | 0,810 | due domande hanno la fonte decisiva al rank 3 |
| dont_know_rate | 1,000 | l'unica domanda di astensione (R1_Q007) è gestita correttamente |
| latenza media / max | 2 667 ms / 4 477 ms | fascia 7/7, ma R1_Q008 sfora i 4 s da sola |
| costo medio | € 0,000298 | fascia 8/8, con ~16× di margine da spendere in qualità |

**Conseguenza strategica:** i 15 punti di sistema sono già acquisiti e c'è margine di costo per una
seconda chiamata per domanda. Le leve vere sono precisione e ordinamento, non la velocità.

### Casi riproducibili

**Successo — R1_Q007 (astensione).** Domanda: «Le fonti di Act 1-2 provano un accordo formale dei
notabili prima dello sbarco?» · Contesti: `giornale_liberale_01` ×2, `nota_funzionario_borbonico_01`,
`elenco_personaggi_01`, `giornale_borbonico_01` · Risposta: «Non lo so.» · Esito: `OK`, l'unica
risposta corretta possibile — nessuna carta dell'archivio contiene un atto sottoscritto, e la
cronologia avverte esplicitamente di non leggervi dichiarazioni su accordi fra privati.

**Fallimento — R1_Q006 (retrieval/ranking).** Domanda: «Quali anomalie osserva il funzionario
borbonico e quale accusa evita di formulare?» · Contesti: 1 `giornale_borbonico_01`,
2 `elenco_personaggi_01`, 3 `nota_funzionario_borbonico_01`, 4 `dispaccio_console_inglese_01`,
5 `lettera_salina_01` · Risposta: cita la collusione evitata ma non elenca le anomalie (cancelli
aperti, pattuglie spostate, carri in eccesso) · **Sintomo:** precision@5 = 0,20 e fonte decisiva al
rank 3 · **Causa ipotizzata:** il denso premia `giornale_borbonico_01`, che parla degli stessi temi
(carri, voci, accuse senza prove) senza contenere i fatti richiesti — distrattore semantico
perfetto · **Fix candidati:** taglio dei contesti sotto soglia (E2), reranking (E3), ibrido
BM25+RRF (E4) · **Metrica prima:** recall 1,00 / precision 0,20 / rank 3 · **Decisione:**
approfondire con gli esperimenti, misurando su questa stessa domanda.

## Problema 3 — L'OCR corrompeva i documenti nativi digitali

- **Problema:** il default di `DoclingParser` è EasyOCR con `force_full_page=True`, quindi anche i
  PDF con un layer di testo pulito venivano rigenerati da immagine. Nei contesti della baseline si
  legge `1 rapporti` (i→1), `€ affinché`, `corrispondenze; note` (virgola→punto e virgola),
  `dell 'occidente`, `l'11 maggio` reso come `dell' 11 maggio`. Oltre a peggiorare gli embedding,
  `SCORING_AND_FAIRNESS.md` avverte che un contesto non riconducibile al documento tramite supporto
  testuale normalizzato **azzera la Faithfulness** di quella domanda.
- **Com'è stato risolto:** `build_parser(ocr)` sceglie l'engine in base alla `modality` del
  manifest: OCR spento per `text`/`table` (10 documenti), EasyOCR per `scan`/`map` (5). A parità di
  file lo stesso paragrafo passa da `Palermo; 1 giugno 1860` a `Palermo, 1° giugno 1860`.
  `FORCE_OCR_ALL=1` riporta al comportamento originale per gli A/B.
- **Cosa ho imparato:** Tesseract non è installato su questa macchina (`tesseract: command not
  found`), quindi per le scansioni resta EasyOCR. Con `tesseract-ocr-ita` si potrebbe misurare se
  l'italiano migliora `garib_d05` e `garib_d08` — esperimento aperto.

### E1 da solo: **peggiora**, e il perché è la cosa utile

| Metrica | pre-opt | E1 | Δ |
| --- | --- | --- | --- |
| recall@5 | 0,952 | 0,810 | −0,143 |
| precision@5 | 0,571 | 0,457 | −0,114 |
| hit@5 | 1,000 | 0,857 | −0,143 |
| MRR | 0,810 | 0,714 | −0,095 |

Su R1_Q006 `nota_funzionario_borbonico_01` sparisce del tutto dai contesti e la risposta cita
`elenco_personaggi_01` per fatti che quel documento non contiene: un testo più pulito ha spostato
l'ordinamento quel tanto che bastava a far vincere un distrattore. **Decisione: non tenere E1 da
solo** — ma il sintomo ha portato alla causa vera (problema 4).

---

## Problema 4 — `max_char` del chunking non ha mai agito

- **Problema:** `RecursiveSplitter(max_char=1024)` raggruppa le foglie del nodo Docling, ma una
  foglia più grande del limite **passa intera**: lo dice il test della libreria stessa
  (`max_char=10` su una stringa di 21 caratteri → 1 chunk). In questo archivio il corpo di un
  documento è spesso una foglia sola, quindi la nota del funzionario era un unico chunk da 2 270
  caratteri e ogni documento finiva in un solo vettore diluito su molti temi. Ecco perché le fonti
  decisive arrivavano al rank 3 dietro distrattori generici.
- **Com'è stato risolto:** `build_splitter()` restituisce un `SizedSplitter` che ritaglia le
  eccedenze con `TextSplitter`, già presente nella libreria. Il corpus passa da 143 a 174 chunk.
  `CHUNK_MAX_CHAR` / `CHUNK_OVERLAP` restano regolabili da ambiente per i futuri sweep.
- **Cosa ho imparato:** un parametro che sembra configurato non è detto che sia attivo. Andava
  verificato leggendo il codice della libreria, non fidandosi del nome dell'argomento.

### Confronto delle quattro configurazioni (stesse 8 domande, stesse annotazioni)

| Config | recall@5 | precision@5 | hit@5 | MRR | latenza media |
| --- | --- | --- | --- | --- | --- |
| pre-opt | 0,952 | 0,571 | 1,000 | 0,810 | 2 667 ms |
| E1 — solo OCR mirato | 0,810 | 0,457 | 0,857 | 0,714 | 2 052 ms |
| E6 — solo chunking | 0,952 | 0,571 | 1,000 | 0,833 | 2 360 ms |
| **E1+E6 (post-opt)** | 0,952 | 0,571 | 1,000 | **0,886** | 2 772 ms |

**Decisione: tenere E1+E6.** Recall, precision e hit restano invariati, il ranking migliora
(+0,076 di MRR), il testo dei contesti è fedele all'originale e l'ingest è molto più rapido.
Su R1_Q006 la fonte decisiva passa dal rank 3 al rank 1.

```bash
# riproduzione completa
python baseline_naive_rag.py --questions eval/questions_round_1.json --round-id round_1 \
  --output outputs/round1/submission_round_1_post_opt.json --rebuild
python score_submission.py --submission outputs/round1/submission_round_1_post_opt.json \
  --annotations eval/annotations_round_1.json \
  --baseline outputs/round1/submission_round_1_pre_opt.json
```

### Limiti noti, da attaccare nel prossimo giro

- **precision@5 ferma a 0,571**: la pipeline consegna sempre 5 contesti anche quando ne bastano 2.
  Il prossimo esperimento è il taglio adattivo — nota: `QdrantVectorstore.search()` **scarta il
  punteggio di similarità** (`_point_to_chunk` costruisce il `Chunk` dal solo payload), quindi
  servirà passare da `client.query_points` per avere una soglia.
- **R1_Q003**: `lettera_salina_01` scende al rank 5 e la risposta perde i «dodici carri». È il caso
  peggiore rimasto e il candidato naturale per il reranking.
- **R1_Q008**: recall 0,67 stabile in ogni configurazione — `lettera_tancredi_01` non viene mai
  recuperata. Domanda multi-hop su tre documenti con soli cinque slot.
- **Latenza dominata dall'API**: una prima esecuzione del post-opt ha registrato 16 607 ms su
  R1_Q003 (contro 2 155 ms della stessa identica configurazione), portando la media a 3 950 ms —
  a un soffio dalla soglia dei 4 secondi. Il tempo non è nostro: conviene misurarlo più volte prima
  di dichiararlo.
- **I verdetti di generation oscillano fra run**: `required_facts` è un controllo di parole chiave e
  il modello varia la formulazione. Le metriche di retrieval sono invece deterministiche a indice
  fermo.
