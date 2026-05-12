#!/usr/bin/env python3
"""
Testes unitários para funções puras do job_runner.
Funções que interagem com BD ou Selenium são testadas via integração.
"""

import unittest
from unittest.mock import MagicMock, patch
from src.harvester.job_runner import (
    safe_filename,
    mark_job_success,
    mark_job_failed,
    requeue_failed_jobs,
)


class TestSafeFilename(unittest.TestCase):
    def test_safe_filename_normal(self):
        name = safe_filename("Oracle ACFS: Conceitos")
        self.assertNotIn(" ", name)
        self.assertNotIn(":", name)

    def test_safe_filename_long(self):
        name = safe_filename("A" * 100)
        self.assertLessEqual(len(name), 80)


class TestJobDatabaseFunctions(unittest.TestCase):
    """Testa as funções que interagem com a BD, usando mock da conexão."""

    def setUp(self):
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        # Configurar o __enter__ e __exit__ para ser usado com 'with'
        self.mock_cursor.__enter__ = MagicMock(return_value=self.mock_cursor)
        self.mock_cursor.__exit__ = MagicMock(return_value=None)
        self.mock_conn.cursor.return_value = self.mock_cursor

        patcher = patch('src.harvester.job_runner.get_connection', return_value=self.mock_conn)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_mark_job_success(self):
        mark_job_success(10)
        self.mock_cursor.execute.assert_called_once()
        self.mock_conn.commit.assert_called_once()

    def test_mark_job_failed(self):
        mark_job_failed(10, "Erro de rede")
        self.mock_cursor.execute.assert_called_once()
        args, _ = self.mock_cursor.execute.call_args
        self.assertIn("Erro de rede", args[1]['err'])
        self.mock_conn.commit.assert_called_once()

    def test_requeue_failed_jobs(self):
        # rowcount precisa de ser um int, não um MagicMock
        self.mock_cursor.rowcount = 3
        requeue_failed_jobs(max_attempts=3)
        self.mock_cursor.execute.assert_called_once()
        self.mock_conn.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
