# SimuPoke

Outil **hors-ligne** d'aide à la décision pour **Pokémon Champions**, à **saisie
manuelle**, s'appuyant sur un moteur de combat de type Pokémon Showdown.

> Outil séparé, à saisie manuelle, qui ne communique **jamais** avec le jeu
> (cf. cadre CGU, §3 du document socle). C'est un calculateur / conseiller, au
> même titre qu'un *damage calc* ou un *team builder* communautaire.

Document de conception complet : [`docs/conception_socle.md`](docs/conception_socle.md).

## État du projet

**Phase 0 — Socle données & stats** (en cours).

Le modèle de stats Champions est **figé et vérifié en jeu** (Tyranocif Jovial,
4/4 stats exactes le 23/06/2026). Voir §8.3 du document socle.

| Phase | Objet | Statut |
|---|---|---|
| 0 | Socle données + conversion SP→stats + (à venir) damage calc | 🟡 en cours |
| 1 | B2 — Aide au tirage (Roster Ranch) | ⏳ |
| 2 | B3 — Team builder + team preview | ⏳ |
| 3 | B1 — Mode analyse (Singles) | ⏳ |
| 4 | B1 — Mode simultané (MCTS/ISMCTS) | ⏳ |
| 5 | Doubles | ⏳ |
| 6 | (optionnel) Apprentissage | ⏳ |

## Décisions actées (§0 du document socle)

- **Singles d'abord**, mais **architecture pensée Doubles** dès le départ
  (`SideState.active` est une liste).
- **Python** comme langage cœur ; UI v1 = **CLI**, UI v2 = page HTML autonome.
- **IDs internes en anglais** (style Showdown) ; **affichage FR par défaut**,
  bascule EN prévue (couche i18n).
- L'outil **connaît mon Box** (Pokémon possédés) pour personnaliser les conseils.
- Données **versionnées par régulation** en JSON, modifiables sans toucher au code.

## Structure

```
SimuPoke/
├── docs/conception_socle.md      # document socle de conception (v0.4)
├── data/
│   ├── pokedex.json              # base stats + méta (généré depuis @pkmn/dex)
│   ├── my_roster.json            # « mon Box » (Pokémon possédés)
│   └── reg_m_b/                  # données de la régulation courante (M-B)
│       ├── roster.json           # espèces légales + flags (peut méga ?)
│       ├── abilities.json        # talents custom (delta Champions, §7.2)
│       ├── items.json
│       ├── moves_overrides.json  # exceptions de moves vs VGC classique
│       └── clauses.json          # Species/Item Clause, formats
├── scripts/
│   ├── gen_pokedex.mjs           # génère data/pokedex.json (hors-ligne, via npm)
│   └── package.json
├── src/simupoke/
│   ├── stats.py                  # modèle de stats figé (conversion SP→stats)
│   ├── basestats.py              # base stats + méta (lit data/pokedex.json)
│   ├── model.py                  # OwnedPokemon + état de combat (Doubles-ready)
│   ├── i18n.py                   # couche d'affichage FR/EN
│   ├── loaders.py                # chargement roster + régulation
│   └── cli.py                    # CLI de validation du pipeline
└── tests/                        # tests pytest
```

## Données de base (base stats)

Les base stats proviennent de **`@pkmn/dex`** (source nommée au §12), alignées
sur les IDs Showdown utilisés en interne. Elles sont **figées dans un fichier
versionné** `data/pokedex.json` (1300+ espèces, formes Méga incluses), de sorte
que le runtime reste **100 % hors-ligne** (§3) — aucune requête réseau pendant
l'utilisation de l'outil.

> Les base stats sont identiques à celles du jeu principal : Champions ne change
> que le système IV/SP, pas les stats de base (§4.3).

Pour **régénérer** le fichier (mise à jour `@pkmn/dex`, nouvelle régulation) :

```bash
cd scripts
npm install
node gen_pokedex.mjs   # réécrit ../data/pokedex.json
```

## Démarrage rapide

```bash
# Optionnel : environnement virtuel
python -m venv .venv && source .venv/bin/activate

# Installation (mode développement) avec les dépendances de test
pip install -e ".[dev]"

# Lancer les tests
pytest

# Afficher mon Box avec stats finales calculées
python -m simupoke.cli roster

# Calculer les stats d'un build ad hoc
#   stats <species> <nature> <hp> <atk> <def> <spa> <spd> <spe>
python -m simupoke.cli stats tyranitar jolly 2 32 0 0 0 32
```

> Sans installation, on peut aussi lancer depuis la racine du dépôt avec
> `PYTHONPATH=src python -m simupoke.cli ...` et `PYTHONPATH=src pytest`.

## Modèle de stats (rappel, §8.3)

Niveau 50, IV 31 partout, SP ∈ [0, 32] par stat, budget total **66 SP**.

```
I       = 2·Base + 31 + 2·SP
PV      = ⌊I / 2⌋ + 60
Autres  = ⌊ (⌊I / 2⌋ + 5) · Nature ⌋     (Nature ∈ {0.9, 1.0, 1.1})
```

## Prochaines étapes (Phase 0 → Phase 1)

- [x] Brancher une vraie source de base stats (`@pkmn/dex`) → `data/pokedex.json`.
- [ ] Calculateur de dégâts intégrant le delta Champions (Méga + talents §7.2).
- [ ] Importeur de stats d'usage (limitless / pokedata) → priors adversaire (§0.2).
- [ ] B2 — Aide au tirage (saisie des 10, scoring, classement).
