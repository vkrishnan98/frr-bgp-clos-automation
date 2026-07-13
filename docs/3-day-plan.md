# 3-day plan: get hands-on fast, and be able to defend every design choice

The goal isn't "finish the repo," it's "be able to answer follow-up
questions about every layer." Time-box ruthlessly; skip anything not in
today's box.

## Day 1 — Topology + Ansible (the 80% skill: config-as-code)

1. `sudo apt install containerlab` (or the install script), `docker pull frrouting/frr:latest`.
2. `containerlab deploy -t topology/fabric.clab.yml`, then manually
   `docker exec -it clab-fabric-leaf1 vtysh` and hand-configure one eBGP
   unnumbered neighbor + verify `show bgp summary` — do this by hand once so
   you deeply understand what Ansible will template later. This is the
   single highest-leverage hour: everything else is "how do I generate this
   safely and repeatably."
3. Install `community.docker` (`ansible-galaxy collection install community.docker`)
   and `netaddr` (`pip install netaddr --break-system-packages`, needed for the
   `ipaddr` Jinja filter).
4. Run `ansible-playbook playbooks/deploy_fabric.yml`, then
   `playbooks/validate_fabric.yml`. Break something on purpose (typo an ASN
   in `host_vars/leaf2.yml`), re-run, watch validation fail with a clear
   message — this "break it, watch it get caught" loop is the fastest way
   to build real intuition, and it's a great interview anecdote.
5. **Be ready to explain**: why `frr-reload.py` instead of a full restart;
   why unnumbered eBGP instead of numbered /31s at scale; why redistribution
   at the fabric/WAN boundary needs prefix-lists in both directions (avoid
   accidentally becoming a transit AS, avoid route leaks/loops).

## Day 2 — Python: state validation, then the YANG/NETCONF/gRPC boundary

1. Run `python3 python/vtysh_client.py clab-fabric-leaf1` — confirm you get
   structured JSON back. Extend it with one getter of your own (e.g. `show
   interface json`) to prove you can read FRR's `vtysh` JSON conventions.
2. Run `pytest python/validate_fabric.py -v` against the live lab.
3. **Spend at most 2 hours** attempting the sysrepo/netopeer2 build
   (`--enable-sysrepo`) from `docs` links in the README — it's a real,
   valuable skill, but it's also genuinely slow to compile from source. If
   it's not done in 2 hours, stop, read `netconf_yang_demo.py` line by line
   instead, and move on. What matters for the interview is that you can
   *explain* the architecture (mgmtd -> backend clients -> YANG DB ->
   frontend adapters -> NETCONF/RESTCONF/gRPC), not that you personally
   compiled it under time pressure.
4. If you have time left, try the gRPC path instead
   (`--enable-grpc` is a much smaller compile/config surface than sysrepo) —
   it'll get you a real, working model-driven CRUD demo faster.
5. **Be ready to explain**: exactly which FRR daemons are northbound-converted
   today (interfaces, VRF, staticd, filter/route-map) vs. which aren't
   (bgpd, ospfd) — and why that means production BGP config still goes
   through the CLI/`vtysh` layer, templated by Ansible, not through YANG.
   This single fact differentiates you from candidates who only skimmed
   marketing slides.

## Day 3 — Integration, testing, and interview framing

1. Wire `validate_fabric.yml` (Ansible) and `validate_fabric.py` (pytest)
   into a mental "pipeline": Ansible deploys -> pytest gates -> (in a real
   job) a CI runner would block a merge on failure. You don't need actual
   Jenkins/GitLab CI for this exercise — you need to be able to draw the
   diagram and say confidently "this is a network CI/CD loop."
2. Skim `SKILL.md`-style structure once more: inventory/group_vars/host_vars
   separation, Jinja2 templates, idempotent reload, structured getters,
   automated assertions. Practice narrating this repo out loud in under
   3 minutes — that's your interview answer to "tell me about a project."
3. Prepare 3 talking points beyond this repo, since interviewers probe
   breadth:
   - **Source of truth**: in real shops config isn't hand-written in
     `host_vars` — it comes from a system like NetBox/Nautobot, and Ansible
     (or a Python service) renders from that. Mention `pynautobot`/
     `netbox-ansible` if asked.
   - **OpenConfig vs FRR-native YANG**: OpenConfig is the vendor-neutral
     model set (used heavily by gNMI/streaming telemetry shops); FRR ships
     its own `frr-*` models, not OpenConfig, so a multi-vendor NaaS platform
     usually needs a translation layer either way.
   - **Testing pyramid**: unit-test your Jinja2 templates/Python logic with
     plain pytest (no lab needed) before you ever need a full containerlab
     topology — that's the fast inner loop; containerlab/pytest-against-real-
     state is your slower integration loop.
