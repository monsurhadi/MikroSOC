# Set up MikroSOC in VS Code and on your RB941-2nD

This guide uses Windows PowerShell, Python 3.12 and a physical MikroTik router. Start with the demo, confirm your actual network addresses, then connect the router. The software runs on your PC. Nothing is installed into the router's flash other than the configuration changes and certificates you choose to make.

The RouterOS version and current configuration were not supplied. The code targets RouterOS 6.43+ and 7 binary API login and common commands; the physical integration must be verified on your device. Prefer a currently supported stable release suitable for the SMIPS model. Do not reset or upgrade the router merely to run the demo.

## 1 Prepare the PC

1. Extract `MikroSOC.zip` into a folder you own, for example `C:\Projects\MikroSOC`. Do not run it inside the ZIP preview.
2. Install VS Code from <https://code.visualstudio.com/> and Python 3.12 from <https://www.python.org/downloads/>. Enable the Python launcher during installation.
3. Open VS Code, select **File → Open Folder**, and choose the extracted folder containing `manage.py`.
4. Install Microsoft's **Python** and **Python Debugger** extensions when VS Code recommends them.
5. Open **Terminal → New Terminal** and select PowerShell. Check the prompt points to your project folder.
6. Run:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expected: Python 3.12 and a successful Flask/Waitress installation. If `py` is not found, reopen VS Code after installing Python. Use the full path to your Python installation if necessary.

7. Press **Ctrl+Shift+P → Python: Select Interpreter** and select `.venv\Scripts\python.exe`.

All commands below use the venv interpreter directly. You do not need to activate the venv or change PowerShell's execution policy to complete the setup.

## 2 Run the demo first

```powershell
.\.venv\Scripts\python.exe manage.py init
```

This creates `config.json`, a demo SQLite database and an administrator. Choose a username and password of at least 12 characters. Password input is hidden. Do not use your router password for the web administrator.

```powershell
.\.venv\Scripts\python.exe manage.py demo
.\.venv\Scripts\python.exe manage.py run
```

Open <http://127.0.0.1:8000>. You should see a **DEMO** banner, traffic history, two example devices and five example alerts/incidents. These are synthetic, not detections from your home network. Open each sidebar page. Open an incident, add a note, assign it and save a stage change.

To check the UDP listener without a router, open another VS Code terminal:

```powershell
.\.venv\Scripts\python.exe scripts\send_test_syslog.py
```

Look for `MikroSOC loopback connectivity test` in **Live logs**. Stop the server with **Ctrl+C** before changing mode or ports. `demo` is intentionally a one-time seed per demo database; running it twice reports that it has already been loaded.

## 3 Connect the physical router and discover its settings

1. Power the RB941-2nD using its proper supply.
2. Connect the PC by Ethernet to a LAN port. With an unchanged factory configuration this is normally ether2, ether3 or ether4; ether1 is commonly WAN. If the router was reconfigured, inspect the port/bridge configuration first.
3. Download WinBox from <https://mikrotik.com/download>. Use its **Neighbors** tab or your known router IP to connect. Use your existing router credentials; this guide does not assume a blank password.
4. In a **WinBox → New Terminal**, run these read-only commands:

```routeros
/system resource print
/system package print
/ip address print
/interface print
/interface bridge port print
/ip dhcp-server lease print
/ip service print detail
/ip firewall filter print detail
```

Record the RouterOS version, router LAN address, LAN bridge, WAN interface, enabled API services, and existing firewall rule order. The WAN interface might be `pppoe-out1` rather than `ether1`; choose the interface that actually carries Internet traffic.

5. In Windows PowerShell, run:

```powershell
ipconfig
```

Record the Ethernet IPv4 address and default gateway. In the rest of this guide:

| Meaning | Example only |
| --- | --- |
| Router LAN address | `192.168.88.1` |
| Monitoring PC address | `192.168.88.10` |
| LAN network | `192.168.88.0/24` |
| WAN interface | `ether1` |
| Web page | `127.0.0.1:8000` |
| Router → PC syslog | UDP `5514` |
| PC → router API TLS | TCP `8729` |

**Replace all example network values with your real ones.** Reserve the PC's current DHCP lease in **IP → DHCP Server → Leases → Make Static** so its address does not change. Use the existing lease rather than choosing an arbitrary address that could conflict with another device.

## 4 Make a router backup before changing configuration

In WinBox **Files**, use **Backup**, provide a strong backup password, and download the backup to a private folder on your PC. Also create a text export:

```routeros
/export file=before-mikrosoc
```

