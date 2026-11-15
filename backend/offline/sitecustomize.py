"""Block external Python network connections in inference and spawned children.

This module is loaded by Python's normal site initialization only when the
inference launcher explicitly adds this directory and enables the guard.
No global OS/firewall settings are modified. Installation has no such flag.
"""
import ipaddress
import os
import socket

if os.environ.get('CHEST_OFFLINE_INFERENCE') == '1':
    _connect = socket.socket.connect
    _connect_ex = socket.socket.connect_ex
    _getaddrinfo = socket.getaddrinfo

    def _local(host):
        """Reject names before DNS; permit only explicit loopback IPC targets."""
        if host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def _guard_connect(self, address):
        if isinstance(address, tuple) and not _local(address[0]):
            raise PermissionError('External network disabled during CT inference')
        return _connect(self, address)

    def _guard_connect_ex(self, address):
        if isinstance(address, tuple) and not _local(address[0]):
            raise PermissionError('External network disabled during CT inference')
        return _connect_ex(self, address)

    def _guard_dns(host, *args, **kwargs):
        if host is not None and not _local(host):
            raise PermissionError('External DNS disabled during CT inference')
        return _getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = _guard_connect
    socket.socket.connect_ex = _guard_connect_ex
    socket.getaddrinfo = _guard_dns
