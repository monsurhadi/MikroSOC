# REVIEW BEFORE PASTING. Change the two example addresses to your actual LAN values.
# Does not reset the router, modify NAT, or enable disk logging.
/system logging action add name=mikrosoc target=remote remote=192.168.88.10 remote-port=5514 src-address=192.168.88.1
/system logging add action=mikrosoc topics=account
/system logging add action=mikrosoc topics=critical,!account
/system logging add action=mikrosoc topics=warning,!account,!critical
/system logging add action=mikrosoc topics=firewall,!account,!critical,!warning
/system logging add action=mikrosoc topics=dhcp,!debug,!account,!critical,!warning,!firewall
# Explicit prefix rule for test messages; topic lists above avoid common duplication.
/system logging add action=mikrosoc topics=script,info
:log info "MikroSOC syslog connection test"
