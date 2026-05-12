"""
Job Runner — Execução resiliente e controlada da extração do Roaz Codex.

Agora lê as fontes da tabela ROAZ_SOURCES (não mais de CSV).
Cada job é processado independentemente, com retentativas e pausas.
"""

import re
import unicodedata
import os
import asyncio
import logging
import json
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import aiofiles

from src.harvester.sources_db import load_sources
from src.harvester.extractor import (
    discover_links_from_toc,
    extract_content,
    extract_structured
)
from src.utils.oracle_connector import get_connection
from src.harvester.dynamic_extractor import DynamicExtractor

# ──────────────────────────────────────────────────────────────────
# Configuração de logging
# ──────────────────────────────────────────────────────────────────
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/job_runner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("roaz.job_runner")

# ──────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────
STAGING_ROOT = Path("data/staging")
STAGING_ROOT.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────
# Funções auxiliares
# ──────────────────────────────────────────────────────────────────
def make_staging_dir(base_url: str) -> Path:
    """Converte URL base em subdiretório de staging."""
    parsed = urlparse(base_url)
    parts = parsed.path.strip('/').split('/')
    if parts and len(parts) > 1 and len(parts[0]) == 2:  # idioma, ex: 'en'
        parts = parts[1:]
    return STAGING_ROOT / '/'.join(parts)


def get_guide_base_url(page_url: str) -> str:
    """
    Extrai a URL base do guia a partir da URL de uma página.
    Exemplo: https://.../26/admin/intro.html → https://.../26/admin/
    """
    parsed = urlparse(page_url)
    path = Path(parsed.path)
    parent = path.parent
    base_path = str(parent).rstrip('/') + '/'
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def safe_filename(text: str, max_length: int = 80) -> str:
    """
    Converte um texto arbitrário num nome de ficheiro seguro.
    """
    text = unicodedata.normalize('NFKD', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s-]', '', text)
    text = text.strip().replace(' ', '_')
    return text[:max_length]


def save_text_staging(doc: dict, target_dir: Path):
    """Guarda a estrutura (.jsonl) no diretório indicado."""
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = safe_filename(doc['title'])
    if 'content_json' in doc and doc['content_json']:
        with open(target_dir / f"{doc['doc_id']}_{safe}.jsonl", 'w', encoding='utf-8') as jf:
            for sec in doc['content_json']:
                jf.write(json.dumps(sec, ensure_ascii=False) + '\n')


# ──────────────────────────────────────────────────────────────────
# Gerenciamento de jobs (agora sobre ROAZ_SOURCES)
# ──────────────────────────────────────────────────────────────────
def fetch_next_pending_job():
    """Busca um job com status PENDING e marca como RUNNING (bloqueio otimista)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source_id, source_url, title, expert_id, attempt
                FROM roaz_sources
                WHERE status = 'PENDING'
                ORDER BY source_id
                FETCH FIRST 1 ROW ONLY
            """)
            row = cur.fetchone()
            if not row:
                return None

            source_id = row[0]
            cur.execute("""
                UPDATE roaz_sources 
                SET status = 'RUNNING', updated_at = SYSTIMESTAMP
                WHERE source_id = :id AND status = 'PENDING'
            """, {'id': source_id})

            if cur.rowcount == 0:
                conn.commit()
                return None

            conn.commit()
            return {
                'job_id': source_id,
                'source_url': row[1],
                'title': row[2],
                'expert_id': row[3],
                'attempt': row[4] + 1
            }
    finally:
        conn.close()


def mark_job_success(job_id):
    """Marca um job como concluído com sucesso."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE roaz_sources 
                SET status = 'SUCCESS', last_processed = SYSTIMESTAMP,
                    updated_at = SYSTIMESTAMP
                WHERE source_id = :id
            """, {'id': job_id})
            conn.commit()
    finally:
        conn.close()


def mark_job_failed(job_id, error_msg):
    """Regista a falha de um job e incrementa a tentativa."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE roaz_sources 
                SET status = 'FAILED', last_error = :err,
                    attempt = attempt + 1, updated_at = SYSTIMESTAMP
                WHERE source_id = :id
            """, {'err': str(error_msg)[:1000], 'id': job_id})
            conn.commit()
    finally:
        conn.close()


def requeue_failed_jobs(max_attempts=3):
    """Coloca em PENDING jobs que falharam mas ainda têm tentativas disponíveis."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE roaz_sources 
                SET status = 'PENDING'
                WHERE status = 'FAILED' AND attempt < :max
            """, {'max': max_attempts})
            updated = cur.rowcount
            conn.commit()
    finally:
        conn.close()
    if updated > 0:
        logger.info(f"{updated} jobs recolocados em PENDING para retentativa.")


