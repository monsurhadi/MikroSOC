import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS organizations (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES organizations(id), username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','analyst','viewer')), active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS routers (id INTEGER PRIMARY KEY, org_id INTEGER NOT NULL REFERENCES organizations(id), name TEXT NOT NULL, ip TEXT NOT NULL, last_poll REAL, last_syslog REAL, error TEXT, status TEXT NOT NULL DEFAULT 'unknown', baseline INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS devices (id INTEGER PRIMARY KEY, router_id INTEGER NOT NULL REFERENCES routers(id), mac TEXT NOT NULL, ip TEXT, hostname TEXT, first_seen REAL NOT NULL, last_seen REAL NOT NULL, trusted INTEGER NOT NULL DEFAULT 0, UNIQUE(router_id,mac));
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, router_id INTEGER NOT NULL REFERENCES routers(id), received_at REAL NOT NULL, kind TEXT NOT NULL, src_ip TEXT, dst_ip TEXT, dst_port INTEGER, username TEXT, message TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS logs_detect ON logs(router_id,kind,src_ip,received_at);
CREATE INDEX IF NOT EXISTS logs_time ON logs(received_at);
CREATE TABLE IF NOT EXISTS detection_rules (key TEXT PRIMARY KEY, title TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, threshold REAL NOT NULL, window_seconds INTEGER NOT NULL, severity TEXT NOT NULL, cooldown_seconds INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, router_id INTEGER NOT NULL REFERENCES routers(id), rule_key TEXT NOT NULL REFERENCES detection_rules(key), created_at REAL NOT NULL, severity TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open');
CREATE INDEX IF NOT EXISTS alerts_dedupe ON alerts(router_id,rule_key,source,created_at);
CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY, alert_id INTEGER UNIQUE NOT NULL REFERENCES alerts(id), stage TEXT NOT NULL DEFAULT 'detected', assignee TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS response_actions (id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id), user_id INTEGER NOT NULL REFERENCES users(id), created_at REAL NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics (id INTEGER PRIMARY KEY, router_id INTEGER NOT NULL REFERENCES routers(id), collected_at REAL NOT NULL, cpu REAL, memory_percent REAL, uptime TEXT, rx_mbps REAL, tx_mbps REAL, interfaces TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS metrics_time ON metrics(collected_at);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingress_receipts (event_id TEXT PRIMARY KEY, received_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notifications (alert_id INTEGER PRIMARY KEY REFERENCES alerts(id), state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0, detail TEXT);
'''

RULES = [
    ('port_scan', 'Possible port scan', 12, 60, 'high', 300),
    ('brute_force', 'Repeated login failures', 5, 120, 'high', 300),
    ('new_device', 'New DHCP device', 1, 60, 'medium', 86400),
    ('ssh_enumeration', 'Possible SSH username enumeration', 4, 120, 'medium', 300),
    ('exfiltration', 'Sustained WAN upload anomaly', 10, 300, 'high', 900),
]


@contextmanager
def connect(cfg):
    conn = sqlite3.connect(cfg['database'], timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(cfg):
    Path(cfg['database']).parent.mkdir(parents=True, exist_ok=True)
    with connect(cfg) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript(SCHEMA)
        existing = c.execute("SELECT value FROM meta WHERE key='mode'").fetchone()
        if existing and existing['value'] != cfg['mode']:
            raise ValueError('Demo and live must use separate databases. Change database in config.json.')
        c.execute("INSERT OR IGNORE INTO meta VALUES ('mode',?)", (cfg['mode'],))
        old_ip = c.execute("SELECT value FROM meta WHERE key='router_ip'").fetchone()
        if old_ip and old_ip['value'] != cfg['router_ip']:
            raise ValueError('Router IP changed. Use a new database to preserve attribution.')
        c.execute("INSERT OR IGNORE INTO meta VALUES ('router_ip',?)", (cfg['router_ip'],))
        c.execute('INSERT OR IGNORE INTO organizations VALUES (1,?)', (cfg['organization'],))
        c.execute('INSERT OR IGNORE INTO routers(id,org_id,name,ip) VALUES(1,1,?,?)', (cfg['router_name'], cfg['router_ip']))
        for key, title, threshold, window, severity, cooldown in RULES:
            c.execute('INSERT OR IGNORE INTO detection_rules VALUES(?,?,1,?,?,?,?)', (key,title,threshold,window,severity,cooldown))


def audit(c, actor, action, detail):
    c.execute('INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)', (time.time(),actor,action,str(detail)[:4000]))


def prune(cfg):
    with connect(cfg) as c:
        cutoff = time.time() - cfg['retention_days'] * 86400
        for table, column, maximum in [('logs','received_at',cfg['max_log_rows']),('metrics','collected_at',cfg['max_metric_rows'])]:
            c.execute(f'DELETE FROM {table} WHERE {column} < ?', (cutoff,))
            c.execute(f'DELETE FROM {table} WHERE id < COALESCE((SELECT id FROM {table} ORDER BY id DESC LIMIT 1 OFFSET ?),0)', (maximum - 1,))
        # Alerts, incident records and audit history deliberately survive raw-data retention.


def rows(c, sql, params=()):
    return [dict(row) for row in c.execute(sql, params)]
