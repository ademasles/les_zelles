"""Wording variants: the matcher and the rules on synthetic CCTP sentences."""

from __future__ import annotations

import pytest

from zelles.domain.spec import Requirement, SpecField
from zelles.evaluation.harness import _comparable
from zelles.extraction.rules import extract_with_rules
from zelles.ingest.chunking import chunk_document
from zelles.ingest.parsers import parse_document

F = SpecField


@pytest.mark.parametrize(
    ("want", "have"),
    [
        ("20.501", "conforme à la norme NF P 20-501"),
        ("20.501", "essais selon NF.P 20 501"),
        ("NF P 20-501", "essais selon NF.P 20.501"),
        ("DTU 39", "mise en oeuvre suivant le D.T.U. n°39"),
        ("DTU 39", "suivant le D.T.U. N° 39 Vitrerie"),
        ("1 aout 2006", "arrêté du 1er août 2006 relatif à l'accessibilité"),
        ("S.N.J.F", "joints titulaires du label S.N.J.F."),
        ("CERFF", "certificat d'essais CER.F.F"),
        ("NFS 61-937", "conforme aux normes NFS 61.937"),
        ("1.30 m", "commandes situées entre 0,90 et 1,30 m"),
        ("37 dB", "entrées d'air 37dB(A)"),
        ("thermolaqués", "profilés aluminium thermolaqué"),
    ],
)
def test_comparable_folds_wording_variants(want: str, have: str) -> None:
    assert _comparable(want) in _comparable(have)


@pytest.mark.parametrize(
    ("want", "have"),
    [
        ("20.501", "norme NF P 20.502"),
        ("DTU 39", "DTU 36.5"),
        ("4/16/4", "4/20/4"),
    ],
)
def test_comparable_keeps_different_values_apart(want: str, have: str) -> None:
    assert _comparable(want) not in _comparable(have)


def _extract(body: str, heading: str = "2.1 Menuiseries extérieures") -> list[Requirement]:
    text = f"# 2 Description des ouvrages\n\n## {heading}\n\n{body}\n"
    document, _ = parse_document(text.encode(), "cctp.md")
    return extract_with_rules(chunk_document(document))


def _values(reqs: list[Requirement], field: SpecField) -> set[str]:
    return {r.value for r in reqs if r.field == field}


def _numbers(reqs: list[Requirement], field: SpecField) -> set[float]:
    return {r.numeric_value for r in reqs if r.field == field and r.numeric_value is not None}


def test_afnor_standards_in_dotted_spaced_and_glued_forms() -> None:
    reqs = _extract(
        "Les ouvrages respecteront notamment :\n\n"
        "- NF.P 08.322 : essais de résistance au vent\n"
        "- N.F. P 26 102 : crémones\n"
        "- NFP 01-010 : déclaration environnementale\n"
        "- NF EN 14351-1 et NF D.T.U. 34.1 P1-1\n"
        "- Règles NV 65 et N 84 modifiées\n\n"
        "Barre anti-panique conforme à la norme EN 1125."
    )
    found = " | ".join(sorted(_values(reqs, F.STANDARDS)))
    for want in ("08.322", "26 102", "01-010", "14351-1", "34.1", "NV 65", "N 84", "EN 1125"):
        assert want in found, (want, found)


def test_solar_and_light_factors_written_as_swc_and_tl_global() -> None:
    reqs = _extract(
        "Fenêtres PVC : Uw : 1,40 W/m².K SWC (facteur solaire hiver sans protection) = 0,38 "
        "SW (facteur solaire avec protection) = 0,25 TL global : 0,55\n\n"
        "Performances à obtenir : coefficient Uw moyen < 1,30 W/m².K"
    )
    assert _numbers(reqs, F.SW) == {0.38, 0.25}
    assert _numbers(reqs, F.TLW) == {0.55}
    assert _numbers(reqs, F.UW) == {1.4, 1.3}


def test_facade_db_kept_apart_from_box_and_inlet_db() -> None:
    reqs = _extract(
        "Isolement minimal de façade : 30 d(B) à 38 d(B), selon étude acoustique.\n\n"
        "- Façades à 35 dB DnTA,tr - 35 dB Châssis vitrés RA, tr (Rw+Ctr) - 35 dB "
        "Coffres de volets roulants sans EA Dn,e,w + Ctr ≥ 48 dB "
        "Entrées d'air dans châssis Dn,e,w + Ctr ≥ 39 dB"
    )
    # facade values plus the shutter box's own Dn,e,w; never the inlet's 39 dB
    assert _numbers(reqs, F.ACOUSTIC) == {30, 35, 38, 48}
    assert "39 dB" in _values(reqs, F.AIR_INLETS)


