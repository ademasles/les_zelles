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

F = SpecField
_I = re.IGNORECASE

_SENTENCE_END = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÀ-Ÿ0-9])|\n")


@dataclass(frozen=True)
class Rule:
    field: SpecField
    pattern: re.Pattern[str]
    confidence: float = 0.75
    requires: re.Pattern[str] | None = None  # the sentence must also match this
    excludes: re.Pattern[str] | None = None  # ...and must not match this
    normalize: Callable[[re.Match[str]], str] | None = None


def _material(match: re.Match[str]) -> str:
    word = match.group(0).lower()
    if "bois" in word and "alu" in word:
        return "Wood-aluminium"
    if "pvc" in word and "alu" in word:
        return "PVC-aluminium"
    return {"pvc": "PVC", "aluminium": "Aluminium", "alu": "Aluminium", "bois": "Wood"}.get(
        word, match.group(0)
    )


NUM = r"(\d+(?:[.,]\d+)?)"
CMP = r"(?:\s*(?:[:=]|≤|≥|<=|>=|<|>|inférieur(?:e)?\s+(?:ou\s+égal\s+)?à|supérieur(?:e)?\s+(?:ou\s+égal\s+)?à|de|d'au plus|d'au moins|maxi(?:mum)?|mini(?:mum)?)\s*)*"
U_UNIT = r"(?:\s*W\s*/\s*\(?\s*m\s*2\s*[.·]?\s*K\s*\)?)?"

