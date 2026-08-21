"""Add the v1.3.9 « Revoir le tutoriel » keys to every language file."""
from __future__ import annotations

import json

TRANS = {
    "fr": {
        "settings.review_tutorial": "Revoir le tutoriel",
        "settings.review_tutorial_tooltip": "Relance le tutoriel de découverte de l'application",
    },
    "en": {
        "settings.review_tutorial": "Review the tutorial",
        "settings.review_tutorial_tooltip": "Restart the app discovery tutorial",
    },
    "es": {
        "settings.review_tutorial": "Repasar el tutorial",
        "settings.review_tutorial_tooltip": "Reinicia el tutorial de descubrimiento de la aplicación",
    },
    "de": {
        "settings.review_tutorial": "Tutorial ansehen",
        "settings.review_tutorial_tooltip": "Startet das App-Entdeckungs-Tutorial erneut",
    },
    "it": {
        "settings.review_tutorial": "Rivedi il tutorial",
        "settings.review_tutorial_tooltip": "Riavvia il tutorial di scoperta dell'app",
    },
    "nl": {
        "settings.review_tutorial": "Tutorial bekijken",
        "settings.review_tutorial_tooltip": "Start de app-ontdekkingstutorial opnieuw",
    },
    "pl": {
        "settings.review_tutorial": "Przejrzyj samouczek",
        "settings.review_tutorial_tooltip": "Uruchamia ponownie samouczek poznawania aplikacji",
    },
    "pt": {
        "settings.review_tutorial": "Rever o tutorial",
        "settings.review_tutorial_tooltip": "Reinicia o tutorial de descoberta do aplicativo",
    },
    "ru": {
        "settings.review_tutorial": "Повторить обучение",
        "settings.review_tutorial_tooltip": "Запускает обучающий тур по приложению заново",
    },
    "tr": {
        "settings.review_tutorial": "Eğitimi tekrar gör",
        "settings.review_tutorial_tooltip": "Uygulama tanıtım eğitimini yeniden başlatır",
    },
}

for code, mapping in TRANS.items():
    path = f"app/i18n/translations/{code}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for dotted, value in mapping.items():
        parts = dotted.split(".")
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")
    print(f"{code}: ok")
