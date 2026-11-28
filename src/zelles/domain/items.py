"""Joinery items: the spec sheet grouped by what each value applies to.

A récapitulatif technique lists each joinery item of a tender (a window type, a
door, a curtain wall, a shutter) with its own material, glazing, Uw, hardware
and so on. The spec sheet holds the same values as a flat list, each with the
heading it was read under (its scope). This module groups that list into items.

A value read under a heading that names no item ("2.1 Généralités", "Prescriptions
communes") is a general clause. An item that states nothing for a field inherits
the general clauses of its own chapter, marked as inherited so the estimator can
tell a general clause from the item's own. Standards, certifications and
regulations bind the whole tender and stay with the general clauses.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field

from zelles.domain.documents import Chunk
from zelles.domain.spec import FIELD_CATALOG, Requirement, SpecField, SpecSheet

_I = re.IGNORECASE
F = SpecField


class ItemKind(StrEnum):
    WINDOW = "window"
    DOOR = "door"
    FACADE = "facade"
    SHUTTER = "shutter"


# Checked in this order: "Porte-fenêtre" is a window, "Façades vitrées et baies d'accès"
# a facade, "Volet roulant électrique" a shutter even though it sits on a window.
_KINDS: tuple[tuple[ItemKind, re.Pattern[str]], ...] = (
    (ItemKind.WINDOW, re.compile(r"portes?[- ]fen[êe]tres?", _I)),
    (
        ItemKind.FACADE,
        re.compile(
            r"fa[çc]ades?\s+(?:vitr[ée]es?|rideaux?)|murs?[- ]rideaux?|verri[èe]res?|v[ée]randas?",
            _I,
        ),
    ),
    (
        ItemKind.SHUTTER,
        re.compile(
            r"\bvolets?\b|\bstores?\b|brise[- ]?soleil|\bBSO\b|persiennes?|occultations?|"
            r"rideaux?\s+m[ée]talliques?",
            _I,
        ),
    ),
    (
        ItemKind.DOOR,
        re.compile(
            r"\bportes?\b|blocs?[- ]portes?|\bportails?\b|\bportillons?\b|baies?\s+d'acc[èe]s|"
            r"\bissues?\b",
            _I,
        ),
    ),
    (
        ItemKind.WINDOW,
        re.compile(
            r"fen[êe]tres?|ch[âa]ssis|\bbaies?\b|ensembles?\s+(?:de\s+)?(?:vitr|menuis|ch[âa]ssis|type|fen|porte)|"
            r"lanterneaux?|oscillo|coulissants?|"
            r"impostes?",
            _I,
        ),
    ),
)
# "Menuiseries aluminium" names a family, not an item: an item only when the
# tender describes no item more precisely.
_FAMILY = re.compile(r"\bmenuiseries?\b", _I)
# The item's mark on the plans: "M2", "PE 3", "CH1a", "ME01".
_MARK = r"(?:M|F|P|PE|PF|PV|CH|VR|BS|ME|EN|MR|SR)\s?\d{1,3}(?:[a-z]{1,2}|')?"
_CODE = re.compile(rf"\b({_MARK})(?=\W|$)")
# A mark that opens a line of the item's text: "ME11 - Porte d'entrée".
_CODE_LINE = re.compile(rf"(?m)^\W*({_MARK})\s*[-–:]")
# A mark that introduces a described item inside a paragraph: "… ME12 - Châssis vitré".
# A mark only cited ("localisation : voir ME02") is not the item's own.
_CODE_INTRO = re.compile(rf"\b({_MARK})\s+[-–]\s+(?=[A-ZÀ-Ÿ])")
# Headings that organise the text rather than name a part of the works.
_GENERAL = re.compile(
    r"^\s*(?:[\w.]+\s+)?(?:g[ée]n[ée]ralit[ée]s|objet|prescriptions?|sp[ée]cifications?|"
    r"principes?|dispositions?|conditions?|normes?|r[ée]glementation|documents?|"
    r"essais|contr[ôo]les?|garanties?|limites?|interfaces?|nature|caract[ée]ristiques|"
    r"calfeutrements?|joints?|mise\s+en\s+(?:œ|oe)uvre|pose|d[ée]pose|fixations?|nettoyage|"
    r"ouvrages?\s+annexes|dispositifs?\s+anti)\b",
    _I,
)
# Accessories of the joinery: their values bind no item.
_ACCESSORY = re.compile(
    r"^\s*(?:[\w.]+\s+)?(?:tablettes?|appuis?\b|habillages?|couvre-?joints?|seuils?|grilles?|bavettes?|"
    r"bandeaux?\s+d'habillage)",
    _I,
)
# Other trades that a joinery lot sometimes carries: their values are set aside.
_OTHER_TRADE = re.compile(
    r"signal[ée]tique|bo[îi]tes?\s+aux\s+lettres|\bprovisions?\b|\bD\.?O\.?E\b|"
    r"dossier\s+des\s+ouvrages|^\W*modifications?\b|indices?\s+de\s+r[ée]vision|"
    r"date\s+de\s+cr[ée]ation",
    _I,
)
_MATERIAL = re.compile(r"\b(alu(?:minium)?|bois|pvc|acier|mixte)\b", _I)
# Tender-wide fields: they stay with the general clauses.
_TENDER_WIDE = frozenset({F.STANDARDS, F.CERTIFICATIONS, F.REGULATION})
# Classes and materials: an item's own replaces its parent's, like a measured value.
_CLASSES = frozenset({F.FRAME_MATERIAL, F.AEV, F.ACOUSTIC, F.SECURITY_CLASS, F.FIRE_RATING})
# What a shutter, blind or roller grille takes from the windows' general clauses: its
# own clauses, colours, finish and fitting. Glazing, Uw, acoustics or PMR clauses
# describe the windows, not it.
_SHUTTER_INHERITS = frozenset({F.SHUTTERS, F.COLOR, F.FINISH, F.INSTALLATION})
# Hardware that only a door has, and hardware that only a window has: a chapter clause
# listing both binds each item with its own kind of parts.
_DOOR_PARTS = re.compile(
    r"ferme[\s-]?portes?|anti[\s-]?panique|cr[ée]mones?\b[^.;]{0,40}?\b(?:pompiers?|[àa]\s+mortaiser)|"
    r"tirage|b[âa]ton\s+de\s+mar[ée]chal|butoirs?|g[âa]ches?\s+[ée]lectriques?|ventouses?|"
    r"cylindres?|serrures?|b[ée]quilles?|pivots?|s[ée]lecteurs?",
    _I,
)
_WINDOW_PARTS = re.compile(
    r"oscillo|cr[ée]mones?|poign[ée]es?\s+de\s+fen[êe]tres?|limiteurs?\s+d'ouverture", _I
)
_SOLID = re.compile(r"\b(?:pleines?|aveugles?)\b|\bsans\s+(?:vitrage|oculus|hublot)\b", _I)
_GLAZED = re.compile(
    r"\bvitr(?:[ée]e?s?|ages?)\b|\boculus\b|\bhublots?\b|\bremplissage\s+verre", _I
)
_GLAZING = frozenset(
    {F.GLAZING_COMPOSITION, F.GLAZING_TYPE, F.SAFETY_GLAZING, F.SPACER, F.UG, F.SW, F.TLW}
)
_UD = re.compile(r"\bUd\b")
_UW = re.compile(r"\bUw\b", _I)


def kind_of(heading: str) -> ItemKind | None:
    """The kind of joinery item a heading names, or None for a general heading."""
    if _GENERAL.search(heading) or _ACCESSORY.search(heading) or _OTHER_TRADE.search(heading):
        return None
    for kind, pattern in _KINDS:
        if pattern.search(heading):
            return kind
    return ItemKind.WINDOW if _CODE.search(heading) else None


def code_of(heading: str) -> str | None:
    match = _CODE.search(heading)
    return match.group(1).replace(" ", "") if match else None


class ItemValue(BaseModel):
    requirement: Requirement
    inherited: bool = Field(
        default=False, description="Read in a general clause, not under the item's own heading."
    )


class JoineryItem(BaseModel):
    """One joinery item of the tender and the values that apply to it."""

    name: str = Field(description="The heading that names the item, e.g. '3.2 Fenêtres PVC'.")
    group: str | None = Field(
        default=None, description="The heading above it, which tells same-named items apart."
    )
    codes: list[str] = Field(default_factory=list, description="Its marks on the plans: 'M2'.")
    kind: ItemKind
    solid: bool = Field(
        default=False, description="A solid door or panel: it takes no glazing clause."
    )
    values: dict[SpecField, list[ItemValue]] = Field(default_factory=dict)

    def own(self, field: SpecField) -> list[Requirement]:
        return [v.requirement for v in self.values.get(field, []) if not v.inherited]

    def own_fields(self) -> set[SpecField]:
        return {f for f, values in self.values.items() if any(not v.inherited for v in values)}


class ItemBook(BaseModel):
    """The spec sheet as a list of items, plus the general clauses they inherit."""

    items: list[JoineryItem] = Field(default_factory=list)
    general: dict[SpecField, list[Requirement]] = Field(default_factory=dict)
    accessories: dict[str, list[Requirement]] = Field(
        default_factory=dict, description="Values of accessory articles (sills, trims), by heading."
    )
    outside: dict[str, list[Requirement]] = Field(
        default_factory=dict, description="Values of other trades' articles (signage), by heading."
    )


_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s")


def _parents(scopes: set[str]) -> set[str]:
    """Scopes whose number heads other scopes: "2 Menuiseries" above "2.2 Fenêtres M1".

    A value lands on the parent heading when it sits under a general sub-heading
    ("2.1 Généralités"), so the parent holds the chapter's common clauses, not an item.
    """
    numbers = {m.group(1): scope for scope in scopes if (m := _NUMBER.match(scope))}
    return {
        scope
        for number, scope in numbers.items()
        if any(other.startswith(f"{number}.") for other in numbers)
    }


class _Place:
    """Where a value sits in the outline, when the chunks are known."""

    def __init__(self, chunks: Sequence[Chunk] | None) -> None:
        self.by_id = {c.id: c for c in chunks or ()}

    def chunk(self, req: Requirement) -> Chunk | None:
        return self.by_id.get(req.citation.chunk_id) if req.citation else None

    def path(self, req: Requirement) -> list[str]:
        chunk = self.chunk(req)
        return list(chunk.section_path) if chunk else []

    def position(self, req: Requirement) -> int:
        chunk = self.chunk(req)
        return chunk.index if chunk else 0


def _chapter(path: list[str], scope: str | None, above_items: set[str]) -> list[str]:
    """The outline a general clause binds.

    A clause in "5.1.4.1 Dispositif anti-pince-doigts" under "5.1.4 Ouvrages annexes"
    binds the items of "5.1 Menuiseries du foyer": its own article and the general
    headings above it are dropped, the first chapter that names a part of the works stays.
    """
    if scope not in path:
        return path
    path = path[: path.index(scope) + 1]
    if path[-1] not in above_items:  # its own article, which heads no item
        path = path[:-1]
    while path and (_GENERAL.search(path[-1]) or _ACCESSORY.search(path[-1])):
        path = path[:-1]
    return path


def build_items(sheet: SpecSheet, chunks: Sequence[Chunk] | None = None) -> ItemBook:
    """Group a spec sheet by joinery item, in document order.

    With the document's chunks, every item heading becomes an item, even one whose
    text only gives sizes and location; items carry their parent heading and plan
    marks, and inherit only the clauses of their own chapter. Without them, items
    come from the values' scopes and every general clause binds every item.
    """
    place = _Place(chunks)
    reqs = sorted(sheet.requirements, key=place.position)
    # every heading of the outline, with its path, in reading order
    outline: dict[str, list[str]] = {}
    for chunk in sorted(chunks or (), key=lambda c: c.index):
        if chunk.scope:
            outline.setdefault(chunk.scope, list(chunk.section_path))
    for req in reqs:
        if req.scope:
            outline.setdefault(req.scope, place.path(req))
    scopes = set(outline)
    candidates = {s for s in scopes if kind_of(s) is not None and not _OTHER_TRADE.search(s)}
    if not candidates:  # "3 Menuiseries PVC" is the item when nothing names one more precisely
        candidates = {s for s in scopes if _FAMILY.search(s) and not _GENERAL.search(s)}
    parents = _parents(scopes) | _outline_parents(candidates, outline)
    items: dict[str, JoineryItem] = {}
    for scope, path in outline.items():
        if scope in candidates and scope not in parents:
            group = path[path.index(scope) - 1] if scope in path and path.index(scope) else None
            items[scope] = JoineryItem(
                name=scope, group=group, codes=_codes(scope), kind=kind_of(scope) or ItemKind.WINDOW
            )
    texts: dict[str, list[str]] = {}
    for chunk in chunks or ():
        if chunk.scope in items:
            item = items[chunk.scope]
            item.codes = list(dict.fromkeys([*item.codes, *_codes_in(chunk.text)]))
            texts.setdefault(chunk.scope, []).append(chunk.text)
    for scope, item in items.items():
        item.solid = item.kind is ItemKind.DOOR and _is_solid(scope, texts.get(scope, []))
    general: list[Requirement] = []
    shared: list[Requirement] = []  # a parent item's values, for its children only
    accessories: dict[str, list[Requirement]] = {}
    outside: dict[str, list[Requirement]] = {}
    for req in reqs:
        where = req.scope or ""
        if where and _OTHER_TRADE.search(where) and _states(req, where, place):
            outside.setdefault(where, []).append(req)
        elif where and _ACCESSORY.search(where):
            accessories.setdefault(where, []).append(req)
        elif where in items:
            items[where].values.setdefault(req.field, []).append(ItemValue(requirement=req))
        elif where in candidates:
            shared.append(req)
        else:
            general.append(req)
    for scope in _contents_twins(items):
        del items[scope]
    above_items = {h for scope in items for h in outline.get(scope, [])}
    shutters_apart = any(i.kind is ItemKind.SHUTTER for i in items.values())
    for scope, item in items.items():
        _inherit(
            item,
            outline.get(scope, []),
            [*shared, *general],
            place,
            above_items,
            shutters_apart=shutters_apart,
        )
        item.values = {f: item.values[f] for f in FIELD_CATALOG if f in item.values}
    by_field: dict[SpecField, list[Requirement]] = {}
    for req in general:
        by_field.setdefault(req.field, []).append(req)
    return ItemBook(
        items=list(items.values()),
        general={f: by_field[f] for f in FIELD_CATALOG if f in by_field},
        accessories=accessories,
        outside=outside,
    )


def _outline_parents(candidates: set[str], outline: dict[str, list[str]]) -> set[str]:
    """Item headings with item headings below them: "5.1 Façade vitrée" above "5.1.1 Châssis A".

    The parent describes what its children share; its values bind them, not the tender.
    """
    above: set[str] = set()
    for scope, path in outline.items():
        if scope in candidates and scope in path:
            above.update(h for h in path[: path.index(scope)] if h in candidates)
    return above


def _codes(heading: str) -> list[str]:
    code = code_of(heading)
    return [code] if code else []


def _codes_in(text: str) -> list[str]:
    marks = [m.group(1).replace(" ", "") for m in _CODE_LINE.finditer(text)]
    intro = [m.group(1).replace(" ", "") for m in _CODE_INTRO.finditer(text)]
    return list(dict.fromkeys([*marks, *intro]))


def _states(req: Requirement, scope: str, place: _Place) -> bool:
    """True when the value sits in the article its scope names.

    A chunk under "MODIFICATIONS > 4.0 Généralités" takes the revision block as its
    scope because "Généralités" is generic; its values are the lot's, not the block's.
    """
    chunk = place.chunk(req)
    return chunk is None or chunk.heading == scope


def _contents_twins(items: dict[str, JoineryItem]) -> list[str]:
    """Items read from a table-of-contents entry of an article that also has its own heading.

    The contents line "5.2.1 Porte de garage - Bat" and the article "5.2.1 Porte de
    garage - Battante" are one item: the twin without values goes. Same-numbered items
    with other names ("3.4.7 Châssis repère G", "3.4.7 Châssis repère H") are distinct.
    """
    by_number: dict[str, list[str]] = {}
    for scope in items:
        if m := _NUMBER.match(scope):
            by_number.setdefault(m.group(1), []).append(scope)
    twins: list[str] = []
    for scopes in by_number.values():
        for scope in scopes:
            empty = not items[scope].values
            same = [
                other
                for other in scopes
                if other != scope and other[:25].casefold() == scope[:25].casefold()
            ]
            if empty and same and any(items[o].values or o not in twins for o in same):
                twins.append(scope)
    return twins


def _is_solid(heading: str, texts: list[str]) -> bool:
    """A door said solid ("porte pleine", "bloc-porte aveugle") with no glass named."""
    for text in (heading, " ".join(texts)):
        if _SOLID.search(text):
            return not _GLAZED.search(_SOLID.sub(" ", text))
    return False


def _fits(
    kind: ItemKind,
    req: Requirement,
    *,
    shutters_apart: bool,
    ud_stated: bool,
    solid: bool = False,
) -> bool:
    """Whether a general clause can describe an item of this kind."""
    if kind is ItemKind.SHUTTER:
        return req.field in _SHUTTER_INHERITS
    if solid and req.field in _GLAZING:
        return False
    if req.field == F.SHUTTERS:
        return not shutters_apart  # the tender describes its shutters as items of their own
    if req.field == F.HARDWARE:
        door_part = bool(_DOOR_PARTS.search(req.value))
        if kind is ItemKind.DOOR:
            return door_part or not _WINDOW_PARTS.search(req.value)
        return not door_part
    if req.field == F.FIRE_RATING:
        return kind is ItemKind.DOOR  # a chapter's fire classes are its doors' and walls'

    if req.field == F.UW:
        if kind is ItemKind.DOOR:  # a Uw binds doors only when the tender gives no Ud
            return not (ud_stated and _UW.search(req.value))
        return not _UD.search(req.value)
    return True


def _inherit(
    item: JoineryItem,
    path: list[str],
    general: list[Requirement],
    place: _Place,
    above_items: set[str],
    *,
    shutters_apart: bool = False,
) -> None:
    ud_stated = any(r.field == F.UW and _UD.search(r.value) for r in general)
    own_material = {
        m.group(1).lower()[:3]
        for r in item.own(F.FRAME_MATERIAL)
        if (m := _MATERIAL.search(r.value))
    }
    own = item.own_fields()
    for req in general:
        field = req.field
        # A parent item's description adds to its children's ("Brise-soleil orientable"
        # above "Brise-soleil des bureaux"); a measured value of the child replaces the parent's.
        from_parent = req.scope is not None and req.scope in path
        adds = from_parent and not FIELD_CATALOG[field].numeric and field not in _CLASSES
        if field in _TENDER_WIDE or (field in own and not adds):
            continue
        if not _fits(
            item.kind, req, shutters_apart=shutters_apart, ud_stated=ud_stated, solid=item.solid
        ):
            continue
        chapter = _chapter(place.path(req), req.scope, above_items)
        if path and chapter and path[: len(chapter)] != chapter:
            continue  # a general clause of another chapter or lot
        material = _MATERIAL.search(req.scope or "")
        if material and own_material and material.group(1).lower()[:3] not in own_material:
            continue  # "Menuiseries bois" clauses do not bind an aluminium door
        item.values.setdefault(field, []).append(ItemValue(requirement=req, inherited=True))
