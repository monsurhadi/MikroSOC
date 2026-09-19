"""Authenticated edge telemetry ingestion. Router credentials never leave the LAN."""
import ipaddress
import json
import math
import re
import time
from .db import connect
from .detection import ingest, update_devices, check_upload


def accept_event(cfg, event):
    eid = event.get('event_id','')
    if not isinstance(eid,str) or not re.fullmatch(r'[A-Za-z0-9:_.-]{1,120}',eid):
        raise ValueError('Invalid event ID')
    if event.get('router_ip') != cfg['router_ip']:
        raise ValueError('Router IP does not match this instance.')
    stamp = event.get('observed_at')
    if type(stamp) not in (float,int) or not math.isfinite(stamp) or not time.time()-7*86400 <= stamp <= time.time()+300:
        raise ValueError('Timestamp must be within the last seven days; synchronize clocks.')
    kind,payload = event.get('kind'),event.get('payload')
    if kind not in ('log','metric','devices') or not isinstance(payload,dict):
        raise ValueError('Unknown event type')
    with connect(cfg) as c:
        # BEGIN IMMEDIATE serializes duplicate checks and all associated effects.
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM ingress_receipts WHERE event_id=?',(eid,)).fetchone():
            return {'ok':True,'duplicate':True}
        if kind=='log':
            message = payload.get('message')
            if not isinstance(message,str) or len(message)>4096:
                raise ValueError('Invalid log message')
            ingest(cfg,message,stamp,connection=c)
        elif kind=='metric':
            for key in ('cpu','memory_percent','rx_mbps','tx_mbps'):
                value = payload.get(key)
                if value is not None and (type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=100000):
                    raise ValueError('Invalid metric')
            interfaces = payload.get('interfaces',[])
            if not isinstance(interfaces,list) or len(interfaces)>100 or any(not isinstance(i,dict) for i in interfaces):
                raise ValueError('Invalid interfaces')
            c.execute('INSERT INTO metrics(router_id,collected_at,cpu,memory_percent,uptime,rx_mbps,tx_mbps,interfaces) VALUES(1,?,?,?,?,?,?,?)',(stamp,payload.get('cpu'),payload.get('memory_percent'),str(payload.get('uptime',''))[:80],payload.get('rx_mbps'),payload.get('tx_mbps'),json.dumps(interfaces)))
            c.execute("UPDATE routers SET last_poll=?,status='online',error=NULL WHERE id=1 AND (last_poll IS NULL OR last_poll<=?)",(stamp,stamp))
            check_upload(c,cfg,stamp)
        else:
            leases = payload.get('leases')
            if not isinstance(leases,list) or len(leases)>200 or any(not isinstance(i,dict) for i in leases):
                raise ValueError('At most 200 DHCP devices per snapshot')
            for lease in leases:
                ipaddress.IPv4Address(lease.get('address'))
                if not isinstance(lease.get('mac-address'),str) or not isinstance(lease.get('host-name',''),str):
                    raise ValueError('Invalid DHCP lease')
            update_devices(c,leases,stamp)
        c.execute('INSERT INTO ingress_receipts VALUES(?,?)',(eid,time.time()))
        c.execute('DELETE FROM ingress_receipts WHERE received_at<?',(time.time()-8*86400,))
    return {'ok':True,'duplicate':False}
