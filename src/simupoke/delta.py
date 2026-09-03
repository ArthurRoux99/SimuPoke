"""Couche « delta » Champions (§7.2) — talents custom branchés sur le calc.

Le Showdown vanilla connaît ~90 % de Champions ; cette couche ajoute le reste.
Elle expose les effets de talents qui impactent le calcul de dégâts, en
combinant :
  - des templates intégrés (familles déjà implémentées : -ate) ;
  - les talents custom décrits dans les données de régulation
    (`data/<reg>/abilities.json`), de sorte qu'ajouter un clone de template
    soit une opération **de données**, sans toucher au moteur.

Catégories (cf. abilities.json) :
  - B (clone de template) : ex. **Dragonize** (M. Feraligatr) = patron des
    -ate (Pixilate/Aerilate/…), « moves Normal → Dragon, +20 % ».
  - C (talent neuf) : ex. **Mega Sol** (M. Meganium) = soleil « personnel ».

Les talents purement « moteur de combat » (Piercing Drill = passe Protect,
Spicy Spray = brûlure au contact) ne sont pas des modificateurs de dégâts et
ne sont donc pas gérés ici (ils relèveront du simulateur de tour).
"""

from __future__ import annotations

from functools import cache

from .loaders import load_regulation

# Famille -ate intégrée (talents déjà présents dans @pkmn/dex).
_BUILTIN_ATE: dict[str, str] = {
    "pixilate": "Fairy",
    "aerilate": "Flying",
    "refrigerate": "Ice",
    "galvanize": "Electric",
}

# Multiplicateur de puissance des -ate : ×1.2 en base 4096.
ATE_POWER_MOD = 4915

# Météo « personnelle » (talents custom catégorie C).
_PERSONAL_WEATHER: dict[str, str] = {"megasol": "sun"}


@cache
def ate_type_map(reg_id: str = "reg_m_b") -> dict[str, str]:
    """Talents qui transforment les moves Normal en un autre type (-ate).

    Combine la famille intégrée et les talents custom de la régulation dont les
    paramètres décrivent `from_type=Normal` → `to_type` (catégorie B).
    """
    out = dict(_BUILTIN_ATE)
    try:
        abilities = load_regulation(reg_id).get("abilities", {}).get("abilities", [])
    except (FileNotFoundError, OSError, KeyError):
        abilities = []
    for ab in abilities:
        params = ab.get("params", {}) or {}
        if params.get("from_type") == "Normal" and params.get("to_type"):
            out[ab["id"]] = params["to_type"]
    return out


def type_change_for(ability_id: str | None, reg_id: str = "reg_m_b") -> str | None:
    """Nouveau type imposé aux moves Normal par un talent -ate, sinon None."""
    if not ability_id:
        return None
    return ate_type_map(reg_id).get(ability_id)


def personal_weather_for(ability_id: str | None) -> str | None:
    """Météo personnelle accordée par un talent (ex. Mega Sol → 'sun')."""
    if not ability_id:
        return None
    return _PERSONAL_WEATHER.get(ability_id)
