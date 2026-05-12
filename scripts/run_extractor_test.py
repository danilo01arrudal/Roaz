#!/usr/bin/env python3
"""
Teste do Extractor – valida a descoberta de links e a extração de conteúdo.
Uso: python scripts/run_extractor_test.py <URL_BASE> [--dynamic]
Exemplo: python scripts/run_extractor_test.py https://docs.oracle.com/en/database/oracle/oracle-database/26/ratug/ --dynamic
"""

import sys
import asyncio
import json
import aiohttp
from pathlib import Path
from src.harvester.extractor import discover_links_from_toc, extract_content, extract_structured
from src.harvester.dynamic_extractor import DynamicExtractor

async def test_extraction(base_url: str, use_dynamic: bool = False):
    user_agent = "RoazCodex-Test/1.0"

    print(f"\n{'='*70}")
    print(f"🔍 Teste de Extração — URL Base: {base_url}")
    print(f"{'='*70}\n")

    # 1. Descoberta de links
    print("📋 Fase 1: Descobrindo links a partir do índice (toc.htm)...")
    links = discover_links_from_toc(base_url, user_agent=user_agent)
    print(f"   ✅ Encontrados {len(links)} links de conteúdo.\n")

    if not links:
        print("❌ Nenhum link encontrado.")
        return

    # 2. Escolhe uma página para testar a extração (a primeira)
    test_page = links[0]
    print(f"📄 Fase 2: Extraindo a primeira página: {test_page['title'][:80]}")
    print(f"   URL: {test_page['url']}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(test_page['url'], headers={"User-Agent": user_agent}) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except Exception as e:
            print(f"   ❌ Falha ao baixar a página: {e}")
            return

    # 3. Extração estática
    text = extract_content(html)
    print(f"   📝 Extração estática: {len(text)} caracteres {'✅' if len(text) >= 1000 else '⚠️ (curto)'}")

    # 4. Extração estruturada
    sections = extract_structured(html)
    print(f"   🧱 Estrutura extraída: {len(sections)} secções")

    # 5. Se pedido, tenta extração dinâmica (com Selenium local)
    if use_dynamic and len(text) < 1000:
        print("   🔄 Tentando extração dinâmica (Selenium local)...")
        try:
            # Guarda o HTML em ficheiro temporário para o Selenium abrir localmente
            tmp_file = Path("/tmp/roaz_test_page.html")
            tmp_file.write_text(html, encoding='utf-8')
            file_url = tmp_file.resolve().as_uri()
            dynamic_extractor = DynamicExtractor()
            try:
                html_dyn, text_dyn = dynamic_extractor.fetch(file_url)
                if text_dyn and len(text_dyn) > len(text):
                    print(f"   ✅ Extração dinâmica obteve {len(text_dyn)} caracteres.")
                    text = text_dyn
                    # Re-extrai a estrutura com o HTML renderizado
                    sections = extract_structured(html_dyn)
                    print(f"   🧱 Estrutura atualizada: {len(sections)} secções")
                else:
                    print("   ⚠️ Extração dinâmica não melhorou o conteúdo.")
            finally:
                dynamic_extractor.close()
                tmp_file.unlink(missing_ok=True)
        except Exception as e:
            print(f"   ❌ Falha na extração dinâmica: {e}")

    # 6. Mostra amostra do texto e da estrutura
    print(f"\n   📄 Amostra do texto limpo (primeiros 300 caracteres):")
    print("   " + text[:300].replace('\n', '\n   ') + "...")

    print(f"\n   📋 Amostra da estrutura (primeira secção):")
    if sections:
        print("   " + json.dumps(sections[0], indent=6, ensure_ascii=False)[:500])
    else:
        print("   (sem secções)")

    print(f"\n{'='*70}")
    print(f"📊 Resumo: links={len(links)}, texto={len(text)} chars, secções={len(sections)}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/run_extractor_test.py <URL_BASE> [--dynamic]")
        sys.exit(1)

    base_url = sys.argv[1]
    use_dynamic = "--dynamic" in sys.argv
    asyncio.run(test_extraction(base_url, use_dynamic))
