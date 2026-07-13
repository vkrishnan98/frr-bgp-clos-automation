"""
validate_fabric.py
---------------------
pytest suite that treats the network like a piece of software: after
Ansible deploys, this asserts the fabric actually converged correctly.
This is the "network CI/CD" skill senior interviewers probe for.

    pip install pytest --break-system-packages
    pytest -v python/validate_fabric.py
"""
import pytest

from vtysh_client import VtyshClient

NODES = {
    "spine1": "clab-fabric-spine1",
    "spine2": "clab-fabric-spine2",
    "leaf1": "clab-fabric-leaf1",
    "leaf2": "clab-fabric-leaf2",
    "edge1": "clab-fabric-edge1",
}


@pytest.fixture(params=NODES.items(), ids=list(NODES.keys()))
def client(request):
    name, container = request.param
    return VtyshClient(container)


def test_bgp_sessions_established(client):
    summary = client.get_bgp_summary()
    peers = summary.get("ipv4Unicast", {}).get("peers", {})
    assert peers, f"No BGP peers found on {client.container}"
    for peer, info in peers.items():
        assert info["state"] == "Established", (
            f"{client.container}: peer {peer} is {info['state']}, expected Established"
        )


def test_leaf1_has_ecmp_to_leaf2_loopback():
    leaf1 = VtyshClient("clab-fabric-leaf1")
    ecmp_count = leaf1.get_bgp_ecmp_paths("10.0.0.12/32")
    assert ecmp_count == 2, (
        f"Expected 2 ECMP paths from leaf1 to leaf2's loopback via spine1+spine2, got {ecmp_count}"
    )


def test_leaf2_has_ecmp_to_leaf1_loopback():
    leaf2 = VtyshClient("clab-fabric-leaf2")
    ecmp_count = leaf2.get_bgp_ecmp_paths("10.0.0.11/32")
    assert ecmp_count == 2, (
        f"Expected 2 ECMP paths from leaf2 to leaf1's loopback via spine1+spine2, got {ecmp_count}"
    )


def test_wan_prefix_reaches_leaf2():
    """edge1's WAN prefix should be redistributed OSPF->BGP at leaf1, then
    propagated across the fabric to leaf2 — proves the redistribution
    boundary and route-maps are actually working, not just configured."""
    leaf2 = VtyshClient("clab-fabric-leaf2")
    route = leaf2.get_ip_route("172.16.0.0/24")
    assert "172.16.0.0/24" in route, "WAN prefix did not propagate to leaf2"
