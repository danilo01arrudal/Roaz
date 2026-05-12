# scripts/seed_staging.py
import csv
import re
from src.utils.oracle_connector import get_connection

CSV_PATH = "data/csv/oracle_db_26_docs.csv"

# Padrão para reconhecer URLs da documentação Oracle
ORACLE_DOCS_PATTERN = re.compile(r'https://docs\.oracle\.com/.*/26/')

conn = get_connection()
try:
    with conn.cursor() as cur, open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        # Pular cabeçalho se existir (primeira linha)
        first_row = next(reader, None)
        if first_row and first_row[0].lower() in ('title', 'título', 'group', 'nome', 'name'):
            pass  # era cabeçalho, continua para as próximas linhas
        else:
            # A primeira linha pode ser dados; voltamos a lê-la no loop
            f.seek(0)
            reader = csv.reader(f)

        for row in reader:
            if not row or len(row) < 2:
                continue

            # Tenta encontrar a URL na linha (pode estar em qualquer coluna)
            url = None
            title = None
            for cell in row:
                cell = cell.strip()
                if ORACLE_DOCS_PATTERN.match(cell):
                    url = cell
                    break

            if not url:
                continue  # linha sem URL válida

            # O título deve ser a primeira coluna não vazia antes da URL
            for cell in row:
                cell = cell.strip()
                if cell and cell != url and not cell.startswith('http'):
                    title = cell
                    break
            if not title:
                title = url.split('/')[-1] or 'Untitled'

            cur.execute("""
                MERGE INTO roaz_sources s
                USING (SELECT :url AS source_url, :title AS title FROM dual) d
                ON (s.source_url = d.source_url)
                WHEN NOT MATCHED THEN
                    INSERT (source_url, title, source_type)
                    VALUES (d.source_url, d.title, 'ORACLE_DOCS')
            """, {'url': url, 'title': title[:500]})
        conn.commit()
finally:
    conn.close()

print("Catálogo de fontes carregado em ROAZ_SOURCES.")
