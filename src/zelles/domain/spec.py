"""The joinery spec sheet: what a CCTP analysis produces.

A spec sheet is a list of *requirements*. Each requirement is one value for one
field (for example ``uw = 1.3 W/m².K``), scoped to what it applies to (a lot, a
building, a window type) and backed by a citation into the source document.
A CCTP often states several values for the same field (one per lot or per
opening type), so a field maps to a list of requirements, never a single value.

The field catalogue below is the domain knowledge of the project: what a
joinery estimator looks for in a CCTP, with the French vocabulary used to find
it. It replaces the six hard-coded questions of the original prototype.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    MATERIALS = "materials"
    GLAZING = "glazing"
    THERMAL = "thermal"
    WEATHER = "weather_tightness"
    ACOUSTICS = "acoustics"
    SECURITY = "security"
    EQUIPMENT = "equipment"
    ACCESSIBILITY = "accessibility"
    INSTALLATION = "installation"
    COMPLIANCE = "compliance"


class SpecField(StrEnum):
    # materials and finishes
    FRAME_MATERIAL = "frame_material"
    OPENING_TYPE = "opening_type"
    PROFILE_SYSTEM = "profile_system"
    COLOR = "color"
    FINISH = "finish"
    # glazing
    GLAZING_COMPOSITION = "glazing_composition"
    GLAZING_TYPE = "glazing_type"
    SAFETY_GLAZING = "safety_glazing"
    SPACER = "spacer"
    # thermal and solar
    UW = "uw"
    UG = "ug"
    UJN = "ujn"
    SW = "sw"
    TLW = "tlw"
    # weather tightness
    AEV = "aev"
    # acoustics
    ACOUSTIC = "acoustic"
    # security
    SECURITY_CLASS = "security_class"
    HARDWARE = "hardware"
    # equipment
    SHUTTERS = "shutters"
    AIR_INLETS = "air_inlets"
    # accessibility
    ACCESSIBILITY = "accessibility"
    # installation
    INSTALLATION = "installation"
    # compliance
    STANDARDS = "standards"
    CERTIFICATIONS = "certifications"
    REGULATION = "regulation"


class FieldInfo(BaseModel):
    """Catalogue entry for a spec field."""

    field: SpecField
    category: Category
    label: str
    description: str
    unit: str | None = None
    numeric: bool = False
    search_terms: list[str] = Field(
        default_factory=list, description="French vocabulary used to retrieve relevant articles."
    )


def _f(
    field: SpecField,
    category: Category,
    label: str,
    description: str,
    terms: list[str],
    *,
    unit: str | None = None,
    numeric: bool = False,
) -> FieldInfo:
    return FieldInfo(
        field=field,
        category=category,
        label=label,
        description=description,
        unit=unit,
        numeric=numeric,
        search_terms=terms,
    )


C = Category
F = SpecField

FIELD_CATALOG: dict[SpecField, FieldInfo] = {
    info.field: info
    for info in [
        _f(
            F.FRAME_MATERIAL,
            C.MATERIALS,
            "Frame material",
            "Material of the joinery frames: PVC, aluminium, wood, or mixed (wood-aluminium, PVC-aluminium).",
            [
                "matériau",
                "PVC",
                "aluminium",
                "bois",
                "mixte",
                "bois-aluminium",
                "menuiseries extérieures",
            ],
        ),
        _f(
            F.OPENING_TYPE,
            C.MATERIALS,
            "Opening types",
            "Kinds of openings: casement, tilt-and-turn, sliding, lift-and-slide, fixed, French door, entrance door.",
            [
                "fenêtre",
                "porte-fenêtre",
                "oscillo-battant",
                "coulissant",
                "galandage",
                "châssis fixe",
                "ouvrant à la française",
                "porte d'entrée",
                "soufflet",
            ],
        ),
        _f(
            F.PROFILE_SYSTEM,
            C.MATERIALS,
            "Profile system",
            "Profile range or system named by the spec, with reference or equivalent clause.",
            [
                "profilé",
                "gamme",
                "système",
                "type",
                "ou techniquement équivalent",
                "dormant",
                "ouvrant",
            ],
        ),
        _f(
            F.COLOR,
            C.MATERIALS,
            "Colors",
            "Required colors, ideally as RAL codes, including bi-color (inside / outside) requirements.",
            [
                "coloris",
                "couleur",
                "teinte",
                "RAL",
                "blanc",
                "gris anthracite",
                "bicolore",
                "plaxage",
            ],
        ),
        _f(
            F.FINISH,
            C.MATERIALS,
            "Finish",
            "Surface treatment: powder coating, anodising, foil, wood species and stain, with quality labels.",
            [
                "finition",
                "thermolaquage",
                "laquage",
                "anodisation",
                "Qualicoat",
                "Qualimarine",
                "Qualanod",
                "essence",
                "lasure",
                "lamellé-collé",
                "plaxé",
            ],
        ),
        _f(
            F.GLAZING_COMPOSITION,
            C.GLAZING,
            "Glazing composition",
            "Pane build-up such as 4/16/4, 4/20/4 or 44.2/16/4, as written in the spec.",
            ["vitrage", "composition", "épaisseur", "lame", "4/16/4", "44.2"],
        ),
        _f(
            F.GLAZING_TYPE,
            C.GLAZING,
            "Glazing type",
            "Single, double or triple glazing, low-emissivity coating, gas fill (argon, krypton), solar control.",
            [
                "double vitrage",
                "triple vitrage",
                "faiblement émissif",
                "ITR",
                "argon",
                "krypton",
                "contrôle solaire",
                "vitrage isolant",
            ],
        ),
        _f(
            F.SAFETY_GLAZING,
            C.GLAZING,
            "Safety glazing",
            "Laminated or toughened glazing for safety or burglary resistance (44.2, SP10, P2A...).",
            [
                "feuilleté",
                "trempé",
                "sécurité",
                "retardateur d'effraction",
                "SP10",
                "P2A",
                "P4A",
                "44.2",
            ],
        ),
        _f(
            F.SPACER,
            C.GLAZING,
            "Spacer",
            "Insulating glass spacer bar, typically warm edge.",
            ["intercalaire", "warm edge", "bord chaud", "Swisspacer", "TGI"],
        ),
        _f(
            F.UW,
            C.THERMAL,
            "Uw (window)",
            "Thermal transmittance of the whole window.",
            ["Uw", "coefficient de transmission thermique", "performance thermique", "W/m².K"],
            unit="W/m².K",
            numeric=True,
        ),
        _f(
            F.UG,
            C.THERMAL,
            "Ug (glazing)",
            "Thermal transmittance of the glazing at centre of pane.",
            ["Ug", "vitrage", "W/m².K"],
            unit="W/m².K",
            numeric=True,
        ),
        _f(
            F.UJN,
            C.THERMAL,
            "Ujn (day-night)",
            "Day-night thermal transmittance with closed shutters.",
            ["Ujn", "jour-nuit", "fermeture"],
            unit="W/m².K",
            numeric=True,
        ),
        _f(
            F.SW,
            C.THERMAL,
            "Sw (solar factor)",
            "Solar factor of the window (share of solar energy let through), 0 to 1.",
            ["Sw", "facteur solaire", "S", "apports solaires"],
            numeric=True,
        ),
        _f(
            F.TLW,
            C.THERMAL,
            "TLw (light transmission)",
            "Light transmission factor of the window, 0 to 1.",
            ["TLw", "transmission lumineuse", "facteur de transmission lumineuse"],
            numeric=True,
        ),
        _f(
            F.AEV,
            C.WEATHER,
            "AEV classification",
            "Air, water and wind resistance classes (NF EN 12207, 12208, 12210), e.g. A*3 E*7B V*A2.",
            [
                "AEV",
                "A*",
                "E*",
                "V*",
                "perméabilité à l'air",
                "étanchéité à l'eau",
                "résistance au vent",
                "classement",
            ],
        ),
        _f(
            F.ACOUSTIC,
            C.ACOUSTICS,
            "Acoustic insulation",
            "Required sound insulation, usually Ra,tr or Rw(C;Ctr) in dB, sometimes by facade exposure.",
            [
                "affaiblissement acoustique",
                "isolement acoustique",
                "Ra,tr",
                "Rw",
                "dB",
                "acoustique",
                "Acotherm",
            ],
            unit="dB",
            numeric=True,
        ),
        _f(
            F.SECURITY_CLASS,
            C.SECURITY,
            "Burglary resistance",
            "Burglary resistance class (NF EN 1627 RC2/RC3, or CR2 in older specs) and related requirements.",
            ["anti-effraction", "effraction", "RC2", "RC3", "CR2", "CR3", "NF EN 1627"],
        ),
        _f(
            F.HARDWARE,
            C.SECURITY,
            "Hardware",
            "Handles, locking points, hinges, tilt-and-turn mechanisms, door closers.",
            [
                "quincaillerie",
                "crémone",
                "poignée",
                "paumelles",
                "points de fermeture",
                "ferme-porte",
                "serrure",
                "béquille",
            ],
        ),
        _f(
            F.SHUTTERS,
            C.EQUIPMENT,
            "Shutters and sun protection",
            "Roller shutters, box type, slat material, operation (manual, electric, radio, solar), BSO, louvres.",
            [
                "volet roulant",
                "coffre",
                "lames",
                "motorisation",
                "manœuvre",
                "BSO",
                "brise-soleil",
                "persienne",
                "volet battant",
                "occultation",
            ],
        ),
        _f(
            F.AIR_INLETS,
            C.EQUIPMENT,
            "Air inlets",
            "Ventilation air inlets in the frames: type, airflow module, acoustic rating, humidity control.",
            [
                "entrée d'air",
                "entrées d'air",
                "mortaise",
                "module",
                "hygroréglable",
                "VMC",
                "ventilation",
            ],
        ),
        _f(
            F.ACCESSIBILITY,
            C.ACCESSIBILITY,
            "Accessibility",
            "Accessibility requirements for people with reduced mobility: low thresholds, handle height, operating force.",
            [
                "PMR",
                "accessibilité",
                "seuil",
                "handicapé",
                "personnes à mobilité réduite",
                "effort de manœuvre",
            ],
        ),
        _f(
            F.INSTALLATION,
            C.INSTALLATION,
            "Installation",
            "Installation method (applique, tunnel, feuillure, renovation on existing frame, full removal) and sealing.",
            [
                "pose",
                "mise en œuvre",
                "applique",
                "tunnel",
                "feuillure",
                "rénovation",
                "dépose totale",
                "dormant existant",
                "calfeutrement",
                "compribande",
            ],
        ),
        _f(
            F.STANDARDS,
            C.COMPLIANCE,
            "Standards",
            "Standards and codes of practice referenced: NF DTU 36.5, NF EN 14351-1, NF DTU 39, Eurocodes...",
            ["norme", "NF DTU", "NF EN", "DTU 36.5", "14351-1", "règles de l'art", "Eurocode"],
        ),
        _f(
            F.CERTIFICATIONS,
            C.COMPLIANCE,
            "Certifications and labels",
            "Required marks and labels: CE marking, NF mark, CSTB technical approval (Avis Technique), CEKAL, Acotherm, PEFC/FSC.",
            [
                "certification",
                "marque NF",
                "marquage CE",
                "Avis Technique",
                "DTA",
                "CEKAL",
                "Acotherm",
                "label",
                "PEFC",
                "FSC",
                "QB",
            ],
        ),
        _f(
            F.REGULATION,
            C.COMPLIANCE,
            "Regulations",
            "Regulatory frameworks the work must meet: RE2020, existing-building thermal rules, fire safety, seismic.",
            [
                "RE2020",
                "RT2012",
                "RT existant",
                "réglementation",
                "sécurité incendie",
                "parasismique",
                "ERP",
                "code de la construction",
            ],
        ),
    ]
}


class RequirementSource(StrEnum):
    RULES = "rules"
    LLM = "llm"


class RequirementStatus(StrEnum):
    VERIFIED = "verified"  # quote found in the source and value passes validation
    UNVERIFIED = "unverified"  # quote not found verbatim, or no citation
    INVALID = "invalid"  # quote found but value fails domain validation


class Citation(BaseModel):
    """Where a value comes from in the source document."""

    chunk_id: str
    quote: str = Field(description="Verbatim excerpt from the source that states the value.")
    page: int | None = None
    locator: str = ""
    match_score: float = Field(default=0.0, ge=0.0, le=1.0)


class Requirement(BaseModel):
    """One value for one spec field, scoped and cited."""

    field: SpecField
    value: str = Field(description="The value as stated, e.g. '≤ 1.3 W/m².K' or 'PVC blanc'.")
    numeric_value: float | None = None
    unit: str | None = None
    comparator: str | None = Field(default=None, description="'<=', '>=', '=' when stated.")
    scope: str | None = Field(
        default=None, description="What it applies to: a lot, a building, an opening type."
    )
    citation: Citation | None = None
    source: RequirementSource = RequirementSource.LLM
    status: RequirementStatus = RequirementStatus.UNVERIFIED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

    @property
    def category(self) -> Category:
        return FIELD_CATALOG[self.field].category

    def dedupe_key(self) -> tuple[str, str, str]:
        if self.numeric_value is not None:
            normalized = f"{self.numeric_value:g}"
        else:
            normalized = " ".join(self.value.lower().split())
        return (self.field.value, normalized, (self.scope or "").lower().strip())


class Usage(BaseModel):
    """Token and cost accounting for one analysis."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float | None = None
    seconds: float = 0.0

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.seconds += other.seconds
        if other.cost_usd is not None:
            self.cost_usd = (self.cost_usd or 0.0) + other.cost_usd


class SpecSheet(BaseModel):
    """The structured result of analysing one CCTP."""

    schema_version: str = "1.0"
    document_id: str
    filename: str
    title: str | None = Field(default=None, description="Project name from the cover page.")
    model: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lots: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    summary: str | None = None
    usage: Usage = Field(default_factory=Usage)
    warnings: list[str] = Field(default_factory=list)

    def by_field(self) -> dict[SpecField, list[Requirement]]:
        grouped: dict[SpecField, list[Requirement]] = defaultdict(list)
        for req in self.requirements:
            grouped[req.field].append(req)
        return {f: grouped[f] for f in FIELD_CATALOG if f in grouped}

    def missing_fields(self) -> list[SpecField]:
        present = {r.field for r in self.requirements}
        return [f for f in FIELD_CATALOG if f not in present]

    def coverage(self) -> float:
        return 1.0 - len(self.missing_fields()) / len(FIELD_CATALOG)
