# Rivals Config Manager

Application Windows (Python + PySide6) pour gérer facilement ses fichiers de
configuration **Fleasion** (Rivals). Au lieu de manipuler les fichiers à la
main, on choisit une catégorie → une arme → une configuration, puis on clique
sur **ACTIVER** : l'application copie les fichiers nécessaires dans le dossier
de configuration Fleasion, après les avoir validés (et en sauvegardant les
anciens fichiers au passage).

> L'application est un **gestionnaire de fichiers**. Elle ne modifie pas
> Fleasion, n'injecte rien et ne contourne aucune protection : elle copie
> simplement des fichiers JSON (et leurs meshes) dans le dossier que vous
> avez choisi.

---

## 1. Installation pour le développeur

Prérequis : **Python 3.10+** (testé sous Python 3.14, Windows 10/11).

```bash
# Créer un environnement virtuel (recommandé)
python -m venv .venv
.venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt
```

## 2. Lancement en Python

```bash
python main.py
```

Au **premier lancement**, l'application demande les deux dossiers :

| Champ | Exemple |
|---|---|
| Fleasion Config Folder | `C:\Users\<vous>\AppData\Local\FleasionNT\config` |
| Rivals Configs Library | `C:\Users\<vous>\Desktop\Rivals configs` |

Ces chemins sont enregistrés dans `%APPDATA%\RivalsConfigManager\settings.json`
et **jamais** codés en dur dans le programme : chacun peut utiliser ses propres
dossiers.

## 3. Configuration des dossiers

Tout se passe dans la page **Paramètres** (⚙) :

- **Fleasion Config Directory** — dossier de configuration de Fleasion.
  S'il n'existe pas encore, il sera créé lors de la première activation.
- **Rivals Configs Library** — dossier contenant vos configurations.
- Boutons : **Test Connection**, **Refresh Library**, **Open Folder**,
  **Restore Backup**, et une option de sauvegarde automatique avant
  remplacement.

Les sauvegardes sont créées dans `%APPDATA%\RivalsConfigManager\backups`
et peuvent être restaurées depuis les paramètres.

## 4. Création du `.exe`

```bash
pyinstaller RivalsConfigManager.spec --noconfirm
```

Résultat : `dist\RivalsConfigManager.exe` — un seul fichier, l'utilisateur
final n'a pas besoin d'installer Python.

- L'icône est générée par `tools/make_icon.py` (`assets/icon.ico`).
  Régénérez-la puis relancez le build si vous changez le design.
- Variante simple en ligne de commande :

  ```bash
  pyinstaller --noconfirm --onefile --windowed --icon assets/icon.ico main.py
  ```

## 5. Utilisation du programme

1. L'écran d'accueil affiche les **catégories** de votre bibliothèque
   (Charms, emotes, FastFlags, Skins, Texture & skyboxes, …) sous forme de
   cartes — détectées automatiquement par scan du dossier.
2. Naviguez : **Catégorie → Type d'arme → Arme → Configuration**.
3. Ouvrez une configuration : aperçu (si une image `preview.png`,
   `thumbnail.png`, `cover.jpg`, … existe), liste des fichiers inclus.
4. Cliquez **ACTIVER** : l'application
   - vérifie que les fichiers existent,
   - valide les JSON,
   - sauvegarde les fichiers existants qui seraient remplacés,
   - copie les fichiers vers le dossier Fleasion,
   - affiche une confirmation (ou une erreur claire).
5. La **barre de recherche** cherche dans les noms de catégories, armes,
   skins et configurations (ex. `sniper`).

## 6. Fonctionnement générique

Le programme ne connaît **aucune** arme, skin ou configuration en dur.
Au démarrage, il scanne la bibliothèque et construit un arbre :

```
Scanner le dossier → Construire l'arbre → Afficher les dossiers
→ Afficher les configurations → L'utilisateur sélectionne → Copie des fichiers
```

Ajoutez un dossier ou un JSON dans la bibliothèque : il apparaît
automatiquement. Règles de détection :

- un dossier **avec plusieurs JSON** = conteneur : chaque JSON est une
  configuration (ex. `Arme → Skin 1, Skin 2`) ;
- un dossier **avec un JSON + d'autres fichiers** (meshes, aperçu) = une
  seule configuration : tout le contenu est copié ;
- un JSON **directement dans un dossier** = une configuration ;
- les meshes `.obj` référencés par un JSON sont copiés automatiquement.

## 6bis. Images à tous les niveaux de l'arborescence

Chaque élément affiché sous forme de carte (catégorie, sous-dossier, arme,
configuration finale) peut avoir sa propre image : clic droit sur la carte →
**Modifier l'image** (ou bouton dans la vue de détail). L'image est stockée
comme métadonnée séparée (`.image.json` ou `image.json` dans le dossier),
jusqu'à un fichier par élément, identifié par son **chemin complet** : deux
éléments portant le même nom à des endroits différents ont des images
indépendantes. Priorité d'affichage : image personnalisée → preview
automatique → placeholder. Une image de catégorie ne remplace jamais les
images de ses enfants.

