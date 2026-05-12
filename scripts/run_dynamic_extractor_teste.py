#!/usr/bin/env python3
"""
Teste unitário / de componente do DynamicExtractor.
Valida criação, uso, recuperação de falhas e encerramento.
"""

import logging
import tempfile
from pathlib import Path
from src.harvester.dynamic_extractor import DynamicExtractor
from src.harvester.extractor import extract_content   # para debug

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("test")

HTML_TESTE = """<!DOCTYPE html>
<html lang="en">
<head><title>Teste Roaz</title></head>
<body>
    <nav>Menu irrelevante</nav>
    <main>
        <article>
            <h1>Introdução ao Oracle ACFS</h1>
            <p>Oracle Advanced Cluster File System (Oracle ACFS) é um sistema de ficheiros para bases de dados.</p>
            <p>Suporta snapshots, replicação e compressão.</p>
        </article>
    </main>
    <footer>Rodapé irrelevante</footer>
</body>
</html>"""

def test_dynamic_extractor():
    logger.info("🔧 Criando uma instância de DynamicExtractor...")
    try:
        ext = DynamicExtractor()
    except Exception as e:
        logger.error(f"❌ Falha ao criar o extrator: {e}")
        return False

    try:
        # 1. Escreve o HTML de teste num ficheiro temporário
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False, mode='w', encoding='utf-8') as f:
            f.write(HTML_TESTE)
            tmp_path = Path(f.name)

        file_url = tmp_path.resolve().as_uri()
        logger.info(f"📄 Ficheiro de teste: {file_url}")

        # 2. Testa a extração estática (só para debug)
        html_raw = tmp_path.read_text(encoding='utf-8')
        text_static = extract_content(html_raw)
        logger.info(f"🔍 Extração estática obteve {len(text_static)} caracteres: {text_static[:100]}...")

        # 3. Testa a extração dinâmica
        logger.info("🚀 Extraindo com DynamicExtractor...")
        html, text = ext.fetch(file_url)

        if not html:
            logger.error("❌ fetch() retornou HTML vazio.")
            return False
        if not text or "Oracle ACFS" not in text:
            logger.error(f"❌ Texto extraído não contém o esperado. Texto: {text[:200] if text else '(vazio)'}")
            return False
        logger.info(f"✅ Extração dinâmica OK: {len(text)} caracteres.")

        # 4. Simula falha do driver
        logger.info("💣 Forçando falha do driver e testando recuperação...")
        try:
            ext.driver.quit()
        except:
            pass
        html2, text2 = ext.fetch(file_url)
        if not html2 or "Oracle ACFS" not in text2:
            logger.error("❌ Recuperação do driver falhou.")
            return False
        logger.info("✅ Driver recuperado com sucesso.")

        # 5. Fecha o extrator
        logger.info("🚪 Fechando o extrator...")
        ext.close()
        logger.info("✅ close() executado sem erros.")

    finally:
        # Limpeza
        if 'tmp_path' in locals():
            tmp_path.unlink(missing_ok=True)
        try:
            ext.close()
        except:
            pass

    return True

if __name__ == "__main__":
    if test_dynamic_extractor():
        logger.info("🏁 Todos os testes do DynamicExtractor passaram.")
    else:
        logger.error("🏁 Alguns testes falharam.")
