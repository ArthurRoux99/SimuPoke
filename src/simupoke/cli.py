"""CLI minimale — valide le pipeline Phase 0 (§12, « UI v1 = CLI »).

Usage (option globale : [--lang fr|en] ou SIMUPOKE_LANG) :
    python -m simupoke.cli roster      # affiche mon Box avec stats finales
    python -m simupoke.cli stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>
    python -m simupoke.cli damage <atk_species> <atk_nature> <move> <def_species> <def_nature>
        [--crit] [--spread] [--weather X] [--item-atk X] [--ability-atk X]
        [--atk-sp k=v,...] [--def-sp k=v,...] [--boost-atk N] [--screen reflect|lightscreen|auroraveil]
    python -m simupoke.cli draft <lineup.json> [--no-roster]   # B2 aide au tirage
    python -m simupoke.cli team <team.json>                     # B3 analyse d'équipe
    python -m simupoke.cli preview <my_team.json> <opp.json> [--format singles|doubles] [--no-damage]
    python -m simupoke.cli analyze <me_species> <me_nature> <me_moves> <opp_species> <opp_nature>
        [--opp-move X] [--opp-moves a,b,c] [--me-sp k=v,...] [--opp-sp k=v,...]
        [--me-item X] [--opp-item X] [--me-hp 0..1] [--opp-hp 0..1] [--weather X]
        [--bench "species,nature,move1|move2;species2,nature2,move1|move2"]  # évalue les switchs
    python -m simupoke.cli speed <team.json> [<team2.json> ...] [--trick-room]
    python -m simupoke.cli outspeed <me_species> <me_nature> <target_species> <target_nature>
        [--target-sp k=v,...] [--me-tailwind] [--target-tailwind] [--tie]
    python -m simupoke.cli survive <def_species> <def_nature> <atk_species> <atk_nature> <move>
        [--atk-sp k=v,...] [--atk-item X] [--weather X]      # SP défensif mini pour survivre
    python -m simupoke.cli ko <atk_species> <atk_nature> <move> <def_species> <def_nature>
        [--hits N] [--def-sp k=v,...] [--def-hp 0..1] [--atk-item X]   # SP offensif mini pour KO
    python -m simupoke.cli spread <species> <nature> [--item X] [--ability X] [--budget 66]
        [--outspeed species,nature,spe=SP[,scarf][,tw][,tie]]          # objectifs répétables
        [--survive atk_species,atk_nature,move[,off=SP][,item=X]]
        [--ko def_species,def_nature,move[,hits=N][,hp=0..1][,item=X]] # -> spread SP complet
    python -m simupoke.cli sim <me_species> <me_nature> <me_moves> <opp_species> <opp_nature> <opp_moves>
        [--me-sp k=v,...] [--opp-sp k=v,...] [--me-item X] [--roll 0..1] [--weather X]
        # rejoue une ligne tour par tour (séquences de coups séparées par des virgules)
    python -m simupoke.cli paste <paste.txt> [--json]   # importe un paste Showdown (EV->SP) + analyse
    python -m simupoke.cli decide <me_species> <me_nature> <me_moves> <opp_species> <opp_nature>
        [--opp-moves a,b,c] [--me-sp k=v] [--opp-sp k=v] [--roll 0..1] [--weather X]
        [--bench "species,nature,move1|move2;species2,..."] [--depth 1..5] [--cautious] [--samples N]
        # classe mes actions ; --depth ≥2 = multi-tours ; --cautious = pire cas ; --samples N = build adverse échantillonné (usage)
"""

from __future__ import annotations

import os
import sys

