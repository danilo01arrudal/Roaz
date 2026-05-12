"""
Módulo de Consulta RAG — Pesquisa vetorial no Oracle e recuperação de textos.

Utiliza o índice HNSW sobre roaz_chunks (sinónimo) e lê os textos completos
dos ficheiros Parquet da versão ativa.
"""

import logging
import json
from pathlib import Path
from typing import List, Optional, Dict
import numpy as np
import pandas as pd
import oracledb
from sentence_transformers import SentenceTransformer
from src.utils.oracle_connector import get_connection

logger = logging.getLogger("roaz.query")

# ──────────────────────────────────────────────────────────────────
# Singleton do modelo de embeddings
# ──────────────────────────────────────────────────────────────────
_model = None

def get_model() -> SentenceTransformer:
    """Carrega o modelo de embeddings uma única vez."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-mpnet-base-v2", device="cuda")
    return _model


def _get_active_version_dir() -> Optional[Path]:
    """Devolve o diretório da versão ativa registada em roaz_versions."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT parquet_file
                FROM roaz_versions
                WHERE is_active = 'Y'
                FETCH FIRST 1 ROW ONLY
            """)
            row = cur.fetchone()
            if row:
                return Path(row[0])
    finally:
        conn.close()
    return None


def _load_parquet_texts(parquet_file: Path) -> Dict[int, str]:
    """Carrega um ficheiro Parquet e devolve dicionário chunk_id -> chunk_text."""
    try:
        df = pd.read_parquet(parquet_file)
        return dict(zip(df['chunk_id'], df['chunk_text']))
    except Exception as e:
        logger.error(f"Erro ao ler Parquet {parquet_file}: {e}")
        return {}


def search(
    query: str,
    source_ids: Optional[List[int]] = None,
    top_k: int = 5
) -> List[Dict[str, any]]:
    """
    Pesquisa vetorial e retorna lista de resultados com texto, metadados e similaridade.

    Args:
        query: Texto da pergunta.
        source_ids: Lista opcional de source_id para restringir a pesquisa.
        top_k: Número máximo de resultados.

    Returns:
        Lista de dicionários com:
        - chunk_id, doc_id, source_id, chunk_index
        - similarity (distância coseno, quanto menor melhor)
        - chunk_text
        - metadata (dicionário ou None)
    """
    model = get_model()

    # Gera embedding e converte para FLOAT32 (compatível com VECTOR(FLOAT32) do Oracle)
    query_emb = np.array(model.encode(query)).astype(np.float64).tolist()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. Pesquisa vetorial
            if source_ids:
                # Gera lista SQL segura (source_ids são inteiros controlados)
                ids_str = ','.join(str(sid) for sid in source_ids)
                sql = f"""
                    SELECT chunk_id, doc_id, source_id, chunk_index,
                           embedding <=> :emb AS similarity,
                           metadata_json
                    FROM roaz_chunks
                    WHERE source_id IN ({ids_str})
                    ORDER BY similarity
                    FETCH FIRST :k ROWS ONLY
                """
            else:
                sql = """
                    SELECT chunk_id, doc_id, source_id, chunk_index,
                           embedding <=> :emb AS similarity,
                           metadata_json
                    FROM roaz_chunks
                    ORDER BY similarity
                    FETCH FIRST :k ROWS ONLY
                """

            # Indica que :emb é do tipo VECTOR
            cur.setinputsizes(emb=oracledb.DB_TYPE_VECTOR)
            cur.execute(sql, {'emb': query_emb, 'k': top_k})

            rows = cur.fetchall()
            if not rows:
                return []

            # 2. Obter os textos dos Parquets da versão ativa
            version_dir = _get_active_version_dir()
            if version_dir is None:
                logger.warning("Nenhuma versão ativa encontrada; os textos podem estar em falta.")
                texts_by_id = {}
            else:
                texts_by_id = {}
                for parquet_file in version_dir.rglob("*.parquet"):
                    texts_by_id.update(_load_parquet_texts(parquet_file))

            # 3. Montar resultados
            results = []
            for row in rows:
                chunk_id = row[0]
                doc_id = row[1]
                source_id = row[2]
                chunk_index = row[3]
                similarity = row[4]
                metadata_raw = row[5]

                # Lê o LOB enquanto a conexão está ativa
                if metadata_raw is not None:
                    try:
                        # Se for um objeto LOB, lê o conteúdo
                        metadata_str = metadata_raw.read()
                        metadata = json.loads(metadata_str)
                    except AttributeError:
                        # Já é uma string comum
                        metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                    except Exception:
                        metadata = str(metadata_raw)
                else:
                    metadata = None

                chunk_text = texts_by_id.get(chunk_id, "[Texto não encontrado]")

                results.append({
                    'chunk_id': chunk_id,
                    'doc_id': doc_id,
                    'source_id': source_id,
                    'chunk_index': chunk_index,
                    'similarity': similarity,
                    'chunk_text': chunk_text,
                    'metadata': metadata
                })

            return results
    finally:
        conn.close()
