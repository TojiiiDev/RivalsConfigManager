# Assets partagés

Ce dossier contient les **images partagées** de la bibliothèque (armes, skins,
charms, catégories…). Elles ne sont **pas** compilées dans le `.exe` : elles
sont publiées dans le dépôt, décrites par le `manifest.json` à la racine, puis
téléchargées à la demande dans le cache local de chaque utilisateur.

## Arborescence

Le dossier **reflète la bibliothèque** : chaque image vit au même chemin
relatif (en slugs) que l'élément qu'elle illustre.

```text
assets/
├── charms.png                              # image de la catégorie « Charms »
├── charms/nemesis_charm.jpg                # image du charm « nemesis charm »
├── rivals_skins.jpg                        # image de la catégorie « rivals skins »
├── rivals_skins/melee/battle_axe.webp      # image de l'arme « Battle Axe »
├── rivals_skins/melee/battle_axe/nordicaxe.webp   # image du skin « NordicAxe »
├── wraps/...
├── emotes.jpg
├── fastflags.png
└── kill_and_hit_sounds/...
```

La **clé du manifest** est la même chaîne que le chemin (sans le préfixe
`assets/` ni l'extension) : `rivals_skins/melee/battle_axe/nordicaxe`. Comme
la clé encode le chemin **complet** et pas seulement le nom, deux éléments qui
ne diffèrent que par la casse (le dossier « Hand gun » et le skin « hand gun »)
ne se mélangent jamais.

## Publier / mettre à jour les images

Ne pas éditer `manifest.json` à la main : utiliser l'outil qui lit la
bibliothèque locale et son cache d'images, copie chaque image dans `assets/`
et régénère le manifest (version par asset, taille, sha256) :

```bash
python tools/sync_assets_from_library.py
```

Comportement :

* une image **nouvelle** démarre à la version 1 ;
* une image dont le **contenu a changé** voit sa version incrémentée ;
* une image dont le sidecar a été **supprimé** est retirée du manifest et du
  dépôt ;
* un relancement sans changement ne produit **aucune** nouvelle version.

Ensuite, committer et pousser :

```bash
git add assets/ manifest.json
git commit -m "assets: ..."
git push
```

Les utilisateurs récupèrent les nouveautés à la prochaine synchronisation
(**Paramètres → Synchroniser les ressources**) — **sans** reconstruire le `.exe`.

> `assets/icon.ico` et `assets/icon.png` sont l'icône de l'application
> (utilisée au moment du build) — elles ne font pas partie du manifest.
