"""
Módulo de Chunking Semântico com breadcrumb hierárquico.

Gera chunks com texto limpo e prefixo de localização (ex.: "Parte II > Capítulo 3 > Seção").
"""

import re
import unicodedata
from typing import List, Dict, Any
from langchain_text_splitters import RecursiveCharacterTextSplitter

fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""]
)


def clean_chunk_text(text: str) -> str:
    """Normalização agressiva de espaços, quebras e caracteres não imprimíveis."""
    text = unicodedata.normalize('NFKD', text)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    text = '\n'.join(line.strip() for line in text.splitlines())
    return text.strip()


def _build_breadcrumb(title_stack: List[str]) -> str:
    """Constrói uma string de breadcrumb a partir da pilha de títulos."""
    return ' > '.join(title_stack) if title_stack else ''


def chunk_structured(
    sections: List[Dict[str, Any]],
    doc_id: int,
    source_id: int,
    doc_url: str = "",
    guide_base_url: str = ""
) -> List[Dict[str, Any]]:
    """
    Transforma a lista de secções estruturadas em chunks limpos, com breadcrumb.
    """
    chunks = []
    title_stack = []  # pilha de títulos atual (nível 1,2,3...)

    for section in sections:
        title = section.get('title', '')
        level = section.get('level', 1)
        content = ' '.join(section.get('content', []))
        if not content and not title:
            continue

        # Atualizar pilha de títulos conforme o nível
        # Remove títulos de nível igual ou superior ao atual
        while title_stack and len(title_stack) >= level:
            title_stack.pop()
        title_stack.append(title)

        breadcrumb = _build_breadcrumb(title_stack)

        chunk_text = f"{'#' * level} {title}\n{content}" if title else content
        
        # Prefixa o breadcrumb (formato destaque)
        if breadcrumb:
            chunk_text = f"**{breadcrumb}**\n{chunk_text}"

        chunk_text = clean_chunk_text(chunk_text)

        # Se o chunk for muito grande, divide mantendo o breadcrumb
        if len(chunk_text) > 1500:
            sub_texts = fallback_splitter.split_text(chunk_text)
            for sub in sub_texts:
                sub = clean_chunk_text(sub)
                if not sub:
                    continue
                chunks.append({
                    'text': sub,
                    'metadata': {
                        'doc_id': doc_id,
                        'source_id': source_id,
                        'url': doc_url,
                        'section_title': title,
                        'level': level,
                        'chunk_index': len(chunks),
                        'guide_base_url': guide_base_url,
                        'breadcrumb': breadcrumb
                    }
                })
        else:
            chunks.append({
                'text': chunk_text,
                'metadata': {
                    'doc_id': doc_id,
                    'source_id': source_id,
                    'url': doc_url,
                    'section_title': title,
                    'level': level,
                    'chunk_index': len(chunks),
                    'guide_base_url': guide_base_url,
                    'breadcrumb': breadcrumb
                }
            })

    return chunks


def chunk_text_simple(
    text: str,
    doc_id: int = None,
    source_id: int = None,
    doc_url: str = "",
    guide_base_url: str = ""
) -> List[Dict[str, Any]]:
    """Fallback para documentos sem estrutura. Não há breadcrumb."""
    text = clean_chunk_text(text)
    texts = fallback_splitter.split_text(text)
    return [
        {
            'text': clean_chunk_text(t),
            'metadata': {
                'doc_id': doc_id,
                'source_id': source_id,
                'url': doc_url,
                'section_title': '',
                'level': 0,
                'chunk_index': i,
                'guide_base_url': guide_base_url,
                'breadcrumb': ''
            }
        }
        for i, t in enumerate(texts)
        if clean_chunk_text(t)
    ]