from .stats import STAT_KEYS, Build, validate_sp
from .basestats import is_known
from .i18n import stat_label, label, set_language
from .loaders import load_my_roster
from .model import PokemonState, FieldState
from .damage import calculate
from .loaders import load_lineup, load_team
from .draft import rank_lineup
from .team import analyze_team, select_team_preview
from .combat import analyze_turn
from .bench import (
    speed_tiers, min_sp_to_outspeed, min_sp_to_survive, min_sp_to_ko,
)
from .optimize import optimize_spread, Outspeed, Survive, Ko
from .sim import Mon, rollout
from .search import rank_actions, rank_actions_sampled
from .showdown import parse_team as parse_showdown


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
                      crit="crit" in flags, apply_spread="spread" in flags,
                      screen=opts.get("screen"))
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
    use_damage = True
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--format":
            fmt = args[i + 1] if i + 1 < len(args) else fmt
            i += 1
        elif a == "--no-damage":
            use_damage = False
        elif not a.startswith("--"):
            pos.append(a)
        i += 1
    if len(pos) != 2:
        print("Usage : preview <my_team.json> <opp.json> "
              "[--format singles|doubles] [--no-damage]", file=sys.stderr)
        return 2
    try:
        my_team = load_team(pos[0])
        opp = load_team(pos[1])
    except FileNotFoundError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    for line in select_team_preview(my_team, opp, fmt, use_damage=use_damage).lines():
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
    bench: list[PokemonState] = []
    for chunk in opts.get("bench", "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        species = parts[0]
        if not is_known(species):
            print(f"Espèce inconnue (banc) : {species!r}", file=sys.stderr)
            return 1
        nature = parts[1] if len(parts) > 1 and parts[1] else "serious"
        moves = ([m.strip() for m in parts[2].split("|") if m.strip()]
                 if len(parts) > 2 else [])
        bench.append(PokemonState(species=species, nature=nature, moves=moves))
    try:
        analysis = analyze_turn(me, opp, field, opp_move=opts.get("opp-move"),
                                bench=bench)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', me_species)}  vs  {label('species', opp_species)}\n")
    for line in analysis.lines():
        print(line)
    return 0


def _split_args(args: list[str], flag_names: set[str]) -> tuple[list[str], dict, set]:
    """Sépare positionnels, drapeaux booléens et options `--clé valeur`."""
    pos: list[str] = []
    opts: dict[str, str] = {}
    flags: set[str] = set()
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            if key in flag_names:
                flags.add(key)
            else:
                opts[key] = args[i + 1] if i + 1 < len(args) else ""
                i += 1
        else:
            pos.append(a)
        i += 1
    return pos, opts, flags


def _owned_to_state(mon) -> PokemonState:
    return PokemonState(species=mon.species, nature=mon.nature,
                        stat_points=mon.stat_points, item=mon.item,
                        ability=mon.ability, moves=mon.moves)


def cmd_speed(args: list[str]) -> int:
    pos, _, flags = _split_args(args, {"trick-room", "tr"})
    if not pos:
        print("Usage : speed <team.json> [<team2.json> ...] [--trick-room]",
              file=sys.stderr)
        return 2
    states: list[PokemonState] = []
    for path in pos:
        try:
            states.extend(_owned_to_state(m) for m in load_team(path))
        except FileNotFoundError as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
    tr = bool(flags & {"trick-room", "tr"})
    tiers = speed_tiers(states, trick_room=tr)
    header = "Speed tiers" + (" (Trick Room : le plus lent agit en premier)" if tr else "")
    print(header + "\n")
    for i, e in enumerate(tiers, 1):
        note = f"  [{', '.join(e.notes)}]" if e.notes else ""
        print(f"{i:2}. {label('species', e.species):<16} {e.speed:>4}{note}")
    return 0


def cmd_outspeed(args: list[str]) -> int:
    pos, opts, flags = _split_args(args, {"me-tailwind", "target-tailwind", "tie"})
    if len(pos) != 4:
        print("Usage : outspeed <me_species> <me_nature> <target_species> "
              "<target_nature> [--target-sp k=v] [--me-tailwind] "
              "[--target-tailwind] [--tie]", file=sys.stderr)
        return 2
    me_sp, me_nat, tg_sp, tg_nat = pos
    for sp in (me_sp, tg_sp):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    me = PokemonState(species=me_sp, nature=me_nat,
                      item=opts.get("me-item"),
                      stat_points=_parse_sp(opts.get("me-sp", "")))
    target = PokemonState(species=tg_sp, nature=tg_nat,
                          item=opts.get("target-item"),
                          stat_points=_parse_sp(opts.get("target-sp", "")))
    res = min_sp_to_outspeed(
        me, target, me_tailwind="me-tailwind" in flags,
        target_tailwind="target-tailwind" in flags, strict="tie" not in flags)
    print(f"{label('species', me_sp)} vs {label('species', tg_sp)}")
    print(res.line())
    return 0


def cmd_survive(args: list[str]) -> int:
    pos, opts, _ = _split_args(args, {"crit"})
    if len(pos) != 5:
        print("Usage : survive <def_species> <def_nature> <atk_species> "
              "<atk_nature> <move> [--atk-sp k=v] [--atk-item X] [--weather X]",
              file=sys.stderr)
        return 2
    def_sp, def_nat, atk_sp, atk_nat, move = pos
    for sp in (def_sp, atk_sp):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    defender = PokemonState(species=def_sp, nature=def_nat)
    attacker = PokemonState(species=atk_sp, nature=atk_nat,
                            item=opts.get("atk-item"),
                            ability=opts.get("atk-ability"),
                            stat_points=_parse_sp(opts.get("atk-sp", "")))
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"))
    try:
        res = min_sp_to_survive(defender, attacker, move, field)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', def_sp)} face à {label('species', atk_sp)}")
    print(res.line())
    return 0


def cmd_ko(args: list[str]) -> int:
    pos, opts, _ = _split_args(args, {"crit"})
    if len(pos) != 5:
        print("Usage : ko <atk_species> <atk_nature> <move> <def_species> "
              "<def_nature> [--hits N] [--def-sp k=v] [--def-hp 0..1] "
              "[--atk-item X]", file=sys.stderr)
        return 2
    atk_sp, atk_nat, move, def_sp, def_nat = pos
    for sp in (atk_sp, def_sp):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    attacker = PokemonState(species=atk_sp, nature=atk_nat,
                            item=opts.get("atk-item"),
                            ability=opts.get("atk-ability"))
    defender = PokemonState(species=def_sp, nature=def_nat,
                            item=opts.get("def-item"),
                            stat_points=_parse_sp(opts.get("def-sp", "")),
                            current_hp_pct=float(opts.get("def-hp", 1.0)))
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"))
    try:
        res = min_sp_to_ko(attacker, defender, move, field,
                           hits=int(opts.get("hits", 1)))
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', atk_sp)} -> {label('species', def_sp)}")
    print(res.line())
    return 0


def _parse_spec(spec: str, n_pos: int) -> tuple[list[str], dict[str, str], set[str]]:
    """Découpe 'garchomp,jolly,spe=32,scarf' en (positionnels, k=v, drapeaux)."""
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    pos = parts[:n_pos]
    kv: dict[str, str] = {}
    flags: set[str] = set()
    for p in parts[n_pos:]:
        if "=" in p:
            k, _, v = p.partition("=")
            kv[k.strip()] = v.strip()
        else:
            flags.add(p)
    return pos, kv, flags


def cmd_spread(args: list[str]) -> int:
    # Options répétables (--outspeed/--survive/--ko) : parseur dédié.
    pos: list[str] = []
    objectives: list = []
    budget = 66
    item = ability = None
    i = 0
    err = None
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:]
            val = args[i + 1] if i + 1 < len(args) else ""
            i += 2
            try:
                if key == "outspeed":
                    p, kv, fl = _parse_spec(val, 2)
                    objectives.append(Outspeed(
                        target=PokemonState(species=p[0], nature=p[1],
                            item="choicescarf" if "scarf" in fl else None,
                            stat_points={"spe": int(kv.get("spe", 0))}),
                        strict="tie" not in fl,
                        target_tailwind="tw" in fl, label=p[0]))
                elif key == "survive":
                    p, kv, fl = _parse_spec(val, 3)
                    off = int(kv.get("off", 0))
                    objectives.append(Survive(
                        attacker=PokemonState(species=p[0], nature=p[1],
                            item=kv.get("item"),
                            stat_points={"atk": off, "spa": off}),
                        move=p[2], crit="crit" in fl, label=f"{p[2]} de {p[0]}"))
                elif key == "ko":
                    p, kv, fl = _parse_spec(val, 3)
                    objectives.append(Ko(
                        defender=PokemonState(species=p[0], nature=p[1],
                            item=kv.get("item"),
                            current_hp_pct=float(kv.get("hp", 1.0))),
                        move=p[2], hits=int(kv.get("hits", 1)),
                        crit="crit" in fl, label=f"{p[2]} sur {p[0]}"))
                elif key == "budget":
                    budget = int(val)
                elif key == "item":
                    item = val
                elif key == "ability":
                    ability = val
            except (IndexError, ValueError):
                err = a
                break
        else:
            pos.append(a)
            i += 1
    if err or len(pos) != 2:
        print("Usage : spread <species> <nature> [--item X] [--ability X] "
              "[--budget 66]\n"
              "  --outspeed <species,nature,spe=SP[,scarf][,tw][,tie]>   (répétable)\n"
              "  --survive  <atk_species,atk_nature,move[,off=SP][,item=X][,crit]>\n"
              "  --ko       <def_species,def_nature,move[,hits=N][,hp=0..1][,item=X]>",
              file=sys.stderr)
        return 2
    me_species, me_nature = pos
    if not is_known(me_species):
        print(f"Espèce inconnue : {me_species!r}", file=sys.stderr)
        return 1
    try:
        res = optimize_spread(me_species, me_nature, objectives,
                              item=item, ability=ability, budget=budget)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', me_species)} ({label('nature', me_nature)})"
          + (f" @ {item}" if item else "") + "\n")
    for line in res.lines():
        print(line)
    return 0


