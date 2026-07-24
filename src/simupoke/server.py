"""Serveur local SimuPoke — UI hébergée sur le PC (§0.4, §12).

Sert le frontend et expose une **API JSON** qui réutilise directement le moteur
Python (calc + delta Champions, B1/B2/B3) — une seule source de vérité, déjà
testée. Uniquement la bibliothèque standard (`http.server`), aucune dépendance.

    python -m simupoke.server            # http://127.0.0.1:8000
    python -m simupoke.server --port 9000 --host 0.0.0.0

Endpoints :
    GET  /                      page principale (onglets)
    GET  /static/<f>            fichiers statiques (css/js)
    GET  /api/meta              listes (espèces, capacités, natures)
    GET  /api/samples           jeux d'exemple (équipe, adversaire, tirage)
    POST /api/stats             stats finales d'un build
    POST /api/damage            calcul de dégâts
    POST /api/analyze           B1 — analyse de tour
    POST /api/draft             B2 — classement d'un tirage
    POST /api/team              B3 — analyse d'équipe
    POST /api/preview           B3 — assistant team preview
    POST /api/speed             speed tiers (Tailwind/Trick Room)
    POST /api/outspeed          SP mini en Vitesse pour dépasser une cible
    POST /api/survive           SP défensif mini pour survivre à une attaque
    POST /api/ko                SP offensif mini pour garantir un KO en N coups
    POST /api/spread            optimiseur de spread SP (objectifs combinés)
    POST /api/decide            recherche 1-ply à coups simultanés (§10.2)
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .model import PokemonState, FieldState, OwnedPokemon
from .stats import STAT_KEYS, NATURES, compute_all_stats, validate_sp
from .basestats import get_base_stats, is_known, get_species
from .damage import calculate, DamageResult
from .combat import analyze_turn
from .bench import (
    speed_tiers, min_sp_to_outspeed, min_sp_to_survive, min_sp_to_ko,
)
from .optimize import optimize_spread, Outspeed, Survive, Ko
from .sim import Mon
from .search import rank_actions
from .draft import rank_lineup
from .team import analyze_team, select_team_preview
from .usage import usage_prior, has_usage, likely_set
from .loaders import load_my_roster, DATA_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"
SERVER_WEB = WEB_DIR / "server"


# ---------------------------------------------------------------------------
# Construction d'objets depuis le JSON entrant
# ---------------------------------------------------------------------------

def _state(d: dict) -> PokemonState:
    return PokemonState(
        species=d.get("species", ""),
        nature=d.get("nature", "serious"),
        stat_points=d.get("stat_points", d.get("sp", {})) or {},
        item=d.get("item") or None,
        ability=d.get("ability") or None,
        moves=d.get("moves", []) or [],
        status=d.get("status") or None,
        boosts=d.get("boosts", {}) or {},
        current_hp_pct=float(d.get("current_hp_pct", d.get("hpPct", 1.0))),
    )


def _owned(d: dict) -> OwnedPokemon:
    return OwnedPokemon(
        species=d["species"], nature=d.get("nature", "serious"),
        stat_points=d.get("stat_points", d.get("sp", {})) or {},
        item=d.get("item"), ability=d.get("ability"),
        moves=d.get("moves", []) or [],
        is_shiny=d.get("is_shiny", False), has_title=d.get("has_title", False),
        status_ownership=d.get("status_ownership", "permanent"),
        trial_expires_in_days=d.get("trial_expires_in_days"),
        display_fr=d.get("display_fr"),
    )


def _owned_list(entries: list[dict]) -> list[OwnedPokemon]:
    return [_owned(e) for e in entries]


# ---------------------------------------------------------------------------
# Sérialisation des résultats
# ---------------------------------------------------------------------------

def _damage_json(r: DamageResult) -> dict:
    return {
        "move": r.move, "rolls": r.rolls,
        "min": r.min_damage, "max": r.max_damage,
        "minPct": r.min_pct, "maxPct": r.max_pct,
        "maxHp": r.defender_max_hp, "curHp": r.defender_current_hp,
        "eff": r.type_effectiveness, "isStab": r.is_stab, "crit": r.crit,
        "koGuaranteed": r.guaranteed_ko_hits, "koPossible": r.possible_ko_hits,
        "describe": r.describe(),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def api_meta() -> dict:
    dex = _dex()
    species = sorted(v["name"] for v in dex.values())
    from .moves import _load_moves
    moves = sorted(m["name"] for m in _load_moves().values()
                   if m["category"] != "Status" and m["basePower"] > 0)
    return {"species": species, "moves": moves, "natures": sorted(NATURES.keys())}


def _dex() -> dict:
    from .basestats import _load_dex
    return _load_dex()


def api_samples() -> dict:
    out = {}
    for key, fname in (("team", "sample_team.json"),
                       ("opponent", "sample_opponent.json"),
                       ("lineup", "sample_lineup.json")):
        path = DATA_DIR / fname
        if path.exists():
            out[key] = json.loads(path.read_text(encoding="utf-8"))
    return out


def api_stats(body: dict) -> dict:
    species = body["species"]
    if not is_known(species):
        raise ValueError(f"Espèce inconnue : {species}")
    sp = body.get("stat_points", body.get("sp", {})) or {}
    problems = validate_sp(sp)
    stats = compute_all_stats(get_base_stats(species), sp, body.get("nature", "serious"))
    return {"species": species, "stats": stats, "problems": problems}


def api_damage(body: dict) -> dict:
    r = calculate(_state(body["attacker"]), _state(body["defender"]),
                  body["move"], FieldState(**(body.get("field") or {})),
                  crit=body.get("crit", False),
                  apply_spread=body.get("spread", False))
    return _damage_json(r)


def api_analyze(body: dict) -> dict:
    me, opp = _state(body["me"]), _state(body["opp"])
    field = FieldState(**(body.get("field") or {}))
    bench = [_state(d) for d in (body.get("bench") or [])]
    a = analyze_turn(me, opp, field, opp_move=body.get("opp_move") or None,
                     bench=bench)
    inc = a.incoming
    return {
        "incoming": {"move": inc.move, "maxPct": inc.max_pct,
                     "ohko": inc.ohko, "known": inc.known,
                     "estimated": inc.estimated},
        "options": [{"move": e.move, "minPct": e.min_pct, "maxPct": e.max_pct,
                     "ko": e.ko, "first": e.first, "value": e.value,
                     "notes": e.notes} for e in a.options],
        "other": [{"move": e.move, "value": e.value, "notes": e.notes}
                  for e in a.other],
        "switches": [{"species": s.species, "incomingPct": s.incoming_pct,
                      "survives": s.survives, "bestMove": s.best_move,
                      "bestMovePct": s.best_move_pct, "value": s.value,
                      "notes": s.notes} for s in a.switches],
        "recommendation": a.recommendation,
        "lines": a.lines(),
    }


def api_speed(body: dict) -> dict:
    """Speed tiers d'une liste de Pokémon (avec Tailwind/Trick Room)."""
    states = [_state(d) for d in body.get("mons", [])]
    tailwinds = body.get("tailwinds")
    tiers = speed_tiers(states, tailwinds=tailwinds,
                        trick_room=body.get("trick_room", False))
    return {"trickRoom": body.get("trick_room", False),
            "tiers": [{"species": e.species, "speed": e.speed, "notes": e.notes}
                      for e in tiers]}


