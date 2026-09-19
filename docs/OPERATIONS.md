# Operating MikroSOC

## Daily workflow

Open Overview and check the last API sample, last log arrival, listener state and drop count. A stale API sample or a stopped PC means a monitoring gap. Quiet syslog alone does not prove failure. Collector counters cover the current process lifetime; database counts survive restarts.

In Security alerts, acknowledge signals you have reviewed. Acknowledgement and incident closure are separate: one records alert review, the other records investigation completion. In Incidents, record evidence, owner, containment decision, recovery checks and lessons learned. Stages can be changed without rigid ordering for false positives and reopened investigations; later stages require notes. Every save records an audit event. The audit table is operational history, not tamper-proof storage.

## Detection defaults and interpretation

| Rule | Default trigger | Cooldown per source | Limitation |
| --- | --- | --- | --- |
| Port scan | At least 12 distinct destination ports from an IPv4 source in 60 s | 300 s | Received connection logs only; counts across destinations; legitimate service discovery can trigger |
| Brute force | At least 5 failed logins from an IPv4 source in 120 s | 300 s | Depends on RouterOS login-failure text and remote logging |
| SSH enumeration | At least 4 distinct usernames in failed SSH logins from a source in 120 s | 300 s | Username diversity heuristic, not proof of enumeration or SSH protocol exploitation |
| New device | A new MAC after initial DHCP baseline | 24 h | Bound DHCP leases only; static-IP clients and MAC changes have limitations |
| Exfiltration anomaly | WAN upload interval averages at or above 10 Mbps for about 300 s | 900 s | Aggregate WAN traffic; no host attribution, payload inspection or evidence of stolen content |

Threshold comparisons are inclusive (`>=`). Each alert creates one incident. Rule windows use collector receipt time for local syslog; raw RouterOS timestamps remain in the message. New-device window is descriptive; the rule triggers on first observation after baseline. Its threshold stays fixed at one. Trust labels document your review; they do not whitelist traffic or disable other detections.

Upload checks require samples spanning the configured window within one polling interval and reject large gaps or null counter intervals. Values are average Mbps since the previous poll, not instantaneous speed. Choose a window at least two poll intervals. Router reboot or decreased interface counters discard that interval; the next valid interval resumes calculation. A long gap resets rate history.

## Email alerts

Email is optional and disabled by default. Enabling it causes alerts from the preceding 24 hours to enter the delivery queue; start with a clean live database if you do not want recent existing alerts mailed. Use a provider/account you control and a recipient who should receive router metadata.

Add `"smtp_enabled": true` to config, then set these process environment variables before launching:

| Variable | Meaning |
| --- | --- |
| `MIKROSOC_SMTP_HOST` | Your authenticated SMTP server |
| `MIKROSOC_SMTP_PORT` | STARTTLS submission port, usually 587 |
| `MIKROSOC_SMTP_USER` | SMTP account username |
| `MIKROSOC_SMTP_PASSWORD` | SMTP/app password; read with a secure prompt |
| `MIKROSOC_SMTP_FROM` | Authorized sender email |
| `MIKROSOC_SMTP_TO` | Intended recipient email |

The sender requires authenticated STARTTLS and verifies TLS certificates. Implicit TLS port 465 is not implemented. The worker processes at most five messages every 30 seconds and makes at most five attempts per alert with backoff. A successful SMTP acknowledgement records `sent`; delivery to an inbox is outside the app's control. A crash after SMTP accepted but before DB commit can produce a duplicate email. This is at-least-once delivery.

Inspect status locally:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('data/live.sqlite3'); print(c.execute('select alert_id,state,attempts,detail from notifications order by alert_id desc limit 20').fetchall())"
```

For cloud SMTP, the template's egress permits only HTTPS 443. Keep cloud email disabled unless you explicitly add an egress rule for your approved mail server and verify provider/account restrictions. Prefer local email for this lab. No real email has been sent during the build.

## Offline IP intelligence

The project can enrich a directly observed IPv4 source against a local CSV. This avoids recurring lookup costs and avoids automatically disclosing addresses to third parties. It does not include a commercial geolocation database or reputation feed.

Create `data/intelligence.csv` with these exact column names:

```csv
cidr,country,asn,label,reputation,source,updated
192.168.88.0/24,,,Home lab,trusted,local inventory,2026-09-18
203.0.113.0/24,,,Documentation example,unknown,example only,2026-09-18
```

Use data you are licensed to use, valid IPv4/IPv6 CIDRs, country/ASN fields supplied by that dataset, and source/date metadata. The example is not real threat intelligence. The endpoint `GET /api/intelligence/<address>` is available to authenticated users, and source-bearing incidents include an intelligence lookup button. Matching records are informative and do not trigger automatic blocks. Maximum CSV size is 5 MB; at most 20 matches are returned.

For an external GeoIP/ASN API, add a deliberately configured provider later, with caching, limits and consent to send IPs. No API key is required for the included offline path.

## Storage and security boundaries

Raw logs default to 14 days and 100,000 rows; metrics default to 14 days and 25,000 rows. Cleanup runs every minute, so small temporary overshoot is possible. SQLite may retain allocated disk space after rows are deleted. Alert/incident/response/audit/device history is intentionally retained and can grow; back up and archive it deliberately. Run a stopped-database maintenance/VACUUM procedure only after making a backup if disk size matters.

Passwords are hashed with Werkzeug's password hashing. Session cookies are signed, HTTP-only and SameSite Strict. All browser writes require a CSRF token. The web app accepts loopback hosts only; it is not configured as a public HTTPS SaaS service. Role checks are server-side. Viewer can read/export; analyst can acknowledge/investigate/label devices; admin can additionally manage users/rules and explicitly execute router response.

The operating-system account controls the database, session key and secrets; protect that account and the `data/` folder. The session key persists in `data/.session-key`. To invalidate all sessions after compromise, stop the server, replace that file with a newly generated random key, then restart. Changing a password signs out that browser but does not revoke every previously issued signed session; disabling an account is checked on each request and blocks its sessions immediately.

Syslog UDP is plaintext and unauthenticated. The allowed source IP and Windows firewall reduce exposure but do not cryptographically authenticate a router. Keep it on a trusted LAN. An attacker with local network spoofing access could inject logs; investigate evidence before blocking. Do not send raw UDP syslog over the public Internet.

## Additional routers

One instance maps telemetry to one router. To monitor a second router today, duplicate the project configuration, use separate databases, web ports, syslog ports, credentials and cloud instances/tokens as appropriate. Do not point two routers at one current listener: the nonconfigured source is rejected. A shared multi-router UI and tenant isolation require a future data-access/collector redesign, not just an extra row in the database.
