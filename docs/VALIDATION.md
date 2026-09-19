# Validation and acceptance

## Verified during the build

- Automated Python behavioral tests: parsing, rule thresholds, time windows, source isolation, cooldown/deduplication, DHCP baseline, upload continuity, counter resets, protected-address response and disabled-response gate.
- Login, CSRF, host restrictions, viewer permissions, incident updates, audit records, rule validation and spreadsheet formula escaping in CSV exports.
- Real local UDP socket ingestion and rejection of a nonconfigured peer.
- RouterOS framing boundaries and login/resource exchange against a mock TCP router.
- Authenticated cloud ingestion, transactional deduplication and offline intelligence lookup.
- SMTP queue delivery using a mocked STARTTLS server and manual containment using a mocked RouterOS API.
- Browser login, overview rendering and incident interface using synthetic data; Python and JavaScript syntax checks.

Run the included suite yourself:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Not verified on external systems

- Physical RB941-2nD connection, its installed RouterOS release, certificate commands, API property availability and existing firewall order.
- Real router containment, packet-flow effects, FastTrack behavior and access recovery.
- AWS provisioning, account-specific permissions/credits, service deployment and an actual Session Manager relay session.
- SMTP provider/inbox delivery and third-party intelligence data quality.

Terraform files are deployment inputs, not proof of deployed resources. Terraform/provider validation must be run during setup; the Terraform CLI was not available in the build environment. No router changes, AWS creation, real SMTP messages or GitHub publishing occurred during the build.

## Before relying on monitoring

Complete SETUP.md's physical acceptance steps, preserve a private router backup, confirm one log and two metric samples, and practice database restore. Test optional response only on an intended lab source with management access protected. Record your RouterOS version, actual interface names, setup date and results alongside your own project notes.

## Known boundaries

One router/organization per instance; no SNMP collector, IPv6 firewall parser, deep packet inspection, external GeoIP API, multi-tenant authorization, MFA or high availability. DHCP inventory is not a full network scanner. Logs are limited and sampled. Upload anomalies cannot identify stolen data or the originating host. Local syslog is unauthenticated UDP. Cloud delivery is bounded by local retention and seven-day acceptance; replayed historical windows may differ from the original real-time detections. Signed sessions are checked for active users but are not a full centrally revocable session store.
