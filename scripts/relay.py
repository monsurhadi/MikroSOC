"""Run beside the local collector. Forward events through an SSM localhost tunnel."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mikrosoc.config import load
from mikrosoc.db import connect


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--port',type=int,default=18000,help='Local SSM tunnel port')
    args=parser.parse_args()
    cfg=load(args.config)
    if cfg['mode']!='live':
        raise ValueError('Relay requires live mode.')
    token=os.environ.get('MIKROSOC_INGEST_TOKEN','')
    if len(token)<32:
        raise ValueError('Set a random MIKROSOC_INGEST_TOKEN of at least 32 characters.')
    state_path=Path(cfg['database']).with_suffix('.relay.sqlite3')
    state=sqlite3.connect(state_path)
    state.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    state.execute("INSERT OR IGNORE INTO state VALUES('node',?)",(uuid.uuid4().hex,))
    state.commit()
    node=state.execute("SELECT value FROM state WHERE key='node'").fetchone()[0]
    cursors={kind:int((state.execute('SELECT value FROM state WHERE key=?',(kind,)).fetchone() or [0])[0]) for kind in ('log','metric')}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def post(event):
        request=urllib.request.Request(f'http://127.0.0.1:{args.port}/api/ingest',data=json.dumps(event).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
        with opener.open(request,timeout=10) as reply:
            return json.load(reply)
    print('Relaying local telemetry through SSM. Keep the local collector and SSM tunnel running.',flush=True)
    while True:
        try:
            for kind,table,column in [('log','logs','received_at'),('metric','metrics','collected_at')]:
                with connect(cfg) as c:
                    minimum=c.execute(f'SELECT MIN(id) FROM {table}').fetchone()[0]
                    records=[dict(r) for r in c.execute(f'SELECT * FROM {table} WHERE id>? ORDER BY id LIMIT 100',(cursors[kind],))]
                if minimum and cursors[kind] and minimum>cursors[kind]+1:
                    print(f'WARNING: {kind} retention removed unforwarded records before ID {minimum}.',flush=True)
                for record in records:
                    if record[column]<time.time()-7*86400:
                        print(f'WARNING: skipping expired {kind} #{record["id"]}; cloud accepts seven days.',flush=True)
                    else:
                        payload={'message':record['message']} if kind=='log' else {k:record[k] for k in ('cpu','memory_percent','uptime','rx_mbps','tx_mbps')}
                        if kind=='metric':
                            payload['interfaces']=json.loads(record['interfaces'])
                        post({'event_id':f'{node}:{kind}:{record["id"]}','router_ip':cfg['router_ip'],'observed_at':record[column],'kind':kind,'payload':payload})
                    cursors[kind]=record['id']
                    state.execute('INSERT OR REPLACE INTO state VALUES(?,?)',(kind,str(record['id'])))
                    state.commit()
            with connect(cfg) as c:
                devices=[dict(r) for r in c.execute('SELECT * FROM devices ORDER BY id LIMIT 200')]
            if devices:
                stamp=max(d['last_seen'] for d in devices)
                if stamp>=time.time()-7*86400:
                    leases=[{'address':d['ip'],'mac-address':d['mac'],'host-name':d['hostname']} for d in devices if d['last_seen']==stamp]
                    digest=hashlib.sha256(json.dumps(leases,sort_keys=True).encode()).hexdigest()[:20]
                    post({'event_id':f'{node}:devices:{stamp}:{digest}','router_ip':cfg['router_ip'],'observed_at':stamp,'kind':'devices','payload':{'leases':leases}})
            time.sleep(10)
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            print(f'Relay waiting: {type(exc).__name__}. Check tunnel/token/configuration; cursors kept for retry.',flush=True)
            time.sleep(15)


if __name__=='__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
