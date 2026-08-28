# Fase 2 — corpus completo (act 1-4): archivio ricco, casi difficili e hardening

> **Stato: eseguito.** Step 0-7 completati; vedi `TEAM_NOTES.md` (Problemi 6-9 ed «Esperimenti della
> Fase 2») per misure e decisioni. Scostamenti rispetto al piano, tutti documentati:
>
> * **Step 0** — il release pack ufficiale non era disponibile: le voci di manifest per act 3 e 4
>   sono state scritte da noi e marcate `metadata_source: team_inferred`, sovrascrivibili da
>   `install_release.py` appena il pack arriva.
> * **Ordine degli esperimenti** — E4 è stato anticipato al posto di E3, perché `CohereReranker`
>   richiede una chiave esterna e il piano prevedeva comunque un fallback lessicale: BM25 + RRF *è*
>   quel fallback, in stdlib. Dopo E4 l'MRR sul corpus di gara è 1,000 e E3 non ha più un bersaglio.
> * **Aggiunto E9** (chunk minimi e deduplicazione), non previsto: causa vera di un'astensione con
>   recall 1,00.
> * **E2 misurato e lasciato spento** (+0,013 di precision = rumore); **E6 misurato e scartato**;
>   **E7 non eseguito** perché nessuna domanda del gold ne misura l'effetto; **E8 già soddisfatto**
>   da E4 + E5.
> * **Gate act 1+2 non superato sull'MRR** (0,821 contro 0,886): eccezione consapevole, la soglia
>   non è stata riscritta.

## Context

La definizione delle fasi nella `PARTICIPANT_GUIDE.md` era sbagliata. Quella corretta è:

* **Fase 1 = act 1 + act 2** — già completata e misurata (`outputs/round1/submission_round_1_post_opt.json`).
* **Fase 2 = act 1 + 2 + 3 + 4** — questo piano.

La Fase 1 non va rifatta: aveva già girato sull'intero manifest, cioè esattamente su act 1 + 2.
Che l'archivio andasse oltre i due atti era peraltro scritto nel codice dello starter — l'help di
`scripts/install_release.py` porta come esempio `act_4.zip`.

**Da dove si parte.** La Fase 1 lascia in eredità gli strumenti che rendono possibile questo giro:

| Strumento | Cosa fa |
| --- | --- |
| `score_submission.py` | recall@5, precision@5, hit@5, MRR, `dont_know_rate`, latenza, costo, diagnosi per domanda, diff prima/dopo |
| cache di parsing (`outputs/parse_cache/`) | Docling parsa ogni file una volta sola: un `--rebuild` dopo l'arrivo di nuovi atti riprocessa **solo** i file nuovi |
| `build_parser(ocr)` | OCR spento sui PDF nativi, EasyOCR su scansioni e immagini, in base alla `modality` del manifest |
| `build_splitter()` | `max_char` finalmente rispettato (`RecursiveSplitter` lasciava passare intere le foglie troppo grandi) |
| `--act` | ricostruisce un sottoinsieme in una collection separata — è il set di regressione |

**Numeri da difendere** (round 1, corpus act 1+2, 174 chunk):

| recall@5 | precision@5 | hit@5 | MRR | latenza media | costo medio |
| --- | --- | --- | --- | --- | --- |
| 0,952 | 0,571 | 1,000 | 0,886 | 2 772 ms (7/7) | € 0,000286 (8/8) |

**Che cosa cambia con act 3 e 4.** Il corpus passa da 15 a 31 documenti: **più che raddoppiano i
distrattori**. La precision@5 è già il punto debole a 0,571 con 15 documenti; è la metrica che
rischia di più. Il costo ha ancora ~16× di margine nella fascia massima: c'è spazio per una seconda
chiamata per domanda (reranker, captioner) se si dimostra che la paga.

**Ricognizione del materiale nuovo** (fatta con `docling_parse`, senza ingest):

