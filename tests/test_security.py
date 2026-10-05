import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime
import server


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        public = root / 'public'
        public.mkdir()
        (public / 'index.html').write_text('public home')
        (public / 'app.js').write_text('public script')
        (root / 'secret.txt').write_text('SECRET')
        sibling = root / 'public-secret'
        sibling.mkdir()
        (sibling / 'secret.txt').write_text('SECRET')
        (public / 'link').symlink_to(root / 'secret.txt')
        (public / 'dirlink').symlink_to(sibling, target_is_directory=True)
        for name, value in [('DB_PATH', root / 'test.db'), ('PUBLIC_DIR', public), ('TOKENS', {})]:
            p = patch.object(server, name, value)
            p.start()
            self.addCleanup(p.stop)
        server.init_db()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)
        self.request('/api/register', {'name': '<img src=x onerror=alert(1)>', 'email': 'test@example.com', 'password': 'secret123'})
        _, login = self.request('/api/login', {'email': 'test@example.com', 'password': 'secret123'})
        self.token = login['token']

    def stop_server(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()

    def request(self, path, data=None, token=None):
        conn = http.client.HTTPConnection(*self.http.server_address, timeout=3)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        conn.request('POST' if data is not None else 'GET', path,
                     json.dumps(data) if data is not None else None, headers)
        res = conn.getresponse()
        payload = res.read().decode()
        status = res.status
        content_type = res.getheader('Content-Type', '')
        conn.close()
        return status, json.loads(payload) if 'application/json' in content_type else payload

    def reserve(self, start='2030-01-01T10:00:00.000Z', **extra):
        data = dict(hall_id=1, table_number=1, hours=1, start_time=start)
        data.update(extra)
        return self.request('/api/reserve', data, self.token)

    def test_reservation_payment_owner_flow(self):
        status, halls = self.request('/api/halls?lat=41.72&lon=44.74')
        self.assertEqual(status, 200)
        self.assertEqual(len(halls['halls']), 2)
        status, booking = self.reserve()
        self.assertEqual(status, 201)
        self.assertEqual(booking['total_price'], 35)
        self.assertEqual(self.reserve()[0], 409)
        status, paid = self.request('/api/pay', {'reservation_id': booking['reservation_id'], 'card_number': '4111111111111111'}, self.token)
        self.assertEqual((status, paid['card_last4']), (200, '1111'))
        status, mine = self.request('/api/my-reservations', token=self.token)
        self.assertEqual(mine['reservations'][0]['payment_status'], 'paid')
        self.assertEqual(mine['reservations'][0]['start_time'], '2030-01-01T10:00:00+00:00')
        _, owner = self.request('/api/login', {'email': 'owner1@biliardi.ge', 'password': 'Owner123!'})
        status, dashboard = self.request('/api/owner/reservations', token=owner['token'])
        self.assertEqual(status, 200)
        self.assertEqual(dashboard['reservations'][0]['customer_name'], '<img src=x onerror=alert(1)>')
        self.assertEqual(dashboard['reservations'][0]['payment_status'], 'paid')
        self.assertEqual(self.request('/api/owner/reservations', token=self.token)[0], 401)

    def test_offset_overlap_and_adjacent_booking(self):
        self.assertEqual(self.reserve('2030-01-01T14:00:00+04:00')[0], 201)
        self.assertEqual(self.reserve('2030-01-01T05:30:00-05:00')[0], 409)
        self.assertEqual(self.reserve('2030-01-01T11:00:00Z')[0], 201)

    def test_existing_offset_records_overlap(self):
        self.reserve()
        conn = server.db_conn()
        conn.execute("UPDATE reservations SET start_time='2030-01-01T14:00:00+04:00', end_time='2030-01-01T15:00:00+04:00'")
        conn.commit()
        conn.close()
        self.assertEqual(self.reserve()[0], 409)

    def test_bad_timestamps_and_duration_return_json_400(self):
        for value in [None, '', 42, [], {}, 'garbage', '2030-02-30T10:00:00Z', '2030-01-01',
                      '2030-01-01T10:00:00', '2030-01-01T10:00:00+04:99', '2030-01-01T10:00:00+24:00']:
            with self.subTest(value=value):
                status, body = self.reserve(value)
                self.assertEqual(status, 400)
                self.assertIn('error', body)
        for hours in [None, 'bad', 0, -1, 10**30]:
            self.assertEqual(self.reserve(hours=hours)[0], 400)
        self.assertEqual(self.reserve()[0], 201)

    def test_static_traversal_and_symlinks(self):
        for path in ['/../secret.txt', '/%2e%2e/secret.txt', '/%2e%2e%2fsecret.txt',
                     '/../public-secret/secret.txt', '/link', '/dirlink/secret.txt', '/%00', '/missing']:
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn('SECRET', body)
        self.assertEqual(self.request('/'), (200, 'public home'))
        self.assertEqual(self.request('/app.js?v=1'), (200, 'public script'))

    def test_python310_parser_receives_normalized_z(self):
        class Python310Datetime:
            @staticmethod
            def fromisoformat(value):
                self.assertFalse(value.endswith(('Z', 'z')))
                return datetime.fromisoformat(value)
        with patch.object(server, 'datetime', Python310Datetime):
            self.assertEqual(server.parse_reservation_time('2030-01-01T10:00:00.123Z').isoformat(),
                             '2030-01-01T10:00:00.123000+00:00')


if __name__ == '__main__':
    unittest.main()
