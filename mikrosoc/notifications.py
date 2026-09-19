import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from .db import connect


def deliver(cfg):
    """Durable bounded retry queue. SMTP is at-least-once, never exactly-once."""
    now = time.time()
    with connect(cfg) as c:
        c.execute("INSERT OR IGNORE INTO notifications(alert_id,state) SELECT id,'pending' FROM alerts WHERE created_at>?",(now-86400,))
        pending = [dict(r) for r in c.execute("SELECT n.*,a.title,a.severity,a.source FROM notifications n JOIN alerts a ON a.id=n.alert_id WHERE n.state='pending' AND n.next_attempt<=? ORDER BY n.alert_id LIMIT 5",(now,))]
    for row in pending:
        try:
            msg = EmailMessage()
            msg['From'] = os.environ['MIKROSOC_SMTP_FROM']
            msg['To'] = os.environ['MIKROSOC_SMTP_TO']
            msg['Subject'] = f'MikroSOC {row["severity"]}: {row["title"]} (#{row["alert_id"]})'
            msg.set_content(f'Alert #{row["alert_id"]}\n{row["title"]}\nSource: {row["source"]}\nOpen your MikroSOC console to investigate. No automatic block was applied.\n')
            with smtplib.SMTP(os.environ['MIKROSOC_SMTP_HOST'],int(os.environ.get('MIKROSOC_SMTP_PORT','587')),timeout=10) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(os.environ['MIKROSOC_SMTP_USER'],os.environ['MIKROSOC_SMTP_PASSWORD'])
                smtp.send_message(msg)
            state,detail = 'sent','SMTP accepted'
        except Exception as exc:
            state = 'failed' if row['attempts']>=4 else 'pending'
            detail = type(exc).__name__
        with connect(cfg) as c:
            c.execute('UPDATE notifications SET state=?,attempts=attempts+1,next_attempt=?,detail=? WHERE alert_id=?',(state,now+min(3600,60*2**row['attempts']),detail,row['alert_id']))
