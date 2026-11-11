"""Find public joinery tenders on BOAMP to grow the evaluation corpus.

BOAMP publishes every French public tender notice as open data
(https://boamp-datadila.opendatasoft.com, Licence Ouverte, no key, 10,000 calls
a day). A notice does not contain the tender documents, but it links to the
buyer profile where the DCE (with the CCTP) can be downloaded for free. This
module lists open notices with a joinery lot and those links; downloading
stays a manual step on the buyer's platform.

The full notice is a JSON string in ``donnees``, in one of three formats:
FNSimple (national), MAPA (adapted procedure) and EFORMS (EU UBL). Each keeps
the buyer, the lots and the links in different places, read below.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

API = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
PAGE = 100  # the API's maximum per call

# Lot titles and CPV codes that mean joinery work.
JOINERY = re.compile(
    r"(?<![a-z])(menuiserie|fenetre|baie|chassis|vitrerie|occultation|volet|facade vitree|"
    r"mur rideau|murs rideaux|store)"
)
INTERIOR = re.compile(r"menuiseries? (bois )?interieur|agencement|parquet")
JOINERY_CPV = ("45421", "44221", "45441", "44112")


def fold(text: str) -> str:
    """Lower case without accents. BOAMP's search() misses accented terms."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True)
class Lot:
    number: str
    title: str
    cpv: str = ""

    @property
    def label(self) -> str:
        """Number and title, without repeating a number the title already starts with."""
        if not self.number or self.title.lstrip().startswith(self.number):
            return self.title
        return f"{self.number} {self.title}"

    @property
    def is_joinery(self) -> bool:
        """Judged on the title; the CPV only when there is no title.

        Notices often copy the main CPV onto every lot, so a partitions or
        flooring lot can carry the joinery code.
        """
        title = fold(self.title)
        if not title.strip():
            return self.cpv.startswith(JOINERY_CPV)
        if INTERIOR.search(title) and "exterieur" not in title:
            return False
        return bool(JOINERY.search(title))


@dataclass
class Lead:
    """One open notice that may hold a joinery CCTP."""

    idweb: str
    title: str
    buyer: str
    published: str
    deadline: str
    notice_url: str
    dce_url: str = ""
    buyer_profile_url: str = ""
    departments: list[str] = field(default_factory=list)
    lots: list[Lot] = field(default_factory=list)
    notice_format: str = ""

    @property
    def joinery_lots(self) -> list[Lot]:
        return [lot for lot in self.lots if lot.is_joinery]

    @property
    def download_url(self) -> str:
        """The most specific link: the consultation page, else the buyer profile."""
        return self.dce_url or self.buyer_profile_url


