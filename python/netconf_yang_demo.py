"""
netconf_yang_demo.py
---------------------
Real NETCONF/YANG against FRR — scoped honestly.

PRE-REQUISITE (not in the stock `frrouting/frr` docker image used by the
containerlab topology in this repo): FRR must be compiled from source with
`--enable-sysrepo`, sysrepo + netopeer2 installed, the relevant frr/yang/*.yang
modules loaded via `sysrepoctl -i`, and the target daemon started with
`-M sysrepo`. See docs/3-day-plan.md and
https://docs.frrouting.org/projects/dev-guide/en/latest/northbound/plugins-sysrepo.html

WHY THIS SCRIPT ONLY TOUCHES INTERFACES + STATIC ROUTES:
bgpd's northbound callbacks are not implemented, so `frr-bgp` xpaths are not
reachable over NETCONF today, no matter how the transport is wired up. This
script demonstrates get-config / edit-config against the two things that
*are* wired: `ietf-interfaces` (description) and `frr-staticd` (static route).

    pip install ncclient --break-system-packages
    python3 netconf_yang_demo.py --host 127.0.0.1 --port 830
"""
import argparse
from ncclient import manager
from ncclient.xml_ import to_ele

GET_INTERFACES_FILTER = """
<filter>
  <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>
</filter>
"""

EDIT_INTERFACE_DESCRIPTION = """
<config>
  <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">
    <interface>
      <name>eth1</name>
      <description>set-via-netconf-demo</description>
    </interface>
  </interfaces>
</config>
"""

ADD_STATIC_ROUTE = """
<config>
  <lib xmlns="https://frrouting.org/yang/staticd">
    <route-list xmlns="https://frrouting.org/yang/route-types">
      <prefix>203.0.113.0/24</prefix>
      <afi-safi>frr-routing:ipv4-unicast</afi-safi>
      <vrf>default</vrf>
      <path-list>
        <table-id>0</table-id>
        <distance>1</distance>
        <frr-nexthops>
          <nexthop>
            <nh-type>ip4</nh-type>
            <vrf>default</vrf>
            <gateway>10.0.0.1</gateway>
          </nexthop>
        </frr-nexthops>
      </path-list>
    </route-list>
  </lib>
</config>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=830)
    ap.add_argument("--user", default="netconf")
    ap.add_argument("--password", default="netconf")
    args = ap.parse_args()

    with manager.connect(
        host=args.host,
        port=args.port,
        username=args.user,
        password=args.password,
        hostkey_verify=False,
        device_params={"name": "default"},
    ) as m:
        print("--- capabilities (look for frr-* modules) ---")
        for cap in m.server_capabilities:
            if "frr" in cap or "ietf-interfaces" in cap:
                print(" ", cap)

        print("\n--- get-config: interfaces ---")
        reply = m.get_config(source="running", filter=to_ele(GET_INTERFACES_FILTER))
        print(reply)

        print("\n--- edit-config: set eth1 description ---")
        m.edit_config(target="running", config=to_ele(EDIT_INTERFACE_DESCRIPTION))
        print("OK")

        print("\n--- edit-config: add static route 203.0.113.0/24 ---")
        m.edit_config(target="running", config=to_ele(ADD_STATIC_ROUTE))
        print("OK")


if __name__ == "__main__":
    main()
