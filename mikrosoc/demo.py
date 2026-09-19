"""Synthetic fixtures only. No traffic is sent to a router or external target."""
import json
import time
from .db import connect
from .detection import ingest, update_devices, check_upload


def seed(cfg):
    if cfg['mode'] != 'demo':
        raise ValueError('Demo data is forbidden in live mode.')
    with connect(cfg) as c:
        if c.execute("SELECT 1 FROM meta WHERE key='demo_seeded'").fetchone():
            raise ValueError('Demo data already loaded. Use a new demo database to start again.')
    now = time.time()
    for port in range(8000,8013):
        ingest(cfg,f'<134>MikroSOC firewall,info MSOC-CONN input: in:bridge out:(unknown 0), proto TCP (SYN), 192.168.88.77:45000->192.168.88.1:{port}, len 60',now-45+port-8000)
    for i in range(6):
        ingest(cfg,f'<132>MikroSOC system,error,critical login failure for user guest{i} from 192.168.88.78 via ssh',now-20+i)
    with connect(cfg) as c:
        update_devices(c,[{'mac-address':'02:00:00:00:00:10','address':cfg['collector_ip'],'host-name':'Monitoring-PC'}],now-600)
        update_devices(c,[{'mac-address':'02:00:00:00:00:20','address':'192.168.88.20','host-name':'Lab-laptop'}],now-60)
        c.execute('UPDATE devices SET trusted=1 WHERE ip=?',(cfg['collector_ip'],))
        for i in range(21):
            stamp = now-(20-i)*cfg['poll_seconds']
            tx = 12.5 if i>=14 else 0.3+(i%4)*0.2
            c.execute('INSERT INTO metrics(router_id,collected_at,cpu,memory_percent,uptime,rx_mbps,tx_mbps,interfaces) VALUES(1,?,?,?,?,?,?,?)',(stamp,8+i%5,64,'2d03:15:00',3.2+i%3,tx,json.dumps([{'name':'ether1','running':'true'},{'name':'bridge','running':'true'}])))
        check_upload(c,cfg,now)
        c.execute("UPDATE routers SET last_poll=?,status='online' WHERE id=1",(now,))
        c.execute("INSERT INTO meta VALUES('demo_seeded','yes')")