| Cartella | File | Layer di testo | Difficoltà attesa |
| --- | --- | --- | --- |
| `act_3` | `agenda_incontri_01`, `lettera_porti_feudi_01`, `movimenti_diplomatici_01`, `registro_passaggio_01` (PDF) | sì, nativi | tabelle e registri: il chunking conta |
| `act_3` | `Sicily_location_map_960px`, `mappa_porti_occidentali_annotata_01`, `lettera_danneggiata_01`, `manifesto_politico_01`, `scansione_manoscritta_01` (PNG) | **no**, immagini pure | OCR obbligatorio; una mappa vale per la geografia, non per le parole |
| `act_4` | `articolo_propaganda_01`, `bozza_comitato_palermo_v1`, `nota_comitato_palermo_v2`, `fonte_dannosa_senza_qualifica_01`, `lettera_allusiva_donnafugata_01`, `nota_diplomatica_incompleta_01`, `testimonianza_contestata_lanza_01` (PDF) | sì, tre con immagini incorporate | propaganda, **bozza contro versione definitiva**, fonte dannosa, testimonianza contestata |

I nomi dicono già quali sono le trappole: `bozza_comitato_palermo_v1` e `nota_comitato_palermo_v2`
sono due versioni dello stesso atto, e la guida avverte che «una versione aggiornata non cancella il
valore documentario della bozza». `fonte_dannosa_senza_qualifica_01` è una fonte che **danneggia se
citata senza qualificarla**.

---

## Step 0 — Prerequisito bloccante: il manifest

Il commit `8665e52` ha aggiunto 16 file sotto `data/act_3` e `data/act_4` ma **non ha toccato
`data/manifest.json`**, che dichiara ancora `available_acts: [1, 2]` e 15 documenti. `iter_ingest_files()`
legge il manifest: finché non viene aggiornato, quei file non entrano nell'indice e un `document_id`
che li citasse farebbe fallire la validazione. Anche `data/checksums.sha256` e
`data/license_manifest.csv` sono fermi a 15 righe.

**Decisione presa: si usa il release pack ufficiale della dashboard.**

```bash
python scripts/install_release.py /percorso/al/act_3_act_4.zip
```

Lo script copia i file e fonde le voci del `release_manifest.json` nel manifest esistente
(`merge_manifest`), aggiornando `available_acts` e `last_release_id`. **Non** aggiorna
`checksums.sha256` né `license_manifest.csv`: se il pack non li porta, vanno rigenerati a parte.

**Verifica di Step 0 — nessun passo successivo parte senza queste tre righe verdi:**

```bash
python -c "import json; m=json.load(open('data/manifest.json')); print(m['available_acts'], len(m['documents']))"
# atteso: [1, 2, 3, 4] 31

python - <<'PY'
import json, hashlib
from pathlib import Path
m = json.load(open("data/manifest.json"))
for d in m["documents"]:
    for r in d["file_records"]:
        p = Path(r["path"])
        assert p.is_file(), f"manca il file: {p}"
        if "sha256" in r:
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            assert digest == r["sha256"], f"checksum diverso: {p}"
print("manifest coerente con il filesystem")
PY
```

Se il pack ufficiale non arriva, l'alternativa — generare noi le voci dal filesystem
(`document_id` = nome del file, convenzione rispettata da tutte e 15 le voci attuali) — resta
possibile ma va decisa esplicitamente: cambierebbe la fonte di verità con metadati non ufficiali.

---

## Step 1 — Ricostruire l'indice e verificare che ogni documento ci sia davvero

```bash
python baseline_naive_rag.py --questions eval/questions_round_1.json --round-id round_1 \
  --output outputs/round2/submission_smoke.json --rebuild
```

La cache di parsing riprocessa solo i 16 file nuovi; i 15 vecchi arrivano dal disco.

**Modifica necessaria a `baseline_naive_rag.py`:** oggi un documento che produce zero chunk sparisce
in silenzio. Con documenti solo-immagine è lo scenario più probabile e la guida chiede esplicitamente
di separare «il testo non è stato recuperato» da «recuperato ma interpretato male». `ingest_corpus()`
deve contare i chunk per `document_id` e stampare in chiaro chi è entrato con quanto, segnalando i
documenti a zero:

```
ingest: manifesto_politico_01 <- manifesto_politico_01.png (ocr=on) -> 2 chunk
ATTENZIONE: 1 documento non ha prodotto nessun chunk: lettera_danneggiata_01
```

**Controllo dell'instradamento OCR sui nuovi materiali.** La regola attuale è «OCR spento per
`modality` ∈ {`text`, `table`}, EasyOCR per tutto il resto». Due punti da verificare, non da dare
per scontati:

