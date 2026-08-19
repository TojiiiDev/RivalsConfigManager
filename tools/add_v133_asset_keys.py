"""One-shot: add the asset-sync i18n keys to all 10 translation files.

Run from the project root:  python tools/add_v133_asset_keys.py
Safe to re-run (existing keys are never overwritten).
"""

from __future__ import annotations

import json
from pathlib import Path

TRANS = Path("app/i18n/translations")

EN = {
    "assets": {
        "sync": "Synchronize resources",
        "syncing": "Synchronizing resources…",
        "sync_ok": "✔ Resources synchronized: {summary}",
        "sync_partial": "✘ Partial synchronization: {summary}",
        "offline": "Could not reach the asset repository (offline?). Using the local cache.",
        "invalid_manifest": "Invalid or unsupported asset manifest.",
        "no_remote": "No remote asset repository configured.",
    }
}

FR = {
    "assets": {
        "sync": "Synchroniser les ressources",
        "syncing": "Synchronisation des ressources…",
        "sync_ok": "✔ Ressources synchronisées : {summary}",
        "sync_partial": "✘ Synchronisation partielle : {summary}",
        "offline": "Impossible de joindre le dépôt d'assets (hors ligne ?). Cache local utilisé.",
        "invalid_manifest": "Manifest d'assets invalide ou non pris en charge.",
        "no_remote": "Aucun dépôt d'assets distant configuré.",
    }
}

#: Per-language overrides for the 8 secondary languages; anything missing
#: falls back to the English value (key parity is enforced by the i18n tests).
_LANG_PATCHES = {
    "es": {
        "assets": {
            "sync": "Sincronizar recursos",
            "syncing": "Sincronizando recursos…",
            "sync_ok": "✔ Recursos sincronizados: {summary}",
            "sync_partial": "✘ Sincronización parcial: {summary}",
            "offline": "No se pudo contactar el repositorio de recursos (¿sin conexión?). Usando la caché local.",
            "invalid_manifest": "Manifiesto de recursos no válido o no compatible.",
            "no_remote": "No hay repositorio remoto de recursos configurado.",
        }
    },
    "de": {
        "assets": {
            "sync": "Ressourcen synchronisieren",
            "syncing": "Ressourcen werden synchronisiert…",
            "sync_ok": "✔ Ressourcen synchronisiert: {summary}",
            "sync_partial": "✘ Teilweise synchronisiert: {summary}",
            "offline": "Asset-Repository nicht erreichbar (offline?). Lokaler Cache wird verwendet.",
            "invalid_manifest": "Ungültiges oder nicht unterstütztes Asset-Manifest.",
            "no_remote": "Kein Remote-Asset-Repository konfiguriert.",
        }
    },
    "it": {
        "assets": {
            "sync": "Sincronizza risorse",
            "syncing": "Sincronizzazione delle risorse…",
            "sync_ok": "✔ Risorse sincronizzate: {summary}",
            "sync_partial": "✘ Sincronizzazione parziale: {summary}",
            "offline": "Impossibile raggiungere il repository delle risorse (offline?). Uso della cache locale.",
            "invalid_manifest": "Manifest delle risorse non valido o non supportato.",
            "no_remote": "Nessun repository remoto di risorse configurato.",
        }
    },
    "pt": {
        "assets": {
            "sync": "Sincronizar recursos",
            "syncing": "Sincronizando recursos…",
            "sync_ok": "✔ Recursos sincronizados: {summary}",
            "sync_partial": "✘ Sincronização parcial: {summary}",
            "offline": "Não foi possível acessar o repositório de recursos (offline?). Usando o cache local.",
            "invalid_manifest": "Manifesto de recursos inválido ou não suportado.",
            "no_remote": "Nenhum repositório remoto de recursos configurado.",
        }
    },
    "nl": {
        "assets": {
            "sync": "Bronnen synchroniseren",
            "syncing": "Bronnen synchroniseren…",
            "sync_ok": "✔ Bronnen gesynchroniseerd: {summary}",
            "sync_partial": "✘ Gedeeltelijk gesynchroniseerd: {summary}",
            "offline": "Kan de bronrepository niet bereiken (offline?). Lokale cache wordt gebruikt.",
            "invalid_manifest": "Ongeldig of niet-ondersteund bronmanifest.",
            "no_remote": "Geen externe bronrepository geconfigureerd.",
        }
    },
    "pl": {
        "assets": {
            "sync": "Synchronizuj zasoby",
            "syncing": "Synchronizowanie zasobów…",
            "sync_ok": "✔ Zasoby zsynchronizowane: {summary}",
            "sync_partial": "✘ Częściowa synchronizacja: {summary}",
            "offline": "Nie można połączyć się z repozytorium zasobów (tryb offline?). Używam lokalnej pamięci podręcznej.",
            "invalid_manifest": "Nieprawidłowy lub nieobsługiwany manifest zasobów.",
            "no_remote": "Nie skonfigurowano zdalnego repozytorium zasobów.",
        }
    },
    "ru": {
        "assets": {
            "sync": "Синхронизировать ресурсы",
            "syncing": "Синхронизация ресурсов…",
            "sync_ok": "✔ Ресурсы синхронизированы: {summary}",
            "sync_partial": "✘ Частичная синхронизация: {summary}",
            "offline": "Не удалось связаться с репозиторием ресурсов (нет сети?). Используется локальный кэш.",
            "invalid_manifest": "Недопустимый или неподдерживаемый манифест ресурсов.",
            "no_remote": "Удалённый репозиторий ресурсов не настроен.",
        }
    },
    "tr": {
        "assets": {
            "sync": "Kaynakları eşitle",
            "syncing": "Kaynaklar eşitleniyor…",
            "sync_ok": "✔ Kaynaklar eşitlendi: {summary}",
            "sync_partial": "✘ Kısmi eşitleme: {summary}",
            "offline": "Kaynak deposuna ulaşılamadı (çevrimdışı?). Yerel önbellek kullanılıyor.",
            "invalid_manifest": "Geçersiz veya desteklenmeyen kaynak manifesti.",
            "no_remote": "Uzak kaynak deposu yapılandırılmadı.",
        }
    },
}


def main() -> None:
    for lang in ("fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "tr"):
        path = TRANS / f"{lang}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if lang == "fr":
            assets = FR["assets"]
        elif lang == "en":
            assets = EN["assets"]
        else:
            assets = dict(EN["assets"])
            assets.update(_LANG_PATCHES.get(lang, {}).get("assets", {}))

        group = data.setdefault("assets", {})
        changed = 0
        for key, value in assets.items():
            if key not in group:
                group[key] = value
                changed += 1
        if changed:
            path.write_text(
                json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        print(f"{lang}: {changed} keys added")


if __name__ == "__main__":
    main()
