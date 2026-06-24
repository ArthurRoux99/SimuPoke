"""Tests de fumée du CLI (dispatch + robustesse d'encodage de sortie)."""

from __future__ import annotations

from simupoke import cli


def test_main_no_args_prints_doc(capsys):
    assert cli.main([]) == 0
    assert "python -m simupoke.cli" in capsys.readouterr().out


def test_main_unknown_command():
    assert cli.main(["pas-une-commande"]) == 2


def test_draft_with_usage_outputs_bullets(capsys):
    # Régression : la sortie contient « • » et des accents — ne doit pas crasher
    # même quand la console est en cp1252 (cf. _force_utf8_stdout).
    assert cli.main(["draft", "data/sample_lineup.json", "--usage"]) == 0
    out = capsys.readouterr().out
    assert "prior d'usage" in out
