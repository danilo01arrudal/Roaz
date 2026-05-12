"""
Módulo de leitura das fontes de documentação a partir da tabela ROAZ_SOURCES.
Substitui o antigo sources.py baseado em CSV.
"""

from dataclasses import dataclass
from typing import List, Optional
from src.utils.oracle_connector import get_connection


@dataclass
class DocumentSource:
    """Representa um documento a ser extraído."""
    title: str
    url: str
    expert_id: Optional[str] = 'general'


def load_sources(status_filter: str = 'PENDING') -> List[DocumentSource]:
    """
    Carrega as fontes de documentação directamente da tabela ROAZ_SOURCES.

    Args:
        status_filter: Filtro de status (padrão: 'PENDING').

    Returns:
        Lista de DocumentSource prontos para processamento.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_url, title, expert_id
                FROM roaz_sources
                WHERE status = :status
                ORDER BY source_id
            """, {'status': status_filter})
            return [
                DocumentSource(title=row[1], url=row[0], expert_id=row[2])
                for row in cur.fetchall()
            ]
    finally:
        conn.close()
