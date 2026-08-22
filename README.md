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

## Fonctionnalités principales

- **Gestion de configurations** : parcours de la bibliothèque par
  catégorie → arme → configuration, activation en un clic (copie validée +
  sauvegarde des anciens fichiers).
- **Import individuel et multiple** : ajoutez un ou plusieurs mods en une
  seule opération (bouton *Ajouter des fichiers* ou glisser-déposer) ; les ZIP
  contenant plusieurs mods sont découpés automatiquement.
- **Sélection rapide des destinations** : chaque élément importé est trié via
  un sélecteur **Catégorie → Destination** construit depuis la structure
  réelle de la bibliothèque (y compris les armes vides) — aucune catégorie
  fantôme n'est créée.
- **Détection automatique** : catégorie/destination proposées en analysant le
  fichier, toujours corrigibles manuellement.
- **Profils** : créez, appliquez et **exportez/importez** des profils en
  fichier `.zip` portable (manifeste `profile.json`, références relatives,
  gestion des conflits de nom).
- **Favoris** : étoilez vos configurations favorites pour les retrouver dans
  une page dédiée.
- **Recherche** : barre de recherche globale (noms de catégories, armes,
  skins, configurations).
- **Textures & Skyboxes** : catégories gérées comme les autres, avec previews.
- **Corbeille** : suppression douce (déplacement vers la Corbeille Windows,
  jamais de suppression définitive).
- **Validation des dépendances** : fichiers manquants/JSON invalides signalés
  avant activation, avec possibilité de valider manuellement.
- **Plusieurs langues** : 10 langues disponibles (français, anglais,
  allemand, espagnol, italien, néerlandais, polonais, portugais, russe,
  turc). **L'anglais est la langue par défaut** au premier lancement ; elle
  reste modifiable à tout moment dans les Paramètres.
- **Tutoriel intégré** : parcours de découverte au premier lancement
  (spotlight translucide, repositionnement responsive).
- **Thèmes et préférences** : thème clair/sombre, langue, sauvegarde
  automatique, dossier actif Fleasion, raccourcis clavier, bouton
  *Recharger*.

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

Au **premier lancement**, l'application demande deux dossiers :

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
- **Recharger** : relance proprement l'application (comme une actualisation
  de page), sans perdre aucun réglage.

Les sauvegardes sont créées dans `%APPDATA%\RivalsConfigManager\backups`
et peuvent être restaurées depuis les paramètres.

## 4. Langues

L'application démarre avec **l'anglais comme langue par défaut** pour une
nouvelle installation. Au premier lancement, l'écran de choix de langue
apparaît avec l'anglais présélectionné : choisissez n'importe quelle langue
disponible — elle est appliquée immédiatement, persistée, et le tutoriel
démarre dans cette langue.

Les 10 langues disponibles : français, anglais, allemand, espagnol, italien,
néerlandais, polonais, portugais, russe, turc.

## 5. Import de configurations

- **Import individuel** : bouton *Ajouter des fichiers* ou glisser-déposer
  d'un fichier/dossier → choix de la destination (**Catégorie → Arme**, une
  arme vide est une destination valide) → import.
- **Import multiple** : plusieurs fichiers/dossiers/ZIP d'un coup → fenêtre
  **« Importer plusieurs éléments »** : chaque élément est listé avec sa
  propre sélection **Catégorie → Destination** (indépendante des autres),
  pré-remplie par la détection automatique si elle est fiable. Un seul clic
  importe tout le lot ; les échecs éventuels sont signalés sans bloquer le
  reste.
- Les destinations proposées viennent toujours de la **structure réelle** de
  la bibliothèque ; pour créer une nouvelle destination, utilisez l'action
  explicite « + Nouvelle destination » (jamais de catégorie créée
  automatiquement).

## 6. Profils

La page **Profils** permet de :

