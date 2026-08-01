
## Open issue (Day 2) — OSPF adjacency never forms on leaf1<->edge1

- `ospfd.conf` on leaf1 clearly shows `interface eth3 / ip ospf area 0.0.0.51`
  written to disk correctly (confirmed via `cat /etc/frr/ospfd.conf`).
- Despite that, `show ip ospf interface eth3` reports "OSPF not enabled on
  this interface" on both leaf1 and edge1 — the daemon's live state
  disagrees with its own config file.
- Ruled out: not a template/Ansible bug (typing the command manually via
  vtysh had the same result); not a transient interface-state issue
  (flapping eth3/eth1 with `ip link set down/up` did not fix it).
- eBGP unnumbered on this same physical link works perfectly — so the
  link, veth pair, and IPv6 link-local addressing are all fine; this is
  isolated specifically to ospfd's interface-to-area binding.
- Leading hypothesis not yet tested: FRR's traditional (per-daemon config
  file) mode may require an explicit `router ospf` + `network area`
  statement, or an explicit `no ip ospf area` + re-add cycle, rather than
  purely an interface-level command, on this FRR version (8.4_git). Worth
  testing `show ip ospf` process-level state, and reviewing whether
  ospfd's config was actually reloaded (vs zebra's) during the last
  frr-reload.py run.
- Downstream effect: `edge1`'s WAN prefix never gets redistributed
  OSPF->BGP into the fabric, so leaf2 will never see it — expect
  `test_wan_prefix_reaches_leaf2` in the pytest suite to fail until this
  is resolved.

## Day 2 progress
- Extended vtysh_client.py with get_ospf_database() getter — works correctly.
- Ran pytest validate_fabric.py: 7/8 passed (all BGP sessions, both ECMP
  paths). test_wan_prefix_reaches_leaf2 failed as expected, confirming the
  OSPF issue above via a second, independent tool.
- Switched to a Python venv (~/netauto-venv) for pytest specifically, kept
  Ansible's dependencies on system Python untouched — avoided repeating
  today's earlier version-conflict pattern.
exit
## OSPF issue — root cause found (not yet resolved)

Confirmed root cause: container logs show `ospfd state -> down : read
returned EOF` followed by an automatic restart — ospfd crashed at some
point (likely during the earlier veth-link-loss incident) and came back
up with an empty area table (`show ip ospf` reports "Number of areas
attached to this router: 0"), even though the on-disk config
(ospfd.conf) correctly retained `ip ospf area 0.0.0.51`.

Attempted fix that did NOT work: re-running `ansible-playbook
deploy_fabric.yml` to trigger frr-reload.py. This failed because
frr-reload.py's diff engine compares the new config against its own
stored/previous config file — since the file already said the area was
set, it computed zero changes and sent nothing to ospfd, never knowing
the live daemon's memory disagreed with the file. This is a genuine,
useful limitation to understand: diff-based reload tools trust
configuration state, not live process state.

Not yet tried (next session): a full container restart
(`docker restart clab-fabric-leaf1`) rather than an in-place reload,
which should force ospfd to cold-start and re-read its config file from
scratch — the cleanest test of whether this is purely an ospfd
in-memory-state problem.

Interview-ready framing: "I traced an OSPF adjacency failure past the
config layer into the daemon's live process state by cross-referencing
container logs, and identified a real limitation in FRR's incremental
reload tooling — it won't resend a command if the file-level diff shows
no change, even if the live daemon crashed and lost that state
in-memory. The clean fix is a full process/container restart, not
another incremental reload."

## OSPF issue — RESOLVED (final root causes, there were two)

1. OSPFv2 requires a real IPv4 address on the interface to form
   adjacencies — BGP unnumbered doesn't need one because it transports
   over IPv6 link-local regardless of address-family. Fix: added a
   /31 point-to-point IPv4 address (10.255.0.0/1) to the leaf1<->edge1
   link, plus `ip ospf network point-to-point` (since it's not a normal
   broadcast segment).
2. Separately, BGP's `network X.X.X.X/Y` statement only announces a
   prefix if that exact route already exists in the RIB (static,
   connected, etc.) — it does not create the route. edge1's WAN prefix
   was never actually in its own routing table, so `network
   172.16.0.0/24` was silently announcing nothing. Fix: added
   `ip route 172.16.0.0/24 Null0` as a top-level static route (separate
   from the `network` statement inside `router bgp` — these are two
   distinct config objects, not one combined line).

All 8 pytest checks pass: 5x BGP Established, 2x ECMP, WAN prefix
propagation. Full fabric validated end-to-end via two independent tools
(Ansible assert playbook + pytest).

Interview-ready summary: "I hit an OSPF adjacency failure that turned
out to have two independent root causes stacked on top of each other —
missing IPv4 addressing (OSPFv2's actual requirement, distinct from BGP
unnumbered's IPv6-link-local approach) and a separate BGP redistribution
gap where the network statement had no RIB entry to actually announce.
Fixing the first one didn't fully resolve it, which taught me not to
declare victory on the first plausible fix — I re-validated with pytest
each time and let the test suite's precision point me to what was still
actually missing."
