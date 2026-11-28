"""Wording variants: the matcher and the rules on synthetic CCTP sentences."""

from __future__ import annotations

import pytest

from zelles.domain.spec import Citation, Requirement, SpecField
from zelles.evaluation.harness import Expected, _comparable, matches
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
        "Ferrage par fiches bichromatées, tringlerie dissimulée, ferme-porte hydraulique et ventouses 300 daN.\n\n"
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
    for want in ("NF Fermeture", "VEMCROS", "CERFF", "SNJF", "A2P"):
        assert want in certs, (want, certs)
    assert _values(reqs, F.SECURITY_CLASS) == {"V*4 E*2 M*1 CROS*1"}  # A2P is a mark
    assert "circulaire du 30 novembre 2007" in {v.lower() for v in _values(reqs, F.REGULATION)}


def test_fire_class_read_under_a_fire_heading() -> None:
    reqs = _extract("Les menuiseries PVC sont M1 ou M2 au maximum.", heading="2.2 Tenue au feu")
    assert {"M1", "M2"} <= _values(reqs, F.FIRE_RATING)


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


def test_white_named_on_the_material() -> None:
    reqs = _extract("Les menuiseries des façades arrière seront en PVC blanc.")
    assert any("blanc" in v for v in _values(reqs, F.COLOR))
    handles = _extract("Poignées en PVC blanc sur toutes les fenêtres.")
    assert not _values(handles, F.COLOR)  # a handle's colour is not the joinery's


def test_shutter_maker_named_under_a_shutter_heading() -> None:
    reqs = _extract(
        "Les volets pleins seront fournis de chez Menuisol, finition lasurée.",
        heading="2.6 Volets battants",
    )
    assert "Menuisol" in _values(reqs, F.SHUTTERS)
    elsewhere = _extract("Fourniture de joints de chez Menuisol pour les dormants.")
    assert not _values(elsewhere, F.SHUTTERS)


def test_glazing_unit_total_thickness() -> None:
    reqs = _extract("Vitrage isolant de 28 mm d'épaisseur pour les baies du séjour.")
    assert "28 mm" in _values(reqs, F.GLAZING_COMPOSITION)
    gap = _extract("Double vitrage avec une lame d'air de 16 mm d'épaisseur.")
    assert "16 mm" not in _values(gap, F.GLAZING_COMPOSITION)  # the gap, not the unit


def test_unit_m2_is_no_fire_class() -> None:
    reqs = _extract(
        "Réaction au feu : les panneaux auront une résistance thermique R ≥ 2 M2.K/W.",
        heading="3 Sécurité incendie",
    )
    assert "M2" not in _values(reqs, F.FIRE_RATING)
    fire = _extract("Les menuiseries PVC seront classées M1.", heading="3 Sécurité incendie")
    assert "M1" in " ".join(_values(fire, F.FIRE_RATING))


def test_frame_material_ignores_hinges_added_frames_and_interior_joinery() -> None:
    for text in (
        "Les paumelles des fenêtres seront en aluminium.",
        "Bâti bois rapporté autour des châssis existants.",
        "Les menuiseries intérieures seront en bois.",
    ):
        assert not _values(_extract(text), F.FRAME_MATERIAL), text
    assert _values(_extract("Les fenêtres seront en aluminium."), F.FRAME_MATERIAL)


def test_opaque_wall_is_no_glazing() -> None:
    assert not _values(
        _extract("Remplissage du châssis par une paroi opaque sous le vitrage."), F.GLAZING_TYPE
    )
    assert _values(_extract("Vitrage opaque pour les salles de bains."), F.GLAZING_TYPE)


def test_panic_device_bolt_is_no_opening_type() -> None:
    reqs = _extract("Les portes recevront un dispositif anti-panique à pêne coulissant.")
    assert not _values(reqs, F.OPENING_TYPE)


def test_safety_stay_keeps_its_qualifier() -> None:
    reqs = _extract("Les ouvrants à soufflet seront équipés de compas de sécurité.")
    assert "compas de sécurité" in _values(reqs, F.HARDWARE)


