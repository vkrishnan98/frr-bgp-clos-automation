"""
grpc_policy_demo.py
---------------------
FRR's built-in gRPC northbound is the *easiest* model-driven path to stand
up today (no sysrepo/netopeer2 build chain needed) — just compile FRR with
`--enable-grpc` and start a daemon with e.g.:

    zebra_options=" -M grpc:50051"
    staticd_options=" -M grpc:50052"

Coverage is the same as sysrepo's: frr-interface, frr-vrf, frr-staticd,
frr-filter (prefix-lists), frr-route-map — NOT frr-bgp (see README). This
script CRUDs a prefix-list on the candidate datastore and commits it, which
is a realistic "policy-as-code" building block: e.g. your CI pipeline pushes
an updated allow-list of customer prefixes without ever touching a BGP
neighbor definition.

PRE-REQUISITE:
    pip install grpcio grpcio-tools --break-system-packages
    # Get FRR's proto definitions (from the FRR source tree):
    #   frr/grpc/frr-northbound.proto
    python3 -m grpc_tools.protoc -I frr/grpc \
        --python_out=. --grpc_python_out=. frr/grpc/frr-northbound.proto

This produces frr_northbound_pb2.py / frr_northbound_pb2_grpc.py, imported
below. This script is intentionally illustrative — treat the exact message
shapes as "check against your FRR version's .proto file", since this is an
actively-evolving part of FRR.
"""
import grpc

import frr_northbound_pb2 as pb
import frr_northbound_pb2_grpc as pb_grpc

PREFIX_LIST_XPATH = (
    "/frr-filter:lib/prefix-list[type='ipv4'][name='CI-ALLOWED-CUSTOMERS']"
    "/entry[sequence='10']"
)


def add_prefix_list_entry(channel, prefix: str) -> None:
    stub = pb_grpc.NorthboundStub(channel)

    caps = stub.GetCapabilities(pb.GetCapabilitiesRequest())
    print("Supported modules:", [m.name for m in caps.supported_modules])
    if not any(m.name == "frr-filter" for m in caps.supported_modules):
        raise RuntimeError("frr-filter module not available on this daemon")

    candidate = stub.CreateCandidate(pb.CreateCandidateRequest())
    candidate_id = candidate.candidate_id

    edit = pb.EditCandidateRequest(
        candidate_id=candidate_id,
        update=[
            pb.PathValue(
                path=f"{PREFIX_LIST_XPATH}/action", value="permit"
            ),
            pb.PathValue(
                path=f"{PREFIX_LIST_XPATH}/ipv4-prefix", value=prefix
            ),
        ],
    )
    stub.EditCandidate(edit)

    stub.Commit(
        pb.CommitRequest(
            candidate_id=candidate_id,
            phase=pb.CommitRequest.ALL,
            comment="CI: add customer prefix to allow-list",
        )
    )
    print(f"Committed: permit {prefix} into CI-ALLOWED-CUSTOMERS")


def read_prefix_list(channel) -> None:
    stub = pb_grpc.NorthboundStub(channel)
    for resp in stub.Get(
        pb.GetRequest(
            type=pb.GetRequest.CONFIG,
            path=["/frr-filter:lib"],
        )
    ):
        print(resp)


if __name__ == "__main__":
    with grpc.insecure_channel("127.0.0.1:50052") as channel:
        add_prefix_list_entry(channel, "203.0.113.0/24")
        read_prefix_list(channel)
