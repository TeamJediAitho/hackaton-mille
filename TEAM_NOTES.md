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

---

## Problema 6 — Il manifest non copriva act 3 e act 4, e il release pack non è arrivato

- **Problema:** blocco descritto sopra. Senza le voci di manifest, i 16 file di `data/act_3` e
  `data/act_4` non esistono per la pipeline.
- **Com'è stato risolto:** il release pack ufficiale non era disponibile sul disco, quindi le voci
  sono state **scritte da noi leggendo i documenti**, con `document_id` = nome del file (la
  convenzione che tutte e 15 le voci precedenti rispettano). Ogni voce nuova porta
  `"metadata_source": "team_inferred"`: quando arriva il pack ufficiale,
  `python scripts/install_release.py <zip>` sovrascrive per `document_id` (`merge_manifest`) e il
  marcatore sparisce da solo. Rigenerati anche `data/checksums.sha256` e
  `data/license_manifest.csv`, che erano fermi a 15 righe.
- **Etichette `reliability` inventate da noi** (il vocabolario del manifest non le prevedeva):
  `draft` per `bozza_comitato_palermo_v1`, `revised` per `nota_comitato_palermo_v2`,
  `unverified_hearsay` per `fonte_dannosa_senza_qualifica_01`, `contested` per
  `testimonianza_contestata_lanza_01`. Alimentano il prompt in E5: sono un'interpretazione nostra,
  non un dato ufficiale.
- **Verifica:** `available_acts = [1, 2, 3, 4]`, 31 documenti, ogni `sha256` del manifest coincide
  col file su disco (`sha256sum -c data/checksums.sha256` senza errori).

---

## Problema 7 — Un documento può entrare nell'indice senza portare testo

- **Sintomo:** con l'ingest di act 3, `Sicily_location_map_960px.png` produce **1 chunk di 0
  caratteri**. Entrava nell'indice, occupava un vettore, non poteva rispondere a niente, e nessun
  messaggio lo diceva.
- **Causa:** è una mappa di localizzazione senza annotazioni testuali: l'OCR non ha niente da
  leggere. Il log dell'ingest contava solo il totale dei chunk della collection.
- **Fix:** `ingest_corpus()` misura chunk **e caratteri** per documento e segnala chi entra sotto
  `MUTE_DOCUMENT_CHARS` (40):

  ```
  ingest: manifesto_politico_01 <- manifesto_politico_01.png (ocr=on) -> 1 chunk, 144 caratteri
  ATTENZIONE: 1 documenti sono entrati senza testo utile: Sicily_location_map_960px
  ```

- **Decisione:** tenere. Risponde direttamente alla richiesta della guida di separare «il testo non
  è stato recuperato» da «recuperato ma interpretato male», e il documento muto è il candidato
  naturale per un captioner (E7, non eseguito — vedi sotto).

### Riga per documento problematico

| document_id | modality | OCR | esito | nota |
| --- | --- | --- | --- | --- |
| `Sicily_location_map_960px` | map | EasyOCR | **0 caratteri** | mappa senza annotazioni: muta per il retrieval testuale |
| `mappa_porti_occidentali_annotata_01` | map | EasyOCR | 215 caratteri | toponimi e annotazioni sì, relazioni spaziali no («faro: luce ridotl» = OCR rumoroso) |
| `manifesto_politico_01` | scan | EasyOCR | 144 caratteri | testo breve ma pulito; accenti persi («LORA E VENUTA») |
| `lettera_danneggiata_01` | scan | EasyOCR | 342 caratteri | leggibile; la lacuna è dichiarata nel documento stesso |
| `scansione_manoscritta_01` | scan | EasyOCR | 356 caratteri | leggibile; qualche refuso OCR («0» al posto di «.») |
| `garib_d08` | scan | EasyOCR | 94 536 caratteri | 113 chunk su 193: da solo è il 59% dell'indice |

---

## Problema 8 — I distrattori di act 3 e 4 costano recall sulle domande del round 1

