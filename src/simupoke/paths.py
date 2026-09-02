"""Résolution centralisée du dossier de données (§7.3).

Une **seule** source pour localiser `data/`, avec surcharge par la variable
d'environnement ``SIMUPOKE_DATA_DIR``. Indispensable pour exécuter le moteur là
où l'arborescence du dépôt n'existe pas : wheel installé, ou navigateur via
**Pyodide** (on écrit les JSON dans le FS virtuel puis on pointe la variable
dessus).

Précédence :

1. ``$SIMUPOKE_DATA_DIR`` s'il est défini ;
2. données empaquetées dans le paquet (``<package>/data``), si présentes ;
3. dossier ``data/`` à la racine du dépôt (checkout de développement).
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]  # .../SimuPoke (src/simupoke/ -> deux crans)


def resolve_data_dir() -> Path:
    """Localise `data/` selon la précédence documentée en tête de module."""
    env = os.environ.get("SIMUPOKE_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    packaged = PACKAGE_DIR / "data"
    if packaged.is_dir():
        return packaged
    return REPO_ROOT / "data"


#: Dossier de données résolu à l'import. En Pyodide / wheel, définir
#: ``SIMUPOKE_DATA_DIR`` **avant** d'importer les modules de `simupoke`.
DATA_DIR = resolve_data_dir()
