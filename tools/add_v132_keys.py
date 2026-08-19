"""One-shot: add v1.3.2 i18n keys to all 10 translation files.

Run from the project root:  python tools/add_v132_keys.py
Safe to re-run (existing keys are never overwritten).
"""

from __future__ import annotations

import json
from pathlib import Path

TRANS = Path("app/i18n/translations")

EN = {
    ("destination", "step_configs"): "3 — Configuration",
    ("destination", "configs_hint"): "Choose a configuration in {weapon}:",
    ("destination", "pick_title"): "Add to profile",
    ("destination", "pick_hint"): "Choose the configuration to add to the profile:",
    ("destination", "add_to_profile"): "Add to profile",
    ("favorites", "title"): "Favorites",
    ("favorites", "subtitle"): "Your favorite configurations",
    ("favorites", "empty"): "No favorites yet — click the star on a configuration.",
    ("nav", "favorites"): "Favorites",
    ("profiles", "browse"): "Browse the library…",
    ("profiles", "browse_tooltip"): "Choose a configuration through the tree",
    ("profile_dialog", "browse"): "Browse…",
    ("profile_dialog", "browse_tooltip"): "Add a configuration chosen in the tree",
}

FR = {
    ("destination", "step_configs"): "3 — Configuration",
    ("destination", "configs_hint"): "Choisissez une configuration dans {weapon} :",
    ("destination", "pick_title"): "Ajouter au profil",
    ("destination", "pick_hint"): "Choisissez la configuration à ajouter au profil :",
    ("destination", "add_to_profile"): "Ajouter au profil",
    ("favorites", "title"): "Favoris",
    ("favorites", "subtitle"): "Vos configurations favorites",
    ("favorites", "empty"): "Aucun favori pour l'instant — cliquez sur l'étoile d'une configuration.",
    ("nav", "favorites"): "Favoris",
    ("profiles", "browse"): "Parcourir la bibliothèque…",
    ("profiles", "browse_tooltip"): "Choisir une configuration via l'arborescence",
    ("profile_dialog", "browse"): "Parcourir…",
    ("profile_dialog", "browse_tooltip"): "Ajouter une configuration choisie dans l'arborescence",
}