def test_shutter_box_rating_under_a_shutter_heading() -> None:
    reqs = _extract(
        "Performance acoustique\n\nDne,w,Ctr = 45 dB\n\n"
        "Coffres : Dn,e,w + Ctr ≥ 47 à 42 dB suivant façades (sans entrée d'air)",
        heading="2.3 Volets roulants",
    )
    assert _numbers(reqs, F.ACOUSTIC) == {45, 47, 42}


def test_finishes_and_named_colours() -> None:
    reqs = _extract(
        "Menuiseries en PVC plaxé, teintées dans la masse, coloris RAL Gris 7007.\n\n"
        "Traitement par thermolaquage, teinte Canon de fusil.\n\n"
        "Lame finale en aluminium laqué."
    )
    finishes = _values(reqs, F.FINISH)
    assert {"plaxé", "teinté dans la masse", "thermolaquage"} <= finishes
    assert "laqué" not in finishes  # a shutter slat, not the joinery
    colours = _values(reqs, F.COLOR)
    assert "gris RAL 7007" in colours
    assert any("canon de fusil" in c.lower() for c in colours)


def test_type_x_ou_equivalent_follows_the_subject() -> None:
    reqs = _extract(
        "Allège en vitrage anti-chute de type STADIP PROTECT de chez Verrier ou équivalent.\n\n"
        "Crémone encastrée type FERCO ou équivalent.\n\n"
        "Coffres acoustiques de type COFFRAX de chez Fabricant ou équivalent.\n\n"
        "Profilés de type Gamme Confort 70 ou équivalent."
    )
    assert any("STADIP" in v for v in _values(reqs, F.SAFETY_GLAZING))
    assert any("FERCO" in v for v in _values(reqs, F.HARDWARE))
    assert any("COFFRAX" in v for v in _values(reqs, F.SHUTTERS))
    profiles = _values(reqs, F.PROFILE_SYSTEM)
    assert any("Confort 70" in v for v in profiles)
    assert not any(word in v for v in profiles for word in ("STADIP", "FERCO", "COFFRAX"))


def test_glazing_hardware_and_opening_wordings() -> None:
    reqs = _extract(
        "Vitrage sablé en salle de bains, double vitrage avec remplissage argon.\n\n"
        "Vitrage feuilleté STADIP PROTECT 44.2 pour les allèges, vitrage anti-effraction au RDC.\n\n"
        "Ferrage par fiches bichromatées, tringlerie dissimulée, ferme-porte et ventouses.\n\n"
        "Ouverture oscillo-battante pour les cuisines, portes battantes motorisées en hall."
    )
    assert {"sablé", "argon"} <= {v.split()[-1] for v in _values(reqs, F.GLAZING_TYPE)}
    safety = " | ".join(_values(reqs, F.SAFETY_GLAZING))
    assert "44.2" in safety and "effraction" in safety
    hardware = " | ".join(_values(reqs, F.HARDWARE)).lower()
    for want in ("fiches", "tringlerie", "ferme-porte", "ventouses"):
        assert want in hardware, (want, hardware)
    openings = " | ".join(_values(reqs, F.OPENING_TYPE)).lower()
    assert "oscillo-battante" in openings and "portes battantes motorisées" in openings


def test_marks_classes_and_dated_texts() -> None:
    reqs = _extract(
        "Les volets roulants répondront à la NF Fermeture, classement VEMCROS : V*4 E*2 M*1 CROS*1.\n\n"
        "Certificat d'essais CERFF et joints labellisés SNJF ; serrures A2P.\n\n"
        "Circulaire interministérielle n°2007-053 du 30 novembre 2007 relative à l'accessibilité."
    )
    certs = " | ".join(_values(reqs, F.CERTIFICATIONS))
    for want in ("NF Fermeture", "VEMCROS", "CERFF", "SNJF"):
        assert want in certs, (want, certs)
    assert {"V*4 E*2 M*1 CROS*1", "A2P"} <= _values(reqs, F.SECURITY_CLASS)
    assert "circulaire du 30 novembre 2007" in {v.lower() for v in _values(reqs, F.REGULATION)}