- **Ipotesi:** il corpus passa da 15 a 31 documenti, quindi più che raddoppiano i distrattori.
- **Misura:** stesse 8 domande del round 1, stessa pipeline, solo il corpus cambia.

  | corpus | recall@5 | precision@5 | hit@5 | MRR |
  | --- | ---: | ---: | ---: | ---: |
  | act 1+2 (15 doc, 174 chunk) | 0,952 | 0,571 | 1,000 | 0,886 |
  | act 1-4 (31 doc, 214 chunk) | 0,810 | 0,429 | 0,857 | 0,786 |

- **Caso riproducibile:** R1_Q003 passa da `GENERATION_FAIL` a `RETRIEVAL_FAIL` —
  `lettera_salina_01` esce del tutto dai primi cinque, spinta fuori dai documenti nuovi.
- **Cosa ho imparato:** è il numero più utile da raccontare. Non è la pipeline a essere peggiorata:
  è il compito a essere diventato più difficile, e la misura lo quantifica.

---

## Problema 9 — Titoli e date isolati occupavano i contesti al posto delle prove (E9)

- **Sintomo riproducibile:** R2_Q004 («il comitato ha dato per raggiunto un accordo?») rispondeva
  **«Non lo so»** con `recall 1,00`: entrambe le versioni erano state recuperate.
- **Causa:** i contesti erano quattro frammenti di intestazione, di cui due identici fra loro:

  ```
  1 bozza_comitato_palermo_v1  50 car.  «## COMITATO DI PALERMO - MINUTA DEL 12 MAGGIO 1860»
  2 bozza_comitato_palermo_v1  50 car.  «## COMITATO DI PALERMO - MINUTA DEL 12 MAGGIO 1860»
  3 lettera_salina_01          22 car.  «Palermo, 8 maggio 1860»
  4 lettera_salina_01          22 car.  «Palermo, 8 maggio 1860»
  5 nota_comitato_palermo_v2  318 car.
  ```

  Docling ripete le intestazioni di sezione e `RecursiveSplitter` le emette come chunk autonomi.
  Corti e densi di parole chiave, vincono il confronto con una domanda breve: **4 slot su 5 sprecati**.
- **Fix:** `SizedSplitter` scarta i chunk sotto `CHUNK_MIN_CHAR` (80) e deduplica i testi identici
  all'interno del documento. 214 → 193 chunk.
- **Prima/dopo (corpus act 1-4, gold round 2):**

  | | recall@5 | precision@5 | hit@5 | MRR | astensioni indebite | affermazioni vietate |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | E5 | 0,938 | 0,500 | 1,000 | 0,906 | 1 | 1 |
  | E5+E9 | 0,875 | 0,475 | 1,000 | 0,938 | **0** | **0** |

- **Decisione:** tenere. Il recall perso su R2_Q004 viene recuperato da E4; le astensioni indebite e
  la propaganda ripetuta come fatto spariscono.

---

## Esperimenti della Fase 2

Protocollo invariato: una variabile alla volta, submission in `outputs/round2/`, confronto con
`--baseline`, e **due** gate — le domande nuove (`eval/annotations_round_2.json`) e la regressione
act 1+2 (`make regression`, soglie recall@5 ≥ 0,952 e MRR ≥ 0,886).

Il gold del round 2 è scritto da noi (`annotation_source` lo dichiara) e copre le quattro famiglie
difficili: solo-immagine (R2_Q001, R2_Q002), mappa (R2_Q003), conflitto di versione (R2_Q004),
fonte dannosa e testimonianza contestata (R2_Q005, R2_Q006), propaganda (R2_Q007), registri (R2_Q008).

### Baseline di Fase 2 (pipeline di Fase 1, corpus act 1-4)

| recall@5 | precision@5 | hit@5 | MRR | qualification | astensioni indebite | affermazioni vietate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0,938 | 0,500 | 1,000 | 0,906 | 0,500 | 1 | 1 |

Il retrieval regge; **è la generazione a cedere**, e cede nel modo peggiore possibile. R2_Q005
chiedeva se il console avesse consegnato una garanzia scritta e la pipeline rispondeva:

