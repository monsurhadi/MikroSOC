'use strict';
// Synthetic fixtures and browser-only state. This file never makes a network request.
const Demo = (() => {
  const key='mikrosoc-showcase-v1';
  const now=()=>Date.now()/1000;
  const definitions=[
    ['port_scan','Possible port scan',12,60,'high',300,'192.0.2.77'],
    ['brute_force','Repeated login failures',5,120,'high',300,'192.0.2.78'],
    ['ssh_enumeration','Possible SSH username enumeration',4,120,'medium',300,'192.0.2.78'],
    ['new_device','New DHCP device',1,60,'medium',86400,'02:00:00:00:00:20'],
    ['exfiltration','Sustained WAN upload anomaly',10,300,'high',900,'ether1']
  ];
  function seed(){
    const t=now();
    const rules=definitions.map(([key,title,threshold,window_seconds,severity,cooldown_seconds])=>({key,title,threshold,window_seconds,severity,cooldown_seconds,enabled:true}));
    const alerts=definitions.map(([rule_key,title,threshold,window,severity,cooldown,source],i)=>({id:i+1,router_id:1,rule_key,title,severity,source,created_at:t-(5-i)*90,status:'open',evidence:JSON.stringify({synthetic:true,description:'Generated showcase example, not an observed attack.',threshold,window_seconds:window,source,limitation:rule_key==='exfiltration'?'Aggregate upload is not proof of stolen data.':'Investigation is required before drawing conclusions.'})}));
    const incidents=alerts.map(a=>({id:a.id,alert_id:a.id,title:a.title,severity:a.severity,source:a.source,rule_key:a.rule_key,evidence:a.evidence,stage:'detected',assignee:'',notes:'',updated_at:a.created_at}));
    const devices=['Monitoring PC','Lab laptop','Test phone','Guest tablet'].map((hostname,i)=>({id:i+1,hostname,ip:'192.0.2.'+(10+i),mac:'02:00:00:00:00:'+String(10+i),first_seen:t-86400,last_seen:t,trusted:i<2}));
    const logs=Array.from({length:145},(_,i)=>({id:145-i,received_at:t-i*8,kind:i%5===0?'ssh_failure':i%3===0?'connection':'other',src_ip:i%3===0?'192.0.2.77':null,message:i%5===0?'[DEMO] login failure for user test-user from 192.0.2.78 via ssh':i%3===0?'[DEMO] firewall TCP 192.0.2.77:45000->192.0.2.1:'+(8000+i):'[DEMO] system,info synthetic lab event '+(145-i)}));
    return {version:1,rules,alerts,incidents,devices,logs,response_actions:[],audit:[],created:t};
  }
  let state;
  try{const value=JSON.parse(localStorage.getItem(key));state=value?.version===1&&Array.isArray(value.incidents)&&Array.isArray(value.rules)?value:seed();}catch{state=seed();}
  function save(){try{localStorage.setItem(key,JSON.stringify(state));}catch{/* Private browsing or full storage: current-tab demo remains usable. */}}
  function record(action,detail){state.audit.unshift({id:state.audit.length+1,at:now(),actor:'Demo analyst',action,detail});state.audit=state.audit.slice(0,200);save();}
  function metrics(){const t=now();return Array.from({length:40},(_,i)=>({collected_at:t-(39-i)*60,cpu:Math.round(8+4*Math.sin(i*.7)),memory_percent:64,uptime:'2d03:15:00',rx_mbps:Number((4+2*Math.sin(i*.5)).toFixed(2)),tx_mbps:Number((i>32?12.5:1+.5*Math.sin(i*.8)).toFixed(2))}));}
  const clone=x=>JSON.parse(JSON.stringify(x));
  async function request(url,method='GET',data={}){
    const parsed=new URL(url,'https://demo.invalid');
    const path=parsed.pathname;
    if(path==='/api/session')return {csrf:'static-demo',user:{id:1,username:'Demo analyst',role:'admin'},mode:'demo',organization:'MikroSOC showcase'};
    if(path==='/api/overview'){
      const history=metrics(),metric={...history.at(-1),interfaces:JSON.stringify([{name:'ether1',running:'true',disabled:'false'},{name:'bridge',running:'true',disabled:'false'},{name:'wlan1',running:'true',disabled:'false'}])};
      return {router:{name:'RB941-2nD · simulated',ip:'192.0.2.1',status:'online',last_poll:now(),last_syslog:state.logs[0].received_at,error:'Synthetic telemetry. No router, syslog service or backend is connected.'},metric,history,counts:{logs:state.logs.length,devices:state.devices.length,open_alerts:state.alerts.filter(a=>a.status==='open').length,active_incidents:state.incidents.filter(i=>i.stage!=='closed').length},collector:{syslog:'simulated',accepted:state.logs.length,dropped:0},response_enabled:false};
    }
    if(path==='/api/logs'){
      const q=(parsed.searchParams.get('q')||'').toLowerCase(),before=Number(parsed.searchParams.get('before')||0);
      const items=state.logs.filter(l=>(!before||l.id<before)&&l.message.toLowerCase().includes(q)).slice(0,100);
      return clone({items,next_before:items.length===100?items.at(-1).id:null});
    }
    if(method==='GET'&&['alerts','incidents','devices','rules','response_actions','audit'].includes(path.slice(5)))return {items:clone(state[path.slice(5)])};
    let match=path.match(/^\/api\/alerts\/(\d+)\/ack$/);
    if(match&&method==='POST'){const a=state.alerts.find(a=>a.id===Number(match[1]));if(!a)throw Error('Alert not found');a.status='acknowledged';record('acknowledged_alert','Demo alert #'+a.id);return {ok:true};}
    match=path.match(/^\/api\/incidents\/(\d+)$/);
    if(match&&method==='POST'){
      const i=state.incidents.find(i=>i.id===Number(match[1]));if(!i)throw Error('Incident not found');
      if(!['detected','investigation','containment','recovery','lessons_learned','closed'].includes(data.stage))throw Error('Invalid stage');
      if(['closed','lessons_learned'].includes(data.stage)&&!data.notes.trim())throw Error('Add investigation notes before closing.');
      Object.assign(i,{stage:data.stage,notes:String(data.notes).slice(0,8000),assignee:String(data.assignee).slice(0,64),updated_at:now()});record('incident_updated','Demo incident #'+i.id+' → '+i.stage);return {ok:true};
    }
    match=path.match(/^\/api\/devices\/(\d+)\/trust$/);
    if(match&&method==='POST'){const d=state.devices.find(d=>d.id===Number(match[1]));if(!d)throw Error('Device not found');d.trusted=!!data.trusted;record('device_reviewed',d.hostname);return {ok:true};}
    match=path.match(/^\/api\/rules\/(\w+)$/);
    if(match&&method==='POST'){
      const r=state.rules.find(r=>r.key===match[1]);if(!r)throw Error('Rule not found');
      const threshold=Number(data.threshold),window_seconds=Number(data.window_seconds),cooldown_seconds=Number(data.cooldown_seconds);
      if(!Number.isFinite(threshold)||threshold<=0||threshold>100000||!Number.isInteger(window_seconds)||window_seconds<30||window_seconds>86400||!Number.isInteger(cooldown_seconds)||cooldown_seconds<30||cooldown_seconds>604800)throw Error('Invalid numeric rule settings.');
      if(r.key==='new_device'&&threshold!==1)throw Error('New-device threshold must remain 1.');
      Object.assign(r,{threshold,window_seconds,cooldown_seconds,severity:data.severity,enabled:!!data.enabled});record('rule_updated',r.title+' (simulation; existing fixtures are unchanged)');return {ok:true};
    }
    match=path.match(/^\/api\/incidents\/(\d+)\/response$/);
    if(match){
      const i=state.incidents.find(i=>i.id===Number(match[1]));if(!i||!['port_scan','brute_force','ssh_enumeration'].includes(i.rule_key))throw Error('No source-address response for this alert.');
      if(method==='GET')return {command:'SIMULATION ONLY — add '+i.source+' to MikroSOC-blocked for 1 hour',note:'No command will be sent. This creates a local demo audit record only.'};
      if(data.confirmation!=='CONFIRM '+i.id)throw Error('Type CONFIRM '+i.id+' to simulate this action.');
      if(!['block','unblock'].includes(data.action))throw Error('Unknown simulated action');
      state.response_actions.unshift({id:state.response_actions.length+1,incident_id:i.id,created_at:now(),action:data.action,target:i.source,status:'simulated',detail:'Browser-only simulation; no network effect.'});record('simulated_'+data.action,'Incident #'+i.id);return {status:'simulated',detail:'Demo action recorded. No router was contacted.'};
    }
    if(path.startsWith('/api/intelligence/'))return {ip:path.split('/').at(-1),scope:'documentation address',matches:[],note:'Synthetic documentation-range IP. No external lookup is made.'};
    throw Error('This operation is not part of the static showcase.');
  }
  function csv(kind){
    const allowed=['alerts','incidents','logs','devices','metrics'];if(!allowed.includes(kind))throw Error('Unknown report');
    const rows=kind==='metrics'?metrics():state[kind];
    const headers=Object.keys(rows[0]||{message:''});
    const cell=v=>{let s=String(v??'');if(/^[\s]*[=+@\-\t\r\n]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
    return '\ufeff'+[headers,...rows.map(r=>headers.map(h=>r[h]))].map(row=>row.map(cell).join(',')).join('\r\n');
  }
  function download(kind){const url=URL.createObjectURL(new Blob([csv(kind)],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='mikrosoc-DEMO-'+kind+'.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);record('demo_export',kind);}
  return {request,download,csv,reset(){state=seed();save();}};
})();