- **Créer** un profil (nom + configurations) et l'**appliquer** d'un clic ;
- **Exporter le profil** en fichier `.zip` (`NomDuProfil.zip`) contenant un
  manifeste `profile.json` (format versionné, références relatives — aucun
  chemin absolu ni nom d'utilisateur) ;
- **Importer un profil** depuis un `.zip` : le fichier est validé (un ZIP qui
  n'est pas un profil est refusé proprement) ; en cas de conflit de nom, vous
  choisissez entre remplacer, créer une copie ou annuler.

## 7. Création du `.exe`

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

## 8. Fonctionnement générique

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

### Images à tous les niveaux de l'arborescence

Chaque élément affiché sous forme de carte (catégorie, sous-dossier, arme,
configuration finale) peut avoir sa propre image : clic droit sur la carte →
**Modifier l'image**. L'image est stockée comme métadonnée séparée
(`.image.json` ou `image.json` dans le dossier), identifiée par son **chemin
complet**. Priorité d'affichage : image personnalisée → preview automatique →
placeholder. Une image de catégorie ne remplace jamais les images de ses
enfants.

### Mode Éditeur (créateur)

Le **Mode Éditeur** est l'outil du créateur pour gérer rapidement les
previews de la bibliothèque. Il est accessible via un bouton discret de la
barre supérieure, **uniquement** quand le mode admin est actif (voir
`RCM_ADMIN_MODE` dans `.env.example`).

Workflow : **Sélectionner → Aperçu → Intégrer → Carte mise à jour**.

1. Sélectionnez un élément (dossier, arme, skin, charm, …) dans la liste.
2. Choisissez une image depuis le PC : un **aperçu avant validation**
   s'affiche (`Annuler` ne modifie rien).
3. **Intégrer l'image** :
   - l'image est copiée dans le cache local de l'application et associée à
     l'élément via un sidecar (le fichier du PC n'est plus nécessaire) ;
   - elle est aussi copiée dans `assets/` et enregistrée dans `manifest.json`
     sous la **clé stable** de l'élément (la chaîne de slugs de son chemin
     relatif à la racine de la bibliothèque — jamais un chemin absolu) ;
   - la carte s'actualise immédiatement.

L'image intégrée devient une **ressource du projet source** : après
`git add assets/ manifest.json && git commit && git push`, chaque utilisateur
la récupère à la prochaine synchronisation, sans reconstruire le `.exe`
(comme tout autre asset partagé). Un remplacement nettoie proprement
l'ancien fichier (aucun `AK_1.png`, `AK_2.png`, …). Le Mode Éditeur ne
modifie jamais les vrais fichiers de configuration (`.json` / `.obj`).

### Modèles 3D (OBJ)

Une configuration peut être associée à un modèle `.obj` :

- **Détection automatique** (déterministe) : `Skin.json` + `Skin.obj`
  (même nom exact) dans le même dossier, ou un unique `.obj` référencé par
  le contenu du JSON, ou un unique `.obj` dans un dossier-configuration.
- **Ajouter un OBJ** dans la vue de détail : copie le modèle dans le cache
  de l'application (`obj_cache`, sous `%APPDATA%`), enregistre l'association
  dans un sidecar `.obj.json`, sans jamais modifier le vrai `.obj` ni le
  JSON original.
- À l'activation, le modèle est copié **à côté de la configuration** dans
  le dossier Fleasion.

### Activation Fleasion

Le bouton **ACTIVER** copie la configuration dans le dossier `configs/` de
Fleasion puis, si `settings.json` existe, **sélectionne réellement** la
configuration (ajout à `enabled_configs`, mise à jour de `last_config`),
avec sauvegarde préalable et vérification de l'enregistrement. L'état du
bouton reflète la réalité : `ACTIVER` → `✓ COPIÉ` (fichiers copiés,
sélection manuelle requise) → `✓ ACTIF` (sélection confirmée).

## 9. Tests

```bash
python -m pytest tests -q
```

