"""
Módulo de conexão centralizada ao Oracle Database 26ai.
Utiliza python-oracledb em modo thin e carrega credenciais do ficheiro .env.
"""

import oracledb
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do .env (caso ainda não tenham sido carregadas)
load_dotenv()


def get_connection():
    """
    Retorna uma nova conexão ao Oracle Database configurado.

    As credenciais e o endereço são lidos das seguintes variáveis de ambiente:
      - ROAZ_DB_USER
      - ROAZ_DB_PASSWORD
      - ROAZ_DB_DSN       (exemplo: "localhost/orclpdb1")

    Returns:
        oracledb.Connection: Conexão ativa à base de dados.

    Raises:
        ValueError: Se alguma das variáveis de ambiente obrigatórias não estiver definida.
        ConnectionError: Se a ligação ao Oracle falhar.
    """
    user = os.getenv("ROAZ_DB_USER")
    password = os.getenv("ROAZ_DB_PASSWORD")
    dsn = os.getenv("ROAZ_DB_DSN")

    if not all([user, password, dsn]):
        raise ValueError(
            "Credenciais de base de dados incompletas. "
            "Verifique se as variáveis ROAZ_DB_USER, ROAZ_DB_PASSWORD e ROAZ_DB_DSN "
            "estão definidas no ficheiro .env"
        )

    try:
        # Modo thin (padrão) – não requer Oracle Client instalado
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        return conn
    except oracledb.Error as e:
        raise ConnectionError(
            f"Não foi possível ligar à base de dados Oracle. Detalhe: {e}"
        ) from e
