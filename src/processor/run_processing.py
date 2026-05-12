"""
Orquestrador de Processamento — Chunking + Embeddings + Carga + Objetos Oracle.

Fluxo completo:
1. Carrega documentos da tabela documents.
2. Gera chunks semânticos e embeddings (GPU).
3. Insere chunks em roaz_chunks_vnext (com source_id para particionamento).
4. Exporta um Parquet por documento (organizado por guia).
5. Cria dinamicamente os diretórios Oracle e as tabelas externas.
6. Regista a versão em roaz_versions (is_active='N').
"""

import os
import sys
import hashlib
import logging
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from tqdm import tqdm
import oracledb

from src.processor.chunker import chunk_structured, chunk_text_simple
from src.vectorizer.embedding_engine import encode
from src.harvester.extractor import compute_md5
from src.utils.oracle_connector import get_connection

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/run_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("roaz.run_processing")

# ──────────────────────────────────────────────────────────────────
# Parâmetros
# ──────────────────────────────────────────────────────────────────
PARQUET_ROOT = Path(os.getenv("ROAZ_PARQUET_DIR", "/llm_nvme/parquet/roaz"))
PARQUET_ROOT.mkdir(parents=True, exist_ok=True)
BATCH_SIZE = 64


def get_guide_base_url(url: str) -> str:
    """Extrai a URL base do guia a partir de qualquer URL de subpágina."""
    parsed = urlparse(url)
    path = Path(parsed.path)
    parent = path.parent
    base_path = str(parent).rstrip('/') + '/'
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def load_documents(source_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Carrega documentos com conteúdo, retornando os campos necessários
    incluindo source_id para propagação.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if source_id is not None:
                cur.execute("""
                    SELECT d.doc_id, d.source_id, d.source_url, d.title, d.expert_id,
                           d.raw_text, d.content_json
                    FROM documents d
                    JOIN roaz_sources s ON d.source_url LIKE s.source_url || '%'
                    WHERE s.source_id = :sid AND d.raw_text IS NOT NULL
                    ORDER BY d.doc_id
                """, {'sid': source_id})
            else:
                cur.execute("""
                    SELECT doc_id, source_id, source_url, title, expert_id,
                           raw_text, content_json
                    FROM documents
                    WHERE raw_text IS NOT NULL
                    ORDER BY doc_id
                """)
            rows = cur.fetchall()
            docs = []
            for r in rows:
                # Índices:
                # 0: doc_id
                # 1: source_id
                # 2: source_url
                # 3: title
                # 4: expert_id
                # 5: raw_text
                # 6: content_json
                raw_text = r[5]
                if raw_text is not None:
                    if isinstance(raw_text, str):
                        pass
                    elif hasattr(raw_text, 'read'):
                        raw_text = raw_text.read()
                    else:
                        raw_text = str(raw_text)

                content = None
                content_raw = r[6]
                if content_raw is not None:
                    if isinstance(content_raw, (list, dict)):
                        content = content_raw
                    elif isinstance(content_raw, str):
                        try:
                            content = json.loads(content_raw)
                        except Exception:
                            pass
                    elif hasattr(content_raw, 'read'):
                        try:
                            content_str = content_raw.read()
                            content = json.loads(content_str)
                        except Exception:
                            pass
                    else:
                        try:
                            content = json.loads(str(content_raw))
                        except Exception:
                            pass

                source_url = r[2]
                guide_base_url = get_guide_base_url(source_url)
                docs.append({
                    'doc_id': r[0],
                    'source_id': r[1],
                    'source_url': source_url,
                    'title': r[3],
                    'expert_id': r[4],
                    'raw_text': raw_text,
                    'content_json': content,
                    'guide_base_url': guide_base_url
                })
            return docs
    finally:
        conn.close()


def load_source_info() -> Dict[str, tuple]:
    """Retorna dict: source_url_path (sem barra final) -> (source_type, source_id)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT source_url, source_type, source_id FROM roaz_sources")
            return {row[0].rstrip('/'): (row[1], row[2]) for row in cur.fetchall()}
    finally:
        conn.close()


def process_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aplica chunking ao documento, passando source_id."""
    if doc['content_json']:
        chunks = chunk_structured(
            doc['content_json'],
            doc['doc_id'],
            doc['source_id'],        # ← source_id como 3º argumento
            doc['source_url'],
            doc['guide_base_url']
        )
    else:
        chunks = chunk_text_simple(
            doc['raw_text'],
            doc['doc_id'],
            doc['source_id'],        # ← source_id como 3º argumento
            doc['source_url'],
            doc['guide_base_url']
        )
    return chunks


def create_oracle_objects(version_dir: Path):
    """Cria diretórios Oracle e tabelas externas para todos os parquets."""
    print("\n🔧 Criando objetos Oracle (diretórios e tabelas externas)...")
    logger.info("Iniciando criação de diretórios e tabelas externas no Oracle...")

    parquet_files = list(version_dir.rglob("*.parquet"))
    if not parquet_files:
        logger.warning("Nenhum Parquet encontrado.")
        return

    conn = get_connection()
    created_dirs = set()
    try:
        for parquet_file in parquet_files:
            guide_dir = parquet_file.parent
            oracle_dir_name = "PARQUET_" + guide_dir.name.replace('-', '_').replace('.', '_')

            if oracle_dir_name not in created_dirs:
                with conn.cursor() as cur:
                    try:
                        cur.callproc("roaz_utils.create_directory_dynamic_proc", [
                            oracle_dir_name,
                            str(guide_dir),
                            'CREATE'
                        ])
                        print(f"  Diretório Oracle criado: {oracle_dir_name}")
                        logger.info(f"Diretório {oracle_dir_name} criado para {guide_dir}")
                        created_dirs.add(oracle_dir_name)
                    except oracledb.DatabaseError as e:
                        print(f"  ERRO ao criar diretório {oracle_dir_name}: {e}")
                        logger.error(f"Erro ao criar diretório {oracle_dir_name}: {e}")
                        continue

            table_name = f"CHUNKS_EXT_{parquet_file.stem}"[:128]
            table_name = table_name.replace('.', '_').replace('-', '_')

            with conn.cursor() as cur:
                try:
                    cur.callproc("roaz_utils.create_external_table_dynamic_proc", [
                        table_name,
                        oracle_dir_name,
                        parquet_file.name,
                        'CREATE'
                    ])
                    print(f"  Tabela externa criada: {table_name}")
                    logger.info(f"Tabela externa {table_name} criada para {parquet_file.name}")
                except oracledb.DatabaseError as e:
                    print(f"  ERRO ao criar tabela {table_name}: {e}")
                    logger.error(f"Erro ao criar tabela {table_name}: {e}")
    finally:
        conn.close()


def main():
    single_source_id = None
    if '--source_id' in sys.argv:
        idx = sys.argv.index('--source_id')
        if idx + 1 < len(sys.argv):
            single_source_id = int(sys.argv[idx + 1])
            logger.info(f"Modo single-source: processando apenas source_id={single_source_id}")

    logger.info("=== Início do processamento (chunking + embeddings) ===")

    # 1. Carregar documentos
    logger.info("Carregando documentos da tabela documents...")
    docs = load_documents(single_source_id)
    if not docs:
        logger.warning("Nenhum documento encontrado.")
        return
    logger.info(f"Documentos carregados: {len(docs)}")

    # 2. Gerar chunks
    all_chunks = []
    logger.info("Gerando chunks...")
    for doc in tqdm(docs, desc="Chunking"):
        try:
            chunks = process_document(doc)
            all_chunks.extend(chunks)
        except Exception as e:
            logger.error(f"Erro ao processar doc_id={doc['doc_id']}: {e}")
    logger.info(f"Total de chunks gerados: {len(all_chunks)}")

    if not all_chunks:
        logger.warning("Nenhum chunk foi gerado. Encerrando.")
        return

    # 3. Gerar embeddings
    texts = [c['text'] for c in all_chunks]
    logger.info("Gerando embeddings (GPU)...")
    embeddings = encode(texts, batch_size=BATCH_SIZE, show_progress=True)
    if len(embeddings) != len(texts):
        raise RuntimeError("Número de embeddings não corresponde ao número de chunks.")

    # 4. Preparar dados para inserção (com source_id)
    logger.info("Preparando inserção no Oracle...")
    conn = get_connection()
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    version_name = f"v{timestamp}"
    version_dir = PARQUET_ROOT / version_name
    version_dir.mkdir(parents=True, exist_ok=True)

    sequence_sql = "SELECT roaz_chunks_seq.NEXTVAL FROM dual"
    rows_to_insert = []
    doc_chunks: Dict[int, list] = {}

    source_info = load_source_info()

    for i, chunk in enumerate(tqdm(all_chunks, desc="Preparando dados")):
        meta = chunk['metadata']
        chunk_text = chunk['text']
        md5 = compute_md5(chunk_text)
        emb = embeddings[i]

        with conn.cursor() as cur:
            cur.execute(sequence_sql)
            chunk_id = cur.fetchone()[0]

        rows_to_insert.append((
            chunk_id,
            meta['doc_id'],
            meta['source_id'],         # ← source_id no INSERT
            meta['chunk_index'],
            md5,
            emb,
            json.dumps(meta)
        ))

        doc_id = meta['doc_id']
        if doc_id not in doc_chunks:
            doc_chunks[doc_id] = []
        guide_url = meta.get('guide_base_url', '')
        doc_chunks[doc_id].append((chunk_id, chunk_text, meta['url'], guide_url))

    # 5. Inserir na roaz_chunks_vnext (com coluna SOURCE_ID)
    logger.info("Inserindo chunks na roaz_chunks_vnext...")
    insert_sql = """
        BEGIN
            INSERT INTO roaz_chunks_vnext (chunk_id, doc_id, source_id, chunk_index, md5_hash, embedding, metadata_json)
            VALUES (:1, :2, :3, :4, :5, :6, :7);
        END;
    """
    with conn.cursor() as cur:
        cur.setinputsizes(None, None, None, None, None, oracledb.DB_TYPE_VECTOR, None)
        cur.executemany(insert_sql, rows_to_insert)
        conn.commit()
    logger.info(f"{len(rows_to_insert)} chunks inseridos.")

    # 6. Exportar Parquets por documento
    logger.info(f"Exportando Parquets por documento para {version_dir}...")
    for doc_id, chunks in tqdm(doc_chunks.items(), desc="Parquets"):
        if not chunks:
            continue
        first = chunks[0]
        source_url = first[2]
        guide_url = first[3]

        md5_guide = hashlib.md5(guide_url.rstrip('/').encode('utf-8')).hexdigest()
        md5_url = hashlib.md5(source_url.encode('utf-8')).hexdigest()

        source_type, src_id = source_info.get(guide_url.rstrip('/'), ('UNKNOWN', 'UNKNOWN'))
        guide_dir = version_dir / f"{source_type}_{md5_guide}_{src_id}"
        guide_dir.mkdir(parents=True, exist_ok=True)

        parquet_file = guide_dir / f"{doc_id}_{md5_url}_{version_name}.parquet"

        df = pd.DataFrame([(cid, txt) for cid, txt, _, _ in chunks], columns=['chunk_id', 'chunk_text'])
        df.to_parquet(parquet_file, index=False)

    logger.info(f"Parquets exportados para {version_dir}")

    # 7. Criar objetos Oracle
    create_oracle_objects(version_dir)

    # 8. Registrar versão
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO roaz_versions (version_name, chunks_table, parquet_file, is_active)
            VALUES (:1, 'ROAZ_CHUNKS_VNEXT', :2, 'N')
        """, (version_name, str(version_dir)))
        conn.commit()
    logger.info(f"Versão {version_name} registrada em roaz_versions.")

    conn.close()
    logger.info("=== Processamento concluído ===")
    logger.info(f"Versão: {version_name}")
    logger.info(f"Directório de Parquets: {version_dir}")


if __name__ == "__main__":
    main()
