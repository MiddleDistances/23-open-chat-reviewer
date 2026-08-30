"""Credential-free discovery of the local Tailscale identity."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TailscaleIdentity:
    """Safe address facts returned by the local Tailscale client."""

    ipv4: str
    dns_name: str


def tailscale_identity() -> TailscaleIdentity | None:
    """Return one active Tailscale IPv4 and its preferred MagicDNS name."""

    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    addresses = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(addresses) != 1:
        return None
    try:
        address = ipaddress.ip_address(addresses[0])
    except ValueError:
        return None
    if address.version != 4 or address.is_loopback:
        return None

    hostname = str(address)
    try:
        status = subprocess.run(
            ["tailscale", "status", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        payload = json.loads(status.stdout)
        self_status = payload.get("Self", {})
        dns_name = str(self_status.get("DNSName", "")).rstrip(".")
        if self_status.get("Online", True) and dns_name:
            hostname = dns_name
    except (json.JSONDecodeError, FileNotFoundError, subprocess.SubprocessError):
        pass
    return TailscaleIdentity(ipv4=str(address), dns_name=hostname)