def api_outspeed(body: dict) -> dict:
    """SP minimal en Vitesse pour (dé)passer une cible."""
    res = min_sp_to_outspeed(
        _state(body["me"]), _state(body["target"]),
        me_tailwind=body.get("me_tailwind", False),
        target_tailwind=body.get("target_tailwind", False),
        strict=body.get("strict", True))
    return {"feasible": res.feasible, "sp": res.sp, "mySpeed": res.my_speed,
            "targetSpeed": res.target_speed, "tiesOnly": res.ties_only,
            "line": res.line()}


def api_survive(body: dict) -> dict:
    """SP défensif minimal (PV + Déf/Déf.Spé) pour survivre à une attaque."""
    res = min_sp_to_survive(
        _state(body["defender"]), _state(body["attacker"]), body["move"],
        FieldState(**(body.get("field") or {})), crit=body.get("crit", False))
    return {"feasible": res.feasible, "hpSp": res.hp_sp, "defSp": res.def_sp,
            "totalSp": res.total_sp, "stat": res.stat, "move": res.move,
            "maxPct": res.max_pct, "line": res.line()}


def api_ko(body: dict) -> dict:
    """SP offensif minimal (Atq/Atq.Spé) pour garantir un KO en N coups."""
    res = min_sp_to_ko(
        _state(body["attacker"]), _state(body["defender"]), body["move"],
        FieldState(**(body.get("field") or {})),
        hits=int(body.get("hits", 1)), crit=body.get("crit", False))
    return {"feasible": res.feasible, "sp": res.sp, "stat": res.stat,
            "move": res.move, "hits": res.hits, "minPct": res.min_pct,
            "line": res.line()}


