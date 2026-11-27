"""Deterministic extractors: the free, instant first pass.

Most hard numbers in a CCTP follow conventions an estimator recognises at a
glance (``Uw ≤ 1,3 W/m².K``, ``A*3 E*7B V*A2``, ``RAL 7016``, ``4/16/4``,
``NF DTU 36.5``). Regexes catch them with an exact citation at zero cost. The
LLM pass then adds what needs reading comprehension (scope, prose-only
requirements) and the two are merged, agreement raising confidence.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from zelles.domain.documents import Chunk
from zelles.domain.spec import (
    FIELD_CATALOG,
    Citation,
    Requirement,
    RequirementSource,
    RequirementStatus,
    SpecField,
)
from zelles.domain.validators import validate
from zelles.retrieval.text import comparable

F = SpecField
_I = re.IGNORECASE

_SENTENCE_END = re.compile(r"(?<=[.;!?])(?<!\b[A-Z]\.)\s+(?=[A-ZÀ-Ÿ0-9])|\n")


@dataclass(frozen=True)
class Rule:
    field: SpecField
    pattern: re.Pattern[str]
    confidence: float = 0.75
    requires: re.Pattern[str] | None = None  # the sentence must also match this
    excludes: re.Pattern[str] | None = None  # ...and must not match this
    normalize: Callable[[re.Match[str]], str] | None = None
    # the few words just before the match must not match this ("Dn,e,w + Ctr ≥ 39 dB")
    before_excludes: re.Pattern[str] | None = None
    # the sentence or its section headings must match this ("Tenue au feu" > "... sont M1")
    context_requires: re.Pattern[str] | None = None
    # the section headings must not match this (coffre ranges are not facade values)
    heading_excludes: re.Pattern[str] | None = None
    in_heading: bool = False  # also match inside the heading line (standards listed as items)
    # the few words just before the match must match this (the item being rated)
    before_requires: re.Pattern[str] | None = None
    # the section headings must match this ("Volets roulants" > "Dne,w + Ctr = 45 dB")
    heading_requires: re.Pattern[str] | None = None


_BEFORE = 80  # characters looked at by ``before_excludes``


def _material(match: re.Match[str]) -> str:
    word = match.group(0).lower()
    if "bois" in word and "alu" in word:
        return "Bois-aluminium"
    if "pvc" in word and "alu" in word:
        return "PVC-aluminium"
    return {"pvc": "PVC", "aluminium": "Aluminium", "alu": "Aluminium", "bois": "Bois"}.get(
        word, match.group(0)
    )


NUM = r"(\d+(?:[.,]\d+)?)"
CMP = r"(?:\s*(?:[:=]|≤|≥|<\s*/?\s*=|>\s*/?\s*=|<|>|inférieur(?:e)?\s+(?:ou\s+égal\s+)?à|supérieur(?:e)?\s+(?:ou\s+égal\s+)?à|de|d'au plus|d'au moins|maxi(?:mum)?|mini(?:mum)?)\s*)*"
U_UNIT = r"(?:\s*W\s*/\s*\(?\s*m\s*2\s*[.·]?\s*K\s*\)?)?"
PAREN = r"(?:\s*\([^)\n]{0,60}\))?"  # "SWC (facteur solaire hiver sans protection) = 0,38"
DB = r"\s*d\s?\(?B\)?(?:\s*\(?A\)?)?"  # "dB", "dB(A)", "d(B)"

# What sits just before a dB value that belongs to a shutter box or an air inlet.
_NOT_FACADE_DB = re.compile(
    r"(?:Dn\s*,\s*e|coffres?|\bEA\b|entr[ée]es?\s+d'air|grilles?|bouches?)"
    r"(?:(?!\d\s*d\s?\(?B)[^\n]){0,70}$",  # ...with no other dB value in between
    _I,
)
# Same for an air inlet's own rating: not when a shutter box is the item being rated.
_BOX_DB = re.compile(
    r"(?:coffres?|\bEA\b|volets?\s+roulants?)(?:(?!\d\s*d\s?\(?B)[^\n]){0,70}$", _I
)
# Shutter-box sound rating: "Coffres … Dn,e,w + Ctr ≥ 48 dB", "Dne,w,Ctr = 45 dB".
DNEW = r"\bDn\s*,?\s*e\s*,?\s*w\s*[,+]?\s*\+?\s*C\s*tr\b"
_BOX_HEADING = re.compile(r"coffres?|volets?\s+roulants?", _I)
_INLET_ITEM = re.compile(
    r"(?:entr[ée]es?\s+d'air|grilles?|bouches?)(?:(?!\d\s*d\s?\(?B)[^\n]){0,70}$", _I
)
# A material named in a standard's title ("DTU 36.1 / Menuiseries en bois") is no requirement.
_STANDARD_TITLE = re.compile(
    r"\b(?:NF\s+)?DTU\b|D\.T\.U|\b(?:NF|XP|FD)\s?[A-Z]?\s?\d|\bnormes?\b", _I
)
# "type X de chez Y ou équivalent": the product family follows the sentence's subject.
_TYPE_X = (
    r"\b(?:type|gamme|modèle|marque)\s+(?:de\s+)?[^.;\n]{2,60}?ou\s+(?:techniquement\s+)?équivalent"
)
_GLASS_SUBJECT = re.compile(r"\bvitrages?\b|\bverres?\b|\bglaces?\b", _I)
_SAFETY_GLASS = re.compile(r"feuillet|stadip|anti-?\s?chute|effraction|sécurit|\bSP\s?\d", _I)
_SHUTTER_SUBJECT = re.compile(r"\bvolets?\b|\bcoffres?\b|\bstores?\b|\btabliers?\b", _I)
_HARDWARE_SUBJECT = re.compile(
    r"crémone|serrures?|ferme-?\s?portes?|quincaillerie|poignées?|anti-?\s?panique|barres?|"
    r"ventouses?|béquilles?|paumelles?|bandeaux?|limiteurs?|butées?",
    _I,
)
# One character of a hardware part's description. The description keeps the part's
# material, model and maker ("paumelles en acier bichromaté laqué", "… de chez Dorma") and
# ends where a second part or another clause starts ("… avec poignée", "… et permettant",
# "… ou équivalent", "… suivant tableau").
_HW = r"(?:(?!\s+(?:avec|et|ou|pour|suivant|selon|compris)\b)[^.;,\n])"
_SEAL_SUBJECT = re.compile(r"\bjoints?\b|\bmousses?\b|\bbandes?\b|calfeutrement|compriband", _I)
_PRODUCT_NOT_PROFILE = re.compile(
    rf"{_GLASS_SUBJECT.pattern}|{_SHUTTER_SUBJECT.pattern}|{_HARDWARE_SUBJECT.pattern}|"
    rf"{_SEAL_SUBJECT.pattern}|entr[ée]es?\s+d'air|grilles?|isolation|isolants?|laine|panneaux?",
    _I,
)


def _ral(match: re.Match[str]) -> str:
    """'RAL Gris 7007' -> 'gris RAL 7007'; a plain 'gris anthracite RAL 7016' is kept."""
    text = " ".join(match.group(0).split())
    inner = re.match(r"(?i)(.*?)\bRAL\s+([A-Za-zÀ-ÿ ]+?)\s+(\d{4})(.*)", text)
    if inner:
        before, words, code, after = inner.groups()
        return " ".join(f"{before} {words.lower()} RAL {code}{after}".split())
    return text


def _finish(match: re.Match[str]) -> str:
    """One spelling per finish: 'teintées dans la masse' -> 'teinté dans la masse'."""
    text = " ".join(match.group(0).split())
    text = re.sub(r"(?i)\bteint[ée]e?s?(?=\s+dans)", "teinté", text)
    return re.sub(r"(?i)\bthermolaqu[ée]e?s?\b", "thermolaqué", text)


def _date_text(match: re.Match[str]) -> str:
    """Keep the kind of text and its date, drop the title in between."""
    return f"{match.group(1)} du {match.group(2)}"


# The AFNOR alias of a DTU just named, or an index code: "DTU 44.1 (NF P85-210-1)".
_DTU_ALIAS = re.compile(
    r"D\.?\s?T\.?\s?U\.?\s*(?:N°\s*)?\d+(?:[.\-]\d+)*(?:\s+P\s?\d(?:-\d)?)?\s*\(\s*$"
    r"|indice\s+de\s+classement\s*:?\s*$",
    _I,
)
# A standards list whose later codes drop the prefix: the head code, then its items.
_LIST_HEAD = (
    r"(?P<prefix>\b(?:NF\s*\.?\s*|N\.\s?F\.\s*)[A-Z]\s*\.?\s?|\b(?:NF\s+)?D\.?\s?T\.?\s?U\.?\s*(?:N\s*[°º]\s*)?)"
    r"(?P<num>\d{2}(?:\s?[.\-]\s?\d{1,3})?)"
)
_LIST_SEP = r"\s*(?:,|/|\bet\b|&)\s*"
_LIST_ITEM = rf"{_LIST_SEP}(?:\d{{2}}\s?[.\-]\s?\d{{1,3}}|\d{{3}})"
_LIST_RUN = re.compile(rf"{_LIST_HEAD}((?:{_LIST_ITEM})*){_LIST_SEP}$", re.IGNORECASE)


def _list_item(match: re.Match[str]) -> str:
    """'NF P 85-530/540' -> 'NF P 85-540'; 'D.T.U. n° 39.1, 39.4' -> 'D.T.U. n° 39.4'.

    The prefix is repeated as the first code writes it. An item that does not fit
    the head's shape gives an empty value, which validation drops.
    """
    before = match.string[max(0, match.start() - 120) : match.start()]
    runs = list(_LIST_RUN.finditer(before))
    if not runs:
        return ""
    run = runs[-1]
    prefix, num, item = run.group("prefix"), run.group("num"), match.group(0).replace(" ", "")
    if re.search(r"D\.?\s?T\.?\s?U", prefix, re.IGNORECASE):
        return f"{prefix}{item}" if re.fullmatch(r"\d{2}\.\d{1,2}", item) else ""
    head = re.fullmatch(r"(\d{2})\s?([.\-])\s?(\d{3})", num)
    if head is None:
        return ""
    if re.fullmatch(r"\d{3}", item):
        return f"{prefix}{head.group(1)}{head.group(2)}{item}"
    return f"{prefix}{item}" if re.fullmatch(r"\d{2}[.\-]\d{3}", item) else ""


RULES: list[Rule] = [
    # Uw is the whole element's U-value: Ud for doors and Ucw for curtain walls count too.
    Rule(F.UW, re.compile(rf"\b(?:Uw|Ud|Ucw)\b(?:\s+moyen)?{PAREN}{CMP}{NUM}{U_UNIT}", _I), 0.9),
    Rule(F.UG, re.compile(rf"\bUg\b{PAREN}{CMP}{NUM}{U_UNIT}", _I), 0.9),
    Rule(F.UJN, re.compile(rf"\b(?:Ujn|Uws)\b{PAREN}{CMP}{NUM}{U_UNIT}", _I), 0.85),
    Rule(F.SW, re.compile(rf"\b(?:Sw|facteur solaire(?:\s+Sw)?)\b{CMP}{NUM}\s*%?", _I), 0.85),
    Rule(  # "SWC (facteur solaire hiver …) = 0,38", "SW (avec protection) = 0,25"
        F.SW,
        re.compile(rf"\bS\s?W\s?[CE]?\b{PAREN}{CMP}{NUM}\s*%?", _I),
        0.8,
    ),
    Rule(
        F.TLW,
        re.compile(
            rf"\b(?:TLw|TL\s+global|transmission lumineuse(?:\s+TLw)?)\b{PAREN}{CMP}{NUM}\s*%?",
            _I,
        ),
        0.85,
    ),
    Rule(
        F.AEV,
        re.compile(
            r"\bA\s*\*\s*[1-4]\s*[-,/]?\s*E\s*\*\s*(?:[1-9]\s*[AB]?|E\s*\d{3,4})\s*[-,/]?\s*V\s*\*\s*(?:[ABC]\s*[1-5]|E\s*\d{3,4})",
            _I,
        ),
        0.95,
    ),
    Rule(  # "classe A 3 / eau E 7B / vent V A3", "A3 - E7B - VA2"
        F.AEV,
        re.compile(
            r"\bA\s*\*?\s*[1-4]\b[\s\S]{0,45}?\bE\s*\*?\s*(?:[1-9]\s?[AB]?|E\s*\d{3,4})\b[\s\S]{0,45}?\bV\s*\*?\s*(?:[ABC]\s?[1-5]|E\s*\d{3,4})\b",
            _I,
        ),
        0.85,
        requires=re.compile(r"\bair\b|AEV|étanchéité|perméabilité|classement", _I),
    ),
    Rule(
        F.ACOUSTIC,
        re.compile(
            rf"\b(?:R\s*A\s*,?\s*tr|Rw\s*\(\s*C\s*;\s*Ctr\s*\)|Rw\s*\+\s*C\s*tr|Rw)\b{CMP}\s*{NUM}{DB}",
            _I,
        ),
        0.85,
        heading_excludes=re.compile(r"coffres?|volets?|entr[ée]es?\s+d'air|grilles?", _I),
    ),
    Rule(
        F.ACOUSTIC,
        re.compile(
            rf"\b(?:DnT\s*,?\s*A\s*,\s*tr|isolement(?:\s+\w+){{0,2}}\s+de\s+façades?|isolement\s+acoustique|affaiblissement\s+acoustique|classement\s+des?\s+façades?|façades?\s+à)\b[^.;\n]{{0,40}}?{NUM}{DB}",
            _I,
        ),
        0.75,
        before_excludes=_NOT_FACADE_DB,
        heading_excludes=re.compile(r"coffres?|volets?|entr[ée]es?\s+d'air|grilles?", _I),
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # further values in the same sentence: "..., 28 dB pour les autres façades"
        F.ACOUSTIC,
        re.compile(rf"(?<![\w,.])(\d{{2}}){DB}"),
        0.7,
        requires=re.compile(r"Ra\s*,\s*tr|acoustique|affaiblissement|DnT|isolement", _I),
        before_excludes=_NOT_FACADE_DB,
        heading_excludes=re.compile(r"coffres?|volets?|entr[ée]es?\s+d'air|grilles?", _I),
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # a shutter box rated in a list of items: "Coffres de VR … Dn,e,w + Ctr ≥ 48 dB"
        F.ACOUSTIC,
        re.compile(rf"{DNEW}\s*(?:[≥=:]\s*)?(\d{{2}}){DB}", _I),
        0.75,
        before_requires=_BOX_DB,
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # ...or under a shutter heading: "Volets roulants" > "Dne,w,Ctr = 45 dB"
        F.ACOUSTIC,
        re.compile(rf"{DNEW}\s*(?:[≥=:]\s*)?(\d{{2}})(?:\s*(?:à|-)\s*\d{{2}})?{DB}", _I),
        0.75,
        heading_requires=_BOX_HEADING,
        before_excludes=_INLET_ITEM,
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # the upper end of a box range: "Dn,e,w + Ctr ≥ 47 à 42 dB"
        F.ACOUSTIC,
        re.compile(rf"(?<=\d)\s*à\s*(\d{{2}}){DB}", _I),
        0.7,
        requires=re.compile(DNEW, _I),
        heading_requires=_BOX_HEADING,
        before_excludes=_INLET_ITEM,
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(
        F.COLOR,
        re.compile(
            r"(?:\b(?:blanc|gris(?:\s+anthracite|\s+clair|\s+foncé)?|noir|beige|ivoire|bronze|chêne doré)\s+)?\bRAL\s*(?:[A-Za-zé]+\s+){0,2}?\d{4}(?:\s+(?:sablé|mat|satiné|brillant|texturé|fine structure))?",
            _I,
        ),
        0.85,
        normalize=_ral,
    ),
    Rule(
        F.COLOR,
        re.compile(
            r"\b(?:teinte|coloris|couleur|finition)\s*:?\s*(?:blanc(?:he)?|gris(?:\s+(?:anthracite|clair|foncé))?|noir|beige|ivoire|sable|chêne\s+doré|ton\s+bois)\b(?:\s+(?:mat|satiné|brillant|sablé|texturé))?|\b(?:PVC\s+)?blanc(?=\s+teinté\s+dans\s+la\s+masse)|\bPVC\s+blanc\b|\bgris\s+anthracite\b|\bcanon\s+de\s+fusil\b",
            _I,
        ),
        0.7,
        excludes=re.compile(
            r"entr[ée]es?\s+d'air|grilles?|Aldès|Aldes|joints?|quincaillerie|poignées?", _I
        ),
    ),
    Rule(
        F.GLAZING_COMPOSITION,
        re.compile(
            r"(?<![\w/.-])(?!0\d)\d{1,2}(?:[.,]\d)?(?:\s*[/-]\s*(?!0\d)\d{1,2}(?:[.,]\d)?){2,4}(?![\w/-])"
        ),
        0.8,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(  # the gas or a named safety glass inside the build-up: "4/16 argon/4", "SP510/14/4"
        F.GLAZING_COMPOSITION,
        re.compile(
            r"(?<![\w/.-])(?:SP\s?\d{2,3}|\d{1,2}(?:[.,]\d)?)\s*/\s*\d{1,2}\s*(?:argon|krypton|air)?"
            r"\s*/\s*\d{1,2}(?:[.,]\d)?(?![\w/-])",
            _I,
        ),
        0.75,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(  # "4.16.4": dotted notation, the middle number being the gap in mm
        F.GLAZING_COMPOSITION,
        re.compile(r"(?<![\w.])\d{1,2}\.(?:[6-9]|1\d|2[0-4])\.\d{1,2}(?![\w.])"),
        0.7,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(  # the unit's total thickness: "vitrage isolant de 28 mm d'épaisseur"
        F.GLAZING_COMPOSITION,
        re.compile(r"(?<![\w.,])(\d{2})\s*mm\s+d'épaisseur\b", _I),
        0.65,
        before_requires=re.compile(r"vitrages?(?:\s+isolants?)?\s*(?:\(|de\s+|:)?\s*$", _I),
        normalize=lambda m: f"{m.group(1)} mm",
    ),
    Rule(  # "442+16+442": laminated panes written with plus signs
        F.GLAZING_COMPOSITION,
        re.compile(r"(?<![\w+])\d{1,3}(?:\s*\+\s*\d{1,3}){2,4}(?![\w+])"),
        0.75,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(
        F.GLAZING_TYPE,
        re.compile(
            r"\b(?:double|triple)\s+vitrage(?:\s+isolant)?(?:[^.;\n]{0,70}?(?:argon|krypton|émissif|ITR|contrôle solaire))?|\b(?:très\s+)?(?:basse|faible)\s+[ée]missivit[ée]\b|\bcontrôle\s+solaire\b",
            _I,
        ),
        0.75,
    ),
    Rule(  # obscured or special glass, the gas filling, a named float glass
        F.GLAZING_TYPE,
        re.compile(
            r"\b(?:verre\s+|vitrage\s+)?(?:sablé|dépoli|translucide|imprimé|granité|(?<!paroi\s)(?<!parois\s)opaque|occultant)\b|\b(?:remplissage\s+|lame\s+d'|gaz\s+)?argon\b|\bpeu\s+émissif\b|\bisolation\s+thermique\s+renforcée\b|\bplanilux\b",
            _I,
        ),
        0.7,
        requires=_GLASS_SUBJECT,
        excludes=re.compile(r"\bRAL\b|teinte|coloris", _I),
    ),
    Rule(  # the gas filling as an item of a glazing make-up: "- Gaz argon entre les verres"
        F.GLAZING_TYPE,
        re.compile(r"\b(?:remplissage\s+|lame\s+d'|gaz\s+)?(?:argon|krypton)\b", _I),
        0.65,
        before_requires=_GLASS_SUBJECT,
    ),
    Rule(
        F.SAFETY_GLAZING,
        re.compile(
            r"\b(?:vitrage\s+)?(?:feuilleté|trempé)(?:\s+de\s+sécurité)?(?:\s+\d{2}\.\d)?|\bSP\s?\d{2,3}\b|\bP[1-8][AB]\b",
            _I,
        ),
        0.75,
    ),
    Rule(  # "STADIP PROTECT 44.2", "sécurit", "anti-effraction", "anti-chute"
        F.SAFETY_GLAZING,
        re.compile(
            r"\bstadip(?:\s+protect)?(?:\s+\d{2}[.,/-]\d)?\b|\bs[ée]curit\b|\b(?:retardateur\s+d'|anti-?\s?)effraction\b|\banti-?\s?chutes?\b|(?<![\w.,/-])([1-9])\1[.,]\d(?![\w.,/-])",
            _I,
        ),
        0.7,
        requires=re.compile(rf"{_GLASS_SUBJECT.pattern}|{_SAFETY_GLASS.pattern}", _I),
        excludes=re.compile(r"\bserrures?\b|\bportes?\b(?!-fen)|\bvolets?\b", _I),
    ),
    Rule(
        F.SAFETY_GLAZING,
        re.compile(_TYPE_X, _I),
        0.65,
        requires=_SAFETY_GLASS,
    ),
    Rule(
        F.GLAZING_TYPE,
        re.compile(_TYPE_X, _I),
        0.6,
        requires=_GLASS_SUBJECT,
        excludes=_SAFETY_GLASS,
    ),
    Rule(
        F.SPACER,
        re.compile(r"\bintercalaires?\s+[^.;,\n)]{2,40}|\bwarm[- ]edge\b|\bbord chaud\b", _I),
        0.7,
        excludes=re.compile(r"transport|emball|frottement", _I),
    ),
    Rule(
        F.FRAME_MATERIAL,
        re.compile(
            r"\b(?:mixtes?\s+)?(?:bois[- ]alu(?:minium)?|pvc[- ]alu(?:minium)?|PVC|aluminium|bois)\b",
            _I,
        ),
        0.6,
        requires=re.compile(r"menuiserie|fenêtre|porte|châssis|ensemble vitré|ouvrant", _I),
        excludes=re.compile(
            rf"volet|lame|poignée|renfort|coffre|grille|paumelle|charnière|\bbâtis?\b"
            rf"|menuiseries?\s+intérieures?|{_STANDARD_TITLE.pattern}"
            r"|\bBET\b|\bcales?\b|\blaiton\b|\(\s*(?:bois|alu\w*|PVC)\s*,\s*(?:bois|alu\w*|PVC)\s*,",
            _I,
        ),
        normalize=_material,
    ),
    Rule(  # "Bois massif", "bois lamellé-collé": wood named by its kind, even near "lame"
        F.FRAME_MATERIAL,
        re.compile(r"\bbois\s+(?:massif|exotique|résineux|lamellé[- ]collé|aboutés?)\b", _I),
        0.6,
        normalize=lambda m: "Bois",
    ),
    Rule(  # steel doors and frames of a mixed lot: "Porte acier", "profilés acier"
        F.FRAME_MATERIAL,
        re.compile(
            r"\b(?:portes?|menuiseries?|châssis|profilés?|blocs?-?portes?)\s+(?:en\s+)?acier\b", _I
        ),
        0.6,
        normalize=lambda m: "Acier",
    ),
    Rule(
        F.OPENING_TYPE,
        re.compile(
            r"\b(?:oscillo[- ]?battant(?:e|s|es)?|(?:ouvrants?|ouvertures?)\s+à\s+la\s+française|à\s+la\s+française|basculant(?:e|s|es)?|projetant(?:e|s|es)?|coulissant(?:e|s|es)?(?:\s+à\s+galandage)?|galandage|levant[- ]coulissant|châssis\s+fixes?|portes?\s+d'entrée|portes?\s+battantes?\s+motorisées?|soufflets?)\b",
            _I,
        ),
        0.7,
        # a standard's title or the removal of the old windows is not the new opening type
        excludes=re.compile(
            r"\b(?:NF\s+)?(?:DTU|EN)\s?\d|\bdépose|\banciens?\b|\banciennes?\b|anti-?\s?paniques?",
            _I,
        ),
    ),
    Rule(  # "type … ou équivalent" names a profile only when the subject is a profile/window
        F.PROFILE_SYSTEM,
        re.compile(
            r"\b(?:type|gamme|profilés?)\s+[^.;\n]{2,60}?ou\s+(?:techniquement\s+)?équivalent", _I
        ),
        0.65,
        excludes=_PRODUCT_NOT_PROFILE,
    ),
    Rule(  # joinery system makers and their ranges: "TECHNAL", "gamme SOLEAL", "WICSTYLE 65FP"
        F.PROFILE_SYSTEM,
        re.compile(
            r"\b(?:TECHNAL|SCH[ÜU]CO|REYNAERS|KAWNEER|WICONA|SAPA|K-?LINE|INSTALLUX|ALUK|K[ÖO]MMERLING|"
            r"REHAU|VEKA|PROFINE|DECEUNINCK|BIEBER|LORILLARD|MILLET|MINCO|TRYBA|JANNEAU|INTERNORM|JANSEN|"
            r"FORSTER|SEPALUMIC|SOLEAL|LUMEAL|GALENE|WICLINE|WICSTYLE)\b(?:\s?\d{2,3}\s?[A-Z]{0,3}\b)?",
            _I,
        ),
        0.65,
        excludes=re.compile(r"entr[ée]es?\s+d'air|stores?|volets?", _I),
    ),
    Rule(  # glazing bars and traditional wood profiles
        F.PROFILE_SYSTEM,
        re.compile(
            r"\bpetits?\s+bois(?:\s+(?:rapportés|collés|incorporés|intégrés|traversants?))?"
            r"(?:\s+face\s+(?:interne|externe|intérieure|extérieure))?|\bmouton\s+et\s+gueule\s+de\s+loup\b",
            _I,
        ),
        0.65,
        in_heading=True,
    ),
    Rule(
        F.PROFILE_SYSTEM,
        re.compile(
            r"\b(?:\d{2,3}\s*mm[^.;\n]{0,25}?)?\b(?:[3-8]|trois|quatre|cinq|six|sept|huit)\s+chambres\b(?:[^.;\n]{0,50})?",
            _I,
        ),
        0.65,
    ),
    Rule(  # a range listed by name and depth: "- XYZLINE 65 EVO pour les châssis ouvrants"
        F.PROFILE_SYSTEM,
        re.compile(r"\b[A-Z]{4,}\s\d{2,3}(?:\s[A-Z]{2,4})?\b(?=\s+(?:à|pour)\b)"),
        0.6,
        requires=re.compile(r"châssis|murs?\s+rideaux?|portes?|ouvrants?|fenêtres?", _I),
    ),
    Rule(
        F.PROFILE_SYSTEM,
        re.compile(r"\b(?:à\s+)?rupture\s+de\s+pont\s+thermique\b", _I),
        0.65,
        # a property of the profiles, said of them or of the joinery made from them
        requires=re.compile(r"profil|menuiseries?|châssis|fenêtres?|ouvrants?|dormants?", _I),
        excludes=re.compile(rf"{_SHUTTER_SUBJECT.pattern}|{_GLASS_SUBJECT.pattern}", _I),
    ),
    Rule(
        F.FINISH,
        re.compile(
            r"\bteint[ée]e?s?\s+dans\s+la\s+masse\b|\b(?:thermolaqu\w*|laquage|anodisation|plaxage|lasure)\b(?:[^.;,\n]{0,40}?(?:Qualicoat|Qualimarine|Qualanod))?|\b(?:label\s+)?(?:Qualicoat|Qualimarine|Qualanod)\b",
            _I,
        ),
        0.75,
        # the finish of a shutter's guides or of a handle is not the joinery's finish
        excludes=re.compile(
            r"coulisses?|volets?|\blames?\b|tabliers?|coffres?|bavettes?|poignées?|quincaillerie|"
            r"paumelles?|fiches?|garnitures?",
            _I,
        ),
        normalize=_finish,
    ),
    Rule(  # "PVC plaxé", "plaxés ou laqués bi-couleur": the profiles' own finish
        F.FINISH,
        re.compile(r"\bplax[ée]e?s?\b|\blaqu[ée]e?s?\b|\bbi-?\s?couleurs?\b|\bbicolores?\b", _I),
        0.65,
        requires=re.compile(r"PVC|menuiseries?|profil|châssis|ouvrants?|dormants?|fenêtres?", _I),
        excludes=re.compile(
            r"\blames?\b|volets?|coffres?|tabliers?|quincaillerie|poignées?|bavettes?|visserie|"
            r"coulisses?|accessoires?|articles?|paumelles?|fiches?|garnitures?",
            _I,
        ),
    ),
    Rule(  # the wood species and the coating: "mélèze lasuré", "poudre polyester …", "Traitement IFH"
        F.FINISH,
        re.compile(
            r"\b(?:chêne|mélèze|eucalyptus|pin\s+sylvestre|douglas|méranti|moabi|niangon|sipo|iroko|"
            r"red\s+cedar|épicéa|sapin|bois\s+exotique)\b|\bfinition\s+(?:peinte|laquée|lasurée|vernie)"
            r"[^.;,\n]{0,40}|\bpoudre\s+polyester[^.;,\n]{0,60}|\baspect\s+(?:satiné|mat|brillant|sablé)\b|"
            r"\btraitement\s+(?:IFH|fongicide|insecticide)[^.;,\n]{0,40}|\balu(?:minium)?\s+anodisé\b",
            _I,
        ),
        0.6,
        requires=re.compile(
            r"menuiseries?|bois|profil|châssis|fenêtres?|portes?|dormants?|ouvrants?|finition", _I
        ),
        excludes=re.compile(
            r"volets?|\blames?\b|tabliers?|coffres?|quincaillerie|poignées?|paumelles?|ferme-?\s?portes?"
            r"|charpente|parquet|bardage",
            _I,
        ),
    ),
    Rule(  # a varnish is a finish only when it is applied to the joinery, not a site protection
        F.FINISH,
        re.compile(r"\bvernis\b[^.;,\n]{0,25}", _I),
        0.6,
        excludes=re.compile(r"protection|adhési|film|connexes|peinture|ou\s+autres", _I),
    ),
    Rule(
        F.SECURITY_CLASS, re.compile(r"\b(?:RC|CR)\s?[1-6]N?\b(?:\s+selon\s+NF\s+EN\s+1627)?"), 0.85
    ),
    Rule(  # VEMCROS class string
        F.SECURITY_CLASS,
        re.compile(r"\bV\s?\*\s?\d\s+E\s?\*\s?\d\s+M\s?\*\s?\d\s+C\s?R?O\s?S\s?\*\s?\d\b"),
        0.8,
    ),
    Rule(
        F.HARDWARE,
        re.compile(
            rf"\b(?:crémone(?:-serrure)?{_HW}{{0,60}}|paumelles?{_HW}{{0,50}}|ferme-?\s?portes?{_HW}{{0,60}}|poignées?{_HW}{{0,50}}|renvois?\s+d'angle{_HW}{{0,30}}|barres?\s+de\s+man(?:œ|oe)uvre{_HW}{{0,30}}|(?:système\s+|quincaillerie\s+)?(?:Winkhaus|Roto|Siegenia|Ferco|Maco|Sobinco|Hoppe|Assa\s+Abloy|Dormakaba|Vachette)\b[^.;,\n]{{0,30}})",
            _I,
        ),
        0.6,
    ),
    Rule(  # further hardware named in a fitting list
        F.HARDWARE,
        re.compile(
            rf"\b(?:tringlerie|serrures?|béquilles?|(?:ferrage\s+(?:par\s+)?|paumelles\s+ou\s+)fiches|fiches\s+(?:bichromat\w+|réglables|laquées)|gâches?(?:\s+de\s+sécurité)?|ferme[- ]portes?|bandeaux?\s+ventouses?|ventouses?|anti-?\s?paniques?|contacteurs?\s+d'ouverture|contacteurs?\s+à\s+cl[ée]f?s?|compas(?:\s+(?:limiteurs?|de\s+sécurité))?|loqueteaux?|limiteurs?\s+d'ouverture|limitateurs?\s+de\s+débattement|houssette|rosettes?|cylindres?|butées?|sélecteurs?\s+de\s+vantail|supports?\s+d'angle|ailes?\s+de\s+préhension|ferrures|arrêts?\s+de\s+portes?|verrous?)\b{_HW}{{0,60}}",
            _I,
        ),
        0.6,
        # a part the contractor must not supply is no requirement ("pas d'option serrures");
        # a stop on a shutter's slat is a shutter part ("lame finale … butée d'arrêt")
        excludes=re.compile(
            r"\bvolets?\s+roulants?\b|\bpas\s+d'option|\bhors\s+lot\b|options?\s+(?:sont\s+)?disponibles"
            r"|\btabliers?\b|\blames?\s+finales?\b",
            _I,
        ),
    ),
    Rule(  # quality mark of hinges and locks, a certification like NF Fermetures
        F.CERTIFICATIONS,
        re.compile(r"\b(?:NF\s*[-./]?\s*)?S\.?N\.?F\.?Q\.?(?:\s*-?\s*1)?\b"),
        0.6,
    ),
    Rule(
        F.HARDWARE,
        re.compile(_TYPE_X, _I),
        0.6,
        requires=_HARDWARE_SUBJECT,
        excludes=re.compile(rf"{_GLASS_SUBJECT.pattern}|{_SHUTTER_SUBJECT.pattern}", _I),
    ),
    Rule(
        F.SHUTTERS,
        re.compile(
            r"\bvolets?\s+roulants?[^.;\n]{0,90}|\bstores?\s+(?:intérieurs?|extérieurs?|occultants?|vénitiens?|bannes?|à\s+projection|à\s+l'italienne|enrouleurs?|screens?)[^.;,\n]{0,40}|\bmanivelle\b|\bpersiennes?\b[^.;\n]{0,80}|\bvolets?\s+battants?[^.;\n]{0,60}|\bBSO\b|\bbrise-soleil[^.;,\n]{0,40}|\bcoffre\s+(?![-–]|afin\b)[^.;,\n]{2,40}|\bman(?:œ|oe)uvre\s+(?:manuelle|électrique|motorisée|radio|solaire|par\s+(?:sangle|treuil|manivelle))(?:(?!\s+(?:pour|avec)\b)[^.;\n]){0,40}",
            _I,
        ),
        0.65,
        excludes=re.compile(r"\b(?:Sw|Uw|Ug|TLw)\b", _I),  # a performance line, not a shutter spec
    ),
    Rule(  # box form and drive anywhere in a shutter sentence, even past the clause window
        F.SHUTTERS,
        re.compile(
            r"\b(?:monoblocs?|blocs?[- ]baies?|coffres?\s+(?:tunnels?|demi[- ]linteaux?)|"
            r"treuils?|sangles?|tringles?|motoris[ée]e?s?|radio|filaires?)\b",
            _I,
        ),
        0.6,
        requires=_SHUTTER_SUBJECT,
        excludes=re.compile(r"facteur\s+solaire|\bSw\b|entr[ée]es?\s+d'air", _I),
    ),
    Rule(  # an item listed under a shutter article: "- tablier composé de lames …", "- motorisation …"
        F.SHUTTERS,
        re.compile(
            r"(?<=\n)[-*•–]?\s*((?:la\s+|le\s+|les\s+)?(?:motorisation|moteurs?|tabliers?|lames?|coulisses?|"
            r"commandes?|inverseurs?|verrouillages?|treuils?|sangles?|manivelles?|fins?\s+de\s+course|"
            r"capteurs?|anémomètres?|stations?\s+météo|automatismes?|télécommandes?|lame\s+finale)"
            r"\b[^;\n]{0,80})",
            _I,
        ),
        0.6,
        heading_requires=re.compile(
            r"volets?|stores?|brise-?\s?soleil|BSO|persiennes?|protections?\s+solaires?|occultations?",
            _I,
        ),
        normalize=lambda m: m.group(1).strip(" ;:,"),
    ),
    Rule(  # decorative or fixed shutters, motors, anti-lift locks, named makers
        F.SHUTTERS,
        re.compile(
            r"\bvolets?\s+(?:décoratifs|fixes|bois)(?:\s+(?:fixes|décoratifs))?\b|\bmoteurs?\s+tubulaires?\b|\bmoteurs?\s+(?:de\s+chez\s+)?(?-i:[A-Z]{4,})\b|\banti-?\s?soul[èe]vement\b|\b(?:Griesser|Somfy|Simu|Bubendorff|Profalux)\b",
            _I,
        ),
        0.6,
    ),
    Rule(
        F.SHUTTERS,
        re.compile(_TYPE_X, _I),
        0.6,
        requires=_SHUTTER_SUBJECT,
        excludes=re.compile(rf"{_HARDWARE_SUBJECT.pattern}|{_GLASS_SUBJECT.pattern}", _I),
    ),
    Rule(  # a maker named under a shutter heading: "volets pleins de chez Dupont"
        F.SHUTTERS,
        re.compile(r"\bde\s+chez\s+((?-i:[A-Z][a-zà-ÿ]+|[A-Z]{3,}))\b", _I),
        0.6,
        heading_requires=re.compile(r"volets?|persiennes?|stores?|fermetures?", _I),
        excludes=re.compile(rf"{_HARDWARE_SUBJECT.pattern}|{_GLASS_SUBJECT.pattern}", _I),
        normalize=lambda m: m.group(1),
    ),
    Rule(  # where the inlets go: "entrées d'air … dans les coffres de volets roulants"
        F.AIR_INLETS,
        re.compile(
            r"\bentr[ée]es?\s+d'air[^.;\n]{0,60}?\b(?:dans|sur|en)\s+(?:les?\s+|la\s+)?(?:coffres?[^.;,\n]{0,30}|traverses?\s+hautes?|façades?\s+maçonnées?|imposte)",
            _I,
        ),
        0.7,
    ),
    Rule(  # a location item under an air-inlet article: "- dans les coffres de VR des pièces sèches"
        F.AIR_INLETS,
        re.compile(
            r"\b(?:dans|sur)\s+les?\s+(?:coffres?\s+de\s+(?:VR|volets?\s+roulants?)|traverses?\s+(?:hautes?|supérieures?))\b",
            _I,
        ),
        0.65,
        context_requires=re.compile(r"entr[ée]es?\s+d'air|grilles?\s+d'entr|bouches?\s+d'", _I),
    ),
    Rule(  # acoustic rating of the inlet: "Entrées d'air dans châssis Dn,e,w + Ctr ≥ 39 dB"
        F.AIR_INLETS,
        re.compile(rf"\bDn\s*,\s*e\s*,\s*w\s*\+?\s*C\s*tr\s*(?:[≥=:]\s*)?(\d{{2}}){DB}", _I),
        0.7,
        context_requires=re.compile(r"entr[ée]es?\s+d'air|grilles?|bouches?", _I),
        before_excludes=_BOX_DB,
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # "entrée d'air hygro-régulée à affaiblissement acoustique -37dB minimum"
        F.AIR_INLETS,
        re.compile(rf"\bentr[ée]es?\s+d'air\b[^.;\n]{{0,70}}?(\d{{2}}){DB}", _I),
        0.7,
        excludes=re.compile(r"coffres?|\bEA\b", _I),
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # a maker named for the inlets
        F.AIR_INLETS,
        re.compile(r"\b(?:Aldes|Aldès|Anjos|Renson)\b", _I),
        0.65,
        requires=re.compile(r"\bair\b|ventilation|VMC|mortais|grilles?|bouches?", _I),
    ),
    Rule(
        F.AIR_INLETS,
        re.compile(
            r"\bclapets?\s+de\s+ventilation\b[^.;,\n]{0,30}|\b(?:auto|hygro)\s*-?\s*r[ée]g(?:l|ul)(?:ables?|ée?s?)\b(?:\s+type\s+[AB]\b)?",
            _I,
        ),
        0.65,
        requires=re.compile(r"\bair\b|ventilation|VMC|mortais|grilles?|bouches?", _I),
    ),
    Rule(
        F.ACCESSIBILITY,
        re.compile(
            r"\bPMR\b[^.;\n]{0,60}|\bseuil[^.;,\n]{0,60}|\beffort de man(?:œ|oe)uvre[^.;,\n]{0,40}"
            r"|\b(?:hauteur|poignées?|organes?\s+de\s+man(?:œ|oe)uvre|commandes?|man(?:œ|oe)uvres?)\b[^.;\n]{0,50}?\b[01][.,]\d{2}\s*m\b(?:\s*(?:et|à|-)\s*[01][.,]\d{2}\s*m\b)?",
            _I,
        ),
        0.65,
        excludes=re.compile(
            r"\b(?:NF\s+)?EN\s?\d{4,5}\b", _I
        ),  # a standard's title, not a requirement
    ),
    Rule(  # clear passage for wheelchair users: "ouverture ≥ 80 cm"
        F.ACCESSIBILITY,
        re.compile(
            r"\b(?:ouverture|passage(?:\s+libre)?|largeur)\s*(?:de\s+|≥\s*|d'au\s+moins\s+|minimale?\s+de\s+)?\d{2,3}\s*cm\b",
            _I,
        ),
        0.65,
        context_requires=re.compile(r"accès|handicap|PMR|passage|seuil", _I),
    ),
    Rule(
        F.INSTALLATION,
        re.compile(
            r"\bpos(?:e|ée?s?)\s+en\s+(?:applique|tunnel|rénovation)[^.;,\n]{0,40}|\bdépose\s+(?:des?\s+)?(?:menuiseries|châssis|fenêtres|ouvrages)\s+existant(?:e?s)?\b|\bdépose\s+(?:du\s+ou\s+des|des?|du)\s+(?:vantaux|ouvrants?|dormants?)\b|\b(?:menuiseries?|fenêtres?|châssis)\s+(?:PVC\s+|aluminium\s+|bois\s+)?de\s+rénovation\b|\bdépose\s+totale\b|\bsur\s+dormant\s+existant\b",
            _I,
        ),
        0.75,
        # a standard's title in a reference list: "DTU 37.2 : … en rénovation sur dormant existant"
        excludes=re.compile(r"\bD\.?\s?T\.?\s?U\.?\s*(?:N°\s*)?\d+(?:\.\d+)?\s*[:/–]", _I),
    ),
    Rule(  # sealing and fixing of the frame: "mousse imprégnée de classe 1", "pattes à scellement"
        F.INSTALLATION,
        re.compile(
            r"\b(?:mousses?\s+imprégnées?|compri-?band\w*|mastics?|précadres?|bavettes?|"
            r"pat(?:t)?es?\s+(?:à\s+scellement|de\s+fixation)|joints?\s+(?:souples?|portefeuille|de\s+calfeutrement)|"
            r"fixations?\s+(?:mécaniques?|par\s+vis|invisibles?)|couvre-?\s?joints?)\b[^.;,\n]{0,60}",
            _I,
        ),
        0.6,
        excludes=re.compile(rf"{_GLASS_SUBJECT.pattern}|parclose|volets?|coffres?", _I),
    ),
    Rule(  # removal of the old joinery: "La dépose des portes, fenêtres ou volets existants"
        F.INSTALLATION,
        re.compile(
            r"\bdépose\s+(?:des?|du)\s+(?:portes?|fenêtres?|volets?|menuiseries|châssis)\b", _I
        ),
        0.65,
        requires=re.compile(r"existant", _I),
    ),
    Rule(  # rebate fixing of the frame; glass set in a rebate is glazing, not installation
        F.INSTALLATION,
        re.compile(r"\bpos(?:e|ée?s?)\s+en\s+feuillures?[^.;,\n]{0,40}", _I),
        0.7,
        excludes=re.compile(rf"{_GLASS_SUBJECT.pattern}|\bprofilés?\b", _I),
    ),
    Rule(  # short, typed installation details; no free-text caulking sentences
        F.INSTALLATION,
        re.compile(
            r"\bpos(?:e|ée?s?)\s+sur\s+(?:équerres?|cornières?|rejingots?|précadres?)\b|\btapées?(?:\s+(?:d'isolation|intégrées|rapportées|de\s+doublage|de\s+rattrapage))?\b|\bcompriband\b|\bappui\s+déporté\b|\bILLMOD(?:\s+(?-i:[A-Z0-9][A-Z0-9]+))?\b",
            _I,
        ),
        0.65,
    ),
    Rule(
        F.STANDARDS,
        re.compile(
            r"\b(?<!NF )(?<!FD )(?<!XP )(?<!PR )D\.?\s?T\.?\s?U\.?\s*(?:N°\s*)?\d+(?:\.\d+)?(?:-\d{1,2}\b)?"
            r"(?:\s*/\s*\d+(?:\.\d+)?)*(?:\s+P\s?\d(?:-\d)?\b)?|\bEurocode\s?\d\b|\b(?<!EN )(?<!NF )ISO\s?\d{3,5}(?:-\d+)*\b",
            _I,
        ),
        0.9,
        in_heading=True,
    ),
    Rule(  # AFNOR: "NF DTU 36.5", "NF EN 14351-1", "NF.P 08.322", "N.F. P 26 102", "NFP 01-010"
        F.STANDARDS,
        re.compile(
            r"\b(?<!FD )(?<!XP )(?<!PR )(?:NF|N\.\s?F\.)\s*\.?\s*(?:(?:D\.?\s?T\.?\s?U\.?|EN(?:\s+ISO)?)\s*\.?\s?\d{1,5}"
            r"|[A-Z]\s*\.?\s?(?:\d{3,5}|\d{1,2}(?=\s?[.\-]\s?\d|\s\d{3}\b)))(?:\s?[.\-]\s?\d{1,4}|\s\d{3}\b)*"
            r"(?:\s+P\s?\d(?:-\d)?)?(?:\s*/\s*(?:A\d|NA|IN\d?))?\b"
        ),
        0.9,
        before_excludes=_DTU_ALIAS,
        in_heading=True,
    ),
    Rule(  # bare European numbers in a standards context: "conforme à la norme EN 1125"
        F.STANDARDS,
        re.compile(r"(?<![\w.])(?<!NF )(?<!ISO )EN\s?(?:\d{2}\s\d{3}|\d{3,5})(?:-\d+)*\b"),
        0.8,
        requires=re.compile(r"normes?|conformes?|essais?|classification|selon", _I),
        in_heading=True,
    ),
    Rule(  # a list continued with bare numbers: "EN 12207, 12208 et 12210"
        F.STANDARDS,
        re.compile(r"(?<![\w.\-])\d{4,5}(?:-\d+)*\b"),
        0.8,
        before_requires=re.compile(
            r"\bEN\s?\d{3,5}(?:-\d+)*(?:\s*(?:,|/|et|&)\s*(?:EN\s?)?\d{3,5}(?:-\d+)*)*"
            r"\s*(?:,|/|et|&)\s*$"
        ),
        normalize=lambda m: f"EN {m.group(0)}",
        in_heading=True,
    ),
    Rule(  # AFNOR without the NF prefix: "XP P 20-650", "FD P 20-201", "D.T.U. P 06.011"
        F.STANDARDS,
        re.compile(
            r"\b(?:XP|FD|GA|BP|D\.?\s?T\.?\s?U\.?)\s*(?:N°\s*)?[PBASTEX]\s*\.?\s?\d{2}\s?[.\-]\s?\d{3}(?:-\d+)*\b"
        ),
        0.85,
        before_excludes=_DTU_ALIAS,
        in_heading=True,
    ),
    Rule(  # ...or bare in a reference context: "Règles NV 65 (P 06-011)"
        F.STANDARDS,
        re.compile(r"(?<![\w.])(?<!NF )(?<!XP )(?<!FD )[PB]\s?\.?\s?\d{2}\s?[.\-]\s?\d{3}\b"),
        0.75,
        requires=re.compile(r"normes?|règles|conformes?|selon|DTU|D\.T\.U", _I),
        # a prefix of its own, or the AFNOR alias of a DTU just named: "NF DTU 37.1 (P24-203)"
        before_excludes=re.compile(
            r"(?:XP|FD|GA|BP|D\.?\s?T\.?\s?U\.?|NF)\s*(?:N°\s*)?$"
            r"|D\.?\s?T\.?\s?U\.?\s*(?:N°\s*)?\d+(?:[.\-]\d+)*\s*\(\s*$"
            r"|indice\s+de\s+classement\s*:?\s*$",
            _I,
        ),
        in_heading=True,
    ),
    Rule(  # numbered CSTB guides: "Cahier du CSTB n° 3521", "e-cahier du CSTB 3600"
        F.STANDARDS,
        re.compile(r"\b(?:e-?\s?)?cahiers?\s+(?:du\s+)?CSTB\s*(?:n\s*[°º]\s*)?(\d{4})\b", _I),
        0.8,
        normalize=lambda m: f"Cahier du CSTB {m.group(1)}",
        in_heading=True,
    ),
    Rule(  # the prefix is part of the code: "FD DTU 34.2", "XP CEN/TS 1234", "PR NF EN 1279"
        F.STANDARDS,
        re.compile(
            r"\b(?:FD|XP|PR)\s+(?:NF\s+)?(?:D\.?\s?T\.?\s?U\.?\s*(?:N°\s*)?\d+(?:\.\d+)?(?:\s+P\s?\d(?:-\d)?\b)?"
            r"|(?:EN|CEN\s*/\s*TS)(?:\s+ISO)?\s?\d{3,5}(?:-\d+)*\b)"
        ),
        0.85,
        in_heading=True,
    ),
    Rule(  # other bodies' codes: "DIN 18055", "ENV 13050", "UTE C 73.897", "IT 249", "CM 66"
        F.STANDARDS,
        re.compile(
            r"\bDIN\s+(?:EN\s+)?\d{3,5}(?:-\d+)*\b|\bENV\s?\d{3,5}(?:-\d+)*\b"
            r"|\bUTE\s+C\s?\d{2}\s?[.\-]\s?\d{3}\b|\bIT\s?2\d{2}\b|\bCM\s?66\b"
        ),
        0.8,
        in_heading=True,
    ),
    Rule(  # a list sharing the first code's prefix: "NF P 85-530/540", "DTU 31.2 et 31.4"
        F.STANDARDS,
        re.compile(
            r"(?<![\w.\-])(?:\d{2}\s?[.\-]\s?\d{1,3}|\d{3})(?![\w]|\s?[.\-]\s?\d)"
            r"(?!\s*(?:mm|cm|m\b|m2|m²|kg|%|°|dB|Pa\b|h\b))"
        ),
        0.75,
        before_requires=re.compile(rf"{_LIST_HEAD}(?:{_LIST_ITEM})*{_LIST_SEP}$", _I),
        normalize=_list_item,
        in_heading=True,
    ),
    Rule(  # snow and wind rules
        F.STANDARDS,
        re.compile(r"\bN\.?\s?V\.?\s?(?:65|84)\b|\b(?<!R)N\s?84\b"),
        0.8,
        in_heading=True,
    ),
    Rule(
        F.CERTIFICATIONS,
        re.compile(
            r"\b(?:marquage\s+CE|Avis\s+Technique(?:\s+du\s+CSTB)?|\bDTA\b|CEKAL"
            r"|Acotherm(?:\s+AC\s?[1-4]?(?:\s*[-/]?\s*Th\s?\d{1,2})?)?"
            r"|AC\s?[1-4]\s*[-/]?\s*Th\s?(?:[5-9]|1[0-2])|marque\s+NF(?:\s+Fermetures?)?|PEFC|FSC"
            r"|NF\s+Fermetures?|(?:NF\s*[/-]\s*)?CSTB[aâ]t|certification\s+QB|C\.?E\.?R\.?F\.?F"
            r"|S\.?N\.?J\.?F|NF\s?\.?\s?CTB|NF\s+Habitat(?:\s+HQE)?|VEMCROS|label\s+NF\s?Q"
            r"|ECCA|E\.?\s?W\.?\s?A\.?\s?A|NF\s*-?\s*CSTB\s+certified)\b",
            _I,
        ),
        0.85,
    ),
    Rule(  # numbered NF marks: "marque NF040", "certification « NF 252 »"
        F.CERTIFICATIONS,
        re.compile(r"\b(?:marque|certification|label)\s+\"?\s*(NF\s?-?\s?\d{3})\b", _I),
        0.75,
        normalize=lambda m: m.group(1),
    ),
    Rule(  # the NF mark alone: "La certification minimale requise est la certification NF."
        F.CERTIFICATIONS,
        re.compile(r"\b[Cc]ertification\s+(NF)\b(?![\s\-]*(?:\d|[A-Z]))"),
        0.7,
        normalize=lambda m: m.group(1),
    ),
    Rule(  # lock, wood and quality marks: "A2P", "CTB-P+", "certification D.24", "ISO 14001"
        F.CERTIFICATIONS,
        re.compile(r"\b[Aa]\s?2\s?[Pp]\b|\bCTB\s?-?\s?(?:P\+|B\+|LCA\b|[AF]\b)"),
        0.75,
    ),
    Rule(
        F.CERTIFICATIONS,
        re.compile(
            r"\bcertification\s+(D\.\s?\d{2})\b|\bcertificat\w*\s+(?:de\s+qualité\s+)?"
            r"(ISO\s?(?:9001|14001|45001|50001))\b",
            _I,
        ),
        0.7,
        normalize=lambda m: m.group(1) or m.group(2),
    ),
    Rule(  # fire resistance: "EI 30", "E30", "(EI / 60)" in a fire context
        F.FIRE_RATING,
        re.compile(
            r"\b(E\s?I|EW|E)\s?(?:/\s?)?(15|20|30|45|60|90|120|180|240)\b(?!\s*(?:mm|cm|%|°|kg|dB))"
        ),
        0.85,
        context_requires=re.compile(
            r"\bfeu\b|incendie|coupe|pare-?\s?flammes?|\bCF\b|\bPF\b|\bEI\b|résistance", _I
        ),
        normalize=lambda m: f"{m.group(1).replace(' ', '')} {m.group(2)}",
    ),
    Rule(  # fire degrees: "CF1h", "PF ½ heure", "coupe-feu 1/2 heure"
        F.FIRE_RATING,
        re.compile(
            r"\b(?:CF|PF|coupe-?\s?feu|pare-?\s?flammes?)\s*(?:de\s+)?(?:1\s?[/⁄]\s?2|[12])\s*h(?:eures?)?\b",
            _I,
        ),
        0.8,
    ),
    Rule(  # reaction to fire, Euroclass: "B-s2,d0", "A2-s1, d0"
        F.FIRE_RATING,
        re.compile(r"\b(?:A[12]|[B-F])\s?-\s?s\s?[123]\s?,\s?d\s?[012]\b"),
        0.85,
    ),
    Rule(  # reaction to fire, M class: "classement M1"
        F.FIRE_RATING,
        re.compile(r"\b(?:classement|classé|classe)\s+M[0-4]\b", _I),
        0.8,
    ),
    Rule(  # fire reaction class under a fire heading: "Les menuiseries PVC sont M1 ou M2"
        F.FIRE_RATING,
        re.compile(r"(?<![/.])\bM[0-4]\b(?!\s*[.·]?\s*K\b|\s*/)"),  # not the unit "M2.K/W"
        0.7,
        context_requires=re.compile(r"\bfeu\b|incendie", _I),
    ),
    Rule(
        F.REGULATION,
        re.compile(
            r"\b(arrêtés?|décrets?|circulaires?|ordonnances?)\b[^.;\n]{0,70}?\bdu\s+(\d{1,2}(?:er)?\s+[a-zéû]+\s+\d{4})\b",
            _I,
        ),
        0.85,
        normalize=_date_text,
    ),
    Rule(
        F.REGULATION,
        re.compile(
            r"\b(?:RE\s?2020|RT\s?2012|RT\s+existant|réglementation\s+(?:incendie|parasismique|thermique)(?:\s+20\d\d)?|\bERP\b)",
            _I,
        ),
        0.85,
    ),
]


# Sections that describe the existing building, not what the contractor must supply.
_EXISTING = re.compile(r"\bexistant(?:e?s)?\b|\bétat\s+des\s+lieux\b|\bconstat\b", _I)
_WORKS = re.compile(r"\bdépose|démolition|remplacement|travaux|reprise|adaptation|neuf", _I)

# Descriptive fields: one value per article and trigger word is enough
# ("persienne", "persienne)", "Persienne offrant..." are the same requirement).
_ONE_PER_ARTICLE = frozenset(
    {
        F.SHUTTERS,
        F.HARDWARE,
        F.AIR_INLETS,
        F.COLOR,
        F.FINISH,
        F.INSTALLATION,
        F.ACCESSIBILITY,
        F.PROFILE_SYSTEM,
        F.GLAZING_TYPE,
        F.SPACER,
        F.OPENING_TYPE,
        F.SAFETY_GLAZING,
    }
)

# Descriptive fields are not read from a reference list item ("- NF P 78-303 Verre feuilleté",
# "N.F. P 26 303 Crémone : caractéristiques") nor from a list of works outside the lot.
_DESCRIPTIVE = frozenset(
    {
        F.HARDWARE,
        F.SAFETY_GLAZING,
        F.GLAZING_TYPE,
        F.ACCESSIBILITY,
        F.FINISH,
        F.OPENING_TYPE,
        F.FRAME_MATERIAL,
        F.SHUTTERS,
        F.INSTALLATION,
    }
)
_REFERENCE_ITEM = re.compile(
    r"^\W*(?:NF\b|N\.\s?F\.|EN\s?\d|ISO\s?\d|D\.?\s?T\.?\s?U\b|[PBA]\s?\d{2}[.\-]\d)"
)
_EXCLUSION_LEAD = re.compile(
    r"\bne\s+(?:font|fait)\s+pas\s+partie\b|\bprestations?\s+exclues?\b|\bsont\s+exclus\b", _I
)
# The handle's position is an accessibility rule, not a hardware spec.
_HANDLE_POSITION = re.compile(r"\bpositionn[ée]|\bréglementation|\bconformément", _I)


# Head words too generic to tell two values apart on their own: "volets battants" and
# "volets roulants", "pose en tunnel" and "pose en applique" are different requirements.
_GENERIC_HEADS = frozenset(
    {"volet", "pose", "posé", "posée", "ral"}  # "RAL 8004 ou … RAL 8003": two colours
    | {"dan", "sur"}  # location items: "dans les coffres …", "dans les traverses …"
)
_FILLERS = frozenset({"en", "de", "du", "des", "la", "le", "les", "l", "d", "sur", "à", "par"})


def _slot_word(value: str) -> str:
    """The word that names a descriptive value within its article.

    Usually the first word, so that "persienne" and "Persienne offrant …" count
    once; when that word is a generic head, its first qualifier is added.
    """
    words: list[str] = [str(w).rstrip("s") for w in re.findall(r"\w+", value.lower())]
    if not words:
        return ""
    head = words[0]
    if head not in _GENERIC_HEADS:
        return head
    qualifier = next((w for w in words[1:] if w not in _FILLERS), "")
    return f"{head} {qualifier}".strip()


_ACCESS_CONTEXT = re.compile(
    r"\bPMR\b|handicap|accessib|mobilité\s+réduite|\d\s*cm\b|ressaut|plan\s+incliné", _I
)


def _excluded_spans(body: str) -> list[tuple[int, int]]:
    """Lines listed after "Ne font pas partie du présent lot :" up to the next lead-in line."""
    spans: list[tuple[int, int]] = []
    for lead in _EXCLUSION_LEAD.finditer(body):
        start = body.find("\n", lead.end())
        if start < 0:
            continue
        end = start
        for line in re.finditer(r"[^\n]*\n?", body[start + 1 :]):
            text = line.group(0).strip()
            if not text.startswith(("-", "•", "▪", "–", "o ")):  # the list ends with its items
                break
            end = start + 1 + line.end()
        spans.append((start, end))
    return spans


def describes_existing(chunk: Chunk) -> bool:
    """True when the chunk sits under a heading about the existing building."""
    return any(_EXISTING.search(s) and not _WORKS.search(s) for s in chunk.section_path)


def sentences(text: str) -> Iterator[tuple[int, int]]:
    start = 0
    for m in _SENTENCE_END.finditer(text):
        yield start, m.start()
        start = m.end()
    yield start, len(text)


def _sentence_around(text: str, pos: int) -> str:
    for start, end in sentences(text):
        if start <= pos <= end:
            return text[start:end].strip()
    return text.strip()


def _keep(
    rule: Rule,
    match: re.Match[str],
    *,
    body: str,
    sentence: str,
    headings: str,
    outside_lot: list[tuple[int, int]],
) -> bool:
    """Apply a rule's context checks to one match."""
    if rule.requires is not None and not rule.requires.search(sentence):
        return False
    if rule.excludes is not None and rule.excludes.search(sentence):
        return False
    if rule.context_requires is not None and not rule.context_requires.search(
        f"{sentence} {headings}"
    ):
        return False
    before = body[max(0, match.start() - _BEFORE) : match.start()]
    if rule.before_excludes is not None and rule.before_excludes.search(before):
        return False
    if rule.before_requires is not None and not rule.before_requires.search(before):
        return False
    if rule.field in _DESCRIPTIVE and (
        _REFERENCE_ITEM.search(sentence) or any(a <= match.start() < b for a, b in outside_lot)
    ):
        return False
    word = match.group(0).lower()
    if rule.field == F.HARDWARE and word.startswith("poign") and _HANDLE_POSITION.search(sentence):
        return False  # the accessibility note on handle height, not a handle spec
    # a threshold is an accessibility item only in a PMR context
    return not (
        rule.field == F.ACCESSIBILITY
        and word.startswith("seuil")
        and not _ACCESS_CONTEXT.search(f"{sentence} {headings}")
    )


