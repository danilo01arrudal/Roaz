"""
Motor de Embeddings – Geração de vetores semânticos com SentenceTransformer.

Usa o modelo all-mpnet-base-v2, que produz embeddings de dimensão 768,
e aproveita a GPU (via CUDA) se disponível para processamento em lote.
"""

import logging
from typing import List, Union
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("roaz.embedding_engine")

# ──────────────────────────────────────────────────────────────────
# Configuração do modelo (carregado como singleton)
# ──────────────────────────────────────────────────────────────────
MODEL_NAME = "all-mpnet-base-v2"
_model = None

def get_model() -> SentenceTransformer:
    """Obtém a instância do modelo, carregando-a uma única vez."""
    global _model
    if _model is None:
        logger.info(f"Carregando modelo '{MODEL_NAME}'...")
        _model = SentenceTransformer(MODEL_NAME, device="cuda" if _is_cuda_available() else "cpu")
        logger.info(f"Modelo carregado no dispositivo: {_model.device}")
    return _model

def _is_cuda_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False

# ──────────────────────────────────────────────────────────────────
# Funções de uso público
# ──────────────────────────────────────────────────────────────────
def encode(texts: List[str], batch_size: int = 64, show_progress: bool = False) -> List[List[float]]:
    """
    Converte uma lista de textos em embeddings vetoriais.

    Args:
        texts: Lista de strings a codificar.
        batch_size: Tamanho do lote para processamento.
        show_progress: Se True, exibe barra de progresso.

    Returns:
        Lista de embeddings, cada um como lista de floats de dimensão 768.
    """
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=show_progress,
        convert_to_numpy=True
    )
    # Converte para lista de listas (compatível com Oracle VECTOR)
    if isinstance(embeddings, np.ndarray):
        return embeddings.tolist()
    return [emb.tolist() for emb in embeddings]

def encode_single(text: str) -> List[float]:
    """Versão de utilidade para um único texto. Retorna embedding como lista de floats."""
    return encode([text])[0]