def as_list(value: Any) -> list[Any]:
    """BOAMP's JSON turns a repeated key into a list and leaves a single one as is."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _get(data: Any, *path: str) -> Any:
    for key in path:
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("#text", "")
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return "" if value is None else " ".join(html.unescape(str(value)).split())


def _fnsimple(notice: dict[str, Any]) -> tuple[str, str, str, list[Lot]]:
    initial = notice.get("initial", {})
    lots = [
        Lot(
            number=_lot_number(_text(lot.get("description"))),
            title=_text(lot.get("description")),
            cpv=_text(_get(lot, "codeCPV", "objetPrincipal", "classPrincipale")),
        )
        for lot in as_list(_get(initial, "lots", "lot"))
    ]
    if not lots:
        lots = [
            Lot(
                "",
                _text(_get(initial, "natureMarche", "intitule")),
                _text(
                    _get(initial, "natureMarche", "codeCPV", "objetPrincipal", "classPrincipale")
                ),
            )
        ]
    return (
        _text(_get(initial, "communication", "urlDocConsul")),
        _text(_get(initial, "communication", "urlProfilAch")),
        _text(_get(initial, "procedure", "dateReceptionOffres")),
        lots,
    )


def _mapa(notice: dict[str, Any]) -> tuple[str, str, str, list[Lot]]:
    initial = notice.get("initial", {})
    lots = [
        Lot(_text(lot.get("numLot")), _text(lot.get("description")))
        for lot in as_list(_get(initial, "lots", "lot"))
    ]
    if not lots:
        lots = [Lot("", _text(_get(initial, "description", "objet")))]
    profile = _text(_get(notice, "organisme", "urlProfilAcheteur"))
    return (
        profile if "consultation" in profile.lower() else "",
        profile or _text(_get(notice, "organisme", "coord", "url")),
        _text(_get(initial, "delais", "receptionOffres")),
        lots,
    )


def _eforms(notice: dict[str, Any]) -> tuple[str, str, str, list[Lot]]:
    body = notice.get("ContractNotice") or {}
    lots: list[Lot] = []
    dce = deadline = ""
    for lot in as_list(body.get("cac:ProcurementProjectLot")):
        project = lot.get("cac:ProcurementProject", {})
        lots.append(
            Lot(
                _text(project.get("cbc:ID")) or _text(lot.get("cbc:ID")),
                _text(project.get("cbc:Name")),
                _text(
                    _get(project, "cac:MainCommodityClassification", "cbc:ItemClassificationCode")
                ),
            )
        )
        terms = lot.get("cac:TenderingTerms", {})
        dce = dce or _text(
            _get(
                terms,
                "cac:CallForTendersDocumentReference",
                "cac:Attachment",
                "cac:ExternalReference",
                "cbc:URI",
            )
        )
        period = _get(lot, "cac:TenderingProcess", "cac:TenderSubmissionDeadlinePeriod") or {}
        deadline = deadline or " ".join(
            filter(None, [_text(period.get("cbc:EndDate")), _text(period.get("cbc:EndTime"))])
        )
    profile = _text(_get(body, "cac:ContractingParty", "cbc:BuyerProfileURI"))
    return dce, profile, deadline, lots


_FORMATS = {"FNSimple": _fnsimple, "MAPA": _mapa, "EFORMS": _eforms}


def _lot_number(description: str) -> str:
    match = re.match(
        r"\s*(?:lot\s*(?:n\s*[°º]?\s*)?)?(\d{1,3}[a-z]?)(?![a-z0-9])", description, re.I
    )
    return match.group(1) if match else ""


def parse_record(record: dict[str, Any]) -> Lead:
    """Turn one API record into a lead, whatever the notice format."""
    raw = record.get("donnees") or "{}"
    try:
        donnees = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        donnees = {}
    dce = profile = deadline = ""
    lots: list[Lot] = []
    notice_format = next((k for k in _FORMATS if k in donnees), "")
    if notice_format:
        dce, profile, deadline, lots = _FORMATS[notice_format](donnees[notice_format])
    idweb = str(record.get("idweb") or "")
    return Lead(
        idweb=idweb,
        title=_text(record.get("objet")),
        buyer=_text(record.get("nomacheteur")),
        published=str(record.get("dateparution") or ""),
        deadline=str(record.get("datelimitereponse") or deadline or ""),
        notice_url=str(
            record.get("url_avis") or f"https://www.boamp.fr/pages/avis/?q=idweb:{idweb}"
        ),
        dce_url=dce.replace("&amp;", "&"),
        buyer_profile_url=profile.replace("&amp;", "&"),
        departments=[str(d) for d in as_list(record.get("code_departement"))],
        lots=lots,
        notice_format=notice_format,
    )


def build_where(terms: Iterable[str], *, since: date, open_only: bool) -> str:
    """ODSQL filter: open calls for tenders on works that mention any term."""
    search = " OR ".join(f'search("{fold(t)}")' for t in terms)
    clauses = [
        f"({search})",
        'nature="APPEL_OFFRE"',
        'type_marche="TRAVAUX"',
        f"dateparution>=date'{since.isoformat()}'",
    ]
    if open_only:
        clauses.append("(datelimitereponse>=now() OR datelimitereponse is null)")
    return " AND ".join(clauses)


DEFAULT_TERMS = ("menuiseries exterieures", "menuiserie exterieure", "fenetres")


def search(
    client: httpx.Client,
    *,
    terms: Iterable[str] = DEFAULT_TERMS,
    days: int = 60,
    open_only: bool = True,
    departments: Iterable[str] = (),
    max_records: int = 500,
    today: date | None = None,
) -> Iterator[Lead]:
    """Yield leads with at least one joinery lot, newest first."""
    since = (today or date.today()) - timedelta(days=days)
    where = build_where(terms, since=since, open_only=open_only)
    wanted = {d.zfill(2) for d in departments}
    if wanted:
        where += " AND (" + " OR ".join(f'code_departement="{d}"' for d in sorted(wanted)) + ")"
    offset = 0
    while offset < max_records:
        response = client.get(
            API,
            params={
                "where": where,
                "order_by": "dateparution desc",
                "limit": min(PAGE, max_records - offset),
                "offset": offset,
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        for record in results:
            lead = parse_record(record)
            if lead.joinery_lots:
                yield lead
        if len(results) < PAGE:
            return
        offset += PAGE


CSV_COLUMNS = (
    "idweb",
    "published",
    "deadline",
    "departments",
    "buyer",
    "title",
    "joinery_lots",
    "download_url",
    "notice_url",
    "format",
    "downloaded",
)


def to_csv(leads: Iterable[Lead]) -> str:
    """A sheet to work through: one row per notice, a column to tick when downloaded."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for lead in leads:
        writer.writerow(
            [
                lead.idweb,
                lead.published,
                lead.deadline,
                " ".join(lead.departments),
                lead.buyer,
                lead.title,
                " | ".join(lot.label[:120] for lot in lead.joinery_lots),
                lead.download_url,
                lead.notice_url,
                lead.notice_format,
                "",
            ]
        )
    return out.getvalue()
