"""Small synchronous RouterOS 6.43+/7 API client. Never evaluates CLI strings."""
import socket
import ssl
import time


def encode_length(n):
    if n < 0 or n > 0xffffffff:
        raise ValueError('Invalid word length')
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return (n | 0x8000).to_bytes(2,'big')
    if n < 0x200000:
        return (n | 0xc00000).to_bytes(3,'big')
    if n < 0x10000000:
        return (n | 0xe0000000).to_bytes(4,'big')
    return b'\xf0' + n.to_bytes(4,'big')


class RouterAPI:
    def __init__(self, cfg, username, password):
        self.sock = socket.create_connection((cfg['router_ip'],cfg['api_port']), timeout=8)
        try:
            if cfg['api_tls']:
                context = ssl.create_default_context(cafile=cfg['api_ca_file'])
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                self.sock = context.wrap_socket(self.sock, server_hostname=cfg['router_ip'])
            elif not cfg['allow_insecure_api']:
                raise ValueError('Unencrypted API is disabled')
            self.command('/login', name=username, password=password)
        except Exception:
            self.sock.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.sock.close()

    def _read(self, n):
        data = bytearray()
        while len(data) < n:
            if time.monotonic() > self.deadline:
                raise TimeoutError('Router response deadline exceeded')
            chunk = self.sock.recv(n-len(data))
            if not chunk:
                raise ConnectionError('Router disconnected')
            data.extend(chunk)
        return bytes(data)

    def _length(self):
        b = self._read(1)[0]
        if b < 0x80:
            return b
        if b < 0xc0:
            return ((b & 0x3f) << 8) | int.from_bytes(self._read(1),'big')
        if b < 0xe0:
            return ((b & 0x1f) << 16) | int.from_bytes(self._read(2),'big')
        if b < 0xf0:
            return ((b & 0xf) << 24) | int.from_bytes(self._read(3),'big')
        if b == 0xf0:
            return int.from_bytes(self._read(4),'big')
        raise ValueError('Unsupported API control byte')

    def command(self, path, queries=(), **attrs):
        self.deadline = time.monotonic() + 20
        words = [path] + [f'={k}={v}' for k,v in attrs.items()] + list(queries)
        self.sock.sendall(b''.join(encode_length(len(w.encode())) + w.encode() for w in words) + b'\0')
        records, error, total = [], None, 0
        while True:
            sentence = []
            while True:
                size = self._length()
                if not size:
                    break
                total += size
                if size > 1048576 or total > 8388608:
                    raise ValueError('Router response too large')
                sentence.append(self._read(size).decode('utf-8','replace'))
            if not sentence:
                continue
            kind = sentence[0]
            record = dict(w[1:].split('=',1) for w in sentence[1:] if w.startswith('=') and '=' in w[1:])
            if kind in ('!trap','!fatal'):
                error = record.get('message','Router API error')
                if kind == '!fatal':
                    raise RuntimeError(error)
            elif kind == '!re':
                records.append(record)
            elif kind == '!done':
                if error:
                    raise RuntimeError(error)
                return records
