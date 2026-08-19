# Assets partagés

Ce dossier contient les **images partagées** de la bibliothèque (armes, skins,
charms, catégories, profils…). Elles ne sont **pas** compilées dans le `.exe` :
elles sont publiées dans le dépôt, décrites par le `manifest.json` à la racine,
puis téléchargées à la demande dans le cache local de chaque utilisateur.

## Arborescence

```text
assets/
├── weapons/      # images d'armes (ex. assault_rifle.png)
├── skins/        # images de skins
├── charms/       # images de charms
├── melee/        # images de la catégorie mêlée
├── primary/      # images de la catégorie primaire
├── secondary/    # images de la catégorie secondaire
├── utility/      # images de la catégorie utilitaire
├── categories/   # images de catégories génériques
└── profiles/     # images de profils (futur)
```

Les noms de fichiers sont des **slugs** (minuscules, `_` comme séparateur) pour
pouvoir être mis en correspondance avec les noms de la bibliothèque de
l'utilisateur, quelle que soit la casse ou la ponctuation.

## Ajouter une image

1. Déposer le fichier dans le sous-dossier approprié.
2. Ajouter son entrée dans `manifest.json` (avec une `version` incrémentée) :

```json
{
    "assault_rifle": {
        "path": "assets/weapons/assault_rifle.png",
        "version": 1
    }
}
```

3. Pousser sur le dépôt. Les utilisateurs récupèrent la nouvelle image à la
   prochaine synchronisation — **sans** reconstruire le `.exe`.

> `assets/icon.ico` et `assets/icon.png` sont l'icône de l'application
> (utilisée au moment du build) — elles ne font pas partie du manifest.
