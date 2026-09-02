"""Couche d'affichage / internationalisation (§0.5, §15 Q8).

Les IDs canoniques internes sont en anglais (style Showdown). Cette couche mappe
ID -> libellé FR/EN sans jamais toucher au moteur. Le français est la langue par
défaut ; la bascule EN est **effective** :

  - une table de traduction par catégorie/langue (species, nature, stat, …) ;
  - à défaut d'entrée, on **dérive le libellé des données** (nom anglais du
    Pokédex / des capacités) ou on « embellit » l'ID — jamais on ne retombe sur
    l'autre langue (le mode EN ne doit pas afficher « Carchacrok »).

La langue courante est un état de processus (`set_language`) que la CLI pilote
via `--lang` / `SIMUPOKE_LANG` ; les appels peuvent aussi passer `lang=` en dur.
"""

from __future__ import annotations

DEFAULT_LANG = "fr"
_CURRENT_LANG = DEFAULT_LANG


def set_language(lang: str) -> None:
    """Fixe la langue d'affichage courante ('fr' ou 'en')."""
    global _CURRENT_LANG
    _CURRENT_LANG = "en" if str(lang).lower().startswith("en") else "fr"


def get_language() -> str:
    return _CURRENT_LANG


# Catégorie -> { lang -> { id_anglais -> libellé } }
TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "stat": {
        "fr": {
            "hp": "PV", "atk": "Attaque", "def": "Défense",
            "spa": "Atq. Spé.", "spd": "Déf. Spé.", "spe": "Vitesse",
        },
        "en": {
            "hp": "HP", "atk": "Attack", "def": "Defense",
            "spa": "Sp. Atk", "spd": "Sp. Def", "spe": "Speed",
        },
    },
    "nature": {
        "fr": {
            "hardy": "Hardi", "lonely": "Solo", "brave": "Brave",
            "adamant": "Rigide", "naughty": "Mauvais", "bold": "Assuré",
            "docile": "Docile", "relaxed": "Relax", "impish": "Malin",
            "lax": "Lâche", "timid": "Timide", "hasty": "Pressé",
            "serious": "Sérieux", "jolly": "Jovial", "naive": "Naïf",
            "modest": "Modeste", "mild": "Doux", "quiet": "Discret",
            "bashful": "Pudique", "rash": "Foufou", "calm": "Calme",
            "gentle": "Gentil", "sassy": "Malpoli", "careful": "Prudent",
            "quirky": "Bizarre",
        },
        "en": {},  # l'ID anglais capitalisé sert de libellé EN
    },
    "species": {
        "fr": {
            "tyranitar": "Tyranocif", "garchomp": "Carchacrok",
            "incineroar": "Félinferno",
        },
        "en": {},  # nom anglais dérivé du Pokédex
    },
    "item": {"fr": {}, "en": {}},
    "ability": {"fr": {}, "en": {}},
    "move": {"fr": {}, "en": {}},
}


def _canonical(category: str, ident: str) -> str:
    """Libellé « données/anglais » d'un ID, servant de repli universel.

    Ne dépend jamais de la table FR — c'est ce qui rend le mode EN correct.
    """
    if category == "species":
        from .basestats import get_species, is_known
        if is_known(ident):
            return get_species(ident).get("name", ident)
    elif category == "move":
        from .moves import get_move, is_known as move_known
        if move_known(ident):
            try:
                return get_move(ident).name
            except KeyError:
                pass
    elif category == "stat":
        return TRANSLATIONS["stat"]["en"].get(ident, ident)
    if not ident:
        return ident
    # Natures, objets, talents… : ID « embelli » (mots capitalisés).
    return " ".join(w.capitalize() for w in ident.replace("_", "-").split("-"))


def label(category: str, ident: str, lang: str | None = None) -> str:
    """Libellé affichable d'un identifiant dans la langue voulue.

    `lang=None` utilise la langue courante (`set_language`). À défaut de
    traduction, dérive le libellé des données (jamais de l'autre langue).
    """
    lang = lang or _CURRENT_LANG
    table = TRANSLATIONS.get(category, {}).get(lang, {})
    if ident in table:
        return table[ident]
    return _canonical(category, ident)


def stat_label(stat_key: str, lang: str | None = None) -> str:
    return label("stat", stat_key, lang)
