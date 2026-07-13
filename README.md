# netauto-lab — FRR + containerlab + Ansible + Python (NETCONF/gRPC) + pytest

A moderately-complex, scalable lab that mirrors what a senior network-automation
engineer actually builds in production: a small BGP Clos fabric with an OSPF
WAN edge, driven by Ansible for day-0/1 config, and Python for model-driven
state validation and policy CRUD.

## 0. The one fact that changes your whole design (read this first)

If you search around, you'll find a lot of confident-sounding tutorials that
show FRR being fully configured over NETCONF with YANG models for BGP. **That
does not work today (FRR 10.x, 2026).** Here's the actual state of FRR's
model-driven northbound (`mgmtd`):

| Daemon / feature                          | YANG northbound wired in? | Usable via NETCONF/gRPC today? |
|--------------------------------------------|----------------------------|----------------------------------|
| Interfaces (`frr-interface`, `ietf-interfaces`) | Yes | Yes |
| VRFs (`frr-vrf`)                           | Yes | Yes |
| Static routes (`staticd`)                  | Yes | Yes |
| Prefix-lists / route-maps (`frr-filter`, `frr-route-map`) | Yes | Yes |
| **BGP (`bgpd`)**                           | YANG *models exist on disk* but the northbound callbacks are **not implemented in bgpd** | **No** — `mgmtd` returns "Data path not found" for any `frr-bgp` xpath |
| OSPF, ISIS, RIP                            | Partial/none wired         | No |
| RESTCONF                                   | Architecturally planned, no built-in server yet | Only via a separate sysrepo+netopeer2 stack, and only for the rows above |
| NETCONF                                    | Not native to `mgmtd` yet  | Only via a separate sysrepo+netopeer2 stack (older northbound plugin, `--enable-sysrepo`), same model coverage as above |
| gRPC                                       | Built-in (`--enable-grpc`), same model coverage as the table above | Yes, easiest to stand up |

**What this means for your design:** BGP and OSPF — the actual routing
protocols — are configured via **CLI/`vtysh` under the hood** in every
real FRR deployment today (Ansible templating `frr.conf` + `frr-reload.py`,
or SONiC/Cumulus-style "regenerate frr.conf from a database"). YANG/NETCONF
in FRR is currently useful for **interfaces, VRFs, static routes, and
route-policy objects (prefix-lists/route-maps)** — not for turning up a BGP
neighbor.

This is genuinely valuable interview material: you can say "I know exactly
which parts of FRR's northbound are production-ready and which aren't, and I
designed around that boundary" — that is a senior-level statement, and it's
what this lab demonstrates end-to-end.

## 1. Topology (containerlab)

```
        AS65000                 AS65000
      spine1 ─────────eBGP────────── spine2
       │  \                         /  │
       │   \_______eBGP___________/   │
      eBGP                          eBGP
       │                              │
     leaf1 (AS65101)            leaf2 (AS65102)
       │  \__OSPF area 51__            │
      host1                edge1(AS65200)     host2
                       (redistributes OSPF<->BGP)
```

- 2 spines, 2 leaves: eBGP **unnumbered** underlay (real DC Clos design,
  Facebook/Arista style — unique ASN per leaf, shared ASN across spines).
- `edge1`: legacy/WAN-style router speaking **OSPF** to `leaf1` and **eBGP**
  to the fabric — forces you to write redistribution + route-map/prefix-list
  filtering, which is the #1 thing interviewers ask about.
- `host1`/`host2`: Alpine containers to prove end-to-end reachability and ECMP
  across both spines.

See `topology/fabric.clab.yml`. Spin it up with:

```bash
sudo containerlab deploy -t topology/fabric.clab.yml
```

## 2. Ansible layer — the primary automation plane

Ansible doesn't SSH into the FRR containers (the stock `frrouting/frr` image
has no sshd). Instead it uses the **`community.docker`** collection to:

1. Render `frr.conf.j2` per host from `group_vars`/`host_vars` (single
   source of truth for ASNs, interfaces, neighbors, prefix-lists).
2. `docker cp` the rendered file into the container.
3. Run `/usr/lib/frr/frr-reload.py --reload` **inside** the container — this
   is the real production trick: it diffs old vs new config and issues only
   the incremental `vtysh` commands, so it's a safe, idempotent, non-disruptive
   reload (not a full restart).

```bash
cd ansible
ansible-playbook -i inventory/hosts.yml playbooks/deploy_fabric.yml
ansible-playbook -i inventory/hosts.yml playbooks/validate_fabric.yml
```

## 3. Python layer — three separate, honest demos

- `python/vtysh_client.py` — a small NAPALM-style getter library you write
  yourself (because NAPALM doesn't have solid FRR support). Runs
  `vtysh -c "... json"` via `docker exec` and returns parsed dicts. This is
  what you'll actually use for BGP/OSPF state today.
- `python/netconf_yang_demo.py` — a real `ncclient` NETCONF session against
  a sysrepo+netopeer2-fronted FRR build, get-config/edit-config on
  `ietf-interfaces` and a static route. Clearly scoped to what's real.
- `python/grpc_policy_demo.py` — CRUD of a `frr-filter` prefix-list over
  FRR's **built-in gRPC** northbound (`--enable-grpc`) — the easiest
  model-driven path to stand up today, and increasingly what real NaaS
  platforms use for policy objects while BGP stays CLI-driven.
- `python/validate_fabric.py` — pytest suite: asserts all eBGP sessions are
  `Established` and that leaf1/leaf2 each see 2 ECMP paths to the other
  leaf's loopback via the two spines.

## 4. Suggested 2–3 day execution plan

See `docs/3-day-plan.md`.
