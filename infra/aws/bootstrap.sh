#!/bin/bash
set -euo pipefail
dnf install -y python3 python3-pip unzip amazon-cloudwatch-agent
id mikrosoc >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/mikrosoc --shell /sbin/nologin mikrosoc
install -d -o mikrosoc -g mikrosoc -m 750 /opt/mikrosoc/app /var/log/mikrosoc
systemctl enable --now amazon-ssm-agent