#: Per-language patch for the 8 secondary languages. Keys not present fall
#: back to the English value (parity is enforced by the i18n tests).
_LANG_PATCHES = {
    "es": {
        ("destination", "step_configs"): "3 — Configuración",
        ("destination", "configs_hint"): "Elige una configuración en {weapon}:",
        ("destination", "pick_title"): "Añadir al perfil",
        ("destination", "pick_hint"): "Elige la configuración para añadir al perfil:",
        ("destination", "add_to_profile"): "Añadir al perfil",
        ("favorites", "title"): "Favoritos",
        ("favorites", "subtitle"): "Tus configuraciones favoritas",
        ("favorites", "empty"): "Aún no hay favoritos: haz clic en la estrella de una configuración.",
        ("nav", "favorites"): "Favoritos",
        ("profiles", "browse"): "Explorar la biblioteca…",
        ("profiles", "browse_tooltip"): "Elegir una configuración a través del árbol",
        ("profile_dialog", "browse"): "Explorar…",
        ("profile_dialog", "browse_tooltip"): "Añadir una configuración elegida en el árbol",
    },
    "de": {
        ("destination", "step_configs"): "3 — Konfiguration",
        ("destination", "configs_hint"): "Wähle eine Konfiguration in {weapon}:",
        ("destination", "pick_title"): "Zum Profil hinzufügen",
        ("destination", "pick_hint"): "Wähle die Konfiguration, die zum Profil hinzugefügt werden soll:",
        ("destination", "add_to_profile"): "Zum Profil hinzufügen",
        ("favorites", "title"): "Favoriten",
        ("favorites", "subtitle"): "Deine Lieblingskonfigurationen",
        ("favorites", "empty"): "Noch keine Favoriten — klicke auf den Stern einer Konfiguration.",
        ("nav", "favorites"): "Favoriten",
        ("profiles", "browse"): "Bibliothek durchsuchen…",
        ("profiles", "browse_tooltip"): "Konfiguration über den Baum wählen",
        ("profile_dialog", "browse"): "Durchsuchen…",
        ("profile_dialog", "browse_tooltip"): "Konfiguration aus dem Baum hinzufügen",
    },
    "it": {
        ("destination", "step_configs"): "3 — Configurazione",
        ("destination", "configs_hint"): "Scegli una configurazione in {weapon}:",
        ("destination", "pick_title"): "Aggiungi al profilo",
        ("destination", "pick_hint"): "Scegli la configurazione da aggiungere al profilo:",
        ("destination", "add_to_profile"): "Aggiungi al profilo",
        ("favorites", "title"): "Preferiti",
        ("favorites", "subtitle"): "Le tue configurazioni preferite",
        ("favorites", "empty"): "Nessun preferito per ora — clicca la stella di una configurazione.",
        ("nav", "favorites"): "Preferiti",
        ("profiles", "browse"): "Sfoglia la libreria…",
        ("profiles", "browse_tooltip"): "Scegli una configurazione tramite l'albero",
        ("profile_dialog", "browse"): "Sfoglia…",
        ("profile_dialog", "browse_tooltip"): "Aggiungi una configurazione scelta nell'albero",
    },
    "pt": {
        ("destination", "step_configs"): "3 — Configuração",
        ("destination", "configs_hint"): "Escolha uma configuração em {weapon}:",
        ("destination", "pick_title"): "Adicionar ao perfil",
        ("destination", "pick_hint"): "Escolha a configuração para adicionar ao perfil:",
        ("destination", "add_to_profile"): "Adicionar ao perfil",
        ("favorites", "title"): "Favoritos",
        ("favorites", "subtitle"): "Suas configurações favoritas",
        ("favorites", "empty"): "Nenhum favorito ainda — clique na estrela de uma configuração.",
        ("nav", "favorites"): "Favoritos",
        ("profiles", "browse"): "Explorar a biblioteca…",
        ("profiles", "browse_tooltip"): "Escolher uma configuração pela árvore",
        ("profile_dialog", "browse"): "Explorar…",
        ("profile_dialog", "browse_tooltip"): "Adicionar uma configuração escolhida na árvore",
    },
    "nl": {
        ("destination", "step_configs"): "3 — Configuratie",
        ("destination", "configs_hint"): "Kies een configuratie in {weapon}:",
        ("destination", "pick_title"): "Toevoegen aan profiel",
        ("destination", "pick_hint"): "Kies de configuratie om aan het profiel toe te voegen:",
        ("destination", "add_to_profile"): "Toevoegen aan profiel",
        ("favorites", "title"): "Favorieten",
        ("favorites", "subtitle"): "Jouw favoriete configuraties",
        ("favorites", "empty"): "Nog geen favorieten — klik op de ster van een configuratie.",
        ("nav", "favorites"): "Favorieten",
        ("profiles", "browse"): "Bibliotheek verkennen…",
        ("profiles", "browse_tooltip"): "Kies een configuratie via de boom",
        ("profile_dialog", "browse"): "Verkennen…",
        ("profile_dialog", "browse_tooltip"): "Voeg een in de boom gekozen configuratie toe",
    },
    "pl": {
        ("destination", "step_configs"): "3 — Konfiguracja",
        ("destination", "configs_hint"): "Wybierz konfigurację w {weapon}:",
        ("destination", "pick_title"): "Dodaj do profilu",
        ("destination", "pick_hint"): "Wybierz konfigurację do dodania do profilu:",
        ("destination", "add_to_profile"): "Dodaj do profilu",
        ("favorites", "title"): "Ulubione",
        ("favorites", "subtitle"): "Twoje ulubione konfiguracje",
        ("favorites", "empty"): "Brak ulubionych — kliknij gwiazdkę przy konfiguracji.",
        ("nav", "favorites"): "Ulubione",
        ("profiles", "browse"): "Przeglądaj bibliotekę…",
        ("profiles", "browse_tooltip"): "Wybierz konfigurację przez drzewo",
        ("profile_dialog", "browse"): "Przeglądaj…",
        ("profile_dialog", "browse_tooltip"): "Dodaj konfigurację wybraną w drzewie",
    },
    "ru": {
        ("destination", "step_configs"): "3 — Конфигурация",
        ("destination", "configs_hint"): "Выберите конфигурацию в {weapon}:",
        ("destination", "pick_title"): "Добавить в профиль",
        ("destination", "pick_hint"): "Выберите конфигурацию для добавления в профиль:",
        ("destination", "add_to_profile"): "Добавить в профиль",
        ("favorites", "title"): "Избранное",
        ("favorites", "subtitle"): "Ваши избранные конфигурации",
        ("favorites", "empty"): "Пока нет избранного — нажмите на звезду у конфигурации.",
        ("nav", "favorites"): "Избранное",
        ("profiles", "browse"): "Просмотр библиотеки…",
        ("profiles", "browse_tooltip"): "Выберите конфигурацию через дерево",
        ("profile_dialog", "browse"): "Просмотр…",
        ("profile_dialog", "browse_tooltip"): "Добавить конфигурацию, выбранную в дереве",
    },
    "tr": {
        ("destination", "step_configs"): "3 — Yapılandırma",
        ("destination", "configs_hint"): "{weapon} içinde bir yapılandırma seçin:",
        ("destination", "pick_title"): "Profile ekle",
        ("destination", "pick_hint"): "Profile eklenecek yapılandırmayı seçin:",
        ("destination", "add_to_profile"): "Profile ekle",
        ("favorites", "title"): "Favoriler",
        ("favorites", "subtitle"): "Favori yapılandırmalarınız",
        ("favorites", "empty"): "Henüz favori yok — bir yapılandırmanın yıldızına tıklayın.",
        ("nav", "favorites"): "Favoriler",
        ("profiles", "browse"): "Kütüphaneyi göz at…",
        ("profiles", "browse_tooltip"): "Ağaç üzerinden bir yapılandırma seçin",
        ("profile_dialog", "browse"): "Göz at…",
        ("profile_dialog", "browse_tooltip"): "Ağaçta seçilen bir yapılandırmayı ekle",
    },
}


def set_key(data, path, value):
    obj = data
    for part in path[:-1]:
        obj = obj.setdefault(part, {})
    if path[-1] not in obj:
        obj[path[-1]] = value


def main() -> None:
    for lang in ("fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "tr"):
        path = TRANS / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if lang == "fr":
            mapping = FR
        elif lang == "en":
            mapping = EN
        else:
            mapping = dict(EN)
            mapping.update(_LANG_PATCHES.get(lang, {}))
        changed = 0
        for (group, key), value in mapping.items():
            before = None
            obj = data
            for part in (group, key):
                obj = obj.setdefault(part, {}) if part == group else obj
            if key not in obj:
                obj[key] = value
                changed += 1
        if changed:
            path.write_text(
                json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(f"{lang}: {changed} keys added")


if __name__ == "__main__":
    main()
