"""
Módulo de Extração de Conteúdo Web (Estático e Estruturado).

Responsável por:
- Fazer download do HTML de uma URL (assíncrono com aiohttp).
- Extrair conteúdo textual limpo com BeautifulSoup.
- Extrair a estrutura hierárquica da página (títulos, parágrafos, etc.).
- Descobrir todos os links de conteúdo a partir de uma página de índice (toc.htm).
- Normalizar texto e calcular hash MD5 para controlo de versões.
"""

import hashlib
import re
import logging
from typing import List, Dict, Any
from urllib.parse import urljoin

import aiohttp
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("roaz.extractor")

# ──────────────────────────────────────────────────────────────────
# Constantes de seletores
# ──────────────────────────────────────────────────────────────────
REMOVE_SELECTORS = [
    'script', 'style', 'nav', 'footer', 'header', 'aside',
    'noscript', 'form', 'button', 'input',
    '[role="banner"]', '[role="contentinfo"]', '[role="complementary"]',
    '.skip-link', '.legal', '.footer', '.header', '.nav', '.sidebar',
    '#feedback', '#survey', '#cookie-banner'
]

MAIN_CONTENT_SELECTORS = [
    'main', 'article', '[role="main"]',
    '.content', '.main-content', '#main-content',
    '#content', '.section', '#main', 'body'
]

# ──────────────────────────────────────────────────────────────────
# Funções de download e extração simples
# ──────────────────────────────────────────────────────────────────
async def fetch(session: aiohttp.ClientSession, url: str, user_agent: str) -> str:
    """Download assíncrono do HTML."""
    headers = {"User-Agent": user_agent}
    async with session.get(url, headers=headers, timeout=30) as response:
        response.raise_for_status()
        return await response.text()


def extract_content(html: str) -> str:
    """Extrai texto limpo do HTML (mantido para compatibilidade)."""
    soup = BeautifulSoup(html, 'lxml')
    for selector in REMOVE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    main = None
    for sel in MAIN_CONTENT_SELECTORS:
        main = soup.select_one(sel)
        if main:
            break
    if main:
        return main.get_text(separator='\n', strip=True)
    body = soup.find('body')
    return body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)


# ──────────────────────────────────────────────────────────────────
# Extração estruturada (nova!)
# ──────────────────────────────────────────────────────────────────
def extract_structured(html: str) -> List[Dict[str, Any]]:
    """
    Extrai a estrutura hierárquica do conteúdo da página.
    Retorna uma lista de secções; cada secção é um dict com:
        - title: título da secção
        - level: nível (1 para h1, 2 para h2, …)
        - content: lista de strings (parágrafos, listas, texto)
    """
    soup = BeautifulSoup(html, 'lxml')
    # Remove elementos não informativos
    for selector in REMOVE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    article = None
    for sel in MAIN_CONTENT_SELECTORS:
        article = soup.select_one(sel)
        if article:
            break
    if not article:
        article = soup.find('body') or soup

    sections = []
    current_section = None
    current_content = []

    def flush_section():
        if current_section is not None:
            current_section['content'] = current_content.copy()
            current_content.clear()

    for tag in article.find_all(['h1','h2','h3','h4','h5','h6','p','ul','ol','table','pre','blockquote']):
        if tag.name.startswith('h'):
            # Novo cabeçalho → nova secção
            flush_section()
            level = int(tag.name[1])
            # Pode guardar a secção anterior
            current_section = {
                'title': tag.get_text(separator=' ', strip=True),
                'level': level,
                'content': []
            }
            sections.append(current_section)
        else:
            # Conteúdo da secção actual
            # Para tabelas, guardamos como texto formatado simples
            if tag.name == 'table':
                rows = []
                for tr in tag.find_all('tr'):
                    cells = [td.get_text(strip=True) for td in tr.find_all(['th','td'])]
                    rows.append(' | '.join(cells))
                current_content.append('\n'.join(rows))
            else:
                text = tag.get_text(separator=' ', strip=True)
                if text:
                    current_content.append(text)

    flush_section()  # última secção
    return sections


# ──────────────────────────────────────────────────────────────────
# Normalização e hash
# ──────────────────────────────────────────────────────────────────
def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()


def compute_md5(text: str) -> str:
    return hashlib.md5(normalize_text(text).encode('utf-8')).hexdigest()


# ──────────────────────────────────────────────────────────────────
# Descoberta de links (toc.htm)
# ──────────────────────────────────────────────────────────────────
def discover_links_from_toc(
    base_url: str,
    user_agent: str = "RoazCodex/1.0"
) -> List[Dict[str, str]]:
    """Acede ao toc.htm e devolve lista de {'url','title'}."""
    toc_url = urljoin(base_url, "toc.htm")
    logger.info(f"Descobrindo links a partir de {toc_url}")

    try:
        headers = {"User-Agent": user_agent}
        resp = requests.get(toc_url, headers=headers, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.error(f"Falha ao obter índice: {e}")
        return []

    soup = BeautifulSoup(html, 'lxml')
    links = soup.select('ul li a[href*="GUID-"], ul li a[href*="preface"]')
    results = []
    seen = set()
    for a in links:
        href = a.get('href')
        if not href:
            continue
        full = urljoin(base_url, href).split('#')[0].rstrip('/')
        if full not in seen:
            seen.add(full)
            results.append({'url': full, 'title': a.get_text(strip=True) or 'Untitled'})
    logger.info(f"Descobertos {len(results)} links de conteúdo.")
    return results