def test_standard_family_without_number_is_no_reference() -> None:
    found = _values(_extract("Normes de la série NF.P 26 et norme NF P 20-302."), F.STANDARDS)
    assert any("20" in v and "302" in v for v in found), found
    assert not any(v.replace(".", " ").split()[-1] == "26" for v in found), found


def test_glass_set_in_a_rebate_is_no_installation() -> None:
    glass = _extract("Le vitrage sera posé en feuillure avec parcloses clippées.")
    assert not _values(glass, F.INSTALLATION)
    frame = _extract("Les fenêtres seront posées en feuillure de maçonnerie.")
    assert _values(frame, F.INSTALLATION)


def test_hardware_values_end_before_a_second_part_and_keep_the_maker() -> None:
    reqs = _extract(
        "Condamnation par crémone encastrée avec poignée à lever en fourche.\n\n"
        'Crémone "pompier" en applique sur vantail semi-fixe.'
    )
    hardware = _values(reqs, F.HARDWARE)
    assert any(v.lower().startswith("poignée à lever") for v in hardware), hardware
    assert not any("crémone" in v.lower() and "poignée" in v.lower() for v in hardware), hardware
    assert any(v.startswith("Crémone pompier") for v in hardware), hardware  # no quotes
    supplier = _values(
        _extract("Poignée de manceuvre laquée des Ets Durand ou équivalent."), F.HARDWARE
    )
    # OCR slip mended; the maker identifies the part, "ou équivalent" does not
    assert "Poignée de manœuvre laquée des Ets Durand" in supplier, supplier


def test_hardware_parts_named_in_a_fitting_list() -> None:
    reqs = _extract(
        "- Béquille sur rosette laquée, demi-cylindre de sûreté\n"
        "- Crémone périphérique à rouleaux, support d'angle et compas de sécurité\n"
        "- Bandeau avec sélecteur de vantail, contacteur à clef et bandeaux ventouses\n"
        "- Butées de porte, aile de préhension sur l'ouvrant, ferrures inox"
    )
    hardware = " | ".join(_values(reqs, F.HARDWARE)).lower()
    for want in (
        "rosette",
        "cylindre",
        "support d'angle",
        "sélecteur de vantail",
        "contacteur à clef",
        "bandeaux ventouses",
        "butées",
        "aile de préhension",
        "ferrures",
    ):
        assert want in hardware, (want, hardware)


def test_a_stop_on_a_shutter_slat_is_not_window_hardware() -> None:
    reqs = _extract("Une butée caoutchouc limite la course du tablier en position haute.")
    assert not _values(reqs, F.HARDWARE)


def test_shutter_drive_ends_before_its_scope_or_backup() -> None:
    reqs = _extract(
        "- Manœuvre électrique pour les baies du séjour avec manœuvre manuelle de secours.",
        heading="2.3 Volets roulants",
    )
    shutters = _values(reqs, F.SHUTTERS)
    # the backup drive is read on its own, and no value runs on past "pour …"
    assert any(v.startswith("manœuvre manuelle de secours") for v in shutters), shutters
    assert not any("pour les baies" in v for v in shutters), shutters
    alone = _values(_extract("- Manœuvre électrique pour les baies du séjour."), F.SHUTTERS)
    assert alone == {"Manœuvre électrique"}, alone


def test_comparable_splits_a_lone_letter_from_its_number() -> None:
    assert _comparable("NF P20-302") == _comparable("NF.P 20.302")
    assert "rc2" in _comparable("classe RC2")


def test_comparable_spaces_codes_and_european_numbers() -> None:
    assert _comparable("NF EN 14 024") == _comparable("NF EN 14024")
    assert _comparable("NF EN 12207") == _comparable("NF EN 12-207")
    assert _comparable("NV 65") == _comparable("NV65")
    assert _comparable("EI 30") == _comparable("EI30")
    assert _comparable("EN 12207") not in _comparable("EN 12208")
    assert _comparable("CTB – A") == _comparable("CTB - A")


