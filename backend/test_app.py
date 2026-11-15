"""Synthetic isolated storage tests. No patient records are loaded."""
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from backend.app import create_app


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.client = TestClient(create_app(self.path), base_url="http://127.0.0.1:8000")
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def test_empty_storage_is_not_a_diagnostic_result(self):
        self.assertEqual(self.client.get('/api/studies').json(), {'items': []})
        health = self.client.get('/api/health').json()
        self.assertEqual(health['analysis'], 'not_connected')
        self.assertEqual(health['storage'], 'ready')

    def test_studies_are_read_from_storage(self):
        with sqlite3.connect(self.path / 'workspace.sqlite3') as conn:
            conn.execute("INSERT INTO studies(id,study_uid,description) VALUES ('test','test-uid','isolated fixture')")
        items = self.client.get('/api/studies').json()['items']
        self.assertEqual(items[0]['id'], 'test')
        self.assertIsNone(items[0]['study_date'])
        self.assertNotIn('study_uid', items[0])

    def test_preferences_survive_recreation(self):
        response = self.client.put('/api/preferences', json={'show_structure': False}, headers={'X-Workspace-Request':'1'})
        self.assertEqual(response.status_code, 200)
        with TestClient(create_app(self.path), base_url='http://127.0.0.1:8000') as restarted:
            self.assertFalse(restarted.get('/api/preferences').json()['show_structure'])

    def test_untrusted_host_and_origin_are_rejected(self):
        self.assertEqual(self.client.get('/api/studies', headers={'host':'attacker.example'}).status_code, 400)
        self.assertEqual(self.client.get('/api/studies', headers={'origin':'https://attacker.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/studies', headers={'sec-fetch-site':'cross-site'}).status_code, 403)

    def test_write_requires_header_and_strict_schema(self):
        self.assertEqual(self.client.put('/api/preferences', json={'show_structure':False}).status_code, 403)
        self.assertEqual(self.client.put('/api/preferences', json={'show_structure':'false'}, headers={'X-Workspace-Request':'1'}).status_code, 422)
        self.assertTrue(self.client.get('/api/preferences').json()['show_structure'])

    def test_patient_responses_are_not_cached(self):
        self.assertEqual(self.client.get('/api/studies').headers['cache-control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