> «**Sì**, si afferma che il console abbia consegnato ai capi locali una garanzia scritta […]
> [fonte_dannosa_senza_qualifica_01]»

citando la copia anonima come prova — mentre il dispaccio consolare che *nega* l'impegno era nei
contesti al rank 2. Precision 1,00 e storia sbagliata: è il caso che dimostra che il retrieval,
da solo, non basta.

### E5 — Qualificare le fonti nel prompt

- **Ipotesi:** il modello non può sapere che `articolo_propaganda_01` è un foglio celebrativo o che
  una bozza è stata rettificata. Se la qualifica non arriva col contesto, la propaganda diventa fatto.
- **Modifica:** `reliability` del manifest tradotta in un'etichetta leggibile (`RELIABILITY_LABELS`),
  portata nel payload dei chunk e stampata accanto al `document_id` nel template; `GROUNDING`
  chiede di qualificare la fonte prima di riportarla, di distinguere prova / indizio / congettura,
  di presentare le versioni concorrenti entrambe con le loro date, e di non astenersi quando
  l'evidenza è parziale. **Zero chiamate in più.**
- **Risultato:** qualification_rate **0,500 → 0,750**, retrieval invariato (+0,000 su tutte e
  quattro le metriche). R2_Q005 diventa `OK`: la stessa domanda ora risponde che l'affermazione
  «proviene da voci non verificate e da un documento anonimo» e cita il dispaccio che la nega.
- **Decisione:** tenere.
- **Effetto collaterale, misurato:** sulla regressione act 1+2, R1_Q007 smette di dire «Non lo so»
  e risponde «Le fonti disponibili non provano un accordo formale…» con quattro fonti. Lo scorer
  la contava come astensione mancata — **errore dello strumento, non della pipeline**: la guida
  chiede di «distinguere assenza di prova», non una formula esatta. Aggiunto
  `INSUFFICIENCY_MARKERS`: una negazione ragionata vale come astensione **purché** la risposta non
  affermi nessuno dei `forbidden_claims`.

### E9 — Chunk minimi e deduplicazione

Vedi Problema 9. Tenuto: astensioni indebite 1 → 0, affermazioni vietate 1 → 0, MRR +0,031.

### E4 — Ibrido BM25 + RRF

- **Ipotesi:** nomi, luoghi e date del 1860 sono terreno lessicale; con 31 documenti il denso da
  solo ordina male.
- **Modifica:** BM25 Okapi in ~30 righe di stdlib (`Bm25`), fuso col denso via Reciprocal Rank
  Fusion. `rank_bm25` **non** è stato aggiunto: la formula sta in una classe e non giustifica una
  dipendenza. Recupero largo (`FETCH_K=15` per lista), consegna stretta (5). Knob `HYBRID=0` per
  tornare al solo denso.
- **Risultato sul corpus di gara (act 1-4):**

  | | recall@5 | precision@5 | hit@5 | MRR |
  | --- | ---: | ---: | ---: | ---: |
  | E5+E9 | 0,875 | 0,475 | 1,000 | 0,938 |
  | E5+E9+E4 | **0,938** | 0,450 | 1,000 | **1,000** |

  MRR 1,000: su ogni domanda la prima fonte rilevante è al rank 1. R2_Q004 recupera entrambe le
  versioni e le racconta correttamente, con date e cancellatura a matita.
- **⚠️ Il gate act 1+2 non passa:** recall 0,952 (ok) e hit 1,000 (ok), ma **MRR 0,821 contro la
  soglia 0,886** e precision 0,457 contro 0,571. Sul corpus piccolo il denso era già quasi perfetto
  e la fusione lo disturba; sul corpus grande la ribalta.
- **Decisione: tenere, con l'eccezione dichiarata.** Il corpus di gara della Fase 2 e della Gold Run
  è act 1-4, dove E4 è un guadagno netto; act 1+2 non viene più valutato da solo. La soglia **non**
  è stata riscritta per farla passare: resta lì a ricordare il compromesso. Per revertire in un
  secondo: `HYBRID=0`.