def test_fire_class_read_under_a_fire_heading() -> None:
    reqs = _extract("Les menuiseries PVC sont M1 ou M2 au maximum.", heading="2.2 Tenue au feu")
    assert {"M1", "M2"} <= _values(reqs, F.CERTIFICATIONS)


def test_precision_reference_lists_and_works_outside_the_lot() -> None:
    reqs = _extract(
        "- NF P 78-303 Verre feuilleté pour vitrage de bâtiment\n"
        "- N.F. P 26 303 Crémone : caractéristiques et essais\n\n"
        "Ne font pas partie du présent lot :\n"
        "- l'exécution des seuils de portes-fenêtres et des appuis\n"
        "- les serrures des portes palières\n\n"
        "Conformément à la réglementation, les poignées seront placées entre 0,90 m et 1,30 m.\n\n"
        "Poignée laquée blanc placée entre 0,90 m et 1,30 m du sol."
    )
    assert not _values(reqs, F.SAFETY_GLAZING)
    hardware = " | ".join(_values(reqs, F.HARDWARE)).lower()
    assert "crémone" not in hardware and "serrure" not in hardware
    assert hardware.count("poign") == 1  # the handle spec, not the regulatory note
    assert not any(v.lower().startswith("seuil") for v in _values(reqs, F.ACCESSIBILITY))
    assert any("0,90 m" in v for v in _values(reqs, F.ACCESSIBILITY))


def test_precision_no_free_text_catch_alls() -> None:
    reqs = _extract(
        "Les entrées d'air devront être prises en compte par l'entreprise.\n\n"
        "Les calfeutrements seront soignés et conformes aux règles de l'art.\n\n"
        "- DTU 36.1 : Menuiseries en bois\n\n"
        "Isolation de la trappe par panneau de laine de roche de type Isolax ou équivalent."
    )
    assert not _values(reqs, F.AIR_INLETS)
    assert not _values(reqs, F.INSTALLATION)
    assert "Bois" not in _values(reqs, F.FRAME_MATERIAL)
    assert not _values(reqs, F.PROFILE_SYSTEM)


def test_values_end_on_a_whole_word() -> None:
    reqs = _extract(
        "Profilés PVC à 5 chambres minimum, renforts acier galvanisé, type Gamme Panoramique "
        "ou techniquement équivalent."
    )
    for value in _values(reqs, F.PROFILE_SYSTEM):
        assert not value.endswith(("Pan", "Panora")), value
    assert any("Panoramique" in v for v in _values(reqs, F.PROFILE_SYSTEM))


def test_bare_numbers_continue_a_list_of_european_standards() -> None:
    reqs = _extract(
        "Les menuiseries seront conformes au NF DTU 36.5 et aux normes "
        "EN 12207, 12208 et 12210 ; la norme 1990 de référence est citée pour mémoire."
    )
    found = _values(reqs, F.STANDARDS)
    assert {"EN 12208", "EN 12210"} <= found, found
    assert "EN 1990" not in found


def test_accessibility_range_keeps_both_bounds() -> None:
    reqs = _extract("Les poignées seront placées entre 0,90 m et 1,30 m du sol fini (PMR).")
    assert any("0,90 m et 1,30 m" in v for v in _values(reqs, F.ACCESSIBILITY))


def test_materials_are_named_in_french() -> None:
    reqs = _extract("Fenêtres en bois-aluminium, portes-fenêtres en bois massif.")
    assert {"Bois-aluminium", "Bois"} <= _values(reqs, F.FRAME_MATERIAL)


def test_standards_with_spaced_numbers_and_part_suffixes() -> None:
    reqs = _extract(
        "Essais selon les normes EN 12 207 - EN 12 208 - EN 12 210.\n\n"
        "Mise en oeuvre conforme au DTU 36-1 et au DTU 39."
    )
    found = " | ".join(sorted(_values(reqs, F.STANDARDS)))
    for want in ("EN 12 207", "EN 12 208", "EN 12 210", "DTU 36-1", "DTU 39"):
        assert want in found, (want, found)