Download `before-mikrosoc.rsc` from **Files**. Treat both files as sensitive. Record the full original `api-ssl` settings separately so you can restore them. If the router already uses remote logging or API TLS for another application, integrate the project without overwriting that service's existing access list or certificate.

Use **Safe Mode** in WinBox for firewall edits. Keep the Ethernet management session open. In Safe Mode, an unexpected session loss can roll back changes; after successful verification, leave Safe Mode normally to keep them. Do not paste every `.rsc` file at once.

## 5 Configure live mode and the Windows firewall

Stop MikroSOC. Edit these fields in `config.json`; leave other fields in place:

```json
{
  "mode": "live",
  "database": "data/live.sqlite3",
  "syslog_host": "192.168.88.10",
  "router_ip": "192.168.88.1",
  "collector_ip": "192.168.88.10",
  "api_enabled": false,
  "wan_interface": "ether1",
  "response_enabled": false,
  "protected_networks": ["192.168.88.1/32", "192.168.88.10/32"]
}
```

This is a **partial example**, not a replacement for the whole file. JSON does not support comments or trailing commas. Add the IPs of any other administrative PCs, gateways and infrastructure that must never be blocked to `protected_networks`.

Initialize the separate live database:

```powershell
.\.venv\Scripts\python.exe manage.py init
```

The live database has its own login accounts. Reusing the demo database in live mode is rejected deliberately.

On your trusted home/lab Ethernet connection, select the Windows **Private** network profile in Settings. Open a separate **PowerShell as Administrator** and add a narrowly scoped rule, replacing the router IP:

```powershell
New-NetFirewallRule -DisplayName 'MikroSOC syslog from router' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 5514 -RemoteAddress 192.168.88.1 -Profile Private
```

Do not create a port-forward on the router, open TCP 8000 to the Internet, or enable this inbound rule for unrelated networks. The app UI is loopback only. If a rule with this name already exists, inspect it instead of repeatedly creating duplicates.

Start the app:

```powershell
.\.venv\Scripts\python.exe manage.py run
```

## 6 Forward router syslog to your PC

Review `router/01-syslog.rsc`. Replace the example PC and router addresses. In the WinBox terminal, run each line once. The essential action is:

```routeros
/system logging action add name=mikrosoc target=remote remote=192.168.88.10 remote-port=5514 src-address=192.168.88.1
```

Then add the topic rules from that file. Existing memory logging remains in place. No persistent disk logging is enabled, helping avoid unnecessary flash writes on this small router.

Send the included harmless test:

```routeros
:log info "MikroSOC syslog connection test"
```

In MikroSOC **Live logs**, search for `MikroSOC`. If the script-topic test is not emitted under the expected topic on your version, inspect `/log print` for its actual topic and temporarily add a matching remote rule, then remove that temporary rule after testing. Do not broaden all logging permanently.

Expected: a message with the current PC receipt time and an advancing **Last received log**. UDP has no delivery acknowledgement. A successful router command alone does not verify delivery.

If nothing appears: check PC IP, Windows profile/firewall, router logging action address/port, the app's listener status and `src-address`. Live mode only accepts UDP from `router_ip`. A test sent from `127.0.0.1` is deliberately rejected in live mode.

At this stage logs work without an API account. CPU/bandwidth/devices remain empty until the next section is complete.

## 7 Enable a verified read-only API connection

This is the recommended path. It uses API TLS on 8729 and verifies the router's certificate. Generating/signing certificates can temporarily load the RB941 CPU; perform one command at a time and allow it to finish.

1. Check **System → Clock**. Correct time on both the router and PC is needed for certificates. Use your existing NTP configuration if available.
2. In WinBox **System → Users → Groups**, add `mikrosoc-read` with only `read` and `api`. The command is:

```routeros
/user group add name=mikrosoc-read policy=read,api
```

3. In **System → Users**, add `mikrosoc-reader` in that group, set a strong unique password and set **Allowed Address** to your monitoring PC's address `/32`. Enter the password in the dialog rather than copying it into a shared script.
4. Review `router/02-api-tls.rsc`, adjusting the router IP in both `common-name` and `subject-alt-name`, and the PC IP in the service access list. Create and sign the CA and server certificate using those commands. Certificate names must be unique; skip creation of groups you already created.
5. Set the API SSL service's certificate and restrict it to the PC. Example:

```routeros
/ip service set api-ssl disabled=no port=8729 certificate=mikrosoc-api address=192.168.88.10/32 tls-version=only-1.2
```

If other legitimate clients already use API TLS, preserve their access and coordinate the certificate change rather than blindly replacing the service configuration.

