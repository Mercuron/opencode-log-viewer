from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SessionTrace:
    session: dict
    messages: list[dict]
    parts: list[dict]
    todo_snapshots: list[dict]


@dataclass
class Detection:
    kind: str
    level: str  # info | warn | bad
    message: str
    evidence: dict = field(default_factory=dict)


class Detector(Protocol):
    name: str

    def run(self, session: SessionTrace) -> list[Detection]: ...


_REGISTRY: list[Detector] = []


def register(cls):
    """Class decorator: instantiates and adds the detector to the registry.
    Adding a new detector is exactly: drop one file in detectors/ with this
    decorator on its class. No other file needs to change."""
    instance = cls()
    _REGISTRY.append(instance)
    return cls


def registered_detectors() -> list[Detector]:
    return list(_REGISTRY)
