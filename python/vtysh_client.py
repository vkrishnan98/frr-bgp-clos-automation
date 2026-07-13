"""
vtysh_client.py
----------------
A small NAPALM-style state-getter library for FRR nodes running inside
containerlab. There is no first-class NAPALM driver for FRR, and BGP/OSPF
are not (yet) exposed over FRR's YANG northbound (see README), so in real
deployments today the pragmatic, honest approach is: shell out to `vtysh`
inside the container and parse its JSON output. This module wraps that
cleanly so the rest of your automation (Ansible callbacks, pytest, a
CI pipeline, a NetBox reconciliation job, whatever) can treat it like any
other getter library.

Usage:
    client = VtyshClient("clab-fabric-leaf1")
    summary = client.get_bgp_summary()
    neighbors = client.get_ospf_neighbors()
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class VtyshError(RuntimeError):
    pass


@dataclass
class VtyshClient:
    container: str

    def _exec(self, vtysh_cmd: str) -> str:
        """Run a single vtysh command inside the target container via `docker exec`."""
        proc = subprocess.run(
            ["docker", "exec", self.container, "vtysh", "-c", vtysh_cmd],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            raise VtyshError(
                f"vtysh command failed on {self.container}: {vtysh_cmd!r}\n{proc.stderr}"
            )
        return proc.stdout

    def _exec_json(self, vtysh_cmd: str) -> dict[str, Any]:
        raw = self._exec(vtysh_cmd)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VtyshError(f"Non-JSON output from {vtysh_cmd!r}: {raw!r}") from exc

    # ---- Getters -----------------------------------------------------

    def get_bgp_summary(self) -> dict[str, Any]:
        return self._exec_json("show bgp summary json")

    def get_bgp_neighbor(self, neighbor: str) -> dict[str, Any]:
        return self._exec_json(f"show bgp neighbor {neighbor} json")

    def get_ip_route(self, prefix: str | None = None) -> dict[str, Any]:
        cmd = "show ip route json" if not prefix else f"show ip route {prefix} json"
        return self._exec_json(cmd)

    def get_ospf_neighbors(self) -> dict[str, Any]:
        return self._exec_json("show ip ospf neighbor json")

    def get_bgp_ecmp_paths(self, prefix: str) -> int:
        """Return how many equal-cost next hops FRR has installed for a prefix.
        Useful for validating spine-leaf ECMP after a deploy."""
        route = self.get_ip_route(prefix)
        entries = route.get(prefix, [])
        if not entries:
            return 0
        return len(entries[0].get("nexthops", []))

    # ---- Mutations (rare — prefer Ansible/frr-reload.py for config) ---

    def run_exec_command(self, cmd: str) -> str:
        """Escape hatch for ad-hoc EXEC-mode commands, e.g. 'clear bgp *'."""
        return self._exec(cmd)


if __name__ == "__main__":
    import sys

    container = sys.argv[1] if len(sys.argv) > 1 else "clab-fabric-leaf1"
    client = VtyshClient(container)
    print(json.dumps(client.get_bgp_summary(), indent=2))
