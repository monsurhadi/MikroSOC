import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from mikrosoc.config import ROOT, load
from mikrosoc.db import init, connect, prune
from mikrosoc.detection import parse, ingest, update_devices, check_upload
from mikrosoc.collector import rates, Collector, uptime_seconds
from mikrosoc.routeros import RouterAPI, encode_length
from mikrosoc.response import target_for, execute
from mikrosoc.web import create_app
from mikrosoc.demo import seed
from mikrosoc.cloud import accept_event
from mikrosoc.intel import lookup


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cfg = json.loads((ROOT/'config.example.json').read_text())
        self.cfg.update(database=str(Path(self.temp.name)/'test.sqlite3'),api_ca_file=str(Path(self.temp.name)/'ca.crt'),config_dir=self.temp.name,intel_file=str(Path(self.temp.name)/'intel.csv'))
        init(self.cfg)
        self.now = time.time()

    def tearDown(self):
        self.temp.cleanup()

    def count(self,table):
        with connect(self.cfg) as c:
            return c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def login_event(self,user='admin',ip='192.168.88.55',via='ssh',now=None):
        return ingest(self.cfg,f'login failure for user {user} from {ip} via {via}',now or self.now)

    def test_parser_realistic_firewall(self):
        p=parse('firewall,info MSOC-CONN input: in:bridge out:(unknown 0), src-mac 00:11:22:33:44:55, proto TCP (SYN), 192.168.88.77:42111->192.168.88.1:22, len 60')
        self.assertEqual((p['kind'],p['src_ip'],p['dst_port']),('connection','192.168.88.77',22))

    def test_parser_invalid_ip_and_port(self):
        for s in ('proto TCP 999.1.1.1:22->1.1.1.1:80','proto TCP 1.1.1.1:22->2.2.2.2:99999'):
            self.assertEqual(parse(s)['kind'],'other')

    def test_brute_force_threshold_and_dedupe(self):
        for _ in range(4):self.login_event()
        self.assertEqual(self.count('alerts'),0)
        for _ in range(8):self.login_event()
        self.assertEqual(self.count('alerts'),1)
        self.assertEqual(self.count('incidents'),1)

    def test_brute_force_time_window(self):
        for _ in range(5):self.login_event(now=self.now-200)
        before=self.count('alerts')
        self.login_event(now=self.now)
        self.assertEqual(self.count('alerts'),before)

    def test_sources_not_combined(self):
        for _ in range(3):
            self.login_event(ip='192.168.88.51')
            self.login_event(ip='192.168.88.52')
        self.assertEqual(self.count('alerts'),0)

    def test_port_scan_unique_ports(self):
        for _ in range(20):ingest(self.cfg,'proto TCP 192.168.88.55:45000->192.168.88.1:80',self.now)
        self.assertEqual(self.count('alerts'),0)
        for p in range(100,112):ingest(self.cfg,f'proto TCP 192.168.88.55:45000->192.168.88.1:{p}',self.now)
        self.assertEqual(self.count('alerts'),1)

    def test_ssh_distinct_usernames(self):
        for i in range(4):self.login_event(user=f'user{i}')
        with connect(self.cfg) as c:
            self.assertEqual(c.execute('SELECT rule_key FROM alerts').fetchone()[0],'ssh_enumeration')

    def test_non_ssh_not_enumeration(self):
        for i in range(4):self.login_event(user=f'user{i}',via='winbox')
        self.assertEqual(self.count('alerts'),0)

    def test_disabled_rule(self):
        with connect(self.cfg) as c:c.execute("UPDATE detection_rules SET enabled=0 WHERE key='brute_force'")
        for _ in range(10):self.login_event()
        self.assertEqual(self.count('alerts'),0)

    def test_dhcp_baseline_then_new_device(self):
        d={'mac-address':'02:00:00:00:00:01','address':'192.168.88.11','host-name':'laptop'}
        with connect(self.cfg) as c:
            update_devices(c,[d],self.now)
            update_devices(c,[d],self.now+60)
        self.assertEqual(self.count('alerts'),0)
        d['mac-address']='02:00:00:00:00:02'
        with connect(self.cfg) as c:update_devices(c,[d],self.now+120)
        self.assertEqual(self.count('alerts'),1)

    def test_rates_counter_reset(self):
        self.assertEqual(rates((100,100),(10,120),60),(None,None))
        self.assertEqual(rates((0,0),(7500000,15000000),60),(1.0,2.0))

    def test_uptime_versions(self):
        self.assertEqual(uptime_seconds('1w2d03:04:05'),788645)
        self.assertEqual(uptime_seconds('1d2h3m4s'),93784)

    def test_upload_requires_sustained_samples(self):
        with connect(self.cfg) as c:
            for i in range(6):
                c.execute("INSERT INTO metrics(router_id,collected_at,tx_mbps,interfaces) VALUES(1,?,12,'[]')",(self.now-i*60,))
            check_upload(c,self.cfg,self.now)
        self.assertEqual(self.count('alerts'),1)

    def test_upload_gap_not_alert(self):
        with connect(self.cfg) as c:
            for t in (self.now-300,self.now):c.execute("INSERT INTO metrics(router_id,collected_at,tx_mbps,interfaces) VALUES(1,?,12,'[]')",(t,))
            check_upload(c,self.cfg,self.now)
        self.assertEqual(self.count('alerts'),0)

    def test_protected_response(self):
        for address in (self.cfg['router_ip'],self.cfg['collector_ip'],'127.0.0.1','224.0.0.1'):
            with self.assertRaises(ValueError):target_for(self.cfg,{'source':address,'rule_key':'port_scan'})
        with self.assertRaises(ValueError):target_for(self.cfg,{'source':'ether1','rule_key':'exfiltration'})

    def test_response_disabled(self):
        with self.assertRaises(ValueError):execute(self.cfg,{'id':1,'source':'192.168.88.55','rule_key':'port_scan'},{'id':1,'username':'admin'},'block')

    def test_demo_has_all_five_rules(self):
        seed(self.cfg)
        with connect(self.cfg) as c:self.assertEqual(len(c.execute('SELECT DISTINCT rule_key FROM alerts').fetchall()),5)
        with self.assertRaises(ValueError):seed(self.cfg)

    def test_retention_preserves_incidents(self):
        for _ in range(5):self.login_event()
        self.cfg['max_log_rows']=2
        prune(self.cfg)
        self.assertEqual(self.count('logs'),2)
        self.assertEqual(self.count('incidents'),1)

    def test_demo_live_database_separation(self):
        self.cfg['mode']='live'
        with self.assertRaises(ValueError):init(self.cfg)

    def test_udp_real_socket_path(self):
        self.cfg['syslog_port']=0
        collector=Collector(self.cfg)
        collector.start()
        try:
            port=collector.sock.getsockname()[1]
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                s.sendto(b'<134>router system,info MikroSOC UDP smoke test',('127.0.0.1',port))
            until=time.time()+3
            while time.time()<until and self.count('logs')<1:time.sleep(.03)
            self.assertEqual(self.count('logs'),1)
        finally:collector.close()

    def test_untrusted_udp_peer_rejected(self):
        self.cfg.update(mode='live',router_ip='192.0.2.1',syslog_port=0)
        collector=Collector(self.cfg)
        collector.start()
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.sendto(b'bad',collector.sock.getsockname())
            until=time.time()+2
            while time.time()<until and collector.stats['rejected']<1:time.sleep(.03)
            self.assertEqual(collector.stats['rejected'],1)
            self.assertEqual(self.count('logs'),0)
        finally:collector.close()

    def app_client(self,role='admin'):
        with connect(self.cfg) as c:c.execute('INSERT INTO users(org_id,username,password_hash,role) VALUES(1,?,?,?)',('tester',generate_password_hash('test-password-123'),role))
        app=create_app(self.cfg)
        app.config['TESTING']=True
        client=app.test_client()
        csrf=client.get('/api/session').json['csrf']
        result=client.post('/api/login',json={'username':'tester','password':'test-password-123'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(result.status_code,200)
        return client,{'X-CSRF-Token':result.json['csrf']}

    def test_auth_csrf_and_host(self):
        client,headers=self.app_client()
        self.assertEqual(client.post('/api/users',json={}).status_code,403)
        self.assertEqual(client.get('/api/session',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(client.get('/api/users').status_code,200)
        client.post('/api/logout',json={},headers=headers)
        self.assertEqual(client.get('/api/overview').status_code,401)

    def test_viewer_cannot_mutate(self):
        client,headers=self.app_client('viewer')
        self.assertEqual(client.post('/api/users',json={},headers=headers).status_code,403)
        self.assertEqual(client.post('/api/incidents/1',json={},headers=headers).status_code,403)
        self.assertEqual(client.get('/api/users').status_code,403)
        self.assertEqual(client.get('/api/overview').status_code,200)

    def test_incident_workflow_and_audit(self):
        seed(self.cfg)
        client,headers=self.app_client('analyst')
        r=client.post('/api/incidents/1',json={'stage':'closed','notes':'Confirmed lab test. Recovered; no ongoing issue.','assignee':'tester'},headers=headers)
        self.assertEqual(r.status_code,200)
        with connect(self.cfg) as c:self.assertEqual(c.execute('SELECT stage FROM incidents WHERE id=1').fetchone()[0],'closed')
        self.assertGreater(self.count('audit'),0)

    def test_csv_formula_escaped(self):
        ingest(self.cfg,'=HYPERLINK("https://example.invalid")')
        client,headers=self.app_client()
        result=client.get('/api/report/logs.csv')
        self.assertIn("'=HYPERLINK",result.get_data(as_text=True))

    def test_rule_validation(self):
        client,headers=self.app_client()
        d={'threshold':'NaN','window_seconds':60,'cooldown_seconds':300,'severity':'high','enabled':True}
        self.assertEqual(client.post('/api/rules/port_scan',json=d,headers=headers).status_code,400)

    def test_cloud_ingest_transaction_and_duplicate(self):
        e={'event_id':'edge:1','router_ip':self.cfg['router_ip'],'observed_at':self.now,'kind':'log','payload':{'message':'hello'}}
        self.assertFalse(accept_event(self.cfg,e)['duplicate'])
        self.assertTrue(accept_event(self.cfg,e)['duplicate'])
        self.assertEqual(self.count('logs'),1)
        e.update(event_id='edge:2',payload={'message':123})
        with self.assertRaises(ValueError):accept_event(self.cfg,e)
        self.assertEqual(self.count('ingress_receipts'),1)

    def test_cloud_requires_token(self):
        self.cfg.update(mode='live',cloud_ingest_enabled=True)
        app=create_app(self.cfg)
        client=app.test_client()
        e={'event_id':'edge:1','router_ip':self.cfg['router_ip'],'observed_at':self.now,'kind':'log','payload':{'message':'hello'}}
        with patch.dict(os.environ,{'MIKROSOC_INGEST_TOKEN':'a'*40}):
            self.assertEqual(client.post('/api/ingest',json=e).status_code,403)
            self.assertEqual(client.post('/api/ingest',json=e,headers={'Authorization':'Bearer '+'a'*40}).status_code,200)

    def test_offline_intelligence(self):
        Path(self.cfg['intel_file']).write_text('cidr,country,asn,label,reputation,source,updated\n192.168.88.0/24,,,My LAN,trusted,local,2026-09-18\n')
        self.assertEqual(lookup(self.cfg,'192.168.88.11')['matches'][0]['label'],'My LAN')

    def test_smtp_queue_with_mock_transport(self):
        from mikrosoc.notifications import deliver
        for _ in range(5):self.login_event()
        env={'MIKROSOC_SMTP_HOST':'smtp.example.invalid','MIKROSOC_SMTP_FROM':'from@example.invalid','MIKROSOC_SMTP_TO':'to@example.invalid','MIKROSOC_SMTP_USER':'test','MIKROSOC_SMTP_PASSWORD':'test'}
        with patch.dict(os.environ,env),patch('mikrosoc.notifications.smtplib.SMTP') as smtp:
            deliver(self.cfg)
            smtp.return_value.__enter__.return_value.starttls.assert_called_once()
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
        with connect(self.cfg) as c:self.assertEqual(c.execute('SELECT state FROM notifications').fetchone()[0],'sent')

    def test_response_mock_api_and_audit(self):
        seed(self.cfg)
        client,headers=self.app_client()
        self.cfg.update(mode='live',response_enabled=True)
        class FakeAPI:
            def __init__(self,*args):self.calls=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def command(self,path,**attrs):
                if path=='/ip/firewall/filter/print':
                    return [{'chain':chain,'action':'drop','src-address-list':'MikroSOC-blocked','disabled':'false','comment':'MikroSOC containment '+chain} for chain in ('input','forward')]
                return []
        with patch.dict(os.environ,{'MIKROSOC_RESPONSE_PASSWORD':'test'}),patch('mikrosoc.response.RouterAPI',FakeAPI):
            result=execute(self.cfg,{'id':1,'rule_key':'port_scan','source':'192.168.88.77'},{'id':1,'username':'tester'},'block')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.count('response_actions'),1)


class ProtocolTest(unittest.TestCase):
    def test_encoding_roundtrip_boundaries(self):
        for n in (0,127,128,16383,16384,2097151,2097152,268435455,268435456,4294967295):
            api=object.__new__(RouterAPI)
            data=io.BytesIO(encode_length(n))
            api._read=data.read
            self.assertEqual(api._length(),n)

    def test_mock_router_login_and_print(self):
        server=socket.socket()
        server.bind(('127.0.0.1',0));server.listen(1)
        received=[]
        def router():
            conn,_=server.accept()
            with conn:
                for i in range(2):
                    words=[]
                    while True:
                        n=conn.recv(1)[0]
                        if n==0:break
                        word=b''
                        while len(word)<n:word+=conn.recv(n-len(word))
                        words.append(word.decode())
                    received.append(words)
                    replies=[['!done']] if i==0 else [['!re','=cpu-load=8','=uptime=1d'],['!done']]
                    for sentence in replies:conn.sendall(b''.join(encode_length(len(w))+w.encode() for w in sentence)+b'\0')
        thread=threading.Thread(target=router);thread.start()
        cfg={'router_ip':'127.0.0.1','api_port':server.getsockname()[1],'api_tls':False,'allow_insecure_api':True}
        try:
            with RouterAPI(cfg,'reader','test-password') as api:
                result=api.command('/system/resource/print',**{'.proplist':'cpu-load,uptime'})
            self.assertEqual(result,[{'cpu-load':'8','uptime':'1d'}])
            self.assertIn('=name=reader',received[0])
        finally:
            server.close();thread.join(2)


if __name__=='__main__':unittest.main()
