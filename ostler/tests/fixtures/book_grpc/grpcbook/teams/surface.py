"""The teams service as a surface: every call goes out through `grpcurl`, or the binary the run is given."""

from __future__ import annotations

from ostler.book import Environment, GrpcClient, GrpcSurface

from .endpoints import Reset


class TeamsSurface(GrpcSurface):
    name = "teams"

    def __init__(self, environment: Environment, binary: str = "grpcurl"):
        super().__init__(GrpcClient(environment.address("teams"), binary=binary))

    def restore(self) -> None:
        Reset().send(self.client)
