# Optional AWS deployment

Complete the local physical-router setup first. This deployment keeps the router integration on the Windows PC and sends telemetry to one EC2 instance through AWS Systems Manager Session Manager. Your RB941 does not need a public IP, inbound port-forward or VPN package. The monitoring PC must remain running.

The Terraform files create infrastructure only. The installation steps below deploy the app. This package has not been applied to an AWS account, and the cloud path needs acceptance testing in your account.

## Cost before you start

AWS Free Tier is not a perpetual free-server guarantee. The current new-account offering uses credits and a time-limited Free plan; older accounts and Paid plans have different rules. Confirm **Billing → Free Tier**, your account plan, service availability and remaining credits. Consult <https://aws.amazon.com/free/> and the AWS Pricing Calculator for your region.

This template uses one `t3.micro`, a 12 GiB encrypted gp3 disk, a public IPv4 address for outbound connectivity, a private S3 bucket and a seven-day CloudWatch log group. EC2 compute, disk, public IPv4, logs, S3 requests/storage and egress can cost money. No NAT gateway, load balancer, RDS, OpenSearch or Elastic IP is created. Standard CPU credits prevent unlimited burst-credit charges. Stopping EC2 does not remove its disk, S3 objects or CloudWatch logs.

Create a small AWS Budget and billing alerts before applying the template. A budget alert is notification, not a hard spending cap. If you need guaranteed no cloud charges, use the local edition and do not apply Terraform.

## 1 Install local deployment tools

Install AWS CLI v2, the AWS Session Manager plugin, and Terraform from their official sites. Authenticate with an IAM Identity Center/SSO profile or other approved administrative identity; do not use root access keys.

```powershell
aws --version
terraform version
aws sts get-caller-identity
```

Your deployment identity needs permissions to create/manage the resources in `infra/aws/main.tf`, including passing the instance role. The template supplies the instance role; it does not grant permissions to your human IAM identity. Your operator must also be allowed `ssm:StartSession`, `ssm:ResumeSession`, `ssm:TerminateSession` and use of the `AWS-StartPortForwardingSession` document for this instance. SSO sessions expire; renew them when needed.

## 2 Review and create infrastructure

From the project folder:

```powershell
Set-Location infra\aws
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`: choose a region you can use, keep a compatible x86 instance type, and set a globally unique bucket name. Example region is `ap-south-1`; it is a configurable example, not an inferred preference.

```powershell
terraform init
terraform fmt -check
terraform validate
terraform plan -out=mikrosoc.tfplan
```

Read the plan and cost implications. It should show no ingress rules, no NAT gateway, no database service and no load balancer. When ready to create those resources:

```powershell
terraform apply mikrosoc.tfplan
terraform output
```

Record `instance_id` and `bucket_name`. Keep Terraform state private and backed up; it is needed for later management and teardown. Retain the provider lock file created by `terraform init` in your repository; do not commit state or personal variable files.

## 3 Upload the clean project release

The delivered ZIP contains a top-level `MikroSOC/` directory. Upload that **clean release ZIP**, not your configured working folder containing `config.json`, certificates, secrets or databases. From a terminal, using your real release path/bucket/region:

```powershell
aws s3 cp C:\Downloads\MikroSOC.zip s3://YOUR-BUCKET/releases/MikroSOC.zip --region YOUR-REGION
```

The human deployment identity needs S3 write permission for this upload. The EC2 role can only read `releases/`, read/write `backups/`, send app logs to its log group and connect to SSM.

## 4 Install the app on EC2

In AWS console, select the instance → **Connect → Session Manager → Connect**. If unavailable, wait for bootstrap and check its IAM instance profile, SSM agent, outbound HTTPS and Internet route. There is intentionally no SSH ingress.

In the EC2 shell, replace the bucket and region:

```bash
sudo cloud-init status --wait
sudo aws s3 cp s3://YOUR-BUCKET/releases/MikroSOC.zip /tmp/MikroSOC.zip --region YOUR-REGION
sudo unzip -q /tmp/MikroSOC.zip -d /tmp/mikrosoc-release
sudo cp -a /tmp/mikrosoc-release/MikroSOC/. /opt/mikrosoc/app/
sudo chown -R mikrosoc:mikrosoc /opt/mikrosoc/app
cd /opt/mikrosoc/app
sudo -u mikrosoc python3 -m venv .venv
sudo -u mikrosoc .venv/bin/python -m pip install -r requirements.txt
sudo -u mikrosoc cp config.example.json config.json
sudo -u mikrosoc mkdir -p data
sudo nano config.json
```

The template selects Amazon Linux 2023. Its system Python may differ from the local 3.12 interpreter; this project requires Python 3.9 or newer. If bootstrap failed, inspect `/var/log/cloud-init-output.log` before continuing.

Edit the cloud copy of `config.json`:

- `mode`: `live`
- `database`: `data/cloud.sqlite3`
- `organization`: a clear name such as `My MikroSOC Cloud Lab`
- `router_ip`: the real **home router LAN IP**, matching the local configuration; it identifies the relay's router, not an EC2-reachable address.
- `collector_ip`: the real **home PC IP**, kept as a protected address.
- `web_host`: `127.0.0.1`, `web_port`: `8000`
- `syslog_host`: `127.0.0.1`, `syslog_port`: `5514` (unused in relay mode)
- `api_enabled`: `false`
- `response_enabled`: `false`
- add `cloud_ingest_enabled`: `true`
- `poll_seconds` and `wan_interface`: match the local PC configuration.

Do not copy router reader/responder credentials to EC2. The cloud host never needs to reach the router.

```bash
sudo -u mikrosoc .venv/bin/python manage.py init
```

Create a cloud dashboard administrator. This is independent of the local dashboard account.

## 5 Configure the relay token and service

Generate a long random relay token on a trusted machine using a password manager or Python's `secrets` module. Store it privately. Enter the **same token** on the cloud host and the local relay. Do not commit it or paste it into a public issue.

```bash
sudo install -m 600 /dev/null /etc/mikrosoc.env
sudo nano /etc/mikrosoc.env
```

File contents, replacing the placeholder with your own token of at least 32 characters:

```ini
MIKROSOC_INGEST_TOKEN=YOUR_RANDOM_SECRET_TOKEN
```

This file is root-readable only. Systemd reads it before starting the service as the restricted `mikrosoc` user.

```bash
sudo cp infra/aws/mikrosoc.service /etc/systemd/system/mikrosoc.service
sudo cp infra/aws/mikrosoc.logrotate /etc/logrotate.d/mikrosoc
sudo systemctl daemon-reload
sudo systemctl enable --now mikrosoc
sudo systemctl status mikrosoc --no-pager
```

Expected: active/running. Inspect `/var/log/mikrosoc/app.log` if it fails. Do not run a second app process using the same database/ports.

## 6 Open the encrypted tunnel from Windows

Open a new local PowerShell terminal and run:

```powershell
aws ssm start-session --target YOUR-INSTANCE-ID --document-name AWS-StartPortForwardingSession --parameters portNumber="8000",localPortNumber="18000" --region YOUR-REGION
```

Keep it running. Browse <http://127.0.0.1:18000> and sign in with the cloud administrator. The HTTP connection exists on loopback at each end; the inter-machine connection is protected by Session Manager. Neither TCP 8000 nor UDP 5514 should be opened in the EC2 security group.

This uses the normal managed-instance port-forwarding document, not the remote-host variant. The Session Manager plugin must be installed on the PC. A tunnel disconnect stops cloud forwarding; the local collector continues storing observations within its retention limits.

## 7 Run the relay beside local MikroSOC

Leave the local application running against the physical router. In another VS Code PowerShell terminal in the **local project**:

```powershell
$relaySecret = Read-Host 'Cloud ingestion token' -AsSecureString
$env:MIKROSOC_INGEST_TOKEN = [System.Net.NetworkCredential]::new('', $relaySecret).Password
.\.venv\Scripts\python.exe scripts\relay.py --port 18000
```