def test_aev_classes_match_with_or_without_stars() -> None:
    def pred(value: str) -> Requirement:
        quote = Citation(chunk_id="c", quote=value, match_score=1.0)
        return Requirement(field=F.AEV, value=value, citation=quote)

    assert matches(pred("A*2 E*4 V*A2"), Expected(field=F.AEV, value="A2 E4 VA2"), strict=True)
    assert matches(
        pred("A*3 E*7B V*A3"), Expected(field=F.AEV, value="A*3 – E*7b – V*a3"), strict=True
    )
    assert not matches(
        pred("A*3 E*6B V*A3"), Expected(field=F.AEV, value="A*3 E*7B V*A3"), strict=True
    )


def test_fire_classes_as_resistance_degrees_and_euroclasses() -> None:
    reqs = _extract(
        "Porte pleine EI 30 à 1 vantail.\n\n"
        "Les vitrages seront de type coupe-feu (EI / 60).\n\n"
        "Performance incendie : E30, châssis fixes et CF1h.\n\n"
        "Baies PF ½ heure en façade.\n\n"
        "Classement de réaction au feu : B-s2,d0 ;"
    )
    fire = _values(reqs, F.FIRE_RATING)
    for want in ("EI 30", "EI 60", "E 30", "CF1h", "B-s2,d0"):
        assert want in fire, (want, fire)
    assert any(v.startswith("PF") for v in fire), fire
    assert not _values(_extract("Vitrage 4/16/4, épaisseur E 30 mm."), F.FIRE_RATING)


def test_standards_keep_prefix_part_and_amendment() -> None:
    reqs = _extract(
        "Normes de référence :\n\n"
        "- FD DTU 34.2 Volets\n"
        "- NF DTU 34.5 P2 - DTU 34.5 Travaux de bâtiment\n"
        "- NF EN 1991-1-4/NA\n"
        "- XP P20-650-1\n"
        "- NF C 15-100\n"
        "- DIN 18055 et ENV 13050\n"
        "- Règles NV 65 et NV 84"
    )
    std = _values(reqs, F.STANDARDS)
    for want in (
        "FD DTU 34.2",
        "NF DTU 34.5 P2",
        "NF EN 1991-1-4/NA",
        "XP P20-650-1",
        "NF C 15-100",
        "DIN 18055",
        "ENV 13050",
        "NV 84",
    ):
        assert want in std, (want, std)
    assert "DTU 34.2" not in std and "DTU 34.5" not in std, std


def test_standards_lists_repeat_the_first_prefix() -> None:
    reqs = _extract(
        "Les ouvrages seront conformes aux normes NF P 85-530/540/541, "
        "aux D.T.U. n° 39.1, 39.4 et 36.1 et aux normes NFP 08.301 et 302."
    )
    std = _values(reqs, F.STANDARDS)
    for want in (
        "NF P 85-530",
        "NF P 85-540",
        "NF P 85-541",
        "D.T.U. n° 39.4",
        "D.T.U. n° 36.1",
        "NFP 08.302",
    ):
        assert want in std, (want, std)
    lone = _values(_extract("Pose selon le DTU 36.5 et 400 m2 de façade."), F.STANDARDS)
    assert lone == {"DTU 36.5"}, lone


def test_standards_skip_aliases_and_index_codes() -> None:
    reqs = _extract(
        "Etanchéité selon le DTU 44.1 (NF P85-210-1) et le DTU 44.1 (FD P85-210-3).\n\n"
        "Norme NF EN 12207 (Indice de classement : P20-302)."
    )
    std = _values(reqs, F.STANDARDS)
    assert "DTU 44.1" in std and "NF EN 12207" in std, std
    assert not any("85-210" in v or "20-302" in v for v in std), std  # aliases, index codes


