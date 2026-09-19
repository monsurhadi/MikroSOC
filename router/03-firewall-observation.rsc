# OPTIONAL. Review load and rule order. Run each add once.
# action=log continues evaluation; these rules do not accept or drop packets.
# Move the two named rules before your existing relevant accept/drop rules in WinBox.
/ip firewall filter add chain=input action=log protocol=tcp connection-state=new tcp-flags=syn limit=10,20:packet log-prefix="MSOC-CONN " comment="MikroSOC observe input"
/ip firewall filter add chain=forward action=log protocol=tcp connection-state=new tcp-flags=syn limit=10,20:packet log-prefix="MSOC-CONN " comment="MikroSOC observe forward"
# Global sampling limits can hide events during bursts; no packet payload capture is performed.