1. i 5 PNG di `act_3` devono produrre testo utilizzabile (oggi `mappa_geografica_semplice_01.png`
   rende un solo chunk: poco);
2. i PDF di `act_4` con immagini incorporate hanno un layer di testo, quindi finiscono con OCR
   spento — va confrontato il testo estratto con e senza OCR (`FORCE_OCR_ALL=1`) per capire se dentro
   le immagini c'è contenuto che stiamo perdendo. Confronto per documento sul numero di caratteri
   estratti, non a occhio.

---

## Step 2 — Strumento nuovo: verifica del supporto testuale dei contesti

`SCORING_AND_FAIRNESS.md`: «Ogni contesto caricato viene confrontato con il corpus tramite supporto
testuale normalizzato. Se il contenuto non è riconducibile al documento indicato, la domanda viene
segnalata e la Faithfulness della domanda è zero.» Con l'OCR sulle scansioni questo è il rischio
numero uno di tutta la Fase 2, e vale fino a 18 punti.

Aggiungere a `score_submission.py` un `--verify-contexts`: per ogni contesto, normalizzare
(minuscole, senza accenti, spazi compattati — la funzione `normalize()` esiste già) e verificare che
il testo sia rintracciabile nel parsing di quel `document_id`, letto dalla cache
`outputs/parse_cache/`. Nessuna API, nessuna dipendenza nuova. Uscita: elenco dei contesti non
tracciabili, con `question_id` e `document_id`.

È anche il modo di soddisfare il punto della guida «verificate che ogni contesto finale sia davvero
quello passato al generatore e abbia `document_id` valido».

---

## Step 3 — Set di regressione della Fase 1

Già verificato funzionante: `--act 1 2` ricostruisce esattamente il corpus di Fase 1 in una
collection separata e riproduce il `post_opt` metrica per metrica.

```bash
make regression   # da aggiungere al Makefile
```

```bash
python baseline_naive_rag.py --questions eval/questions_round_1.json --round-id round_1 --act 1 2 \
  --qdrant-path outputs/qdrant_act12 --output outputs/round1/regressione_act12.json --rebuild
python score_submission.py --submission outputs/round1/regressione_act12.json \
  --annotations eval/annotations_round_1.json --baseline outputs/round1/submission_round_1_post_opt.json
```

Soglia: recall@5 ≥ 0,952 e MRR ≥ 0,886. Ogni esperimento della Fase 2 passa **anche** da qui, non
solo dalle domande nuove: è il modo di accorgersi che un miglioramento su act 3-4 ha rotto act 1-2.

Va aggiunto un secondo confronto, sul corpus completo: le stesse 8 domande del round 1 con tutti i
31 documenti indicizzati. La differenza fra i due numeri misura **quanto costano i distrattori
nuovi** — probabilmente il dato più interessante da raccontare nello speech.

---

## Step 4 — Gold set esteso

Le domande ufficiali del round 2 arrivano dalla dashboard. In attesa, `eval/annotations_round_2.json`
va costruito con la stessa forma di `eval/annotations_round_1.json`, coprendo le quattro famiglie
difficili — una domanda ciascuna come minimo:

1. **Solo-immagine**: un fatto che esiste soltanto in `scansione_manoscritta_01` o
   `lettera_danneggiata_01`. Misura se l'OCR serve a qualcosa.
2. **Mappa**: una domanda geografica su `mappa_porti_occidentali_annotata_01`. Probabile astensione
   con la pipeline attuale — ed è un risultato onesto da annotare, non un fallimento da nascondere.
3. **Conflitto di versione**: una domanda a cui `bozza_comitato_palermo_v1` e
   `nota_comitato_palermo_v2` rispondono diversamente. `relevant_sources` = **entrambe**; la risposta
   corretta le presenta come versioni concorrenti e data la più recente senza cancellare la bozza.
4. **Fonte dannosa**: una domanda che porta il retrieval su `fonte_dannosa_senza_qualifica_01` o
   `testimonianza_contestata_lanza_01`. Si usano i campi già presenti nello schema delle annotazioni:
   `harmful_if_unqualified`, `forbidden_claims`, `uncertainty_required`.

**Nuova metrica nello scorer:** *qualification rate* — quando la risposta cita un documento elencato
in `harmful_if_unqualified`, contiene anche una qualificazione (propaganda, fonte contestata, bozza,
versione non definitiva, testimonianza tardiva)? Si misura con la stessa logica di `required_facts`,
a costo zero, e mappa direttamente sull'Historical Reasoning e sulla Faithfulness.

