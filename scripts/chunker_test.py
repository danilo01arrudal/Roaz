#!/usr/bin/env python3
"""
Testes unitários para o módulo chunker.
"""

import unittest
from src.processor.chunker import chunk_structured, chunk_text_simple

class TestChunkStructured(unittest.TestCase):
    def setUp(self):
        self.sections = [
            {
                'title': 'Introdução',
                'level': 1,
                'content': ['Primeiro parágrafo.', 'Segundo parágrafo.']
            },
            {
                'title': 'Metodologia',
                'level': 2,
                'content': ['Texto da metodologia.']
            }
        ]
        self.doc_id = 10
        self.doc_url = "http://example.com/doc10"

    def test_chunk_count(self):
        chunks = chunk_structured(self.sections, self.doc_id, self.doc_url)
        self.assertEqual(len(chunks), 2)

    def test_chunk_metadata(self):
        chunks = chunk_structured(self.sections, self.doc_id, self.doc_url)
        # Primeiro chunk
        self.assertEqual(chunks[0]['metadata']['doc_id'], 10)
        self.assertEqual(chunks[0]['metadata']['url'], self.doc_url)
        self.assertEqual(chunks[0]['metadata']['section_title'], 'Introdução')
        self.assertEqual(chunks[0]['metadata']['level'], 1)
        self.assertEqual(chunks[0]['metadata']['chunk_index'], 0)
        # Segundo chunk
        self.assertEqual(chunks[1]['metadata']['section_title'], 'Metodologia')
        self.assertEqual(chunks[1]['metadata']['level'], 2)
        self.assertEqual(chunks[1]['metadata']['chunk_index'], 1)

    def test_chunk_text_content(self):
        chunks = chunk_structured(self.sections, self.doc_id)
        self.assertIn('# Introdução', chunks[0]['text'])
        self.assertIn('Primeiro parágrafo.', chunks[0]['text'])
        self.assertIn('Segundo parágrafo.', chunks[0]['text'])
        self.assertIn('## Metodologia', chunks[1]['text'])
        self.assertIn('Texto da metodologia.', chunks[1]['text'])

    def test_empty_sections(self):
        chunks = chunk_structured([], self.doc_id)
        self.assertEqual(len(chunks), 0)

    def test_section_without_content(self):
        sections = [{'title': 'Apenas Título', 'level': 1, 'content': []}]
        chunks = chunk_structured(sections, self.doc_id)
        # Deve gerar um chunk apenas com título
        self.assertEqual(len(chunks), 1)
        self.assertIn('# Apenas Título', chunks[0]['text'])

    def test_long_section_splitting(self):
        # Cria uma secção com conteúdo muito longo para forçar divisão
        long_text = "palavra " * 600  # ~3600 caracteres
        sections = [{'title': 'Longa', 'level': 1, 'content': [long_text]}]
        chunks = chunk_structured(sections, self.doc_id)
        # Deve gerar mais de um chunk devido ao splitter
        self.assertGreater(len(chunks), 1)
        # Todos os sub-chunks devem manter os metadados da secção original
        for c in chunks:
            self.assertEqual(c['metadata']['section_title'], 'Longa')
            self.assertEqual(c['metadata']['level'], 1)

    def test_doc_url_optional(self):
        chunks = chunk_structured(self.sections, self.doc_id)
        self.assertEqual(chunks[0]['metadata']['url'], '')


class TestChunkTextSimple(unittest.TestCase):
    def test_short_text_single_chunk(self):
        chunks = chunk_text_simple("Um texto curto.", doc_id=5, doc_url="http://x.com")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['text'], "Um texto curto.")
        self.assertEqual(chunks[0]['metadata']['doc_id'], 5)
        self.assertEqual(chunks[0]['metadata']['section_title'], '')

    def test_long_text_multiple_chunks(self):
        long_text = "frase normal. " * 300  # aproximadamente 1500 caracteres
        chunks = chunk_text_simple(long_text, doc_id=20)
        self.assertGreater(len(chunks), 1)
        # Verifica índices
        for i, c in enumerate(chunks):
            self.assertEqual(c['metadata']['chunk_index'], i)

    def test_no_doc_id(self):
        chunks = chunk_text_simple("texto")
        self.assertIsNone(chunks[0]['metadata']['doc_id'])

    def test_empty_text(self):
        chunks = chunk_text_simple("")
        self.assertEqual(len(chunks), 0)


if __name__ == '__main__':
    unittest.main()
