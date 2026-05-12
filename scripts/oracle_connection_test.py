from src.utils.oracle_connector import get_connection

try:
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Usando aspas duplas por fora e aspas simples por dentro para o SQL
            cur.execute("SELECT 'Conexão OK' AS status, SYS_CONTEXT('USERENV', 'DB_NAME') AS db FROM dual")
            row = cur.fetchone()
            print(f'Status  : {row[0]}')
            print(f'Database: {row[1]}')
            
    print('Todos os testes passaram.')
except Exception as e:
    print(f'FALHA: {e}')
