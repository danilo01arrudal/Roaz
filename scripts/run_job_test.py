"""
Teste controlado do Job Runner – processa até N jobs PENDING.
Para após N tentativas (sucesso ou falha).
"""

import asyncio
import sys
import logging

from src.harvester.job_runner import (
    fetch_next_pending_job,
    process_job,
    mark_job_success,
    mark_job_failed,
    requeue_failed_jobs,
    logger,
)

async def main_loop(limit=2):
    user_agent = "RoazCodex/1.0"
    attempts = 0

    while attempts < limit:
        job = fetch_next_pending_job()
        if not job:
            logger.info("Não há mais jobs PENDING.")
            break

        try:
            await process_job(job, user_agent)
            mark_job_success(job['job_id'])
            logger.info(f"Job {job['job_id']} concluído com sucesso.")
        except Exception as e:
            err = str(e)
            logger.error(f"Job {job['job_id']} falhou: {err}")
            mark_job_failed(job['job_id'], err)
        finally:
            attempts += 1

    # Reenfileira falhados para retentativa futura
    requeue_failed_jobs()
    logger.info(f"Teste concluído. Processados {attempts} job(s).")

if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    print(f"→ Processando até {limit} job(s) de teste.")
    asyncio.run(main_loop(limit))
    print("→ Teste concluído.")
