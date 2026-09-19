import ipaddress
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path=None):
    path = Path(path or ROOT / 'config.json').resolve()
    if not path.exists():
        raise ValueError('Copy config.example.json to config.json first.')
    cfg = json.loads(path.read_text(encoding='utf-8-sig'))
    cfg.setdefault('cloud_ingest_enabled',False)
    cfg.setdefault('smtp_enabled',False)
    cfg.setdefault('intel_file','data/intelligence.csv')
    if cfg.get('mode') not in ('demo', 'live'):
        raise ValueError('mode must be demo or live')
    for key in ('router_ip', 'collector_ip', 'syslog_host', 'web_host'):
        ipaddress.IPv4Address(cfg[key])
    if cfg['web_host'] != '127.0.0.1':
        raise ValueError('This local edition binds its web UI to 127.0.0.1 only.')
    if cfg['mode'] == 'demo' and cfg['syslog_host'] != '127.0.0.1':
        raise ValueError('Demo syslog must bind to 127.0.0.1.')
    for key in ('web_port', 'syslog_port', 'api_port'):
        if type(cfg[key]) is not int or not 1 <= cfg[key] <= 65535:
            raise ValueError(f'Invalid {key}')
    if not 30 <= cfg['poll_seconds'] <= 3600:
        raise ValueError('poll_seconds must be 30 through 3600')
    for key in ('retention_days', 'max_log_rows', 'max_metric_rows'):
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(f'Invalid {key}')
    for network in cfg['protected_networks']:
        ipaddress.IPv4Network(network)
    if cfg['api_enabled'] and not cfg['api_tls'] and not cfg['allow_insecure_api']:
        raise ValueError('Plain API requires explicit allow_insecure_api=true for an isolated lab.')
    if cfg['response_enabled'] and (not cfg['api_tls'] or cfg['mode'] != 'live'):
        raise ValueError('Live response requires live mode and verified TLS.')
    cfg['database'] = str((path.parent / cfg['database']).resolve())
    cfg['api_ca_file'] = str((path.parent / cfg['api_ca_file']).resolve())
    cfg['config_dir'] = str(path.parent)
    cfg['intel_file'] = str((path.parent/cfg['intel_file']).resolve())
    return cfg