6. Export the **public CA certificate**, download it from WinBox Files, and save it as `certs/mikrosoc-ca.crt`. Do not export a private key.
7. If an existing router input firewall blocks LAN API access, add an accept rule for **only** TCP 8729 from the PC `/32`, scoped to the actual LAN ingress interface. In WinBox, place it before the relevant drop rule. Do not alter WAN accept policies. Example after confirming the LAN interface is `bridge`:

```routeros
/ip firewall filter add chain=input action=accept protocol=tcp dst-port=8729 src-address=192.168.88.10/32 in-interface=bridge comment="MikroSOC API from PC"
```

Move this named rule as needed in WinBox. An appended rule after a drop will not work. Many default LAN configurations already permit the connection, so do not add it unnecessarily.

8. In `config.json`, set:

```json
"api_enabled": true,
"api_port": 8729,
"api_tls": true,
"api_ca_file": "certs/mikrosoc-ca.crt",
"api_username": "mikrosoc-reader",
"allow_insecure_api": false,
"poll_seconds": 60
```

9. Stop MikroSOC. In the normal VS Code PowerShell terminal, read the router password without displaying it or putting it literally in history:

```powershell
$routerSecret = Read-Host 'Router reader password' -AsSecureString
$env:MIKROSOC_ROUTER_PASSWORD = [System.Net.NetworkCredential]::new('', $routerSecret).Password
.\.venv\Scripts\python.exe manage.py doctor
```

Expected: **Read-only API polling succeeded**. `doctor` polls once, stores a sample and establishes the initial DHCP baseline. It does not start the continuous listener.

10. From that **same terminal**, run:

```powershell
.\.venv\Scripts\python.exe manage.py run
```

Keep the terminal open. The password exists only in this terminal process and its children; a different terminal or F5 debugger may not inherit it. `scripts/start.ps1` offers the same prompt-and-run convenience where your PowerShell policy permits local scripts.

Expected: CPU/memory/uptime and bound DHCP leases on the first poll. Bandwidth needs two successful polls roughly 60 seconds apart. Initial inventory creates a baseline without new-device alerts. A later newly observed MAC creates an alert. A static-IP device without a DHCP lease may not appear.

After stopping, clear credentials or close the terminal:

```powershell
Remove-Item Env:\MIKROSOC_ROUTER_PASSWORD -ErrorAction SilentlyContinue
```

### Isolated lab alternative when TLS is not ready

For an isolated wired lab only, you can use API 8728 with a dedicated read-only account and restrict `/ip service api address` and the input firewall to the PC `/32`. Set `api_tls` to `false`, `api_port` to `8728` and `allow_insecure_api` to `true` explicitly. Router API passwords are unencrypted on this connection. Keep response disabled. Restore/disable this service when the temporary lab test ends. TLS remains the recommended setup; the code does not silently bypass certificate verification.

## 8 Enable limited firewall observation

RouterOS does not automatically log every connection. For scan visibility, review `router/03-firewall-observation.rsc` and add its two observation rules once. They log TCP SYN packets for new connections in `input` and `forward`, with a 10 packets/second matcher and a burst allowance of 20 per rule.

In WinBox **IP → Firewall → Filter Rules**, move the observation rules before the accept/drop rules they need to observe. `action=log` continues to subsequent rules, so the observation rule itself does not authorize traffic. The original policy still decides accept/drop.

Check `/system resource print` and responsiveness. If CPU or log volume rises too much, disable the observation rules or lower sampling. The default port-scan threshold is 12 distinct destination ports from a source over 60 seconds. Burst sampling can hide ports, so this is a heuristic rather than comprehensive IDS coverage. It does not observe traffic switched entirely within a bridge by hardware or arbitrary IPv6 flows.

## 9 Verify each feature without running an attack

1. **NOC:** compare CPU/memory and uptime to WinBox; transfer a normal file or browse from a lab device, then wait two polls for WAN traffic to change.
2. **Logs:** repeat the single harmless `:log info` test and inspect its arrival.
3. **New device:** after the initial DHCP baseline, connect a device you own that was not previously in the inventory. Wait one poll, then inspect its alert and mark it trusted if appropriate.
4. **Detection rules:** use the isolated demo database to inspect scan, brute-force, SSH and upload examples. Do not attack your router to prove a UI works.
5. **Incidents:** assign an incident, document evidence, set investigation/recovery/lessons-learned and close. Record why an alert was a false positive when appropriate.
6. **Roles:** as admin create a viewer; sign out and sign in as viewer. It should read/export but not change rules, users or incidents.
7. **Reports:** download logs/alerts/incidents CSVs and verify contents. Export times use UTC Unix seconds; UI times are local to the browser.

## 10 Optional manual router containment

Skip this section until monitoring and backups work. This feature blocks a source address only when you explicitly confirm it in the web UI; detections never automatically block traffic.

