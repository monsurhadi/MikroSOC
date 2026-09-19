"""Optional offline CIDR intelligence. No external IP disclosure or API fees."""
import csv
import ipaddress
from pathlib import Path


def lookup(cfg,address):
    ip = ipaddress.ip_address(address)
    result = {'ip':str(ip),'scope':'public' if ip.is_global else 'non-public','matches':[],
              'note':'Offline user-supplied intelligence. Location and reputation are leads, not proof of compromise.'}
    path = Path(cfg['intel_file'])
    if not path.exists():
        result['note'] = 'No intelligence file installed. See docs/OPERATIONS.md. No third-party lookup performed.'
        return result
    if path.stat().st_size>5_000_000:
        raise ValueError('Intelligence file exceeds 5 MB.')
    with path.open(encoding='utf-8-sig',newline='') as source:
        for row in csv.DictReader(source):
            try:
                network = ipaddress.ip_network(row['cidr'])
            except (ValueError,KeyError):
                continue
            if ip in network:
                result['matches'].append({k:row.get(k,'')[:300] for k in ('cidr','country','asn','label','reputation','source','updated')})
                if len(result['matches'])>=20:
                    break
    return result
