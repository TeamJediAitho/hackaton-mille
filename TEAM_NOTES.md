# Team Notes

## Problema 1

- **Problema:** Il tempo della prima ingestion con Docling risulta enorme, soprattutto per documenti scannerizzati e non digitali. Docling gira in locale ed è molto lento: worst case di ingestion misurato a 37,18 s.
- **Com'è stato risolto:** Non è stato risolto, ma discusso internamente.
- **Cosa ho imparato:** In funzione dell'ambiente e delle risorse a disposizione può essere utile sostituire Docling con una soluzione non locale, ad es. le API di parsing/OCR di OpenAI, o usare librerie di parsing più coerenti. Utilizzando ad esempio una pipeline di check del file (se scanned o digital) potrebbe essere utile utilizzare OCR solo sui documenti scansionati. Un'altra idea potrebbe essere parallelizzare il parsing. Tesseract è spesso più veloce. NOTA: le impostazioni sulla lingua potrebbero migliorare la qualità.

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

### Baseline misurata (pre-opt, corpus di Fase 1 = act 1 + act 2, 15 documenti)

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

---

## Problema 5 — La guida sbagliava la definizione delle fasi

- **Problema:** `PARTICIPANT_GUIDE.md` presenta la Fase 1 come «Act 1» e afferma che gli atti sono
  soltanto due (lo ripete anche il `README.md`: «nessun terzo atto»). La definizione corretta,
  confermata dall'organizzazione, è: **Fase 1 = act 1 + act 2**, **Fase 2 = act 1 + 2 + 3 + 4**.
- **Com'è stato risolto:** niente da rifare. La Fase 1 era già stata misurata sull'intero manifest,
  cioè esattamente su act 1 + act 2: `pre_opt`, E1, E6, E1+E6 e `post_opt` hanno tutti girato sui 15
  documenti. Il flag `--act` esisteva ma non è stato usato in nessun run ufficiale. Corretta solo la
  dicitura «corpus completo», che valeva per la Fase 1 e non per la gara.
- **Cosa ho imparato:** vale la pena verificare l'ipotesi sul corpus *prima* di misurare. Le domande
  del round 1 lo dicevano già da sole — cinque su otto citano documenti di act 2 — e questa è stata
  la prova che ha smentito la lettura «solo Act 1» della guida.

### Il vero blocco della Fase 2: act 3 e act 4 non sono nel manifest

Il commit `8665e52` («data: add new acts») aggiunge 16 file — 9 in `data/act_3`, 7 in `data/act_4` —
ma **non tocca `data/manifest.json`**, che dichiara ancora `available_acts: [1, 2]` e 15 documenti.
Per le regole del progetto quei file non esistono: `iter_ingest_files()` legge il manifest, quindi
l'ingest li salta, e un `document_id` che li citasse farebbe fallire la validazione della
submission. Nemmeno `data/checksums.sha256` (15 righe) e `data/license_manifest.csv` (15 righe) li
coprono. Finché non si installa il release pack ufficiale, la Fase 2 non può iniziare.

Ricognizione fatta sui nuovi file (con `docling_parse`, senza ingest):

| Cartella | File | Layer di testo |
| --- | --- | --- |
| `act_3` | 4 PDF (`agenda_incontri_01`, `lettera_porti_feudi_01`, `movimenti_diplomatici_01`, `registro_passaggio_01`) | sì, nativi |
| `act_3` | 5 PNG (mappa Sicilia, mappa porti annotata, lettera danneggiata, manifesto politico, scansione manoscritta) | no: immagini pure, servono OCR e ragionamento su mappe |
| `act_4` | 7 PDF (propaganda, bozza v1 vs nota v2, fonte dannosa, lettera allusiva, nota diplomatica incompleta, testimonianza contestata) | sì, ma tre hanno immagini incorporate |

### Set di regressione della Fase 1, verificato

Quando il corpus crescerà, il confronto con i numeri di oggi resta possibile: `--act 1 2` ricostruisce
esattamente il corpus di Fase 1 in una collection separata (`caso_dei_mille_act12`, 174 chunk) e
riproduce il `post_opt` metrica per metrica (recall 0,952, precision 0,571, hit 1,000, MRR 0,886).

```bash
python baseline_naive_rag.py --questions eval/questions_round_1.json --round-id round_1 --act 1 2 \
  --qdrant-path outputs/qdrant_act12 --output outputs/round1/regressione_act12.json --rebuild
python score_submission.py --submission outputs/round1/regressione_act12.json \
  --annotations eval/annotations_round_1.json --baseline outputs/round1/submission_round_1_post_opt.json
```
