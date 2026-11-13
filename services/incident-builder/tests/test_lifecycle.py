"""Cycle de vie d'une alerte (EF-06) : transitions et attribution, sans base de données."""
from __future__ import annotations

import itertools
import uuid

import pytest

from incidents.alert_state import STATUSES, TRANSITIONS, Refused, State, assign, change_status

ANA = uuid.UUID("5d6e7f80-91a2-4b3c-8d4e-5f6a7b8c9d05")
BOB = uuid.UUID("5d6e7f80-91a2-4b3c-8d4e-5f6a7b8c9d06")
NOUVELLE = State("nouvelle", None)
EN_COURS = State("en_cours", ANA)
CLOTUREE = State("cloturee", ANA)


def invariant(s: State) -> bool:
    return (s.status != "nouvelle" or s.assigned_to is None) and (s.status != "en_cours" or s.assigned_to is not None)


def test_prise_en_charge_assigne_l_auteur():
    assert change_status(NOUVELLE, "en_cours", ANA) == State("en_cours", ANA)


def test_retour_dans_la_file_retire_l_assigne():
    assert change_status(EN_COURS, "nouvelle", BOB) == NOUVELLE


def test_cloture_conserve_le_dernier_assigne():
    assert change_status(EN_COURS, "cloturee", BOB) == State("cloturee", ANA)


def test_cloture_directe_d_une_alerte_nouvelle():
    assert change_status(NOUVELLE, "cloturee", ANA) == State("cloturee", None)


def test_reouverture_assigne_l_auteur():
    assert change_status(CLOTUREE, "en_cours", BOB) == State("en_cours", BOB)


def test_cloturee_ne_revient_pas_directement_dans_la_file():
    with pytest.raises(Refused) as e:
        change_status(CLOTUREE, "nouvelle", ANA)
    assert e.value.code == "transition_interdite"


@pytest.mark.parametrize("status", STATUSES)
def test_meme_statut_refuse(status):
    state = {"nouvelle": NOUVELLE, "en_cours": EN_COURS, "cloturee": CLOTUREE}[status]
    with pytest.raises(Refused) as e:
        change_status(state, status, ANA)
    assert e.value.code == "transition_interdite" and "déjà" in e.value.message


def test_table_des_transitions_complete_et_sans_boucle():
    assert set(TRANSITIONS) == set(STATUSES)
    assert all(src not in dst and dst <= set(STATUSES) for src, dst in TRANSITIONS.items())


def test_assigner_une_alerte_nouvelle_la_prend_en_charge():
    assert assign(NOUVELLE, BOB) == State("en_cours", BOB)


def test_reassigner_une_alerte_en_cours():
    assert assign(EN_COURS, BOB) == State("en_cours", BOB)


def test_retirer_l_assigne_remet_dans_la_file():
    assert assign(EN_COURS, None) == NOUVELLE


@pytest.mark.parametrize("state,assignee", [(EN_COURS, ANA), (NOUVELLE, None)])
def test_assignation_sans_effet_refusee(state, assignee):
    with pytest.raises(Refused) as e:
        assign(state, assignee)
    assert e.value.code == "transition_interdite"


@pytest.mark.parametrize("assignee", [ANA, BOB, None])
def test_alerte_cloturee_non_assignable(assignee):
    with pytest.raises(Refused) as e:
        assign(CLOTUREE, assignee)
    assert "rouvrir" in e.value.message


def test_invariant_nouvelle_sans_assigne_en_cours_avec_assigne():
    """Toutes les séquences de commandes de longueur 4 partant d'une alerte nouvelle conservent l'invariant."""
    actions = [("statut", s) for s in STATUSES] + [("assigner", ANA), ("assigner", BOB), ("assigner", None)]
    for steps in itertools.product(actions, repeat=4):
        state = NOUVELLE
        for kind, arg in steps:
            try:
                state = change_status(state, arg, BOB) if kind == "statut" else assign(state, arg)
            except Refused:
                continue
            assert invariant(state), (steps, state)
