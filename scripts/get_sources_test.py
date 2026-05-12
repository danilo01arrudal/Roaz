# scripts/get_sources_test.py
"""
Testa a leitura das fontes a partir da tabela ROAZ_SOURCES.
Lista a contagem total e os primeiros 5 registos PENDING.
"""

from src.harvester.sources_db import load_sources

try:
    # Carrega apenas fontes com status PENDING (padrão)
    pending = load_sources('PENDING')
    print(f"Fontes PENDING: {len(pending)}")

    # Opcional: também lista outros
    success = load_sources('SUCCESS')
    failed = load_sources('FAILED')
    print(f"Fontes SUCCESS: {len(success)}")
    print(f"Fontes FAILED : {len(failed)}")

    print("\nPrimeiros 5 PENDING:")
    for s in pending[:5]:
        print(f"  Título    : {s.title}")
        print(f"  URL       : {s.url}")
        print(f"  Expert ID : {s.expert_id}")
        print()

except Exception as e:
    print(f"FALHA: {e}")