- **`FETCH_K` è irrilevante:** 8, 15 e 25 danno lo stesso MRR su entrambi i corpora (act 1+2: 0,821;
  act 1-4: 1,000). La perdita su act 1+2 è intrinseca alla fusione, non alla larghezza del recupero.

### E2 — Taglio adattivo dei contesti

- **Ipotesi:** consegnare meno di 5 contesti alza la precision e riduce il rumore.
- **Modifica:** `TRIM_RATIO` scarta i contesti il cui punteggio RRF scende sotto quella frazione del
  migliore. Con la fusione il punteggio esiste già: **non è servito** passare da
  `client.query_points` come previsto (`QdrantVectorstore.search()` scarta ancora la similarità, ma
  il rank basta a RRF).
- **Risultato (`TRIM_RATIO=0,6`):** precision@5 0,450 → 0,463 (+0,013), recall / hit / MRR invariati.
- **Decisione: knob lasciato a 0 (spento).** +0,013 su 8 domande nostre è rumore, non un risultato.
  Il codice resta per rimisurarlo quando arriveranno le domande ufficiali.

### E3 — Reranker, E7 — Didascalie per le immagini, E8 — Conflitti di versione: non eseguiti

- **E8 è già soddisfatto da E4 + E5.** R2_Q004 recupera entrambe le versioni (recall 1,00) e la
  risposta le presenta con le rispettive date senza cancellare la bozza. Non serviva codice
  dedicato: serviva che entrambe arrivassero nei contesti e che il prompt sapesse cosa farne.
- **E3 non ha più un bersaglio.** Era pensato per il ranking (R1_Q003 con la fonte decisiva al
  rank 5); dopo E4 l'MRR sul corpus di gara è 1,000. Aggiungere `CohereReranker` significherebbe una
  chiamata, una dipendenza e una chiave esterna che può cadere durante la Gold Run, per migliorare
  una metrica già al massimo.
- **E7 non è misurabile con il gold attuale.** L'unico documento muto è
  `Sicily_location_map_960px` (0 caratteri) e nessuna domanda del gold dipende da esso: R2_Q003
  ottiene già recall 1,00 dall'OCR di `mappa_porti_occidentali_annotata_01`. Il gate previsto
  («deve far salire il recall sulla domanda-mappa senza toccare le altre») non è verificabile,
  quindi l'esperimento resta aperto: va fatto se una domanda ufficiale chiede una relazione
  geografica che l'OCR non può dare.

### E6 — Sweep del chunking: **scartato**