## 6ter. Modèles 3D (OBJ)

Une configuration peut être associée à un modèle `.obj` :

- **Détection automatique** (déterministe) : `Skin.json` + `Skin.obj`
  (même nom exact) dans le même dossier, ou un unique `.obj` référencé par
  le contenu du JSON, ou un unique `.obj` dans un dossier-configuration.
  Aucune relation n'est inventée à partir d'un nom partiel.
- **Ajouter un OBJ** dans la vue de détail : copie le modèle dans le cache
  de l'application (`obj_cache`), enregistre l'association dans un sidecar
  `.obj.json` (ou `obj.json`), sans jamais modifier le vrai `.obj` ni le
  JSON original.
- À l'activation, le modèle est copié **à côté de la configuration** dans
  le dossier Fleasion.

## 6quater. Activation Fleasion

Le bouton **ACTIVER** copie la configuration dans le dossier `configs/` de
Fleasion puis, si `settings.json` existe, **sélectionne réellement** la
configuration (ajout à `enabled_configs`, mise à jour de `last_config`),
avec sauvegarde préalable et vérification de l'enregistrement. L'état du
bouton reflète la réalité : `ACTIVER` → `✓ COPIÉ` (fichiers copiés,
sélection manuelle requise) → `✓ ACTIF` (sélection confirmée).

## 7. Tests

```bash
python -m pytest tests -q
```

Les tests couvrent : scan des dossiers, JSON invalides, fichiers manquants,
copie, sauvegardes, restauration, chemins avec espaces, recherche, et un test
de bout en bout de l'interface (mode headless).

## 8. Logs

Les journaux sont écrits dans `%APPDATA%\RivalsConfigManager\app.log` — utiles
pour diagnostiquer un problème sans avoir accès à la console.

## 9. Assets partagés et synchronisation

Les images de la bibliothèque (armes, skins, charms, catégories…) ne sont
**pas** compilées dans le `.exe`. Elles vivent dans le dépôt (`assets/`), sont
décrites par un **manifest versionné** (`manifest.json`) et sont téléchargées
à la demande dans le cache local de chaque utilisateur :

```text
%APPDATA%\RivalsConfigManager\
    assets\            <- fichiers téléchargés
    asset_manifest.json <- ce qui est déjà en cache (clé -> version)
```

- **Manifest** : `schema_version` (format) + `assets_version` (version des
  assets, indépendante de la version de l'application) + `assets` (clé →
  chemin/version/taille).
- **Synchronisation** : bouton **Paramètres → Synchroniser les ressources**
  (et synchronisation opportuniste au démarrage si un remote est configuré).
  Seuls les assets nouveaux/modifiés sont téléchargés, en arrière-plan, sans
  jamais bloquer l'interface.
- **Hors ligne** : sans Internet (ou sans remote configuré), l'application
  continue de fonctionner avec le cache local. Une carte sans image locale
  retombe automatiquement sur l'image partagée du cache, sinon sur un
  placeholder propre.
- **Remote** : définir la variable d'environnement `RCM_ASSET_BASE_URL` (voir
  `.env.example`) sur l'URL HTTPS racine du dépôt (ex. GitHub raw). Par
  défaut, aucun remote n'est configuré.

Ajouter une image = la déposer dans `assets/<catégorie>/` + l'ajouter dans
`manifest.json` + pousser. Les utilisateurs la récupèrent à la prochaine
synchronisation — **sans** reconstruire le `.exe`.

## Structure du projet

```
├── main.py                      # point d'entrée
├── manifest.json                # manifest des assets partagés (versionné)
├── .env.example                 # config d'exemple (RCM_ASSET_BASE_URL, …)
├── requirements.txt
├── RivalsConfigManager.spec     # build PyInstaller
├── README.md
├── app/
│   ├── config.py                # paramètres (dossiers, sauvegarde auto)
│   ├── scanner.py               # scan générique de la bibliothèque
│   ├── json_validator.py        # validation JSON + résolution des meshes
│   ├── backup_manager.py        # sauvegardes / restauration
│   ├── file_manager.py          # activation (copie) d'une configuration
│   ├── assets/                  # manifest, cache local, synchro, sécurité
│   └── launcher.py              # démarrage de l'application
├── ui/
│   ├── theme.py                 # thème sombre (QSS)
│   ├── main_window.py           # fenêtre principale, navigation, recherche
│   └── views/                   # accueil, parcours, config, paramètres, bienvenue
├── assets/                      # images partagées (weapons, skins, …) + icône
├── tools/                       # make_icon, scripts d'ajout de clés i18n
└── tests/                       # tests pytest
```