def _objective(d: dict):
    """Construit un objectif d'optimisation depuis le JSON entrant."""
    kind = d.get("kind")
    field = FieldState(**(d.get("field") or {}))
    if kind == "outspeed":
        return Outspeed(target=_state(d["target"]),
                        strict=d.get("strict", True),
                        me_tailwind=d.get("me_tailwind", False),
                        target_tailwind=d.get("target_tailwind", False),
                        label=d.get("label", ""))
    if kind == "survive":
        return Survive(attacker=_state(d["attacker"]), move=d["move"],
                       field=field, crit=d.get("crit", False),
                       label=d.get("label", ""))
    if kind == "ko":
        return Ko(defender=_state(d["defender"]), move=d["move"],
                  hits=int(d.get("hits", 1)), field=field,
                  crit=d.get("crit", False), label=d.get("label", ""))
    raise ValueError(f"objectif inconnu : {kind!r}")


def api_spread(body: dict) -> dict:
    """Optimiseur de spread : résout un spread SP couvrant tous les objectifs."""
    objectives = [_objective(o) for o in body.get("objectives", [])]
    res = optimize_spread(
        body["species"], body.get("nature", "serious"), objectives,
        item=body.get("item") or None, ability=body.get("ability") or None,
        budget=int(body.get("budget", 66)))
    return {"feasible": res.feasible, "sp": res.sp, "total": res.total,
            "budget": res.budget, "leftover": res.leftover,
            "stats": res.stats, "unmet": res.unmet, "lines": res.lines()}


def api_decide(body: dict) -> dict:
    """Recherche 1-ply à coups simultanés : classe mes actions (§10.2)."""
    me = Mon.from_state(_state(body["me"]))
    opp = Mon.from_state(_state(body["opp"]))
    field = FieldState(**(body.get("field") or {}))
    bench = [Mon.from_state(_state(d)) for d in (body.get("bench") or [])]
    res = rank_actions(me, opp, field, my_bench=bench,
                       use_usage=body.get("use_usage", True),
                       roll=float(body.get("roll", 0.5)),
                       depth=int(body.get("depth", 1)),
                       opp_model=body.get("opp_model", "expected"))
    return {"oppMoves": res.opp_moves,
            "actions": [{"move": a.move, "kind": a.kind, "expected": a.expected,
                         "worst": a.worst, "koChance": a.ko_chance,
                         "survivesWorst": a.survives_worst}
                        for a in res.actions],
            "recommendation": res.recommendation, "lines": res.lines()}


def api_draft(body: dict) -> dict:
    lineup = _owned_list(body["lineup"])
    roster = (_owned_list(body["roster"]) if body.get("roster") is not None
              else load_my_roster())
    reg = body.get("regulation", "reg_m_b")
    # Prior d'usage : fourni explicitement, sinon table de la régulation si dispo.
    prior = body.get("usage_prior")
    used = False
    if prior is None and body.get("use_usage", True) and has_usage(reg):
        prior = usage_prior(reg)
        used = bool(prior)
    elif prior is not None:
        used = True
    evals = rank_lineup(lineup, roster=roster, usage_prior=prior)
    return {"usageApplied": used,
            "ranking": [{"species": e.species, "score": e.score100,
                         "role": e.role_fr, "recommendation": e.recommendation,
                         "reasons": e.reasons, "shiny": e.is_shiny}
                        for e in evals]}


def api_likely(species: str, reg: str = "reg_m_b") -> dict:
    """Set le plus probable d'une espèce (modèle d'adversaire, §10.3)."""
    ls = likely_set(species, reg)
    return {"species": ls.species, "item": ls.item, "ability": ls.ability,
            "nature": ls.nature, "moves": ls.moves, "teammates": ls.teammates,
            "known": bool(ls.item or ls.moves)}