1. Add your router, collector, management PCs, DNS servers and gateways to `protected_networks` as exact `/32` addresses or appropriate protected prefixes. Do not protect the entire client subnet if you later want to block a test client in that subnet.
2. Review `router/04-optional-containment.rsc`. It creates two **disabled** drop rules referencing `MikroSOC-blocked`, one in input and one in forward.
3. In Safe Mode, place the two rules above FastTrack and established/related/other accept rules. Review existing policies. Enable the two named rules only when the list is empty and management access is protected. Confirm normal access still works before leaving Safe Mode.
4. Create `mikrosoc-responder` with group `mikrosoc-response`, allowed address equal to the PC `/32` and a strong unique password. RouterOS's `write` permission is broad; use a separate account from the reader.
5. Require TLS. Set `response_enabled` to `true` in the **local PC's** configuration. Read the responder password into `MIKROSOC_RESPONSE_PASSWORD` using the same secure prompt method as the reader.
6. Restart MikroSOC. In an incident whose evidence has a source IPv4 address, select **Preview router containment**. Inspect the target, one-hour timeout and exact operation. Type `CONFIRM <incident ID>` and choose **Apply one-hour block** only for a device you intend to block.
7. Check WinBox **IP → Firewall → Address Lists**, filter counters and actual traffic from that source. An API acknowledgement is not proof that all traffic is stopped: established FastTrack sessions may continue until they expire. The app does not flush connection tracking.
8. **Remove this incident's block** removes only entries bearing this incident's comment. Another block for the same address can remain. Entries also expire after one hour. If the response status is `needs_verification`, inspect the router before retrying; a lost reply may follow a successful change.

Upload-anomaly and DHCP alerts cannot be blocked through this action because they lack the same directly observed source evidence. Protected-address checks are enforced on the server, not just in the browser. The cloud copy should keep response disabled; perform router actions from the local PC.

## 11 Daily startup, troubleshooting and recovery

Start the PC, connect to the LAN, open the project, read the router password into the terminal environment, then run `manage.py run`. Keep the PC awake for continuous collection. While it sleeps or is shut down, syslog is lost and there is no monitoring.

| Symptom | Check |
| --- | --- |
| Browser cannot connect | Server terminal is running; URL is HTTP and port matches config; another instance is not using the port |
| WinError 10049 | `syslog_host` must be an address actually assigned to this PC; check `ipconfig` |
| Address already in use | Stop the other MikroSOC instance or change its web/syslog ports |
| No syslog | Router remote action, source IP, PC firewall profile and UDP 5514; no WAN forwarding needed |
| Certificate verification fails | PC/router clock, exported CA file, server certificate signed by that CA, subject-alt-name IP matches `router_ip` |
| API connection refused/timed out | `/ip service`, port, reader allowed address and input firewall rule order |
| API login denied | Reader password/group (`read,api`); password environment variable set in the launching terminal |
| WAN counters missing | `wan_interface` matches `/interface print`; choose the real WAN/PPPoE interface |
| Device missing | Device has a currently bound DHCP lease; static-IP clients are outside this inventory source |
| No bandwidth after start | Wait two successful polls; first sample has no previous counter to compare |
| Alerts absent | Required logging is enabled, thresholds are reached, rule enabled, cooldown has elapsed |
| Alerts repeat | Check duplicate remote topic rules and duplicate collectors; review cooldowns |
| Memory/CPU high on router | Increase poll interval to 120 seconds, reduce logging, keep disk logging disabled |
| Forgotten UI password | Stop server, run `manage.py reset-password <username>`, restart |

Back up the database consistently:

```powershell
.\.venv\Scripts\python.exe manage.py backup data\backup-2026-09-18.sqlite3
```

Use a fresh filename each time. To restore, stop MikroSOC, copy your chosen backup to a **new** SQLite filename, update `database` in config to that file, and restart. Preserve the matching mode and router IP. Back up configuration and certificates separately; router credentials are not in the database. A backed-up database contains account password hashes and network evidence, so keep it private.

To remove the integration, review `router/05-rollback.rsc`, disable/remove only project rules and logging actions, restore recorded API service settings, and remove the extra `MikroSOC API from PC` firewall rule if you created it. Remove the Windows firewall rule:

```powershell
Remove-NetFirewallRule -DisplayName 'MikroSOC syslog from router'
```

Do not factory-reset the router as a cleanup step. Use the backup for recovery only when necessary and appropriate for that router/version.

Continue to [AWS.md](docs/AWS.md) only after the local physical-router checks pass. Email, enrichment and maintenance are in [OPERATIONS.md](docs/OPERATIONS.md).
