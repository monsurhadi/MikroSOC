import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from mikrosoc.config import ROOT, load
from mikrosoc.db import init, connect, audit, prune


def main():
    parser = argparse.ArgumentParser(description='MikroSOC local monitoring console')
    parser.add_argument('--config',default=str(ROOT/'config.json'))
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init',help='Initialize DB and create initial admin interactively')
    sub.add_parser('demo',help='Load synthetic demo events, once per demo database')
    sub.add_parser('run',help='Run UI and collectors in a single process')
    sub.add_parser('doctor',help='Check configuration; live mode tests read-only API when enabled')
    sub.add_parser('prune',help='Apply log and metric retention')
    reset = sub.add_parser('reset-password',help='Reset a local web account password')
    reset.add_argument('username')
    backup = sub.add_parser('backup',help='Create consistent SQLite backup')
    backup.add_argument('destination')
    args = parser.parse_args()
    if not Path(args.config).exists():
        shutil.copyfile(ROOT/'config.example.json',args.config)
        print('Created config.json in demo mode.')
    cfg = load(args.config)
    init(cfg)
    if args.command in ('init','reset-password'):
        from werkzeug.security import generate_password_hash
        with connect(cfg) as c:
            if args.command == 'init' and c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
                print('Database initialized; accounts already exist. Use reset-password if needed.')
                return
            username = args.username if args.command == 'reset-password' else input('Admin username [admin]: ').strip() or 'admin'
            import re
            if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',username):
                raise ValueError('Username must be 3–40 letters, numbers, dots, underscores or hyphens.')
            password = getpass.getpass('New password (12–256 characters): ')
            if not 12 <= len(password) <= 256 or password != getpass.getpass('Repeat password: '):
                raise ValueError('Passwords must match and be 12–256 characters long.')
            if args.command == 'init':
                c.execute("INSERT INTO users(org_id,username,password_hash,role) VALUES(1,?,?,'admin')",(username,generate_password_hash(password)))
            elif not c.execute('UPDATE users SET password_hash=? WHERE username=?',(generate_password_hash(password),username)).rowcount:
                raise ValueError('Account not found.')
            audit(c,'local CLI',args.command,username)
        print('Account ready.')
    elif args.command == 'demo':
        from mikrosoc.demo import seed
        seed(cfg)
        print('Synthetic data loaded; run python manage.py run.')
    elif args.command == 'prune':
        prune(cfg)
        print('Retention applied.')
    elif args.command == 'backup':
        destination = Path(args.destination).resolve()
        if destination.exists() or destination == Path(cfg['database']):
            raise ValueError('Choose a new backup filename.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        with connect(cfg) as source:
            dest = sqlite3.connect(destination)
            try:
                source.backup(dest)
            finally:
                dest.close()
        print('Backup saved to',destination)
    elif args.command == 'doctor':
        print(json.dumps({k:cfg[k] for k in ('mode','database','router_ip','collector_ip','api_enabled','api_tls','syslog_host','syslog_port','wan_interface')},indent=2))
        if cfg['mode']=='live' and cfg['api_enabled']:
            from mikrosoc.collector import Collector
            Collector(cfg).poll_once()
            print('Read-only API polling succeeded; metrics and DHCP inventory stored. UDP delivery still needs a router test message.')
        else:
            print('Configuration valid. Live API polling is disabled.')
    elif args.command == 'run':
        from waitress import serve
        from mikrosoc.web import create_app
        from mikrosoc.collector import Collector
        with connect(cfg) as c:
            if not c.execute('SELECT 1 FROM users WHERE active=1').fetchone():
                raise ValueError('Run python manage.py init to create an administrator first.')
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        collector = Collector(cfg)
        collector.start()
        print(f'MikroSOC ({cfg["mode"]}) — http://127.0.0.1:{cfg["web_port"]} — Ctrl+C to stop',flush=True)
        try:
            serve(create_app(cfg,collector),host=cfg['web_host'],port=cfg['web_port'],threads=4,channel_timeout=30,max_request_body_size=65536)
        finally:
            collector.close()


if __name__ == '__main__':
    try:
        main()
    except (ValueError,OSError,RuntimeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        sys.exit(1)