---

## Step 5 — Esperimenti, uno alla volta

Protocollo invariato dalla Fase 1: si cambia **una** variabile, si rigenera la submission in
`outputs/round2/submission_round_2_E<n>.json`, si confronta con `--baseline`, si passa **sia** il
gate sulle domande nuove **sia** la regressione act 1+2, si scrive il blocco in `TEAM_NOTES.md`
anche quando l'esito è negativo.

**E2 — Consegnare meno di 5 contesti (taglio adattivo).** *Ipotesi:* con 31 documenti la
precision@5 crolla; tagliare i contesti sotto soglia la alza e riduce il rumore al generatore.
*Ostacolo tecnico già accertato:* `QdrantVectorstore.search()` **scarta il punteggio** —
`_point_to_chunk` costruisce il `Chunk` dal solo payload — quindi serve passare da
`client.query_points`. *Rischio:* è la mossa che può far scendere il recall; si misurano insieme.

**E3 — Recuperare largo, consegnare stretto (reranking `k=15 → 5`).** *Ipotesi:* il denso trova i
documenti ma li ordina male; con più distrattori il problema peggiora. *Evidenza dalla Fase 1:* su
R1_Q003 la lettera decisiva è al rank 5. *Modifica:* `CohereReranker(top_n=5)` con **fallback
lessicale locale** se la chiave manca — una dipendenza esterna che cade durante la Gold Run sarebbe
fatale. *Costo:* una chiamata in più, coperta dal margine; la latenza va rimisurata.

**E4 — Ibrido BM25 + RRF.** *Ipotesi:* nomi, luoghi e date del 1860 sono terreno di BM25, non del
denso. *Evidenza:* R1_Q001 recuperava `garib_d09`, che nomina Marsala ma nel 1862. *Nota:*
`rank_bm25` sarebbe una dipendenza nuova — prima verificare se bastano ~30 righe di stdlib.

**E5 — Prompt: qualificare le fonti.** *Ipotesi:* il `GROUNDING` attuale non chiede di distinguere
fatto / indizio / congettura né di segnalare propaganda e versioni contestate: sono punti di
Historical Reasoning lasciati sul tavolo, ed è l'unico esperimento che agisce direttamente sul
rischio «fonte dannosa citata senza qualifica». *Modifica:* portare `reliability`, `origin_type` e
`act` nel payload dei chunk ed esporli nel template; il prompt qualifica la fonte quando la
`reliability` lo richiede. *Costo:* zero chiamate in più. **Dove la `reliability` del manifest manca
o è `unknown`, si usano etichette lette e scritte da noi, dichiarate come tali in `TEAM_NOTES.md` e
sovrascritte appena arriva il dato ufficiale.**

**E6 — Sweep del chunking sul corpus nuovo.** `CHUNK_MAX_CHAR` e `CHUNK_OVERLAP` sono già
parametrizzati da ambiente; la cache di parsing rende lo sweep economico. Griglia
`max_char ∈ {512, 768, 1024}` × `overlap ∈ {64, 128, 256}`, giudicata su `hit@5` e `MRR`. Da fare
**dopo** l'ingresso di act 3-4: registri e tabelle hanno una granularità diversa dalle lettere.

**E7 — Didascalie per immagini e mappe.** *Ipotesi:* l'OCR di una mappa produce un elenco di toponimi
senza relazioni; una didascalia generata da un modello con visione rende la mappa interrogabile.
*Modifica:* captioner sul PNG in fase di ingest, con la didascalia indicizzata **accanto** al testo
OCR, mai al posto suo — la guida vieta di sostituire l'originale con una ricostruzione più leggibile.
*Costo:* una chiamata una tantum per immagine, in ingest, non per domanda. *Gate:* deve far salire il
recall sulla domanda-mappa del gold senza toccare le altre.

**E8 — Conflitti di versione.** *Ipotesi:* con `bozza_comitato_palermo_v1` e
`nota_comitato_palermo_v2` in indice, il retrieval ne porta una sola e la risposta presenta come
definitiva una versione qualsiasi. *Modifica:* niente deduplicazione — entrambe restano indicizzate;
il prompt riceve la data e la `reliability` e deve dichiarare l'esistenza di due versioni. *Metrica:*
la domanda-conflitto del gold ha `relevant_sources` con entrambi i documenti, quindi il recall
misura da solo se il retrieval le porta tutte e due.

