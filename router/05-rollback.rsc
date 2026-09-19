# Review first. Removes only project additions with these exact names/comments.
/system logging remove [find action=mikrosoc]
/system logging action remove [find name=mikrosoc]
/ip firewall filter remove [find comment="MikroSOC observe input"]
/ip firewall filter remove [find comment="MikroSOC observe forward"]
/ip firewall filter remove [find comment="MikroSOC containment input"]
/ip firewall filter remove [find comment="MikroSOC containment forward"]
# Inspect MikroSOC-blocked entries; remove only the entries created for your project incidents.
# Restore the PREVIOUS api-ssl service settings from your backup/export.
# Remove project users, groups and certificates only after confirming nothing else uses them.
# This deliberately does not guess the previous service state or touch existing firewall rules.
