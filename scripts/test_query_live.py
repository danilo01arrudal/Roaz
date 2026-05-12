#!/usr/bin/env python3
"""Teste real da pesquisa RAG – requer dados carregados e versão ativa."""

import sys
from src.rag.query import search

pergunta = sys.argv[1] if len(sys.argv) > 1 else "How can I describe Data Guard Broker Concepts?"

print(f"🔍 Pesquisando: {pergunta}")
resultados = search(pergunta, top_k=3)

if not resultados:
    print("⚠️  Nenhum resultado encontrado.")
else:
    for i, r in enumerate(resultados, 1):
        print(f"\n--- Resultado {i} (similaridade: {r['similarity']:.4f}) ---")
        print(f"Chunk ID: {r['chunk_id']}  | Doc ID: {r['doc_id']}  | Source ID: {r['source_id']}")
        print(r['chunk_text'][:500])
        if r['metadata']:
            print(f"Metadados: {r['metadata']}")