def cmd_sim(args: list[str]) -> int:
    pos, opts, flags = _split_args(args, {"trick-room"})
    if len(pos) != 6:
        print("Usage : sim <me_species> <me_nature> <me_moves> "
              "<opp_species> <opp_nature> <opp_moves> "
              "[--me-sp k=v] [--opp-sp k=v] [--me-item X] [--opp-item X] "
              "[--roll 0..1] [--weather X] [--terrain X] [--trick-room]",
              file=sys.stderr)
        return 2
    me_sp, me_nat, me_moves, opp_sp, opp_nat, opp_moves = pos
    for sp in (me_sp, opp_sp):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    me = Mon.from_state(PokemonState(
        species=me_sp, nature=me_nat, stat_points=_parse_sp(opts.get("me-sp", "")),
        item=opts.get("me-item"), ability=opts.get("me-ability")))
    opp = Mon.from_state(PokemonState(
        species=opp_sp, nature=opp_nat, stat_points=_parse_sp(opts.get("opp-sp", "")),
        item=opts.get("opp-item"), ability=opts.get("opp-ability")))
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"),
                       trick_room="trick-room" in flags)
    seq_me = [m.strip() for m in me_moves.split(",") if m.strip()]
    seq_opp = [m.strip() for m in opp_moves.split(",") if m.strip()]
    try:
        roll = float(opts.get("roll", 0.5))
        results = rollout(me, opp, seq_me, seq_opp, field, roll=roll)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"{label('species', me_sp)}  vs  {label('species', opp_sp)}  "
          f"(roll {roll:g})\n")
    for i, tr in enumerate(results, 1):
        print(f"— Tour {i} —")
        for line in tr.log:
            print(line)
        print(f"   État : {label('species', me_sp)} {tr.me_hp}/{tr.me_max} · "
              f"{label('species', opp_sp)} {tr.opp_hp}/{tr.opp_max}")
        if tr.me_fainted or tr.opp_fainted:
            winner = me_sp if tr.opp_fainted and not tr.me_fainted else \
                opp_sp if tr.me_fainted and not tr.opp_fainted else None
            if winner:
                print(f"\n➤ {label('species', winner)} l'emporte sur cette ligne.")
            break
    return 0


