import ipaddress
import json
import re
import time
from contextlib import nullcontext
from .db import connect

FLOW = re.compile(r'(?P<src>\d{1,3}(?:\.\d{1,3}){3}):\d+\s*->\s*(?P<dst>\d{1,3}(?:\.\d{1,3}){3}):(?P<port>\d+)')
LOGIN = re.compile(r'login failure for user\s+(.*?)\s+from\s+(\d{1,3}(?:\.\d{1,3}){3})\s+via\s+(\S+)', re.I)


def parse(message):
    result = dict(kind='other',src_ip=None,dst_ip=None,dst_port=None,username=None)
    login = LOGIN.search(message)
    flow = FLOW.search(message)
    if login:
        try:
            ipaddress.IPv4Address(login[2])
        except ValueError:
            return result
        result.update(kind='ssh_failure' if login[3].lower() == 'ssh' else 'login_failure', src_ip=login[2],username=login[1][:128])
    elif flow:
        try:
            ipaddress.IPv4Address(flow['src'])
            ipaddress.IPv4Address(flow['dst'])
            port = int(flow['port'])
            if not 1 <= port <= 65535:
                return result
        except ValueError:
            return result
        result.update(kind='connection',src_ip=flow['src'],dst_ip=flow['dst'],dst_port=port)
    return result


def alert(c, key, source, evidence, now=None):
    now = now if now is not None else time.time()
    rule = c.execute('SELECT * FROM detection_rules WHERE key=? AND enabled=1',(key,)).fetchone()
    if not rule:
        return None
    recent = c.execute('SELECT id FROM alerts WHERE router_id=1 AND rule_key=? AND source=? AND created_at>?', (key,source,now-rule['cooldown_seconds'])).fetchone()
    if recent:
        return None
    aid = c.execute('INSERT INTO alerts(router_id,rule_key,created_at,severity,source,title,evidence) VALUES(1,?,?,?,?,?,?)', (key,now,rule['severity'],source,rule['title'],json.dumps(evidence))).lastrowid
    c.execute('INSERT INTO incidents(alert_id,updated_at) VALUES(?,?)', (aid,now))
    return aid


def ingest(cfg, message, now=None, connection=None):
    now = now if now is not None else time.time()
    message = message[:4096].replace('\x00','')
    event = parse(message)
    with (nullcontext(connection) if connection is not None else connect(cfg)) as c:
        lid = c.execute('INSERT INTO logs(router_id,received_at,kind,src_ip,dst_ip,dst_port,username,message) VALUES(1,?,?,?,?,?,?,?)', (now,event['kind'],event['src_ip'],event['dst_ip'],event['dst_port'],event['username'],message)).lastrowid
        c.execute('UPDATE routers SET last_syslog=? WHERE id=1',(now,))
        for rule in c.execute('SELECT * FROM detection_rules WHERE enabled=1').fetchall():
            key = rule['key']
            count = 0
            if key == 'port_scan' and event['kind'] == 'connection':
                count = c.execute("SELECT COUNT(DISTINCT dst_port) FROM logs WHERE router_id=1 AND kind='connection' AND src_ip=? AND received_at BETWEEN ? AND ?", (event['src_ip'],now-rule['window_seconds'],now)).fetchone()[0]
            elif key == 'brute_force' and event['kind'] in ('login_failure','ssh_failure'):
                count = c.execute("SELECT COUNT(*) FROM logs WHERE router_id=1 AND kind IN ('login_failure','ssh_failure') AND src_ip=? AND received_at BETWEEN ? AND ?", (event['src_ip'],now-rule['window_seconds'],now)).fetchone()[0]
            elif key == 'ssh_enumeration' and event['kind'] == 'ssh_failure':
                count = c.execute("SELECT COUNT(DISTINCT username) FROM logs WHERE router_id=1 AND kind='ssh_failure' AND src_ip=? AND received_at BETWEEN ? AND ?", (event['src_ip'],now-rule['window_seconds'],now)).fetchone()[0]
            if count >= rule['threshold']:
                alert(c,key,event['src_ip'],{'count':count,'window_seconds':rule['window_seconds'],'trigger_log_id':lid,'sample':message},now)
    return event


def update_devices(c, leases, now):
    baseline = bool(c.execute('SELECT baseline FROM routers WHERE id=1').fetchone()[0])
    for lease in leases:
        mac = lease.get('mac-address','').upper()
        if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}',mac):
            continue
        existing = c.execute('SELECT id FROM devices WHERE router_id=1 AND mac=?',(mac,)).fetchone()
        address, name = lease.get('address',''), lease.get('host-name','')
        if existing:
            c.execute('UPDATE devices SET ip=?,hostname=?,last_seen=? WHERE id=?',(address,name,now,existing['id']))
        else:
            c.execute('INSERT INTO devices(router_id,mac,ip,hostname,first_seen,last_seen) VALUES(1,?,?,?,?,?)',(mac,address,name,now,now))
            if baseline:
                alert(c,'new_device',mac,{'mac':mac,'ip':address,'hostname':name,'source':'DHCP lease snapshot'},now)
    c.execute('UPDATE routers SET baseline=1 WHERE id=1')


def check_upload(c, cfg, now):
    rule = c.execute("SELECT * FROM detection_rules WHERE key='exfiltration' AND enabled=1").fetchone()
    if not rule:
        return
    samples = c.execute('SELECT collected_at,tx_mbps FROM metrics WHERE router_id=1 AND collected_at BETWEEN ? AND ? ORDER BY collected_at',(now-rule['window_seconds'],now)).fetchall()
    # Require full sustained coverage to within one poll; reject missing samples.
    valid = len(samples) >= 2 and samples[0]['collected_at'] <= now-rule['window_seconds']+cfg['poll_seconds']*1.2
    valid = valid and all(s['tx_mbps'] is not None and s['tx_mbps'] >= rule['threshold'] for s in samples)
    valid = valid and all(b['collected_at']-a['collected_at'] <= cfg['poll_seconds']*1.8 for a,b in zip(samples,samples[1:]))
    if valid:
        alert(c,'exfiltration',cfg['wan_interface'],{'minimum_upload_mbps':min(s['tx_mbps'] for s in samples),'samples':len(samples),'window_seconds':rule['window_seconds'],'limitation':'Aggregate WAN traffic anomaly; no host attribution or proof of exfiltration.'},now)