Les tests couvrent : scan des dossiers, JSON invalides, fichiers manquants,
copie, sauvegardes, restauration, chemins avec espaces, recherche, import
individuel/multiple, profils (export/import `.zip`), détection, corbeille,
Fleasion, favoris, langues, tutoriel/onboarding, thèmes, et un test de bout
en bout de l'interface (mode headless).

## 10. Logs

Les journaux sont écrits dans `%APPDATA%\RivalsConfigManager\app.log` — utiles
pour diagnostiquer un problème sans avoir accès à la console.

## 11. Assets partagés et synchronisation

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
  (et synchronisation opportuniste au démarrage). Seuls les assets
  nouveaux/modifiés sont téléchargés, en arrière-plan, sans jamais bloquer
  l'interface.
- **Remote** : par défaut, les assets sont servis depuis
  `https://raw.githubusercontent.com/louisdacostagaudin000-ux/RivalsConfigManager/main`
  (URL définie dans `app/assets/__init__.py`). Elle peut être surchargée (ou
  désactivée) via la variable d'environnement `RCM_ASSET_BASE_URL` (voir
  `.env.example`) — par exemple pour un miroir ou du hors-ligne.
- **Hors ligne** : sans Internet, l'application continue de fonctionner avec
  le cache local ; une carte sans image locale retombe sur l'image partagée
  du cache, sinon sur un placeholder propre.

### Publier / mettre à jour les images

Le dépôt `assets/` reflète la bibliothèque : la **clé du manifest** est la
chaîne (en slugs) du chemin de l'élément (ex.
`rivals_skins/melee/battle_axe/nordicaxe`), ce qui évite toute collision
entre deux éléments homonymes. Ne pas éditer le manifest à la main — utiliser
l'outil qui lit la bibliothèque + son cache, copie les images dans `assets/`
et régénère le manifest (version, taille, sha256) :

```bash
python tools/sync_assets_from_library.py
```

Une image **nouvelle** démarre à la version 1, une image **modifiée** voit sa
version incrémentée, une image **supprimée** est retirée. Puis `git add assets/
manifest.json && git commit && git push` — les utilisateurs la récupèrent à la
prochaine synchronisation, **sans** reconstruire le `.exe`.

## Structure du projet

```
├── main.py                      # point d'entrée
├── manifest.json                # manifest des assets partagés (versionné)
├── .env.example                 # config d'exemple (RCM_ASSET_BASE_URL, …)
├── requirements.txt
├── RivalsConfigManager.spec     # build PyInstaller
├── README.md
├── app/
│   ├── config.py                # paramètres (dossiers, sauvegarde auto, langues)
│   ├── scanner.py               # scan générique de la bibliothèque
│   ├── json_validator.py        # validation JSON + résolution des meshes
│   ├── backup_manager.py        # sauvegardes / restauration
│   ├── file_manager.py          # activation (copie) d'une configuration
│   ├── profiles.py              # profils + export/import .zip
│   ├── batch_import.py          # analyse des lots d'import (multi-éléments, ZIP)
│   ├── detection.py             # détection automatique catégorie/destination
│   ├── validations.py           # validation manuelle des dépendances
│   ├── onboarding.py            # état du premier lancement (langue, tutoriel)
│   ├── restart.py               # redémarrage de l'application
│   ├── assets/                  # manifest, cache local, synchro, sécurité
│   └── launcher.py              # démarrage de l'application
├── ui/
│   ├── theme.py                 # thèmes (QSS, clair/sombre)
│   ├── main_window.py           # fenêtre principale, navigation, recherche
│   ├── card_specs.py            # spécifications des cartes
│   └── views/                   # accueil, parcours, config, profils, paramètres,
│                                #   import multiple, choix de destination, langue…
│   └── widgets/                 # cartes, toast, overlay du tutoriel…
├── assets/                      # images partagées (reflète la bibliothèque) + icône
├── tools/                       # sync_assets, make_icon, clés i18n, vérification
└── tests/                       # tests pytest
```
