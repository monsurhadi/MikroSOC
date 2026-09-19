import json
import logging
import os
import queue
import socket
import threading
import time
from .db import connect, prune
from .detection import ingest, update_devices, check_upload
from .routeros import RouterAPI

log = logging.getLogger(__name__)


def rates(previous, current, elapsed):
    if previous is None or elapsed <= 0 or current[0] < previous[0] or current[1] < previous[1]:
        return None, None
    return tuple(round((n-o)*8/elapsed/1000000,4) for o,n in zip(previous,current))


class Collector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.stop = threading.Event()
        self.queue = queue.Queue(maxsize=5000)
        self.stats = {'accepted':0,'rejected':0,'dropped':0,'errors':0,'syslog':'stopped','poll':'disabled'}
        self.threads = []
        self.sock = None
        self.previous = None
        self.previous_time = None
        self.previous_uptime = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            self.sock.bind((self.cfg['syslog_host'],self.cfg['syslog_port']))
            self.sock.settimeout(1)
        except Exception:
            self.sock.close()
            raise
        self.stats['syslog'] = 'listening'
        targets = [self.receive,self.consume,self.maintenance]
        if self.cfg.get('smtp_enabled'):
            targets.append(self.notify_loop)
        if self.cfg['mode'] == 'live' and self.cfg['api_enabled']:
            targets.append(self.poll_loop)
        for target in targets:
            thread = threading.Thread(target=target,daemon=True,name=target.__name__)
            thread.start()
            self.threads.append(thread)

    def close(self):
        self.stop.set()
        if self.sock:
            self.sock.close()
        for thread in self.threads:
            thread.join(timeout=2)
        self.stats['syslog'] = 'stopped'

    def receive(self):
        allowed = '127.0.0.1' if self.cfg['mode'] == 'demo' else self.cfg['router_ip']
        while not self.stop.is_set():
            try:
                packet, peer = self.sock.recvfrom(8192)
                if peer[0] != allowed:
                    self.stats['rejected'] += 1
                    continue
                try:
                    self.queue.put_nowait(packet[:4096].decode('utf-8','replace'))
                    self.stats['accepted'] += 1
                except queue.Full:
                    self.stats['dropped'] += 1
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    self.stats['syslog'] = 'failed'
                    log.exception('Syslog socket failed')
                return

    def consume(self):
        while not self.stop.is_set():
            try:
                msg = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                ingest(self.cfg,msg)
            except Exception:
                self.stats['errors'] += 1
                log.exception('Could not store syslog')
            finally:
                self.queue.task_done()

    def maintenance(self):
        while not self.stop.is_set():
            try:
                prune(self.cfg)
            except Exception:
                log.exception('Retention cleanup failed')
            self.stop.wait(60)

    def notify_loop(self):
        from .notifications import deliver
        while not self.stop.is_set():
            try:
                deliver(self.cfg)
            except Exception:
                log.warning('Email delivery failed; check SMTP settings and notification records.')
            self.stop.wait(30)

    def poll_once(self):
        password = os.environ.get('MIKROSOC_ROUTER_PASSWORD')
        if not password:
            raise ValueError('Set MIKROSOC_ROUTER_PASSWORD in the terminal before starting.')
        cfg = self.cfg
        with RouterAPI(cfg,cfg['api_username'],password) as api:
            resource = api.command('/system/resource/print', **{'.proplist':'cpu-load,free-memory,total-memory,uptime,version,board-name'})
            interfaces = api.command('/interface/print', **{'.proplist':'name,running,disabled,rx-byte,tx-byte'})
            leases = api.command('/ip/dhcp-server/lease/print',queries=('?status=bound',),**{'.proplist':'address,mac-address,host-name,status'})
        if not resource:
            raise RuntimeError('Router returned no resource information')
        now = time.time()
        r = resource[0]
        wan = next((i for i in interfaces if i.get('name') == cfg['wan_interface']),None)
        if wan is None or 'rx-byte' not in wan or 'tx-byte' not in wan:
            raise ValueError('WAN interface or byte counters missing; check wan_interface in config.json.')
        current = (int(wan['rx-byte']),int(wan['tx-byte']))
        # Discard the first interval after restart, counter reset, or a polling gap.
        elapsed = now-self.previous_time if self.previous_time else 0
        old = self.previous if elapsed <= cfg['poll_seconds']*1.8 else None
        uptime = uptime_seconds(r.get('uptime',''))
        if self.previous_uptime is not None and uptime < self.previous_uptime:
            old = None
        rx,tx = rates(old,current,elapsed)
        total = max(1,int(r.get('total-memory',1)))
        memory = round((1-int(r.get('free-memory',0))/total)*100,2)
        with connect(cfg) as c:
            c.execute('INSERT INTO metrics(router_id,collected_at,cpu,memory_percent,uptime,rx_mbps,tx_mbps,interfaces) VALUES(1,?,?,?,?,?,?,?)',(now,float(r.get('cpu-load',0)),memory,r.get('uptime',''),rx,tx,json.dumps(interfaces)))
            update_devices(c,leases,now)
            c.execute("UPDATE routers SET last_poll=?,status='online',error=NULL WHERE id=1",(now,))
            check_upload(c,cfg,now)
        self.previous,self.previous_time,self.previous_uptime = current,now,uptime

    def poll_loop(self):
        while not self.stop.is_set():
            try:
                self.stats['poll'] = 'polling'
                self.poll_once()
                self.stats['poll'] = 'healthy'
            except Exception as exc:
                self.stats['poll'] = 'failed'
                log.warning('Router poll failed: %s',type(exc).__name__)
                # Avoid storing exception text that might contain credentials or a full reply.
                with connect(self.cfg) as c:
                    c.execute("UPDATE routers SET status='unreachable',error=? WHERE id=1",(type(exc).__name__ + ': check IP, credentials, CA certificate, API service and firewall',))
                self.previous = None
            self.stop.wait(self.cfg['poll_seconds'])


def uptime_seconds(value):
    import re
    total = 0
    for number,unit in re.findall(r'(\d+)([wdhms])',value):
        total += int(number)*{'w':604800,'d':86400,'h':3600,'m':60,'s':1}[unit]
    colon = re.search(r'(\d+):(\d+):(\d+)',value)
    if colon:
        total += int(colon[1])*3600+int(colon[2])*60+int(colon[3])
    return total
