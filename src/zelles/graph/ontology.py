"""Static domain knowledge: which standard governs which topic.

This is the reference layer of the knowledge graph. When a CCTP cites a
standard, the graph links it to the topics it governs, so an agent can answer
"which clauses relate to weather tightness?" even when the CCTP only says
"conforme à la NF EN 12208".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from zelles.domain.spec import Category


@dataclass(frozen=True)
class StandardInfo:
    code: str
    title: str
    categories: tuple[Category, ...]


STANDARDS: tuple[StandardInfo, ...] = (
    StandardInfo(
        "NF DTU 36.5", "Installation of external windows and doors", (Category.INSTALLATION,)
    ),
    StandardInfo("NF DTU 39", "Glazing works", (Category.GLAZING,)),
    StandardInfo(
        "NF EN 14351-1",
        "Product standard for windows and external pedestrian doors",
        (Category.THERMAL, Category.WEATHER, Category.ACOUSTICS, Category.COMPLIANCE),
    ),
    StandardInfo("NF EN 12207", "Air permeability classification", (Category.WEATHER,)),
    StandardInfo("NF EN 12208", "Watertightness classification", (Category.WEATHER,)),
    StandardInfo("NF EN 12210", "Resistance to wind load classification", (Category.WEATHER,)),
    StandardInfo("NF EN 1627", "Burglar resistance of doors and windows", (Category.SECURITY,)),
    StandardInfo(
        "NF EN 356",
        "Security glazing: resistance against manual attack",
        (Category.GLAZING, Category.SECURITY),
    ),
    StandardInfo("NF EN 1279", "Insulating glass units", (Category.GLAZING,)),
    StandardInfo(
        "NF EN ISO 10077",
        "Thermal performance of windows and doors (calculation)",
        (Category.THERMAL,),
    ),
    StandardInfo("NF EN 13659", "Shutters and external venetian blinds", (Category.EQUIPMENT,)),
)

_KEY = re.compile(r"[^a-z0-9.]+")


def standard_key(code: str) -> str:
    """Canonical key: 'nf dtu 36.5' -> 'nf-dtu-36.5'; 'DTU 36.5' maps to the NF form."""
    key = _KEY.sub("-", code.lower()).strip("-")
    if key.startswith("dtu-"):
        key = "nf-" + key
    return key


def lookup(code: str) -> StandardInfo | None:
    key = standard_key(code)
    for info in STANDARDS:
        ref = standard_key(info.code)
        if key == ref or key.startswith(ref + "-"):
            return info
    return None
