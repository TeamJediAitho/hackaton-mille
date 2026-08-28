# Team Notes

## Problema 1

- **Problema:** Il tempo della prima ingestion con Docling risulta enorme, soprattutto per documenti scannerizzati e non digitali. Docling gira in locale ed è molto lento: worst case di ingestion misurato a 37,18 s.
- **Com'è stato risolto:** Non è stato risolto, ma discusso internamente.
- **Cosa ho imparato:** In funzione dell'ambiente e delle risorse a disposizione può essere utile sostituire Docling con una soluzione non locale, ad es. le API di parsing/OCR di OpenAI, o usare librerie di parsing più coerenti. Utilizzando ad esempio una pipeline di check del file (se scanned o digital) potrebbe essere utile utilizzare OCR solo sui documenti scansionati. Un'altra idea potrebbe essere parallelizzare il parsing. Tesseract è spesso più veloce. NOTA: le impostazioni sulla lingua potrebbero migliorare la qualità.

---

Copiate il blocco per aggiungere un nuovo problema, tranquilli che anche il coding agent lo sa gestire
