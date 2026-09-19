# Sources and technical choices

Checked on 18 September 2026. These sources support protocol, hardware and deployment choices; they do not establish that this package has been tested on your physical device.

- [MikroTik RB941-2nD product](https://mikrotik.com/product/RB941-2nD): hardware specifications. With 32 MB RAM and 16 MB flash, collection/storage/analysis are placed on the PC.
- [RouterOS API](https://manual.mikrotik.com/docs/developer-guides/api/): binary framing, attributes, reply types and API/TLS services. The client supports the modern username/password login used from RouterOS 6.43 onward; legacy challenge login is not implemented.
- [RouterOS logging](https://help.mikrotik.com/docs/spaces/ROS/pages/328094/Log): remote logging actions and topics. The command templates use a small common subset rather than requiring new CEF features.
- [RouterOS services](https://help.mikrotik.com/docs/spaces/ROS/pages/103841820/Services): API access restrictions and TLS certificate binding.
- [RouterOS users](https://help.mikrotik.com/docs/spaces/ROS/pages/8978504/User): group permissions and dedicated API accounts.
- [RouterOS certificates](https://manual.mikrotik.com/docs/authentication-authorization-accounting/certificates/): CA/server certificates and IP subject alternative names.
- [RouterOS firewall filter](https://help.mikrotik.com/docs/spaces/ROS/pages/48660608/Filter): firewall logging, matching and rule behavior.
- [Flask security guidance](https://flask.palletsprojects.com/en/stable/web-security/): CSRF, cookies, hosts and response headers.
- [Flask Waitress deployment](https://flask.palletsprojects.com/en/stable/deploying/waitress/): cross-platform WSGI serving.
- [AWS Free Tier](https://aws.amazon.com/free/): current credits/plan approach. Earlier pasted promises of a universally free 750-hour first year or a fixed $0 monthly total are not assumed.
- [Session Manager forwarding](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html): private administration and forwarding through the managed instance.
- [CloudWatch agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html): application-log forwarding.
- [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs): resource configuration reference.

## Relationship to MikroDash

[SecOps-7/MikroDash](https://github.com/SecOps-7/MikroDash) is an existing self-hosted RouterOS 7 monitoring project. Its current README describes Go and TypeScript, streamed router data and a broad monitoring UI. MikroSOC is a separate Python implementation emphasizing persisted detection evidence and incident workflow. The earlier pasted description of that repository was incomplete; this package does not claim to be categorically better or feature-equivalent. No upstream code/assets were copied.

## Supplied materials

The user's MikroSOC Documentation Suite named NOC, SOC, incident response, alerting, logging, reporting and user management, plus a conceptual schema and five detection types. The pasted notes added the two-phase learning approach and optional low-cost AWS. They were used as requirements context; claims of previous ZIP creation or successful deployment inside those notes were not treated as artifacts or verified facts.