def test_numeric_wordings_with_notes_and_slashed_comparators() -> None:
    reqs = _extract(
        "- Coef. de transmission thermique Uw (fenêtre) <= 1.20 W/m2.°C\n"
        "- Coef. de transmission thermique Ud (portes) <= 1.50 W/m2.°C\n"
        "- Coef. de transmission thermique Ug (vitrage) <= 1.00 W/m2.°C\n"
        "- facteur solaire Sw </= 0.35\n"
        "- performance acoustique minimale : RAtr ≥ 30dB\n"
        "- Les Rw+C tr seront calculés pour un classement des façades de 35 dB."
    )
    assert {1.2, 1.5} <= _numbers(reqs, F.UW)
    assert _numbers(reqs, F.UG) == {1.0}
    assert _numbers(reqs, F.SW) == {0.35}
    assert {30.0, 35.0} <= _numbers(reqs, F.ACOUSTIC)


def test_certification_marks_with_their_scope() -> None:
    reqs = _extract(
        "La certification minimale requise est la certification NF.\n\n"
        "Quincaillerie comportant la marque NF040.\n\n"
        "Label ACOTHERM AC2 ; bois certifié CTB-B+.\n\n"
        "Paumelles renforcées NF SNFQ laquées ; label EWAA et label ECCA.\n\n"
        "Les fiches environnementales (FDES) et les essais CEBTP seront fournis."
    )
    certs = _values(reqs, F.CERTIFICATIONS)
    for want in ("NF", "NF040", "ACOTHERM AC2", "CTB-B+", "NF SNFQ", "EWAA", "ECCA"):
        assert want in certs, (want, certs)
    assert not {"FDES", "CEBTP", "SNFQ", "ACOTHERM"} & certs, certs


def test_coded_values_of_glazing_colour_and_steel() -> None:
    reqs = _extract(
        "Double vitrage isolant 4/16 argon/4 ; ailleurs le vitrage sera du SP510/14/4.\n\n"
        "Profilés de teinte Brun cuivré RAL 8004 ou Brun argile RAL 8003.\n\n"
        "Porte acier de type robuste."
    )
    assert {"4/16 argon/4", "SP510/14/4"} <= _values(reqs, F.GLAZING_COMPOSITION)
    colours = " | ".join(_values(reqs, F.COLOR))
    assert "RAL 8004" in colours and "RAL 8003" in colours, colours
    assert "Acier" in _values(reqs, F.FRAME_MATERIAL)
    choice = _extract("Fenêtre type aluminium, PVC ou bois avec double vitrage.")
    assert {"Aluminium", "PVC", "Bois"} <= _values(choice, F.FRAME_MATERIAL)
    article = _extract("3-08-1 Châssis fixe trapézoïdal avec vitrage feuilleté.")
    assert not _values(article, F.GLAZING_COMPOSITION)


def test_hardware_parts_keep_their_qualifiers_to_the_clause_end() -> None:
    reqs = _extract(
        "Quincaillerie :\n\n"
        "- Gâches en Zamak ou en PA 66 chargé de fibres de verre ;\n"
        "- béquille formant butoir au sol et permettant le maintien de la porte ouverte ;\n"
        "- Paumelles en acier bichromaté laqué, de teinte blanche ;\n"
        "- Ferme-porte à glissière intégré au dormant de porte de chez Dorma ou équivalent ;\n"
        "- Gâche électrique suivant tableau de menuiseries."
    )
    hardware = _values(reqs, F.HARDWARE)
    for want in (
        "béquille formant butoir au sol",
        "Paumelles en acier bichromaté laqué",
        "Ferme-porte à glissière intégré au dormant de porte de chez Dorma",
        "Gâche électrique",
    ):
        assert want in hardware, (want, hardware)


def test_items_listed_under_a_shutter_article() -> None:
    reqs = _extract(
        "Les volets seront composés de :\n\n"
        "- tablier composé de lames en aluminium double paroi avec mousse isolante ;\n"
        "- La motorisation électrique avec fins de course ;\n"
        "- verrouillage automatique du volet en position fermée",
        heading="4.2 Volets roulants",
    )
    shutters = " | ".join(_values(reqs, F.SHUTTERS))
    for want in (
        "lames en aluminium double paroi",
        "motorisation électrique",
        "verrouillage automatique",
    ):
        assert want in shutters, (want, shutters)
    store = _extract("Toile acrylique sur store à projection motorisé.")
    assert any("store à projection" in v.lower() for v in _values(store, F.SHUTTERS))


