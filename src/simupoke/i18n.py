"""Couche d'affichage / internationalisation (§0.5).

Les IDs canoniques internes sont en anglais (style Showdown). Cette couche
mappe ID -> libellé FR/EN. Le français est la langue par défaut ; la bascule
EN n'impacte jamais le moteur (simple changement de table).

Seules quelques entrées sont remplies en Phase 0 ; les tables se complèteront
au fil des phases (idéalement alimentées par une source de données).
"""

from __future__ import annotations

DEFAULT_LANG = "fr"

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
            "jolly": "Jovial", "adamant": "Rigide", "timid": "Timide",
            "modest": "Modeste", "bold": "Assuré", "calm": "Calme",
            "serious": "Sérieux",
        },
        "en": {},  # l'ID anglais sert déjà de libellé EN par défaut
    },
    "species": {
        "fr": {
            "tyranitar": "Tyranocif", "garchomp": "Carchacrok",
            "incineroar": "Félinferno",
        },
        "en": {},
    },
    "item": {"fr": {}, "en": {}},
    "ability": {"fr": {}, "en": {}},
    "move": {"fr": {}, "en": {}},
}


def label(category: str, ident: str, lang: str = DEFAULT_LANG) -> str:
    """Libellé affichable d'un identifiant. Retombe sur l'ID si non traduit."""
    cat = TRANSLATIONS.get(category, {})
    table = cat.get(lang, {})
    if ident in table:
        return table[ident]
    # Fallback : autre langue connue.
    for other in cat.values():
        if ident in other:
            return other[ident]
    # Pour une espèce non traduite, on récupère le nom anglais du Pokédex
    # (couche de données) plutôt qu'un ID brut.
    if category == "species":
        from .basestats import get_species
        try:
            return get_species(ident)["name"]
        except KeyError:
            pass
    return ident.replace("-", " ").capitalize()


def stat_label(stat_key: str, lang: str = DEFAULT_LANG) -> str:
    return label("stat", stat_key, lang)