def _whole_words(body: str, match: re.Match[str]) -> str:
    """The match, finished to the end of its last word.

    Rules take a bounded window after a keyword ("5 chambres" + up to 50
    characters), which can stop mid-word: "type Gamme Con". The value an
    estimator reads must not end on a fragment.
    """
    end = match.end()
    if end == match.start() or not body[end - 1 : end].isalnum():
        return match.group(0)
    while end < len(body) and end - match.end() < 40 and body[end].isalnum():
        end += 1
    return body[match.start() : end]


# Quotes around a word are typography, not part of the value ('crémone "pompier"').
_QUOTES = re.compile(r"[\"“”«»]")
# Known text-extraction artefacts, mended in the value (the citation keeps the source as read).
_OCR_FIXES = ((re.compile(r"\bmanceuvre", _I), "manœuvre"),)


def _clean(text: str) -> str:
    """A value as an estimator reads it: one space between words, no quotes, no OCR slips."""
    for slip, fix in _OCR_FIXES:
        text = slip.sub(fix, text)
    return " ".join(_QUOTES.sub(" ", text).split()).rstrip(" ,;:")


def extract_with_rules(chunks: list[Chunk]) -> list[Requirement]:
    """Run every rule over every chunk and return cited requirements."""
    found: dict[tuple[str, str, str], Requirement] = {}
    per_slot: dict[tuple[SpecField, str], tuple[str, str, str]] = {}
    for chunk in chunks:
        if describes_existing(chunk):
            continue
        body = chunk.text
        # The heading line is context, not a requirement ("4.1 Volets roulants").
        skip = len(chunk.heading) if chunk.heading and body.startswith(chunk.heading) else 0
        headings = " > ".join(chunk.section_path)
        outside_lot = _excluded_spans(body)
        for rule in RULES:
            if rule.heading_excludes is not None and rule.heading_excludes.search(headings):
                continue
            if rule.heading_requires is not None and not rule.heading_requires.search(headings):
                continue
            for match in rule.pattern.finditer(body):
                if match.start() < skip and not rule.in_heading:
                    continue
                sentence = _sentence_around(body, match.start())
                if not _keep(
                    rule,
                    match,
                    body=body,
                    sentence=sentence,
                    headings=headings,
                    outside_lot=outside_lot,
                ):
                    continue
                raw = _clean(_whole_words(body, match))
                value = rule.normalize(match) if rule.normalize else raw
                check = validate(rule.field, value)
                if not check.ok:
                    continue
                req = Requirement(
                    field=rule.field,
                    value=check.normalized or value,
                    numeric_value=check.numeric_value,
                    unit=FIELD_CATALOG[rule.field].unit,
                    comparator=check.comparator,
                    scope=chunk.scope,
                    citation=Citation(
                        chunk_id=chunk.id,
                        quote=sentence,
                        page=chunk.page_at(match.start()),
                        locator=chunk.locator(),
                        match_score=1.0,
                    ),
                    source=RequirementSource.RULES,
                    status=RequirementStatus.VERIFIED,
                    confidence=rule.confidence,
                )
                key = req.dedupe_key()
                if rule.field in _ONE_PER_ARTICLE:
                    # hardware parts now carry their qualifiers: two gâches in one article
                    # ("en Zamak", "électrique") are two parts, one per sentence is enough
                    where = f"{chunk.id}:{sentence}" if rule.field == F.HARDWARE else chunk.id
                    slot = (rule.field, f"{where}:{_slot_word(value)}")
                    previous = per_slot.get(slot)
                    if previous is not None and previous in found:
                        # Keep the most informative value for this sentence.
                        if len(req.value) <= len(found[previous].value):
                            continue
                        del found[previous]
                    if key not in found:
                        per_slot[slot] = key
                found.setdefault(key, req)
    return _drop_repeated_standards(list(found.values()))


def _drop_repeated_standards(reqs: list[Requirement]) -> list[Requirement]:
    """Drop a code that a longer code in the same sentence already states.

    A reference list repeats the code in its title ("NF DTU 34.5 P2 - DTU 34.5
    Travaux de bâtiment"): the bare repeat is the same standard, not another one.
    """
    by_sentence: dict[tuple[str, str], list[Requirement]] = {}
    for req in reqs:
        if req.field == F.STANDARDS and req.citation is not None:
            by_sentence.setdefault((req.citation.chunk_id, req.citation.quote), []).append(req)
    dropped: set[int] = set()
    for group in by_sentence.values():
        for req in group:
            short = re.compile(rf"(?<!\S){re.escape(comparable(req.value))}(?!\S)")
            if any(
                other is not req
                and len(comparable(other.value)) > len(comparable(req.value))
                and short.search(comparable(other.value))
                for other in group
            ):
                dropped.add(id(req))
    return [req for req in reqs if id(req) not in dropped]