- **Griglia** `max_char ∈ {512, 768, 1024}` × `overlap ∈ {64, 128, 256}`, misurata sul **solo
  retrieval** (nessuna chiamata LLM: si ricostruisce l'indice e si valutano i primi cinque contesti).

  | max_char | overlap | chunk | recall@5 | precision@5 | hit@5 | MRR |
  | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
  | 512 | 256 | 537 | 0,938 | **0,525** | 1,000 | 1,000 |
  | 512 | 128 | 398 | 0,938 | 0,475 | 1,000 | 0,938 |
  | 512 | 64 | 336 | 0,938 | 0,500 | 1,000 | 0,938 |
  | 768 | 64 | 223 | 0,875 | 0,375 | 1,000 | 1,000 |
  | 768 | 128 | 251 | 0,938 | 0,475 | 1,000 | 1,000 |
  | 768 | 256 | 295 | 0,938 | 0,425 | 1,000 | 1,000 |
  | 1024 | 64 | 165 | 0,938 | 0,450 | 1,000 | 1,000 |
  | **1024** | **128** | **193** | 0,938 | 0,450 | 1,000 | 1,000 |
  | 1024 | 256 | 211 | 0,938 | 0,475 | 1,000 | 1,000 |

- **512/256 sembrava il vincitore** (+0,075 di precision). Verificato end-to-end, non lo è:
  R2_Q006 perde il fatto «ventidue anni» perché i chunk più corti spezzano la testimonianza prima
  che il dettaglio arrivi al generatore, e la regressione act 1+2 scende a MRR 0,714 (contro 0,821).
- **Decisione: scartato**, si resta a 1024/128. **Lezione:** un miglioramento misurato sul solo
  retrieval è un indizio, non una conclusione — la precision guadagnata era evidenza tolta al
  generatore.

---

## Congelamento della Fase 2

**Pipeline in gara:** E5 (qualifica delle fonti nel prompt) + E9 (chunk minimi e deduplicazione) +
E4 (ibrido BM25 + RRF). `TRIM_RATIO=0`, `CHUNK_MAX_CHAR=1024`, `CHUNK_OVERLAP=128`,
`CHUNK_MIN_CHAR=80`, `FETCH_K=15`, `HYBRID=1`. Indice: 31 documenti, **193 chunk**.

| | baseline Fase 2 | finale | delta |
| --- | ---: | ---: | ---: |
| recall@5 | 0,938 | 0,938 | +0,000 |
| precision@5 | 0,500 | 0,450 | −0,050 |
| hit@5 | 1,000 | 1,000 | +0,000 |
| MRR | 0,906 | **1,000** | **+0,094** |
| qualification_rate | 0,500 | 0,600 – 0,800 | + |
| astensioni indebite | 1 | **0** | −1 |
| affermazioni vietate | 1 | **0** | −1 |
| latenza media | 2 758 ms (7/7) | 2 691 ms (7/7) | = |
| costo medio | € 0,000205 (8/8) | € 0,000326 (8/8) | = |

Dry run completo, tutte con `--validate-only` **OK** e `--verify-contexts` a **0 contesti non
tracciabili**:

```bash
python baseline_naive_rag.py --questions eval/questions_round_2.json --round-id round_2 \
  --output outputs/round2/submission_round_2_final.json --rebuild
python baseline_naive_rag.py --questions eval/questions_round_1.json --round-id round_1 \
  --output outputs/round2/submission_round_1_su_corpus_completo.json
python baseline_naive_rag.py --questions eval/sample_questions.json --round-id sample \
  --output outputs/submission_sample.json
make regression
```

### Limiti noti, da dichiarare invece che nascondere

- **La regressione act 1+2 non passa la soglia MRR** (0,821 contro 0,886), per la scelta consapevole
  di E4. Recall e hit sono intatti. `HYBRID=0` reverte in un secondo.
- **`Sicily_location_map_960px` è muto** (0 caratteri): presente nell'indice, inutilizzabile.
- **R2_Q008 resta a recall 0,50**: `agenda_incontri_01` non entra nei primi cinque insieme a
  `registro_passaggio_01`. Come R1_Q008 nella Fase 1, è una domanda multi-hop con cinque slot.
- **La formula «convergenza prudenziale non formalizzata» non viene citata** su R2_Q004: il chunk
  che la contiene non entra nei primi cinque. La risposta è comunque corretta nella sostanza.
- **I verdetti di generation oscillano fra run a configurazione identica** (R2_Q004, R2_Q006,
  R2_Q008 cambiano fra due esecuzioni dello stesso codice). Le metriche di retrieval sono invece
  deterministiche a indice fermo: sono quelle su cui si decide.
- **Il gold del round 2 è nostro.** Otto domande scritte da noi non sono un campione: servono a
  esercitare le famiglie difficili, non a stimare il punteggio.

### Le tre evidenze per lo speech

1. **Retrieval perfetto, storia sbagliata.** R2_Q005 con precision@5 = 1,00 rispondeva «Sì, il
   console ha consegnato una garanzia scritta» citando una copia anonima, mentre il dispaccio che lo
   nega era nei contesti al rank 2. Il fix non è stato recuperare meglio: è stato dire al generatore
   *che cos'è* ogni fonte.
2. **Quattro slot su cinque sprecati in intestazioni.** Il «Non lo so» su R2_Q004 non era prudenza:
   erano due titoli duplicati e due date che avevano occupato i contesti al posto delle prove.
3. **Un miglioramento misurato sul solo retrieval non è un miglioramento.** Lo sweep del chunking
   dava +0,075 di precision e, provato end-to-end, toglieva un fatto richiesto alla risposta.
