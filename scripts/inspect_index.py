"""Ispeziona l'indice Qdrant locale costruito da baseline_naive_rag.py.

NB: funziona solo quando NESSUN altro processo tiene aperto l'indice
(un run di baseline_naive_rag.py in corso tiene il lock su outputs/qdrant).

Esempi:
  python scripts/inspect_index.py                 # conteggio chunk per documento
  python scripts/inspect_index.py --doc garib_d08  # tutti i chunk di un documento
  python scripts/inspect_index.py --grep Marsala   # chunk che contengono "Marsala"
"""

from __future__ import annotations

import argparse
import os
from collections import Counter

from qdrant_client import QdrantClient


def scroll_all(client: QdrantClient, collection: str):
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        yield from points
        if offset is None:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", default=os.getenv("QDRANT_PATH", "outputs/qdrant"))
    parser.add_argument("--collection", default=os.getenv("COLLECTION_NAME", "caso_dei_mille"))
    parser.add_argument("--doc", help="dump tutti i chunk di questo document_id")
    parser.add_argument("--grep", help="mostra i chunk il cui testo contiene questa stringa (case-insensitive)")
    parser.add_argument("--chars", type=int, default=160, help="lunghezza snippet")
    args = parser.parse_args()

    try:
        client = QdrantClient(path=args.path)
    except RuntimeError as exc:
        raise SystemExit(f"Impossibile aprire l'indice ({exc}).\nChiudi ogni run di baseline_naive_rag.py e riprova.")

    if not client.collection_exists(args.collection):
        raise SystemExit(f"Collection '{args.collection}' assente in {args.path}. Collezioni: {client.get_collections()}")

    points = list(scroll_all(client, args.collection))
    per_doc = Counter(p.payload.get("document_id", "<no document_id>") for p in points)

    print(f"{args.path} :: {args.collection} :: {len(points)} chunk totali, {len(per_doc)} documenti\n")
    for document_id, n in sorted(per_doc.items()):
        print(f"  {n:4d}  {document_id}")

    if args.doc:
        print(f"\n--- chunk di {args.doc} ---")
        for p in points:
            if p.payload.get("document_id") == args.doc:
                print(f"[{p.id}] {(p.payload.get('text') or '').strip()[: args.chars]!r}")

    if args.grep:
        needle = args.grep.lower()
        print(f"\n--- chunk che contengono {args.grep!r} ---")
        for p in points:
            text = p.payload.get("text") or ""
            if needle in text.lower():
                idx = text.lower().index(needle)
                snippet = text[max(0, idx - args.chars // 2) : idx + args.chars // 2].strip()
                print(f"{p.payload.get('document_id')}: …{snippet}…")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