def test_shutter_box_form_and_drive_outside_the_clause_window() -> None:
    reqs = _extract(
        "Les coffres monoblocs de volets roulants seront isolés.\n\n"
        "Les volets roulants seront à lames PVC double paroi de 8 mm, coulissant dans des "
        "coulisses aluminium, et s'enroulant sur un axe acier à l'aide d'un mécanisme de treuil.\n\n"
        "Manœuvre manuelle par tringle sauf dans les chambres PMR où les volets seront motorisés."
    )
    found = " | ".join(sorted(_values(reqs, F.SHUTTERS)))
    for want in ("monoblocs", "treuil", "tringle", "motorisés"):
        assert want in found, (want, found)


def test_shutter_drive_words_need_a_shutter_subject() -> None:
    reqs = _extract("Les menuiseries seront livrées avec une radio de chantier et des sangles.")
    assert not _values(reqs, F.SHUTTERS)


def test_generic_heads_keep_distinct_values_in_one_article() -> None:
    reqs = _extract(
        "Les baies du rez-de-chaussée recevront des volets battants à lames.\n\n"
        "Les volets roulants seront à lames aluminium et coffre intérieur isolé.\n\n"
        "- Pose en applique intérieure avec tapées d'isolation rapportées\n"
        "- Pose en tunnel pour les baies du rez-de-chaussée"
    )
    shutters = " | ".join(_values(reqs, F.SHUTTERS))
    assert "volets battants" in shutters and "volets roulants" in shutters, shutters
    installs = " | ".join(_values(reqs, F.INSTALLATION))
    assert "applique" in installs and "tunnel" in installs, installs


def test_inlet_locations_listed_under_an_inlet_article() -> None:
    reqs = _extract(
        "Implantation :\n\n- intégrées dans les coffres de VR du séjour\n- intégrées dans les traverses hautes",
        heading="2.4 Entrées d'air",
    )
    inlets = " | ".join(_values(reqs, F.AIR_INLETS))
    assert "coffres de VR" in inlets and "traverses hautes" in inlets, inlets


def test_afnor_references_without_the_nf_prefix_and_cstb_guides() -> None:
    reqs = _extract(
        "Documents de référence :\n\n"
        "- XP P 20-650 Fenêtres : pose des ouvrages\n"
        "- Règles de calcul du vent (D.T.U. P 06.011)\n"
        "- Règles neige et vent, normes P 06-006 et suivantes\n"
        "- Cahier du CSTB n° 3521 relatif aux menuiseries\n"
        "- NF DTU 37.1 (P24-203) : Menuiseries métalliques"
    )
    found = " | ".join(sorted(_values(reqs, F.STANDARDS)))
    for want in ("20-650", "06.011", "06-006", "Cahier du CSTB 3521", "DTU 37.1"):
        assert want in found, (want, found)
    assert "P24-203" not in found  # the DTU's own AFNOR alias, not another standard


def test_marks_with_their_scope_and_acotherm_classes() -> None:
    reqs = _extract(
        "Les fermetures bénéficieront de la marque NF, et les volets de la marque NF Fermetures.\n\n"
        "Profilés sous certification NF/CSTBât, classement Acotherm AC1 Th8 au minimum."
    )
    certs = " | ".join(sorted(_values(reqs, F.CERTIFICATIONS)))
    for want in ("marque NF Fermetures", "NF/CSTBât", "AC1 Th8"):
        assert want in certs, (want, certs)


def test_gas_filling_listed_under_a_glazing_make_up() -> None:
    reqs = _extract(
        "Composition des doubles vitrages :\n\n- Verre extérieur de 4 mm\n- Gaz krypton entre les verres"
    )
    types = " | ".join(_values(reqs, F.GLAZING_TYPE)).lower()
    assert "krypton" in types, types


def test_gas_word_far_from_any_glazing_is_ignored() -> None:
    reqs = _extract("Soudure des renforts sous protection argon en atelier.")
    assert not _values(reqs, F.GLAZING_TYPE)


def test_thermal_break_said_of_the_joinery() -> None:
    reqs = _extract(
        "Les fenêtres seront en aluminium à rupture de pont thermique.\n\n"
        "Les coffres de volets seront à rupture de pont thermique."
    )
    profiles = [r for r in reqs if r.field == F.PROFILE_SYSTEM]
    assert any("rupture de pont thermique" in r.value for r in profiles), profiles
    # the shutter box sentence is not about the profiles
    assert all(r.citation and "coffres" not in r.citation.quote for r in profiles)
    only_box = _extract("Les coffres de volets seront à rupture de pont thermique.")
    assert not _values(only_box, F.PROFILE_SYSTEM)