def test_removal_and_no_values_from_document_lists_or_list_titles() -> None:
    reqs = _extract("La dépose des portes et volets roulants existants est due au présent lot.")
    installation = " | ".join(_values(reqs, F.INSTALLATION))
    for want in ("dépose des portes",):
        assert want in installation, (want, installation)
    documents = _extract("Fournir les fiches techniques des serrures, mastics et paumelles.")
    assert not _values(documents, F.HARDWARE)
    title = _extract("Tablier :\n- lames en aluminium", heading="4.2 Volets roulants")
    assert "Tablier" not in _values(title, F.SHUTTERS)


def test_finish_species_and_coatings_of_the_joinery() -> None:
    reqs = _extract(
        "Bois : mélèze ou eucalyptus lasuré teinte au choix de l'Architecte.\n\n"
        "Finition laquée par poudre polyester thermodurcissable sur une épaisseur de 80 microns, "
        "aspect satiné."
    )
    finish = " | ".join(_values(reqs, F.FINISH))
    for want in ("mélèze", "eucalyptus", "poudre polyester thermodurcissable", "aspect satiné"):
        assert want in finish, (want, finish)
    handle = _extract("Poignées en aluminium anodisé sur les fenêtres.")
    assert not _values(handle, F.FINISH)


def test_profile_makers_glazing_bars_and_traditional_profiles() -> None:
    reqs = _extract(
        "Les ensembles menuisés proviendront de fournisseurs réputés tel que BIEBER, LORILLARD "
        "ou techniquement équivalent.\n\n"
        "Porte isolante simple action (WICSTYLE 65FP ou techniquement équivalent).\n\n"
        "- Petits bois rapportés face interne selon plans.\n\n"
        "Profils traditionnels à mouton et gueule de loup."
    )
    profiles = " | ".join(_values(reqs, F.PROFILE_SYSTEM))
    for want in (
        "BIEBER",
        "LORILLARD",
        "WICSTYLE 65FP",
        "Petits bois rapportés face interne",
        "mouton et gueule de loup",
    ):
        assert want in profiles, (want, profiles)


def test_no_hardware_or_shutter_values_from_general_or_framing_sentences() -> None:
    general = _extract(
        "Les ferrures utilisées seront de bonne qualité.\n\n"
        "Chaque serrure livrée avec 3 clés.\n\n"
        "Le contrôle, le réglage et la remise en état des paumelles et serrures.\n\n"
        "Serrure à plus de 30 cm d'un angle rentrant.\n\n"
        "Fourniture du cylindre des portes provisoires."
    )
    assert not _values(general, F.HARDWARE)
    lock_case = _extract("Crémone encastrée avec coffre de serrure et cylindre simple entrée.")
    assert not any("coffre" in v.lower() for v in _values(lock_case, F.SHUTTERS))
    framing = _extract("Le rajout de volets roulants extérieurs.", heading="1 Objet du marché")
    assert not _values(framing, F.SHUTTERS)
    contents = _extract("3.6 Volets bois extérieurs ........................ 36")
    assert not _values(contents, F.SHUTTERS)


def test_part_descriptions_keep_counts_and_whole_names() -> None:
    reqs = _extract(
        "Ferrage 4 paumelles de 160 mm par vantail.\n\n"
        "Crémone-serrure à verrouillage automatique, demi-cylindre européen et serrures.\n\n"
        "Barre anti-panique de type 42 CLASSIC de chez Dupont."
    )
    hardware = _values(reqs, F.HARDWARE)
    joined = " | ".join(hardware)
    for want in (
        "4 paumelles de 160 mm",
        "demi-cylindre européen",
        "Barre anti-panique de type 42",
    ):
        assert want in joined, (want, joined)
    assert not any(v.startswith(("serrure à verrouillage", "cylindre")) for v in hardware)
    assert "serrures" not in hardware  # a bare name beside described parts