Ordine consigliato: **E5 → E3 → E2 → E7 → E8 → E4 → E6**. E5 è gratis e protegge la Faithfulness;
E3 attacca il ranking, che è il difetto misurato; E2 dipende dal lavoro tecnico su `query_points`;
E7 ed E8 aprono materiale che oggi è muto.

---

## Step 6 — Telemetria e budget

Dopo ogni esperimento che aggiunge una chiamata, rimisurare **prima** di tenerlo:

* latenza: fascia piena sotto i 4 s. In Fase 1 una singola esecuzione ha registrato 16 607 ms su una
  domanda per un'attesa dell'API, portando la media a 3 950 ms. Il tempo non è nostro: si misura più
  volte prima di dichiararlo.
* costo: € 0,000286 per domanda oggi, contro una soglia di € 0,005. Margine ~16×, non infinito: ogni
  chiamata va dichiarata in `model_calls` con i token reali, mai stimati.

---

## Step 7 — Congelamento e dry run prima della Gold

1. Tag o commit dedicato della pipeline che va in gara, con modello e configurazione annotati.
2. Dry run completo su **tutte** le domande disponibili (sample, round 1, round 2), tutte le
   submission sotto `outputs/`.
3. `--validate-only` su ognuna, poi validazione sul sito — che non consuma il tentativo.
4. Checklist finale: ≤ 5 contesti, rank 1..N consecutivi, `document_id` nel manifest, nessun campo
   extra, telemetria completa, `--verify-contexts` senza segnalazioni.

---

## Chiusura di fase — «Avete finito quando»

| Criterio della guida | Come lo si soddisfa |
| --- | --- |
| Tutte le domande disponibili producono submission valide in `outputs/` | Step 7, punto 2 |
| Conoscete latenza, costo medio e limiti residui | Sezione Sistema dello scorer + limiti noti in `TEAM_NOTES.md` |
| Il diario contiene le tre evidenze più importanti per lo speech | Candidate già in mano: (1) l'OCR mirato da solo peggiorava tutto e la causa vera era il chunking; (2) `max_char` non ha mai agito perché `RecursiveSplitter` lascia passare le foglie troppo grandi; (3) quanto costano in recall i distrattori di act 3-4 |

**Annotazione richiesta per ogni documento problematico** (formato della guida): `document_id`,
`modality`, qualità dell'OCR, trasformazioni applicate, cosa ha funzionato e cosa no — tenendo
sempre separato «il testo non è stato recuperato» da «il modello lo ha recuperato ma lo ha
interpretato male». Lo strumento che distingue i due casi esiste già: la colonna diagnosi dello
scorer (`RETRIEVAL_FAIL` contro `GENERATION_FAIL`).

---

## File toccati

| File | Modifica |
| --- | --- |
| `data/manifest.json` | esteso dal release pack ufficiale (Step 0) |
| `baseline_naive_rag.py` | conteggio chunk per documento con segnalazione degli zero; `reliability` nel payload e nel prompt (E5); poi le modifiche dei singoli esperimenti |
| `score_submission.py` | `--verify-contexts`, *qualification rate* |
| `eval/annotations_round_2.json` | **nuovo** — gold delle quattro famiglie difficili + domande ufficiali |
| `tests/test_score.py` | casi per le metriche nuove |
| `Makefile` | target `regression` |
| `TEAM_NOTES.md` | un blocco per esperimento e una riga per documento problematico |

## Verifica

1. `make test` verde.
2. `make sample` termina con `Submission valida: outputs/submission_sample.json`.
3. Manifest coerente col filesystem (script di Step 0) e `available_acts = [1, 2, 3, 4]`.
4. Nessun documento del manifest entra con zero chunk.
5. `make regression` non scende sotto recall@5 0,952 e MRR 0,886.
6. `--verify-contexts` non segnala contesti non tracciabili.
7. `git status` pulito, PR aperta con `gh` e lasciata in review.

## Fuori scope

RAPTOR, parent-child, query rewriting / HyDE, cache semantica, async fan-out. Entrano solo se i
numeri di questa fase dicono che servono.
