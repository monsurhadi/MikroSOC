import ipaddress
import os
import time
from .db import connect, audit
from .routeros import RouterAPI


def target_for(cfg, incident):
    if incident['rule_key'] not in ('port_scan','brute_force','ssh_enumeration'):
        raise ValueError('Only alerts with a directly observed IPv4 source can be blocked.')
    address = ipaddress.IPv4Address(incident['source'])
    if address.is_loopback or address.is_multicast or address.is_unspecified or address.is_link_local or address.is_reserved:
        raise ValueError('This address cannot be blocked.')
    protected = list(cfg['protected_networks']) + [cfg['router_ip']+'/32',cfg['collector_ip']+'/32']
    if any(address in ipaddress.IPv4Network(n) for n in protected):
        raise ValueError('Protected router, collector or management address.')
    return str(address)


def preview(cfg, incident):
    address = target_for(cfg,incident)
    return {'target':address,'timeout':'1h','list':'MikroSOC-blocked',
            'command':f'/ip firewall address-list add list=MikroSOC-blocked address={address} timeout=1h comment="MikroSOC incident {incident["id"]}"',
            'note':'Requires the two enabled MikroSOC containment filter rules. Source blocks do not remove existing connection-tracking entries.'}


def execute(cfg, incident, user, action):
    address = target_for(cfg,incident)
    if action not in ('block','unblock'):
        raise ValueError('Unknown action')
    if not cfg['response_enabled'] or cfg['mode'] != 'live' or not cfg['api_tls']:
        raise ValueError('Live response is disabled. Follow the optional response setup guide.')
    password = os.environ.get('MIKROSOC_RESPONSE_PASSWORD')
    if not password:
        raise ValueError('MIKROSOC_RESPONSE_PASSWORD is missing.')
    comment = f'MikroSOC incident {incident["id"]}'
    with connect(cfg) as c:
        aid = c.execute('INSERT INTO response_actions(incident_id,user_id,created_at,action,target,status,detail) VALUES(?,?,?,?,?,?,?)',(incident['id'],user['id'],time.time(),action,address,'pending','Router outcome not yet known')).lastrowid
        audit(c,user['username'],'response_requested',f'{action} {address} incident={incident["id"]}')
    try:
        with RouterAPI(cfg,cfg['response_username'],password) as api:
            if action == 'block':
                rules = api.command('/ip/firewall/filter/print',**{'.proplist':'chain,action,src-address-list,disabled,comment'})
                chains = {r.get('chain') for r in rules if r.get('action') == 'drop' and r.get('src-address-list') == 'MikroSOC-blocked' and r.get('disabled') == 'false' and r.get('comment') in ('MikroSOC containment input','MikroSOC containment forward')}
                if not {'input','forward'} <= chains:
                    raise ValueError('Required containment rules are missing or disabled.')
                existing = api.command('/ip/firewall/address-list/print',queries=('?list=MikroSOC-blocked',f'?address={address}',f'?comment={comment}'))
                if not existing:
                    api.command('/ip/firewall/address-list/add',list='MikroSOC-blocked',address=address,timeout='1h',comment=comment)
            else:
                entries = api.command('/ip/firewall/address-list/print',queries=('?list=MikroSOC-blocked',f'?address={address}',f'?comment={comment}'))
                for item in entries:
                    api.command('/ip/firewall/address-list/remove',**{'.id':item['.id']})
        status, detail = 'completed', 'API acknowledged. Verify firewall order/counters and traffic; existing FastTrack connections may continue.'
    except Exception as exc:
        # A timeout can follow a successful router write: do not claim rollback.
        status, detail = 'needs_verification', type(exc).__name__ + ': inspect the router address list before retrying.'
    with connect(cfg) as c:
        c.execute('UPDATE response_actions SET status=?,detail=? WHERE id=?',(status,detail,aid))
        audit(c,user['username'],'response_result',f'action={aid} {status}')
    return {'id':aid,'status':status,'detail':detail}