def api_team(body: dict) -> dict:
    report = analyze_team(_owned_list(body["team"]))
    return {
        "size": report.size,
        "sharedWeaknesses": report.shared_weaknesses,
        "offensiveGaps": report.offensive_gaps,
        "roles": report.roles,
        "clauseViolations": report.clause_violations,
        "lines": report.lines(),
    }


def api_preview(body: dict) -> dict:
    res = select_team_preview(_owned_list(body["my_team"]),
                              _owned_list(body["opp_team"]),
                              body.get("format", "singles"),
                              use_damage=body.get("use_damage", True))
    pick = lambda p: {"species": p.species, "value": p.value,
                      "beats": p.beats, "threatenedBy": p.threatened_by}
    return {"fmt": res.fmt, "bring": res.bring, "byDamage": res.by_damage,
            "picks": [pick(p) for p in res.picks],
            "bench": [pick(p) for p in res.bench],
            "lines": res.lines()}


def _roster_path() -> Path:
    return DATA_DIR / "my_roster.json"


def api_roster_get() -> dict:
    """Renvoie le contenu de « Mon Box » (liste `owned`)."""
    path = _roster_path()
    if not path.exists():
        return {"roster": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {"roster": raw.get("owned", [])}


def api_roster_save(body: dict, path: Path | None = None) -> dict:
    """Écrit « Mon Box » sur le disque (saisie manuelle, §3). Local uniquement."""
    path = Path(path) if path else _roster_path()
    entries = body.get("roster", [])
    if not isinstance(entries, list):
        raise ValueError("`roster` doit être une liste.")
    unknown = [e.get("species") for e in entries
               if e.get("species") and not is_known(e["species"])]
    out: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if "_help" in existing:
                out["_help"] = existing["_help"]
        except (ValueError, OSError):
            pass
    out["owned"] = entries
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return {"ok": True, "count": len(entries), "unknown": unknown}


_POST_ROUTES = {
    "/api/stats": api_stats, "/api/damage": api_damage, "/api/analyze": api_analyze,
    "/api/draft": api_draft, "/api/team": api_team, "/api/preview": api_preview,
    "/api/roster": api_roster_save,
    "/api/speed": api_speed, "/api/outspeed": api_outspeed,
    "/api/survive": api_survive, "/api/ko": api_ko, "/api/spread": api_spread,
    "/api/decide": api_decide,
}
_GET_API = {"/api/meta": api_meta, "/api/samples": api_samples,
            "/api/roster": api_roster_get}

_CONTENT_TYPES = {".html": "text/html", ".css": "text/css",
                  ".js": "application/javascript", ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "SimuPoke/0.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json({"error": "introuvable"}, 404)
            return
        ctype = _CONTENT_TYPES.get(path.suffix, "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    def do_GET(self) -> None:
        route, _, query = self.path.partition("?")
        try:
            if route in _GET_API:
                self._json(_GET_API[route]())
            elif route == "/api/likely":
                from urllib.parse import parse_qs
                q = parse_qs(query)
                species = (q.get("species") or [""])[0]
                if not species:
                    self._json({"error": "paramètre 'species' requis"}, 400)
                else:
                    self._json(api_likely(species, (q.get("reg") or ["reg_m_b"])[0]))
            elif route == "/" or route == "/index.html":
                self._file(SERVER_WEB / "index.html")
            elif route.startswith("/static/"):
                name = route[len("/static/"):]
                base = WEB_DIR if name == "style.css" else SERVER_WEB
                # empêche la traversée de répertoire
                target = (base / name).resolve()
                if base.resolve() in target.parents or target == (base / name).resolve():
                    self._file(target if target.exists() else SERVER_WEB / name)
                else:
                    self._json({"error": "interdit"}, 403)
            else:
                self._json({"error": "route inconnue"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        fn = _POST_ROUTES.get(route)
        if fn is None:
            self._json({"error": "route inconnue"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(fn(body))
        except (ValueError, KeyError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):  # silence par défaut
        pass


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"SimuPoke en écoute sur http://{host}:{port}  (Ctrl-C pour arrêter)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
        httpd.server_close()


def main() -> None:
    p = argparse.ArgumentParser(description="Serveur local SimuPoke")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
