# OPTIONAL. Read SETUP.md section 10 BEFORE enabling. Added DISABLED deliberately.
# Move above FastTrack, established/related accept and other accept rules before enabling.
/ip firewall filter add chain=input action=drop src-address-list=MikroSOC-blocked disabled=yes comment="MikroSOC containment input"
/ip firewall filter add chain=forward action=drop src-address-list=MikroSOC-blocked disabled=yes comment="MikroSOC containment forward"
/user group add name=mikrosoc-response policy=read,write,api
# Create mikrosoc-responder with this group, allowed-address=collector-IP/32, strong unique password.
# RouterOS 'write' is broad, not scoped to address lists. Keep credentials only on the local PC.