RULES: list[Rule] = [
    Rule(F.UW, re.compile(rf"\bUw\b{CMP}{NUM}{U_UNIT}", _I), 0.9),
    Rule(F.UG, re.compile(rf"\bUg\b{CMP}{NUM}{U_UNIT}", _I), 0.9),
    Rule(F.UJN, re.compile(rf"\bUjn\b{CMP}{NUM}{U_UNIT}", _I), 0.9),
    Rule(F.SW, re.compile(rf"\b(?:Sw|facteur solaire(?:\s+Sw)?)\b{CMP}{NUM}\s*%?", _I), 0.85),
    Rule(
        F.TLW,
        re.compile(rf"\b(?:TLw|transmission lumineuse(?:\s+TLw)?)\b{CMP}{NUM}\s*%?", _I),
        0.85,
    ),
    Rule(
        F.AEV,
        re.compile(
            r"\bA\s*\*\s*[1-4]\s*[-,/]?\s*E\s*\*\s*(?:[1-9]\s*[AB]|E\s*\d{3,4})\s*[-,/]?\s*V\s*\*\s*(?:[ABC]\s*[1-5]|E\s*\d{3,4})",
            _I,
        ),
        0.95,
    ),
    Rule(  # "classe A 3 / eau E 7B / vent V A3", "A3 - E7B - VA2"
        F.AEV,
        re.compile(
            r"\bA\s*\*?\s*[1-4]\b[^\n]{0,25}?\bE\s*\*?\s*(?:[1-9]\s?[AB]|E\s*\d{3,4})\b[^\n]{0,25}?\bV\s*\*?\s*(?:[ABC]\s?[1-5]|E\s*\d{3,4})\b",
            _I,
        ),
        0.85,
        requires=re.compile(r"\bair\b|AEV|étanchéité|perméabilité|classement", _I),
    ),
    Rule(
        F.ACOUSTIC,
        re.compile(
            rf"\b(?:Ra\s*,\s*tr|R\s*A\s*,\s*tr|Rw\s*\(\s*C\s*;\s*Ctr\s*\)|Rw)\b{CMP}{NUM}\s*dB", _I
        ),
        0.85,
    ),
    Rule(
        F.ACOUSTIC,
        re.compile(
            rf"\b(?:DnT\s*,\s*A\s*,\s*tr|isolement\s+acoustique|affaiblissement\s+acoustique|classement\s+de\s+façade)\b[^.;\n]{{0,40}}?{NUM}\s*dB(?:\s*\(?A\)?)?",
            _I,
        ),
        0.75,
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(  # further values in the same sentence: "..., 28 dB pour les autres façades"
        F.ACOUSTIC,
        re.compile(r"(?<![\w,.])(\d{2})\s*dB(?:\s*\(?A\)?)?"),
        0.7,
        requires=re.compile(r"Ra\s*,\s*tr|acoustique|affaiblissement|DnT", _I),
        normalize=lambda m: f"{m.group(1)} dB",
    ),
    Rule(
        F.COLOR,
        re.compile(
            r"(?:\b(?:blanc|gris(?:\s+anthracite|\s+clair|\s+foncé)?|noir|beige|ivoire|bronze|chêne doré)\s+)?\bRAL\s*\d{4}(?:\s+(?:sablé|mat|satiné|brillant|texturé|fine structure))?",
            _I,
        ),
        0.85,
    ),
    Rule(
        F.COLOR,
        re.compile(
            r"\b(?:teinte|coloris|couleur|finition)\s*:?\s*(?:blanc(?:he)?|gris(?:\s+anthracite)?|noir|beige|ivoire|sable|chêne\s+doré|ton\s+bois)\b[^.;,\n]{0,25}|\bblanc\s+teinté\s+dans\s+la\s+masse\b",
            _I,
        ),
        0.7,
    ),
    Rule(
        F.GLAZING_COMPOSITION,
        re.compile(
            r"(?<![\w/.-])\d{1,2}(?:[.,]\d)?(?:\s*[/-]\s*\d{1,2}(?:[.,]\d)?){2,4}(?![\w/-])"
        ),
        0.8,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(  # "4.16.4": dotted notation, the middle number being the gap in mm
        F.GLAZING_COMPOSITION,
        re.compile(r"(?<![\w.])\d{1,2}\.(?:[6-9]|1\d|2[0-4])\.\d{1,2}(?![\w.])"),
        0.7,
        requires=re.compile(r"vitrage|verre|glace", _I),
    ),
    Rule(
        F.GLAZING_TYPE,
        re.compile(
            r"\b(?:double|triple)\s+vitrage(?:\s+isolant)?(?:[^.;\n]{0,70}?(?:argon|krypton|émissif|ITR|contrôle solaire))?|\b(?:très\s+)?(?:basse|faible)\s+[ée]missivit[ée]\b|\b(?:verre|vitrage)\s+(?:à\s+)?contrôle\s+solaire\b",
            _I,
        ),
        0.75,
    ),
    Rule(
        F.SAFETY_GLAZING,
        re.compile(
            r"\b(?:vitrage\s+)?(?:feuilleté|trempé)(?:\s+de\s+sécurité)?(?:\s+\d{2}\.\d)?|\bSP\s?\d{2}\b|\bP[1-8][AB]\b",
            _I,
        ),
        0.75,
    ),
    Rule(
        F.SPACER,
        re.compile(r"\bintercalaires?\s+[^.;,\n)]{2,40}|\bwarm[- ]edge\b|\bbord chaud\b", _I),
        0.7,
    ),
    Rule(
        F.FRAME_MATERIAL,
        re.compile(
            r"\b(?:mixtes?\s+)?(?:bois[- ]alu(?:minium)?|pvc[- ]alu(?:minium)?|PVC|aluminium|bois)\b",
            _I,
        ),
        0.6,
        requires=re.compile(r"menuiserie|fenêtre|porte|châssis|ensemble vitré|ouvrant", _I),
        excludes=re.compile(r"volet|lame|poignée|renfort|coffre|grille", _I),
        normalize=_material,
    ),
    Rule(
        F.OPENING_TYPE,
        re.compile(
            r"\b(?:oscillo[- ]?battants?|ouvrants?\s+à\s+la\s+française|coulissants?(?:\s+à\s+galandage)?|galandage|levant[- ]coulissant|châssis\s+fixes?|portes?-fenêtres?|portes?\s+d'entrée|soufflets?)\b",
            _I,
        ),
        0.7,
    ),
    Rule(
        F.PROFILE_SYSTEM,
        re.compile(
            r"\b(?:type|gamme|profilés?)\s+[^.;\n]{2,60}?ou\s+(?:techniquement\s+)?équivalent", _I
        ),
        0.65,
    ),
    Rule(
        F.PROFILE_SYSTEM,
        re.compile(
            r"\b(?:\d{2,3}\s*mm[^.;\n]{0,25}?)?\b(?:[3-8]|trois|quatre|cinq|six|sept|huit)\s+chambres\b(?:[^.;\n]{0,50})?",
            _I,
        ),
        0.65,
    ),
    Rule(
        F.FINISH,
        re.compile(
            r"\b(?:thermolaquage|laquage|anodisation|plaxage|lasure)\b(?:[^.;,\n]{0,40}?(?:Qualicoat|Qualimarine|Qualanod))?|\b(?:label\s+)?(?:Qualicoat|Qualimarine|Qualanod)\b",
            _I,
        ),
        0.75,
    ),
    Rule(
        F.SECURITY_CLASS, re.compile(r"\b(?:RC|CR)\s?[1-6]N?\b(?:\s+selon\s+NF\s+EN\s+1627)?"), 0.85
    ),
    Rule(
        F.HARDWARE,
        re.compile(
            r"\b(?:crémone[^.;,\n]{0,45}|paumelles?[^.;,\n]{0,30}|ferme-porte[^.;,\n]{0,40}|poignées?[^.;,\n]{0,40}|(?:système\s+|quincaillerie\s+)?(?:Winkhaus|Roto|Siegenia|Ferco|Maco|Sobinco|Hoppe|Assa\s+Abloy)\b[^.;,\n]{0,30})",
            _I,
        ),
        0.6,
    ),
    Rule(
        F.SHUTTERS,
        re.compile(
            r"\bvolets?\s+roulants?[^.;\n]{0,90}|\bpersiennes?\b[^.;\n]{0,80}|\bvolets?\s+battants?[^.;\n]{0,60}|\bBSO\b|\bbrise-soleil[^.;,\n]{0,40}|\bcoffre\s+[^.;,\n]{2,40}|\bmanœuvre\s+(?:manuelle|électrique|motorisée|radio|solaire|par\s+(?:sangle|treuil|manivelle))[^.;\n]{0,40}",
            _I,
        ),
        0.65,
    ),
    Rule(F.AIR_INLETS, re.compile(r"\bentrées?\s+d'air[^.;\n]{0,110}", _I), 0.7),
    Rule(
        F.AIR_INLETS,
        re.compile(
            r"\b(?:Aldes|Aldès|Anjos|Renson)\b[^.;\n]{0,50}|\b(?:auto|hygro)réglables?\b[^.;\n]{0,40}",
            _I,
        ),
        0.65,
        requires=re.compile(r"\bair\b|ventilation|VMC|mortais", _I),
    ),
    Rule(
        F.ACCESSIBILITY,
        re.compile(
            r"\bPMR\b[^.;\n]{0,60}|\bseuil[^.;,\n]{0,60}|\beffort de manœuvre[^.;,\n]{0,40}", _I
        ),
        0.65,
        excludes=re.compile(
            r"\b(?:NF\s+)?EN\s?\d{4,5}\b", _I
        ),  # a standard's title, not a requirement
    ),
    Rule(
        F.INSTALLATION,
        re.compile(
            r"\bpose\s+en\s+(?:applique|tunnel|feuillure|rénovation)[^.;,\n]{0,40}|\bdépose\s+totale\b|\bsur\s+dormant\s+existant\b|\bcalfeutrement[^.;\n]{0,70}",
            _I,
        ),
        0.75,
    ),
    Rule(
        F.STANDARDS,
        re.compile(
            r"\bNF\s+(?:DTU|EN(?:\s+ISO)?|P)\s?\d+(?:[.\-]\d+)*\b|\b(?<!NF )DTU\s?\d+(?:\.\d+)?\b|\bEurocode\s?\d\b",
            _I,
        ),
        0.9,
    ),
    Rule(
        F.CERTIFICATIONS,
        re.compile(
            r"\b(?:marquage\s+CE|Avis\s+Technique(?:\s+du\s+CSTB)?|\bDTA\b|CEKAL|Acotherm|marque\s+NF|PEFC|FSC|certification\s+QB)\b",
            _I,
        ),
        0.85,
    ),
    Rule(
        F.REGULATION,
        re.compile(
            r"\b(?:RE\s?2020|RT\s?2012|RT\s+existant|réglementation\s+(?:incendie|parasismique|thermique)|\bERP\b)",
            _I,
        ),
        0.85,
    ),
]


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


def extract_with_rules(chunks: list[Chunk]) -> list[Requirement]:
    """Run every rule over every chunk and return cited requirements."""
    found: dict[tuple[str, str, str], Requirement] = {}
    for chunk in chunks:
        body = chunk.text
        # The heading line is context, not a requirement ("4.1 Volets roulants").
        skip = len(chunk.heading) if chunk.heading and body.startswith(chunk.heading) else 0
        for rule in RULES:
            for match in rule.pattern.finditer(body):
                if match.start() < skip:
                    continue
                sentence = _sentence_around(body, match.start())
                if rule.requires is not None and not rule.requires.search(sentence):
                    continue
                if rule.excludes is not None and rule.excludes.search(sentence):
                    continue
                raw = " ".join(match.group(0).split()).rstrip(" ,;:")
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
                        page=chunk.page_start,
                        locator=chunk.locator(),
                        match_score=1.0,
                    ),
                    source=RequirementSource.RULES,
                    status=RequirementStatus.VERIFIED,
                    confidence=rule.confidence,
                )
                found.setdefault(req.dedupe_key(), req)
    return list(found.values())