You now have three long-running local terminals: local MikroSOC, SSM tunnel and relay. Keep all three running for cloud monitoring.

The relay reads local log/metric rows and the most recent bound-device snapshot. It checkpoints after acknowledgement and retries after failures; cloud event IDs deduplicate retried observations. It forwards at most 100 logs and 100 metrics per cycle, and caps device snapshots at 200. Source data remains subject to local retention. Cloud ingestion rejects records older than seven days. This is a lab relay, not a guaranteed durable enterprise message bus.

The cloud runs its own rules and incident workflow. Rule changes, alert acknowledgements, trust labels, users and incident notes do **not** synchronize between local and cloud dashboards. Configure thresholds consistently if you want comparable detection results. Cloud backfill can arrive after the original event and cannot perfectly recreate every earlier rolling detection window. Use the local records for original real-time investigations.

## 8 Validate the cloud path

1. Keep the local and cloud browsers open on ports 8000 and 18000 respectively.
2. Send one harmless router `:log info "MikroSOC cloud test"` message.
3. Confirm it appears locally, then in the cloud after relay delay.
4. Wait for two new metric samples and check the cloud NOC graph.
5. Stop/restart the relay. Verify existing rows do not duplicate.
6. Stop the SSM tunnel temporarily; verify local collection continues and the relay logs a retry message. Restart the tunnel and confirm catch-up.
7. Verify no router passwords exist in the cloud config or environment file, and the EC2 security group has zero inbound rules.

If cloud metrics go stale, check all three local terminals, the instance service and clock synchronization. If ingestion returns 403, check token, `cloud_ingest_enabled`, and live mode. A 400 commonly means router IP mismatch, bad payload or an expired observation; relay output preserves the cursor until the issue is fixed (expired local records are explicitly skipped with a warning).

## 9 Optional CloudWatch application logs

The log group is created with seven-day retention. To send application operational logs:

```bash
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/mikrosoc/app/infra/aws/cloudwatch.json -s
```

Inspect **CloudWatch → Log groups → /mikrosoc/application**. This sends service output, not every router raw log; router logs remain in SQLite and exports. CloudWatch ingestion still counts toward pricing/credits. Do not enable verbose credential logging.

## 10 Private S3 backups

On EC2, use a unique filename each time:

```bash
cd /opt/mikrosoc/app
sudo -u mikrosoc .venv/bin/python manage.py backup data/cloud-backup-2026-09-18.sqlite3
sudo aws s3 cp data/cloud-backup-2026-09-18.sqlite3 s3://YOUR-BUCKET/backups/cloud-backup-2026-09-18.sqlite3 --region YOUR-REGION
```

These backups include router logs and security records. `backups/` objects expire after 14 days; release uploads do not. Backups are manual in this package. Confirm an uploaded object exists before relying on it. Restore to a new database filename with the app stopped as described in SETUP.md. The EC2 role has no bucket-list permission; use the console/operator identity to list objects.

## 11 Stop or tear down

For a short pause, stop the local relay/tunnel and stop EC2. Stored resources may still incur costs. For complete teardown, export any evidence you want to keep, verify backups, then return to `infra/aws`:

```powershell
terraform plan -destroy
```

Review before applying destruction. The S3 bucket deliberately has `force_destroy=false`, so Terraform will refuse to delete a nonempty bucket. Download wanted objects, then explicitly delete objects you no longer want using the S3 console. Only when you are ready to remove the infrastructure:

```powershell
terraform destroy
```

Destruction deletes the EC2 root disk and CloudWatch group managed by this template. Verify Billing and the region for leftover resources. The local router and PC application are independent and continue to work.

Sources: [AWS Free Tier](https://aws.amazon.com/free/), [Session Manager sessions and forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html), [Amazon Linux Python](https://docs.aws.amazon.com/linux/al2023/ug/python.html), [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs).
