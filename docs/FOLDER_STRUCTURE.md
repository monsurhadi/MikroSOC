# Folder structure

```text
MikroSOC/
├── README.md                   Project overview and feature status
├── SETUP.md                    Windows VS Code and physical-router setup
├── requirements.txt            Runtime dependencies
├── manage.py                   Initialize, run, diagnose, backup and recover accounts
├── config.example.json         Safe demo configuration
├── .vscode/                    Python debugger and extension recommendations
├── mikrosoc/
│   ├── config.py               Configuration validation
│   ├── db.py                   SQL schema, connections, audit and retention
│   ├── routeros.py             RouterOS binary API and TLS client
│   ├── collector.py            UDP listener, polling and background workers
│   ├── detection.py            Parser, five rule types and alert creation
│   ├── response.py             Validated manual containment operations
│   ├── web.py                  Authentication, role checks and HTTP API
│   ├── cloud.py                Authenticated deduplicated relay ingestion
│   ├── intel.py                Offline CIDR enrichment
│   ├── notifications.py        Optional SMTP retry queue
│   ├── demo.py                 Synthetic observations
│   └── static/                 HTML, CSS, JavaScript and SVG chart rendering
├── router/                     Reviewed, opt-in RouterOS command templates
├── certs/                      Public router CA certificate destination
├── scripts/                    Startup helper, test syslog and cloud relay
├── infra/aws/                  Terraform, bootstrap, systemd and CloudWatch config
├── tests/                      Behavioral and integration tests
└── docs/                       Design, operations, roadmap and AWS instructions
```

`config.json`, `.venv/`, SQLite databases, session keys and certificates are created locally during setup. They are intentionally excluded from the release and Git. The ZIP has no saved administrator password, router credential, cloud key or user network log.
