# REVIEW SECTION 7 OF SETUP.md. Adjust addresses; enter real passwords in WinBox UI.
# Execute one command at a time; signing can take time on the RB941.
/user group add name=mikrosoc-read policy=read,api
# Create mikrosoc-reader in System > Users using this group and a strong password.
# Certificates: choose unique names if any of these already exist.
/certificate add name=mikrosoc-ca common-name=MikroSOC-CA key-size=2048 days-valid=3650 key-usage=key-cert-sign,crl-sign
/certificate sign mikrosoc-ca
/certificate set [find name=mikrosoc-ca] trusted=yes
/certificate add name=mikrosoc-api common-name=192.168.88.251 subject-alt-name=IP:192.168.88.251 key-size=2048 days-valid=365 key-usage=digital-signature,key-encipherment,tls-server
/certificate sign mikrosoc-api ca=mikrosoc-ca
/ip service set api-ssl disabled=no port=8729 certificate=mikrosoc-api address=192.168.88.251/32 tls-version=only-1.2
/certificate export-certificate mikrosoc-ca type=pem
# Download cert_export_mikrosoc-ca.crt from WinBox Files, rename to certs/mikrosoc-ca.crt.
# Never export/share the CA private key. Existing service configuration must be recorded first.