def cmd_decide(args: list[str]) -> int:
    pos, opts, flags = _split_args(args, {"cautious", "trick-room"})
    if len(pos) != 5:
        print("Usage : decide <me_species> <me_nature> <me_moves> "
              "<opp_species> <opp_nature> [--me-sp k=v] [--opp-sp k=v] "
              "[--opp-moves a,b,c] [--me-item X] [--opp-item X] [--me-hp 0..1] "
              "[--opp-hp 0..1] [--roll 0..1] [--weather X]", file=sys.stderr)
        return 2
    me_sp, me_nat, me_moves, opp_sp, opp_nat = pos
    for sp in (me_sp, opp_sp):
        if not is_known(sp):
            print(f"Espèce inconnue : {sp!r}", file=sys.stderr)
            return 1
    me = Mon.from_state(PokemonState(
        species=me_sp, nature=me_nat, stat_points=_parse_sp(opts.get("me-sp", "")),
        moves=[m.strip() for m in me_moves.split(",") if m.strip()],
        item=opts.get("me-item"), current_hp_pct=float(opts.get("me-hp", 1.0))))
    opp = Mon.from_state(PokemonState(
        species=opp_sp, nature=opp_nat, stat_points=_parse_sp(opts.get("opp-sp", "")),
        moves=[m.strip() for m in opts.get("opp-moves", "").split(",") if m.strip()],
        item=opts.get("opp-item"), current_hp_pct=float(opts.get("opp-hp", 1.0))))
    field = FieldState(weather=opts.get("weather"), terrain=opts.get("terrain"),
                       trick_room="trick-room" in flags)
    bench: list[Mon] = []
    for chunk in opts.get("bench", "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(",")]
        if not is_known(parts[0]):
            print(f"Espèce inconnue (banc) : {parts[0]!r}", file=sys.stderr)
            return 1
        nat = parts[1] if len(parts) > 1 and parts[1] else "serious"
        mvs = ([m.strip() for m in parts[2].split("|") if m.strip()]
               if len(parts) > 2 else [])
        bench.append(Mon.from_state(PokemonState(species=parts[0], nature=nat,
                                                 moves=mvs)))
    opp_model = "worst" if "cautious" in flags else "expected"
    samples = int(opts.get("samples", 0))
    try:
        if samples > 0:
            res = rank_actions_sampled(
                me, opp, field, my_bench=bench, depth=int(opts.get("depth", 1)),
                opp_model=opp_model, roll=float(opts.get("roll", 0.5)),
                n_samples=samples)
        else:
            res = rank_actions(me, opp, field, my_bench=bench,
                               roll=float(opts.get("roll", 0.5)),
                               depth=int(opts.get("depth", 1)), opp_model=opp_model)
    except (ValueError, KeyError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    depth = max(1, min(5, int(opts.get("depth", 1))))
    mode = "  [prudent : pire cas]" if opp_model == "worst" else ""
    print(f"{label('species', me_sp)}  vs  {label('species', opp_sp)}"
          + (f"  (profondeur {depth})" if depth > 1 else "") + mode + "\n")
    for line in res.lines():
        print(line)
    return 0


def cmd_paste(args: list[str]) -> int:
    pos, _, flags = _split_args(args, {"json"})
    if len(pos) != 1:
        print("Usage : paste <paste.txt> [--json]   # importe un paste Showdown "
              "et analyse l'équipe (EV -> SP)", file=sys.stderr)
        return 2
    try:
        with open(pos[0], encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    team = parse_showdown(text)
    if not team:
        print("Aucun Pokémon reconnu dans le paste.", file=sys.stderr)
        return 1
    if "json" in flags:
        import json
        entries = [{"species": m.species, "nature": m.nature,
                    "stat_points": m.stat_points, "item": m.item,
                    "ability": m.ability, "moves": m.moves,
                    "is_shiny": m.is_shiny} for m in team]
        print(json.dumps({"team": entries}, ensure_ascii=False, indent=2))
        return 0
    print(f"Paste importé — {len(team)} Pokémon "
          f"({', '.join(label('species', m.species) for m in team)})\n")
    for m in team:
        problems = m.validate()
        if problems:
            print(f"⚠ {label('species', m.species)} : {'; '.join(problems)}")
    for line in analyze_team(team).lines():
        print(line)
    return 0


def _force_utf8_stdout() -> None:
    """Évite les UnicodeEncodeError sur console Windows (cp1252) : la sortie
    contient des accents et le séparateur « • ». Sans effet ailleurs."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    argv = argv if argv is not None else sys.argv[1:]
    # Langue d'affichage : --lang <fr|en> (n'importe où) ou SIMUPOKE_LANG.
    set_language(os.environ.get("SIMUPOKE_LANG", "fr"))
    if "--lang" in argv:
        i = argv.index("--lang")
        if i + 1 < len(argv):
            set_language(argv[i + 1])
            del argv[i:i + 2]
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
    if cmd == "speed":
        return cmd_speed(rest)
    if cmd == "outspeed":
        return cmd_outspeed(rest)
    if cmd == "survive":
        return cmd_survive(rest)
    if cmd == "ko":
        return cmd_ko(rest)
    if cmd == "spread":
        return cmd_spread(rest)
    if cmd == "sim":
        return cmd_sim(rest)
    if cmd == "decide":
        return cmd_decide(rest)
    if cmd == "paste":
        return cmd_paste(rest)
    print(f"Commande inconnue : {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
