# Router CA certificate

Place the exported public CA certificate here as `mikrosoc-ca.crt`.
The API client verifies the certificate chain and the router IP subject alternative name.
Do not store or commit router private keys here. See the TLS steps in `../SETUP.md`.
