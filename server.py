#!/usr/bin/env python3
import json
import math
import secrets
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import hashlib

ROOT = Path(__file__).parent
DB_PATH = ROOT / 'biliardi.db'
PUBLIC_DIR = ROOT / 'public'
TOKENS = {}


def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_db():
    conn = db_conn()
    cur = conn.cursor()
    cur.executescript(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'owner')),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS billiard_halls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            table_count INTEGER NOT NULL,
            price_per_hour REAL NOT NULL,
            description TEXT,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            hall_id INTEGER NOT NULL,
            table_number INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            total_price REAL NOT NULL,
            payment_status TEXT NOT NULL CHECK(payment_status IN ('pending', 'paid')) DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(hall_id) REFERENCES billiard_halls(id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            card_last4 TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            FOREIGN KEY(reservation_id) REFERENCES reservations(id)
        );
        '''
    )
    conn.commit()

    owners = [
        ('Green Cue Arena Owner', 'owner1@biliardi.ge', 'Owner123!', 'owner'),
        ('Black Ball Club Owner', 'owner2@biliardi.ge', 'Owner123!', 'owner'),
    ]
    for name, email, pw, role in owners:
        cur.execute('INSERT OR IGNORE INTO users(name, email, password_hash, role, created_at) VALUES(?,?,?,?,?)',
                    (name, email, hash_password(pw), role, datetime.utcnow().isoformat()))
    conn.commit()

    cur.execute("SELECT id, email FROM users WHERE role='owner'")
    owner_ids = {row['email']: row['id'] for row in cur.fetchall()}

    hall_count = cur.execute('SELECT COUNT(*) as c FROM billiard_halls').fetchone()['c']
    halls = [
        (owner_ids.get('owner1@biliardi.ge'), 'Green Cue Arena', 'ვაჟა-ფშაველას გამზირი 45, თბილისი', 41.7253, 44.7431, 12, 35.0, 'VIP და სტანდარტული მაგიდები, პრემიუმ განათება.'),
        (owner_ids.get('owner2@biliardi.ge'), 'Black Ball Club', 'ჭავჭავაძის გამზირი 18, თბილისი', 41.7089, 44.7701, 9, 30.0, 'მყუდრო გარემო და ტურნირების სივრცე.'),
    ]
    if hall_count == 0:
        for hall in halls:
            if hall[0] is None:
                continue
            cur.execute('''INSERT INTO billiard_halls(owner_id,name,address,latitude,longitude,table_count,price_per_hour,description)
                           VALUES(?,?,?,?,?,?,?,?)''', hall)
        conn.commit()
    conn.close()


def haversine(lat1, lon1, lat2, lon2):
    r = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Handler(BaseHTTPRequestHandler):
    def _json(self, status=200, data=None):
        payload = json.dumps(data or {}).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length) if length else b'{}'
        return json.loads(raw.decode('utf-8'))

    def _auth(self):
        token = self.headers.get('Authorization', '').replace('Bearer ', '').strip()
        uid = TOKENS.get(token)
        if not uid:
            return None
        conn = db_conn()
        user = conn.execute('SELECT id, name, email, role FROM users WHERE id=?', (uid,)).fetchone()
        conn.close()
        return dict(user) if user else None

    def do_OPTIONS(self):
        self._json(200, {'ok': True})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api_get(parsed)
        return self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith('/api/'):
            return self._json(404, {'error': 'Not found'})
        return self.handle_api_post(parsed.path)

    def serve_static(self, path):
        file_path = PUBLIC_DIR / ('index.html' if path in ('', '/') else path.lstrip('/'))
        if not file_path.exists() or file_path.is_dir():
            self.send_error(404)
            return
        mime = 'text/plain'
        if file_path.suffix == '.html':
            mime = 'text/html; charset=utf-8'
        elif file_path.suffix == '.css':
            mime = 'text/css; charset=utf-8'
        elif file_path.suffix == '.js':
            mime = 'application/javascript; charset=utf-8'
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_api_get(self, parsed):
        if parsed.path == '/api/health':
            return self._json(200, {'status': 'ok'})

        if parsed.path == '/api/halls':
            qs = parse_qs(parsed.query)
            lat = float(qs.get('lat', [0])[0]) if qs.get('lat') else None
            lon = float(qs.get('lon', [0])[0]) if qs.get('lon') else None
            conn = db_conn()
            halls = [dict(r) for r in conn.execute('SELECT * FROM billiard_halls').fetchall()]
            conn.close()
            if lat is not None and lon is not None:
                for hall in halls:
                    hall['distance_km'] = round(haversine(lat, lon, hall['latitude'], hall['longitude']), 2)
                halls.sort(key=lambda h: h['distance_km'])
            return self._json(200, {'halls': halls})

        if parsed.path == '/api/my-reservations':
            user = self._auth()
            if not user or user['role'] != 'user':
                return self._json(401, {'error': 'Unauthorized'})
            conn = db_conn()
            rows = conn.execute('''SELECT r.*, h.name as hall_name, h.address FROM reservations r
                                   JOIN billiard_halls h ON r.hall_id=h.id WHERE r.user_id=? ORDER BY r.start_time DESC''',
                                (user['id'],)).fetchall()
            conn.close()
            return self._json(200, {'reservations': [dict(r) for r in rows]})

        if parsed.path == '/api/owner/reservations':
            user = self._auth()
            if not user or user['role'] != 'owner':
                return self._json(401, {'error': 'Unauthorized'})
            conn = db_conn()
            rows = conn.execute('''SELECT r.*, h.name as hall_name, u.name as customer_name, u.email as customer_email
                                   FROM reservations r
                                   JOIN billiard_halls h ON r.hall_id=h.id
                                   JOIN users u ON r.user_id=u.id
                                   WHERE h.owner_id=? ORDER BY r.start_time ASC''', (user['id'],)).fetchall()
            conn.close()
            return self._json(200, {'reservations': [dict(r) for r in rows]})

        return self._json(404, {'error': 'Not found'})

    def handle_api_post(self, path):
        body = self._read_json()
        conn = db_conn()
        cur = conn.cursor()

        if path == '/api/register':
            name, email, password = body.get('name', '').strip(), body.get('email', '').strip().lower(), body.get('password', '')
            if not name or '@' not in email or len(password) < 6:
                conn.close()
                return self._json(400, {'error': 'Invalid registration data'})
            try:
                cur.execute('INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                            (name, email, hash_password(password), 'user', datetime.utcnow().isoformat()))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return self._json(409, {'error': 'Email already exists'})
            conn.close()
            return self._json(201, {'success': True})

        if path == '/api/login':
            email, password = body.get('email', '').strip().lower(), body.get('password', '')
            user = cur.execute('SELECT id,name,email,role,password_hash FROM users WHERE email=?', (email,)).fetchone()
            conn.close()
            if not user or user['password_hash'] != hash_password(password):
                return self._json(401, {'error': 'Invalid credentials'})
            token = secrets.token_hex(24)
            TOKENS[token] = user['id']
            return self._json(200, {'token': token, 'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role']}})

        if path == '/api/reserve':
            user = self._auth()
            if not user or user['role'] != 'user':
                conn.close()
                return self._json(401, {'error': 'Unauthorized'})
            hall_id = int(body.get('hall_id', 0))
            table_number = int(body.get('table_number', 0))
            start_time = body.get('start_time', '')
            hours = int(body.get('hours', 0))
            if hall_id <= 0 or table_number <= 0 or hours <= 0:
                conn.close()
                return self._json(400, {'error': 'Invalid reservation data'})
            hall = cur.execute('SELECT * FROM billiard_halls WHERE id=?', (hall_id,)).fetchone()
            if not hall or table_number > hall['table_count']:
                conn.close()
                return self._json(400, {'error': 'Table not available'})
            start_dt = datetime.fromisoformat(start_time)
            from datetime import timedelta
            end_dt = start_dt + timedelta(hours=hours)
            overlap = cur.execute('''SELECT id FROM reservations WHERE hall_id=? AND table_number=?
                                     AND NOT (end_time <= ? OR start_time >= ?)''',
                                  (hall_id, table_number, start_dt.isoformat(), end_dt.isoformat())).fetchone()
            if overlap:
                conn.close()
                return self._json(409, {'error': 'This table is already reserved for selected time'})
            total = round(hall['price_per_hour'] * hours, 2)
            cur.execute('''INSERT INTO reservations(user_id,hall_id,table_number,start_time,end_time,total_price,payment_status,created_at)
                           VALUES(?,?,?,?,?,?,?,?)''',
                        (user['id'], hall_id, table_number, start_dt.isoformat(), end_dt.isoformat(), total, 'pending', datetime.utcnow().isoformat()))
            rid = cur.lastrowid
            conn.commit()
            conn.close()
            return self._json(201, {'reservation_id': rid, 'total_price': total, 'payment_status': 'pending'})

        if path == '/api/pay':
            user = self._auth()
            if not user or user['role'] != 'user':
                conn.close()
                return self._json(401, {'error': 'Unauthorized'})
            reservation_id = int(body.get('reservation_id', 0))
            card_number = body.get('card_number', '').replace(' ', '')
            if len(card_number) < 12:
                conn.close()
                return self._json(400, {'error': 'Invalid card'})
            reservation = cur.execute('SELECT * FROM reservations WHERE id=? AND user_id=?', (reservation_id, user['id'])).fetchone()
            if not reservation:
                conn.close()
                return self._json(404, {'error': 'Reservation not found'})
            if reservation['payment_status'] == 'paid':
                conn.close()
                return self._json(409, {'error': 'Already paid'})
            last4 = card_number[-4:]
            cur.execute('UPDATE reservations SET payment_status=? WHERE id=?', ('paid', reservation_id))
            cur.execute('INSERT INTO payments(reservation_id,amount,card_last4,paid_at) VALUES(?,?,?,?)',
                        (reservation_id, reservation['total_price'], last4, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            return self._json(200, {'success': True, 'card_last4': last4})

        conn.close()
        return self._json(404, {'error': 'Not found'})


if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', 8000), Handler)
    print('Server running at http://0.0.0.0:8000')
    server.serve_forever()
