# Two-phase development and learning roadmap

The implementation of both phases is included. Use this order to learn, demonstrate and validate it incrementally rather than enabling everything on the router at once.

## Phase 1 Network monitoring

| Step | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Install Python and open VS Code; run demo | Login and NOC charts load |
| 2 | Record router version, LAN/WAN interfaces and PC IP; take backups | Private backup and network worksheet |
| 3 | Configure LAN syslog and live database | One harmless router message appears locally |
| 4 | Create read-only API account and verified TLS | Doctor succeeds; CPU, memory and DHCP inventory appear |
| 5 | Verify WAN rate calculation | Two samples and a graph that changes during normal traffic |
| 6 | Create viewer account and export reports | Role restrictions and CSV inspection |
| 7 optional | Deploy AWS and start SSM relay | Same test log reaches cloud with zero EC2 ingress rules |

Suggested learning pace: weeks 1–4 locally, weeks 5–6 for optional AWS. These are learning estimates, not requirements to delay using the delivered code.

## Phase 2 SOC operations

| Step | Work | Acceptance evidence |
| --- | --- | --- |
| 1 | Review all five demo detections | Explain trigger, evidence and false-positive limits |
| 2 | Enable limited firewall observation | Relevant real logs arrive without excessive router CPU |
| 3 | Tune thresholds to normal network activity | Document baseline and chosen thresholds |
| 4 | Practice incident workflow | Investigation, owner, recovery and lessons-learned notes |
| 5 optional | Configure SMTP and local CIDR intelligence | Intended test recipient receives one alert; enrichment has provenance |
| 6 optional | Configure protected addresses and manual containment | One intended lab target blocked/unblocked; management remains accessible |
| 7 | Practice backup and restore | Restore into a separate database and inspect records |

Suggested learning pace: weeks 7–10 for investigation and detection; weeks 11–12 for response, documentation and a portfolio demonstration.

## Demonstrating the project honestly

Record a short demo showing the real router's health, one real syslog message, DHCP inventory, a synthetic detection scenario, the incident workflow and a CSV export. Label synthetic records visibly. If you deploy AWS, add the architecture, zero-ingress security group, relay retry test and teardown evidence. Do not claim a deployed cloud service, confirmed intrusion detection or hardware testing before you have actually completed those checks.

Future work: shared multi-router administration, SNMPv3 polling, durable broker-backed collection, MFA/SSO, externally protected audit storage, IPv6 firewall parsing and provider-specific threat-intelligence connectors.
