"""CLI minimale — valide le pipeline Phase 0 (§12, « UI v1 = CLI »).

Usage :
    python -m simupoke.cli roster      # affiche mon Box avec stats finales
    python -m simupoke.cli stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>
    python -m simupoke.cli damage <atk_species> <atk_nature> <move> <def_species> <def_nature>
        [--crit] [--spread] [--weather X] [--item-atk X] [--ability-atk X]
        [--atk-sp k=v,...] [--def-sp k=v,...] [--boost-atk N]
    python -m simupoke.cli draft <lineup.json> [--no-roster]   # B2 aide au tirage
    python -m simupoke.cli team <team.json>                     # B3 analyse d'équipe
    python -m simupoke.cli preview <my_team.json> <opp.json> [--format singles|doubles]
    python -m simupoke.cli analyze <me_species> <me_nature> <me_moves> <opp_species> <opp_nature>
        [--opp-move X] [--opp-moves a,b,c] [--me-sp k=v,...] [--opp-sp k=v,...]
        [--me-item X] [--opp-item X] [--me-hp 0..1] [--opp-hp 0..1] [--weather X]
"""

from __future__ import annotations

import sys

from .stats import STAT_KEYS, Build, validate_sp
from .basestats import is_known
from .i18n import stat_label, label
from .loaders import load_my_roster
from .model import PokemonState, FieldState
from .damage import calculate
from .loaders import load_lineup, load_team
from .draft import rank_lineup
from .team import analyze_team, select_team_preview
from .combat import analyze_turn


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


def _parse_sp(spec: str) -> dict[str, int]:
    """Parse 'atk=31,spe=20' -> {'atk':31,'spe':20}."""
    sp: dict[str, int] = {}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        sp[k.strip()] = int(v)
    return sp


_DAMAGE_FLAGS = {"crit", "spread"}


def cmd_damage(args: list[str]) -> int:
    # Sépare positionnels, drapeaux (--crit/--spread) et options (--clé valeur).
    pos: list[str] = []
    opts: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            if key in _DAMAGE_FLAGS:
                flags.add(key)
            else:
                opts[key] = args[i + 1] if i + 1 < len(args) else ""
                i += 1
        else:
            pos.append(a)
        i += 1

    if len(pos) != 5:
        print("Usage : damage <atk_species> <atk_nature> <move> "
              "<def_species> <def_nature> [options]", file=sys.stderr)
        return 2
    atk_species, atk_nature, move, def_species, def_nature = pos

    for sp_name, sp_key in (("atk", atk_species), ("def", def_species)):
        if not is_known(sp_key):
            print(f"Espèce inconnue : {sp_key!r}", file=sys.stderr)
            return 1

    attacker = PokemonState(
        species=atk_species, nature=atk_nature,
        stat_points=_parse_sp(opts.get("atk-sp", "")),
        item=opts.get("item-atk"), ability=opts.get("ability-atk"),
        status=opts.get("status-atk"),
        boosts={"atk": int(opts.get("boost-atk", 0)),
                "spa": int(opts.get("boost-spa", 0))},
    )
    defender = PokemonState(
        species=def_species, nature=def_nature,
        stat_points=_parse_sp(opts.get("def-sp", "")),
        item=opts.get("item-def"), ability=opts.get("ability-def"),
    )
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"))
    try:
        r = calculate(attacker, defender, move, field,
                      crit="crit" in flags, apply_spread="spread" in flags)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    a_name = label("species", atk_species)
    d_name = label("species", def_species)
    print(f"{a_name} -> {d_name}")
    print(r.describe())
    return 0


def cmd_draft(args: list[str]) -> int:
    pos = [a for a in args if not a.startswith("--")]
    use_roster = "--no-roster" not in args
    use_usage = "--usage" in args
    if len(pos) != 1:
        print("Usage : draft <lineup.json> [--no-roster] [--usage]", file=sys.stderr)
        return 2
    try:
        lineup = load_lineup(pos[0])
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    roster = load_my_roster() if use_roster else []
    prior = None
    if use_usage:
        from .usage import usage_prior, has_usage
        prior = usage_prior() if has_usage() else None
    print(f"Tirage du jour — {len(lineup)} Pokémon"
          + (f" (synergie avec mon Box : {len(roster)})" if roster else "")
          + (" + prior d'usage" if prior else "")
          + "\n")
    for i, e in enumerate(rank_lineup(lineup, roster=roster, usage_prior=prior), 1):
        name = label("species", e.species)
        print(f"{i:2}. {name:<14} {e.score100:3}/100  {e.role_fr:<8}  "
              f"{e.recommendation}")
        print(f"      {' · '.join(e.reasons)}")
    return 0


def cmd_team(args: list[str]) -> int:
    pos = [a for a in args if not a.startswith("--")]
    if len(pos) != 1:
        print("Usage : team <team.json>", file=sys.stderr)
        return 2
    try:
        team = load_team(pos[0])
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"Analyse d'équipe — {len(team)} Pokémon"
          f" ({', '.join(label('species', m.species) for m in team)})\n")
    for line in analyze_team(team).lines():
        print(line)
    return 0


def cmd_preview(args: list[str]) -> int:
    pos: list[str] = []
    fmt = "singles"
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format":
            fmt = args[i + 1] if i + 1 < len(args) else fmt
            i += 1
        elif not a.startswith("--"):
            pos.append(a)
        i += 1
    if len(pos) != 2:
        print("Usage : preview <my_team.json> <opp.json> [--format singles|doubles]",
              file=sys.stderr)
        return 2
    try:
        my_team = load_team(pos[0])
        opp = load_team(pos[1])
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    for line in select_team_preview(my_team, opp, fmt).lines():
        print(line)
    return 0


def cmd_analyze(args: list[str]) -> int:
    pos: list[str] = []
    opts: dict[str, str] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            opts[a[2:]] = args[i + 1] if i + 1 < len(args) else ""
            i += 1
        else:
            pos.append(a)
        i += 1
    if len(pos) != 5:
        print("Usage : analyze <me_species> <me_nature> <me_moves> "
              "<opp_species> <opp_nature> [options]", file=sys.stderr)
        return 2
    me_species, me_nature, me_moves, opp_species, opp_nature = pos
    for sp in (me_species, opp_species):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    me = PokemonState(
        species=me_species, nature=me_nature,
        stat_points=_parse_sp(opts.get("me-sp", "")),
        moves=[m.strip() for m in me_moves.split(",") if m.strip()],
        item=opts.get("me-item"),
        current_hp_pct=float(opts.get("me-hp", 1.0)),
    )
    opp = PokemonState(
        species=opp_species, nature=opp_nature,
        stat_points=_parse_sp(opts.get("opp-sp", "")),
        moves=[m.strip() for m in opts.get("opp-moves", "").split(",") if m.strip()],
        item=opts.get("opp-item"),
        current_hp_pct=float(opts.get("opp-hp", 1.0)),
    )
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"))
    try:
        analysis = analyze_turn(me, opp, field, opp_move=opts.get("opp-move"))
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', me_species)}  vs  {label('species', opp_species)}\n")
    for line in analysis.lines():
        print(line)
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
    if cmd == "damage":
        return cmd_damage(rest)
    if cmd == "draft":
        return cmd_draft(rest)
    if cmd == "team":
        return cmd_team(rest)
    if cmd == "preview":
        return cmd_preview(rest)
    if cmd == "analyze":
        return cmd_analyze(rest)
    print(f"Commande inconnue : {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
