"""BOAMP lead finder: parsing of the three notice formats, filtering, paging. No network."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any

import httpx

from zelles.corpus.boamp import Lot, build_where, parse_record, search, to_csv


def _record(idweb: str, donnees: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "idweb": idweb,
        "objet": "Construction d'un groupe scolaire",
        "nomacheteur": "Commune exemple",
        "dateparution": "2026-11-02",
        "datelimitereponse": None,
        "code_departement": ["27"],
        "url_avis": f"https://www.boamp.fr/pages/avis/?q=idweb:{idweb}",
        "donnees": json.dumps(donnees),
        **extra,
    }


FNSIMPLE = _record(
    "26-1",
    {
        "FNSimple": {
            "initial": {
                "communication": {
                    "urlDocConsul": "https://www.marches-publics.gouv.fr/?page=X&amp;id=1",
                    "urlProfilAch": "https://marchespublics.example.fr",
                },
                "procedure": {"dateReceptionOffres": "2026-12-04T12:00:00"},
                "lots": {
                    "lot": [
                        {
                            "description": "01_Gros oeuvre",
                            "codeCPV": {"objetPrincipal": {"classPrincipale": "45223220"}},
                        },
                        {
                            "description": "05_Menuiseries extérieures aluminium",
                            "codeCPV": {"objetPrincipal": {"classPrincipale": "45421000"}},
                        },
                    ]
                },
            }
        }
    },
)

MAPA = _record(
    "26-2",
    {
        "MAPA": {
            "organisme": {
                "acheteurPublic": "Office HLM",
                "urlProfilAcheteur": "https://demat.example.fr/index.php?page=Entreprise.EntrepriseDetailsConsultation&amp;id=9",
            },
            "initial": {
                "delais": {"receptionOffres": "2026-12-01"},
                "lots": {"lot": {"numLot": "3", "description": "Remplacement des fenêtres PVC"}},
            },
        }
    },
)

EFORMS = _record(
    "26-3",
    {
        "EFORMS": {
            "ContractNotice": {
                "cac:ContractingParty": {"cbc:BuyerProfileURI": "https://www.marches-securises.fr"},
                "cac:ProcurementProjectLot": {
                    "cbc:ID": {"#text": "LOT-0001"},
                    "cac:ProcurementProject": {
                        "cbc:ID": "07",
                        "cbc:Name": {"#text": "Occultations et volets roulants"},
                        "cac:MainCommodityClassification": {
                            "cbc:ItemClassificationCode": {"#text": "44221000"}
                        },
                    },
                    "cac:TenderingProcess": {
                        "cac:TenderSubmissionDeadlinePeriod": {
                            "cbc:EndDate": "2026-12-10",
                            "cbc:EndTime": "12:00:00",
                        }
                    },
                },
            }
        }
    },
)

NO_JOINERY = _record(
    "26-4",
    {
        "MAPA": {
            "initial": {
                "lots": {"lot": {"numLot": "1", "description": "Menuiseries intérieures bois"}}
            }
        }
    },
)


def test_reads_the_three_notice_formats() -> None:
    fn, mapa, ef = (parse_record(r) for r in (FNSIMPLE, MAPA, EFORMS))
    assert fn.notice_format == "FNSimple"
    assert fn.download_url == "https://www.marches-publics.gouv.fr/?page=X&id=1"
    assert fn.deadline == "2026-12-04T12:00:00"
    assert [lot.number for lot in fn.joinery_lots] == ["05"]
    assert mapa.download_url.endswith("EntrepriseDetailsConsultation&id=9")
    assert mapa.joinery_lots[0].title == "Remplacement des fenêtres PVC"
    assert ef.buyer_profile_url == "https://www.marches-securises.fr"
    assert ef.deadline == "2026-12-10 12:00:00"
    assert ef.joinery_lots == [Lot("07", "Occultations et volets roulants", "44221000")]


def test_interior_joinery_is_not_a_lead() -> None:
    assert parse_record(NO_JOINERY).joinery_lots == []
    assert Lot("", "Menuiseries intérieures et extérieures").is_joinery
    assert Lot("", "Menuiseries intérieurs bois").is_joinery is False
    assert Lot("", "", "45421100").is_joinery  # no title: the CPV decides
    assert not Lot("9", "Serrurerie - Clôtures", "44221000").is_joinery  # copied CPV


def test_html_entities_are_decoded() -> None:
    lead = parse_record({**MAPA, "nomacheteur": "COMMUNAUTE D&#039;AGGLOMERATION"})
    assert lead.buyer == "COMMUNAUTE D'AGGLOMERATION"


def test_search_terms_lose_their_accents() -> None:
    where = build_where(["menuiseries extérieures"], since=date(2026, 9, 1), open_only=True)
    assert 'search("menuiseries exterieures")' in where
    assert "dateparution>=date'2026-09-01'" in where and 'nature="APPEL_OFFRE"' in where


def test_search_pages_and_keeps_joinery_leads_only() -> None:
    calls: list[dict[str, str]] = []
    pages = [[FNSIMPLE] * 50 + [NO_JOINERY] * 50, [MAPA, EFORMS]]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(200, json={"results": pages[len(calls) - 1]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        leads = list(search(client, departments=["27"], today=date(2026, 11, 10)))
    assert len(leads) == 52
    assert [c["offset"] for c in calls] == ["0", "100"]
    assert 'code_departement="27"' in calls[0]["where"]


def test_csv_has_a_column_to_tick() -> None:
    rows = list(csv.DictReader(io.StringIO(to_csv([parse_record(FNSIMPLE)]))))
    assert rows[0]["joinery_lots"] == "05_Menuiseries extérieures aluminium"
    assert rows[0]["downloaded"] == ""
