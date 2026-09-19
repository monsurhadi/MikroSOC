import csv
import functools
import io
import json
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from flask import Flask, abort, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from .db import connect, rows, audit
from .response import preview, execute

STAGES = ['detected','investigation','containment','recovery','lessons_learned','closed']


def create_app(cfg, collector=None):
    app = Flask(__name__,static_folder='static')
    secret_file = Path(cfg['database']).parent / '.session-key'
    if not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32),encoding='ascii')
    app.config.update(SECRET_KEY=secret_file.read_text().strip(),MAX_CONTENT_LENGTH=65536,
                      SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      TRUSTED_HOSTS=['127.0.0.1','localhost'])
    attempts = defaultdict(deque)
    attempt_lock = threading.Lock()
    dummy_hash = generate_password_hash(secrets.token_hex(16))

    def role(*allowed):
        def wrap(fn):
            @functools.wraps(fn)
            def inner(*args,**kwargs):
                if not g.user:
                    abort(401)
                if g.user['role'] not in allowed:
                    abort(403)
                return fn(*args,**kwargs)
            return inner
        return wrap

    @app.before_request
    def guard():
        g.user = None
        if session.get('uid'):
            with connect(cfg) as c:
                user = c.execute('SELECT id,username,role FROM users WHERE id=? AND active=1',(session['uid'],)).fetchone()
                g.user = dict(user) if user else None
        if request.method in ('POST','PUT','PATCH','DELETE') and request.path != '/api/ingest':
            token = request.headers.get('X-CSRF-Token','')
            if not token or not secrets.compare_digest(token,session.get('csrf','')):
                abort(403,description='Refresh the page and try again (CSRF token).')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def http_error(exc):
        return jsonify(error=exc.description),exc.code

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)),400

    @app.errorhandler(sqlite3.IntegrityError)
    def conflict(exc):
        return jsonify(error='Record already exists or violates a data constraint.'),409

    def body():
        data = request.get_json()
        if not isinstance(data,dict):
            abort(400,description='Expected a JSON object.')
        return data

    @app.get('/')
    def index():
        return send_from_directory(app.static_folder,'index.html')

    @app.post('/api/ingest')
    def cloud_ingest():
        import os
        from .cloud import accept_event
        expected = os.environ.get('MIKROSOC_INGEST_TOKEN','')
        supplied = request.headers.get('Authorization','')
        if not cfg['cloud_ingest_enabled'] or cfg['mode'] != 'live' or len(expected)<32 or not secrets.compare_digest(supplied,'Bearer '+expected):
            abort(403)
        return jsonify(accept_event(cfg,body()))

    @app.get('/api/intelligence/<address>')
    @role('admin','analyst','viewer')
    def intelligence(address):
        from .intel import lookup
        return jsonify(lookup(cfg,address))

    @app.get('/api/session')
    def current_session():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return jsonify(user=g.user,csrf=session['csrf'],mode=cfg['mode'],organization=cfg['organization'])

    @app.post('/api/login')
    def login():
        data = body()
        username,password = data.get('username',''),data.get('password','')
        if not isinstance(username,str) or not isinstance(password,str):
            abort(400)
        now = time.monotonic()
        peer = request.remote_addr
        with attempt_lock:
            bucket = attempts[peer]
            while bucket and bucket[0] < now-60:
                bucket.popleft()
            if len(bucket) >= 10:
                abort(429,description='Too many login attempts. Wait one minute.')
            bucket.append(now)
        with connect(cfg) as c:
            user = c.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
            valid = check_password_hash(user['password_hash'] if user else dummy_hash,password)
            if not valid or not user:
                audit(c,username[:64],'login_failed','local web login')
            else:
                session.clear()
                session.update(uid=user['id'],csrf=secrets.token_hex(32))
                session.permanent = True
                audit(c,user['username'],'login','local web login')
        if not valid or not user:
            abort(401,description='Invalid username or password.')
        return jsonify(ok=True,csrf=session['csrf'])

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/overview')
    @role('admin','analyst','viewer')
    def overview():
        with connect(cfg) as c:
            router = dict(c.execute('SELECT * FROM routers WHERE id=1').fetchone())
            metric = c.execute('SELECT * FROM metrics ORDER BY id DESC LIMIT 1').fetchone()
            if router['last_poll'] and time.time()-router['last_poll'] > cfg['poll_seconds']*2.5:
                router['status'] = 'stale'
            counts = {table:c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('logs','devices','alerts','incidents')}
            counts['open_alerts'] = c.execute("SELECT COUNT(*) FROM alerts WHERE status='open'").fetchone()[0]
            counts['active_incidents'] = c.execute("SELECT COUNT(*) FROM incidents WHERE stage!='closed'").fetchone()[0]
            history = rows(c,'SELECT collected_at,cpu,memory_percent,rx_mbps,tx_mbps FROM metrics ORDER BY id DESC LIMIT 60')[::-1]
        return jsonify(router=router,metric=dict(metric) if metric else None,counts=counts,history=history,collector=collector.stats if collector else {},mode=cfg['mode'],response_enabled=cfg['response_enabled'],poll_seconds=cfg['poll_seconds'])

    @app.get('/api/logs')
    @role('admin','analyst','viewer')
    def logs():
        search = request.args.get('q','')[:200]
        before = int(request.args.get('before',0))
        with connect(cfg) as c:
            data = rows(c,"SELECT * FROM logs WHERE message LIKE ? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 100",('%'+search+'%',before,before))
        return jsonify(items=data,next_before=data[-1]['id'] if len(data)==100 else None)

    @app.get('/api/<table>')
    @role('admin','analyst','viewer')
    def listing(table):
        with connect(cfg) as c:
            if table == 'incidents':
                data = rows(c,'SELECT i.*,a.title,a.severity,a.source,a.rule_key,a.evidence,a.status AS alert_status FROM incidents i JOIN alerts a ON a.id=i.alert_id ORDER BY i.id DESC LIMIT 200')
            elif table in ('devices','alerts','response_actions'):
                data = rows(c,f'SELECT * FROM {table} ORDER BY id DESC LIMIT 200')
            elif table == 'rules':
                data = rows(c,'SELECT * FROM detection_rules ORDER BY key')
            elif table in ('audit','users'):
                if g.user['role'] != 'admin':
                    abort(403)
                data = rows(c,'SELECT id,username,role,active FROM users ORDER BY id') if table=='users' else rows(c,'SELECT * FROM audit ORDER BY id DESC LIMIT 200')
            else:
                abort(404)
        return jsonify(items=data)

    @app.post('/api/devices/<int:did>/trust')
    @role('admin','analyst')
    def trust(did):
        trusted = body().get('trusted')
        if type(trusted) is not bool:
            raise ValueError('trusted must be true or false')
        with connect(cfg) as c:
            if not c.execute('UPDATE devices SET trusted=? WHERE id=?',(trusted,did)).rowcount:
                abort(404)
            audit(c,g.user['username'],'device_trust',f'{did}: {trusted}')
        return jsonify(ok=True)

    @app.post('/api/alerts/<int:aid>/ack')
    @role('admin','analyst')
    def acknowledge(aid):
        with connect(cfg) as c:
            if not c.execute("UPDATE alerts SET status='acknowledged' WHERE id=?",(aid,)).rowcount:
                abort(404)
            audit(c,g.user['username'],'acknowledge_alert',aid)
        return jsonify(ok=True)

    @app.post('/api/incidents/<int:iid>')
    @role('admin','analyst')
    def incident_update(iid):
        data = body()
        stage,notes,assignee = data.get('stage'),data.get('notes',''),data.get('assignee','')
        if stage not in STAGES or not isinstance(notes,str) or not isinstance(assignee,str) or len(notes)>8000 or len(assignee)>64:
            raise ValueError('Invalid stage, assignee or notes (maximum 8000 characters).')
        if stage in ('lessons_learned','closed') and not notes.strip():
            raise ValueError('Record investigation/recovery notes before closing.')
        with connect(cfg) as c:
            if not c.execute('UPDATE incidents SET stage=?,notes=?,assignee=?,updated_at=? WHERE id=?',(stage,notes,assignee,time.time(),iid)).rowcount:
                abort(404)
            audit(c,g.user['username'],'incident_update',f'{iid}: {stage}; assignee={assignee}; notes={notes}')
        return jsonify(ok=True)

    @app.get('/api/incidents/<int:iid>/response')
    @role('admin','analyst')
    def response_preview(iid):
        with connect(cfg) as c:
            incident = c.execute('SELECT i.id,a.source,a.rule_key FROM incidents i JOIN alerts a ON a.id=i.alert_id WHERE i.id=?',(iid,)).fetchone()
        if not incident:
            abort(404)
        return jsonify(preview(cfg,incident))

    @app.post('/api/incidents/<int:iid>/response')
    @role('admin')
    def response_execute(iid):
        data = body()
        if data.get('confirmation') != f'CONFIRM {iid}':
            raise ValueError(f'Type CONFIRM {iid} to authorize the router operation.')
        with connect(cfg) as c:
            incident = c.execute('SELECT i.id,a.source,a.rule_key FROM incidents i JOIN alerts a ON a.id=i.alert_id WHERE i.id=?',(iid,)).fetchone()
        if not incident:
            abort(404)
        return jsonify(execute(cfg,incident,g.user,data.get('action')))

    @app.post('/api/rules/<key>')
    @role('admin')
    def rule_update(key):
        data = body()
        try:
            threshold = float(data['threshold'])
            window,cooldown = int(data['window_seconds']),int(data['cooldown_seconds'])
        except (ValueError,KeyError,TypeError):
            raise ValueError('Rule values must be numeric.')
        if not 0 < threshold <= 100000 or not 30 <= window <= 86400 or not 30 <= cooldown <= 604800 or data.get('severity') not in ('low','medium','high','critical') or type(data.get('enabled')) is not bool:
            raise ValueError('Rule values outside allowed ranges.')
        if key == 'new_device' and threshold != 1:
            raise ValueError('New device threshold is always 1.')
        if key == 'exfiltration' and window < cfg['poll_seconds']*2:
            raise ValueError('Upload window must cover at least two poll intervals.')
        with connect(cfg) as c:
            if not c.execute('UPDATE detection_rules SET threshold=?,window_seconds=?,cooldown_seconds=?,severity=?,enabled=? WHERE key=?',(threshold,window,cooldown,data['severity'],data['enabled'],key)).rowcount:
                abort(404)
            audit(c,g.user['username'],'rule_update',json.dumps({'key':key,**data}))
        return jsonify(ok=True)

    @app.post('/api/users')
    @role('admin')
    def user_create():
        data = body()
        import re
        if not isinstance(data.get('username'),str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',data['username']) or data.get('role') not in ('admin','analyst','viewer'):
            raise ValueError('Use a 3–40 character username and valid role.')
        password = data.get('password')
        if not isinstance(password,str) or not 12 <= len(password) <= 256:
            raise ValueError('Password must be 12–256 characters.')
        with connect(cfg) as c:
            c.execute('INSERT INTO users(org_id,username,password_hash,role) VALUES(1,?,?,?)',(data['username'],generate_password_hash(password),data['role']))
            audit(c,g.user['username'],'create_user',data['username']+' '+data['role'])
        return jsonify(ok=True),201

    @app.post('/api/users/<int:uid>')
    @role('admin')
    def user_update(uid):
        data = body()
        if data.get('role') not in ('admin','analyst','viewer') or type(data.get('active')) is not bool:
            raise ValueError('Invalid user role or active flag.')
        if uid == g.user['id']:
            raise ValueError('You cannot disable yourself or change your own role.')
        with connect(cfg) as c:
            if not c.execute('UPDATE users SET role=?,active=? WHERE id=?',(data['role'],data['active'],uid)).rowcount:
                abort(404)
            audit(c,g.user['username'],'update_user',f'{uid}: {data["role"]}, active={data["active"]}')
        return jsonify(ok=True)

    @app.post('/api/password')
    @role('admin','analyst','viewer')
    def password_change():
        data = body()
        old,new = data.get('old',''),data.get('new','')
        if not isinstance(old,str) or not isinstance(new,str) or not 12 <= len(new) <= 256:
            raise ValueError('Password must be 12–256 characters.')
        with connect(cfg) as c:
            row = c.execute('SELECT password_hash FROM users WHERE id=?',(g.user['id'],)).fetchone()
            if not check_password_hash(row[0],old):
                abort(403,description='Current password is incorrect.')
            c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),g.user['id']))
            audit(c,g.user['username'],'password_changed','self')
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/report/<kind>.csv')
    @role('admin','analyst','viewer')
    def report(kind):
        queries = {'alerts':'SELECT * FROM alerts ORDER BY id DESC LIMIT 10000',
                   'incidents':'SELECT i.*,a.title,a.severity,a.source FROM incidents i JOIN alerts a ON a.id=i.alert_id ORDER BY i.id DESC LIMIT 10000',
                   'logs':'SELECT * FROM logs ORDER BY id DESC LIMIT 10000',
                   'devices':'SELECT * FROM devices ORDER BY id DESC LIMIT 10000',
                   'metrics':'SELECT * FROM metrics ORDER BY id DESC LIMIT 10000'}
        if kind not in queries:
            abort(404)
        with connect(cfg) as c:
            cursor = c.execute(queries[kind])
            records = cursor.fetchall()
            columns = [d[0] for d in cursor.description]
            audit(c,g.user['username'],'report_export',kind)
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(columns)
        def safe(value):
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r','\n')):
                return "'"+value
            return value
        writer.writerows([[safe(v) for v in row] for row in records])
        return app.response_class('\ufeff'+buffer.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="mikrosoc-{kind}.csv"'})

    return app
