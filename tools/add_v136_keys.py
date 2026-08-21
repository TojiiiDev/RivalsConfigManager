"""Add the UI/UX phase translation keys to every language file (parity).

Re-dumps each file with the exact original formatting
(``json.dumps(..., ensure_ascii=False, indent=4)`` + trailing newline, LF),
so the only diff is the added keys.
"""
from __future__ import annotations

import json

TRANS = {
    "fr": {
        "home.drop_zone_title": "Glissez-déposez vos fichiers ici pour les ajouter",
        "home.drop_zone_subtitle": "Vous pouvez également cliquer pour parcourir vos fichiers",
        "home.browse_files": "Ajouter des fichiers",
        "home.browse_filter": "Configurations (*.zip *.json);;Tous les fichiers (*)",
    },
    "en": {
        "home.drop_zone_title": "Drag and drop your files here to add them",
        "home.drop_zone_subtitle": "You can also click to browse your files",
        "home.browse_files": "Add files",
        "home.browse_filter": "Configurations (*.zip *.json);;All files (*)",
    },
    "es": {
        "home.drop_zone_title": "Arrastra y suelta tus archivos aquí para añadirlos",
        "home.drop_zone_subtitle": "También puedes hacer clic para explorar tus archivos",
        "home.browse_files": "Añadir archivos",
        "home.browse_filter": "Configuraciones (*.zip *.json);;Todos los archivos (*)",
    },
    "de": {
        "home.drop_zone_title": "Ziehe deine Dateien hierher, um sie hinzuzufügen",
        "home.drop_zone_subtitle": "Du kannst auch klicken, um deine Dateien zu durchsuchen",
        "home.browse_files": "Dateien hinzufügen",
        "home.browse_filter": "Konfigurationen (*.zip *.json);;Alle Dateien (*)",
    },
    "it": {
        "home.drop_zone_title": "Trascina qui i tuoi file per aggiungerli",
        "home.drop_zone_subtitle": "Puoi anche fare clic per sfogliare i tuoi file",
        "home.browse_files": "Aggiungi file",
        "home.browse_filter": "Configurazioni (*.zip *.json);;Tutti i file (*)",
    },
    "nl": {
        "home.drop_zone_title": "Sleep je bestanden hierheen om ze toe te voegen",
        "home.drop_zone_subtitle": "Je kunt ook klikken om je bestanden te bladeren",
        "home.browse_files": "Bestanden toevoegen",
        "home.browse_filter": "Configuraties (*.zip *.json);;Alle bestanden (*)",
    },
    "pl": {
        "home.drop_zone_title": "Przeciągnij i upuść tutaj swoje pliki, aby je dodać",
        "home.drop_zone_subtitle": "Możesz też kliknąć, aby przeglądać swoje pliki",
        "home.browse_files": "Dodaj pliki",
        "home.browse_filter": "Konfiguracje (*.zip *.json);;Wszystkie pliki (*)",
    },
    "pt": {
        "home.drop_zone_title": "Arraste e solte seus arquivos aqui para adicioná-los",
        "home.drop_zone_subtitle": "Você também pode clicar para procurar seus arquivos",
        "home.browse_files": "Adicionar arquivos",
        "home.browse_filter": "Configurações (*.zip *.json);;Todos os arquivos (*)",
    },
    "ru": {
        "home.drop_zone_title": "Перетащите файлы сюда, чтобы добавить их",
        "home.drop_zone_subtitle": "Можно также нажать, чтобы выбрать файлы",
        "home.browse_files": "Добавить файлы",
        "home.browse_filter": "Конфигурации (*.zip *.json);;Все файлы (*)",
    },
    "tr": {
        "home.drop_zone_title": "Dosyalarınızı eklemek için buraya sürükleyip bırakın",
        "home.drop_zone_subtitle": "Dosyalarınıza göz atmak için tıklayabilirsiniz",
        "home.browse_files": "Dosya ekle",
        "home.browse_filter": "Yapılandırmalar (*.zip *.json);;Tüm dosyalar (*)",
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