# ──────────────────────────────────────────────────────────────────
# Processamento de um job (extração do guia completo)
# ──────────────────────────────────────────────────────────────────
async def process_job(job, user_agent):
    job_id = job['job_id']
    base_url = job['source_url']
    guide_dir = make_staging_dir(base_url)
    raw_dir = guide_dir / "raw"
    clean_dir = guide_dir / "clean"
    raw_dir.mkdir(parents=True, exist_ok=True)

    inserted = 0
    logger.info(f"Job {job_id}: processando {base_url}")

    conn = get_connection()
    dynamic_extractor = DynamicExtractor()

    try:
        async with aiohttp.ClientSession() as session:
            # 1. Descobre subpáginas
            try:
                subpages = discover_links_from_toc(base_url, user_agent)
                if not subpages:
                    subpages = [{'url': base_url, 'title': job['title']}]
            except Exception as e:
                raise Exception(f"Falha ao descobrir subpáginas: {e}")

            # 2. FASE 1: Baixa todos os HTMLs brutos (rápido, assíncrono)
            async def download_page(page):
                url = page['url']
                filename = safe_filename(page['title']) + ".html"
                filepath = raw_dir / filename
                try:
                    async with session.get(url, headers={"User-Agent": user_agent}) as resp:
                        resp.raise_for_status()
                        async with aiofiles.open(filepath, 'wb') as f:
                            await f.write(await resp.read())
                    return True
                except Exception as e:
                    logger.error(f"Download falhou para {url}: {e}")
                    return False

            download_tasks = [download_page(p) for p in subpages]
            results = await asyncio.gather(*download_tasks)
            logger.info(f"Fase 1: downloads concluídos ({sum(results)}/{len(subpages)} ok)")

            # 3. FASE 2: Processa cada HTML local
            for page in subpages:
                filename = safe_filename(page['title']) + ".html"
                filepath = raw_dir / filename
                if not filepath.exists():
                    logger.warning(f"HTML não encontrado: {filepath}")
                    continue

                # Lê o HTML baixado
                with open(filepath, 'r', encoding='utf-8') as f:
                    html = f.read()

                # Extração estática
                text = extract_content(html)
                html_used_for_structure = html

                # Se insuficiente, usa Selenium com file://
                if not text or len(text) < 1000:
                    file_url = filepath.resolve().as_uri()
                    logger.info(f"Renderizando localmente: {file_url}")
                    html_dyn, text_dyn = dynamic_extractor.fetch(file_url)
                    if text_dyn and len(text_dyn) > len(text):
                        text = text_dyn
                        html_used_for_structure = html_dyn

                if not text:
                    logger.warning(f"Job {job_id}: conteúdo vazio para {page['url']}")
                    continue

                # 4. Extrai a estrutura hierárquica
                try:
                    structured = extract_structured(html_used_for_structure)
                    content_json_str = json.dumps(structured, ensure_ascii=False)
                except Exception as e:
                    logger.warning(f"Falha ao extrair estrutura para {page['url']}: {e}")
                    structured = []
                    content_json_str = None

                # 5. Insere no Oracle e guarda staging
                source_url_path = get_guide_base_url(page['url'])

                try:
                    with conn.cursor() as cur:
                        doc_id_var = cur.var(int)
                        cur.execute("""
                            INSERT INTO documents (source_url, title, expert_id, raw_text, content_json, source_id, source_url_path)
                            VALUES (:url, :title, :expert_id, :raw_text, :content_json, :source_id, :source_url_path)
                            RETURNING doc_id INTO :did
                        """, {
                            'url': page['url'],
                            'title': page['title'],
                            'expert_id': job['expert_id'],
                            'raw_text': text,
                            'content_json': content_json_str,
                            'source_id': job['job_id'],
                            'source_url_path': source_url_path,
                            'did': doc_id_var
                        })
                        doc_id = doc_id_var.getvalue()
                        conn.commit()
                        inserted += 1

                    # Guarda ficheiros limpos
                    doc_rec = {
                        'doc_id': doc_id,
                        'title': page['title'],
                        'raw_text': text,
                        'content_json': structured if structured else None
                    }
                    save_text_staging(doc_rec, clean_dir)

                except Exception as e:
                    logger.error(f"Job {job_id}: erro ao inserir {page['url']}: {e}")

        logger.info(f"Job {job_id}: concluído. {inserted} documentos inseridos.")
    finally:
        dynamic_extractor.close()
        conn.close()


# ──────────────────────────────────────────────────────────────────
# Loop principal
# ──────────────────────────────────────────────────────────────────
async def main_loop():
    """Executa o pipeline completo de jobs."""
    user_agent = "RoazCodex/1.0"
    total_success = 0

    # Processa jobs pendentes
    while True:
        job = fetch_next_pending_job()
        if not job:
            break
        try:
            await process_job(job, user_agent)
            mark_job_success(job['job_id'])
            total_success += 1
        except Exception as e:
            err = str(e)
            logger.error(f"Job {job['job_id']} falhou: {err}")
            mark_job_failed(job['job_id'], err)

    # Reenfileira jobs falhados que ainda têm tentativas
    requeue_failed_jobs(max_attempts=3)

    # Verifica se ainda há pendentes
    job = fetch_next_pending_job()
    if job:
        logger.info("Ainda há jobs pendentes. Execute novamente para processar retentativas.")
    else:
        logger.info(f"Todos os jobs processados. Sucessos: {total_success}")


if __name__ == "__main__":
    asyncio.run(main_loop())
