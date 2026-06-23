"""CLI minimale — valide le pipeline Phase 0 (§12, « UI v1 = CLI »).

Usage :
    python -m simupoke.cli roster      # affiche mon Box avec stats finales
    python -m simupoke.cli stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>
"""

from __future__ import annotations

import sys

from .stats import STAT_KEYS, Build, validate_sp
from .basestats import is_known
from .i18n import stat_label, label
from .loaders import load_my_roster


def _print_stats(species: str, stats: dict[str, int]) -> None:
    for k in STAT_KEYS:
        print(f"    {stat_label(k):<10} {stats[k]:>4}")


def cmd_roster() -> int:
    try:
        roster = load_my_roster()
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    if not roster:
        print("Box vide.")
        return 0
    for mon in roster:
        name = mon.display_fr or label("species", mon.species)
        shiny = " ✨" if mon.is_shiny else ""
        print(f"\n{name}{shiny}  ({mon.species}, {label('nature', mon.nature)})")
        problems = mon.validate()
        if any("espèce inconnue" in p for p in problems):
            print("    (base stats inconnues — calcul indisponible)")
        else:
            _print_stats(mon.species, mon.final_stats())
        # On signale les autres problèmes (hors espèce inconnue déjà traitée).
        for p in problems:
            if "espèce inconnue" not in p:
                print(f"    ⚠ {p}")
    return 0


def cmd_stats(args: list[str]) -> int:
    if len(args) != 8:
        print("Usage : stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>",
              file=sys.stderr)
        return 2
    species, nature, *sp_vals = args
    if not is_known(species):
        print(f"Espèce inconnue : {species!r} (stub Phase 0)", file=sys.stderr)
        return 1
    sp = {k: int(v) for k, v in zip(STAT_KEYS, sp_vals)}
    problems = validate_sp(sp)
    if problems:
        print("Répartition SP invalide :", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    build = Build(species=species, nature=nature, sp=sp)
    print(f"{label('species', species)} ({label('nature', nature)})")
    _print_stats(species, build.final_stats())
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 0
    cmd, *rest = argv
    if cmd == "roster":
        return cmd_roster()
    if cmd == "stats":
        return cmd_stats(rest)
    print(f"Commande inconnue : {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
