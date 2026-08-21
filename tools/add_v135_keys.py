"""Add the v1.3.5 translation keys to every language file (parity).

Re-dumps each file with the exact original formatting
(``json.dumps(..., ensure_ascii=False, indent=4)`` + trailing newline, LF),
so the only diff is the added keys.
"""
from __future__ import annotations

import json

TRANS = {
    "fr": {
        "settings.restart": "Recharger l'application",
        "settings.restart_tooltip": (
            "Ferme puis relance proprement l'application (comme une actualisation de page). "
            "Aucune donnée n'est perdue : favoris, profils, langue, thème et chemins sont sauvegardés."
        ),
        "toast.restart_failed": "Impossible de relancer l'application.",
    },
    "en": {
        "settings.restart": "Restart the application",
        "settings.restart_tooltip": (
            "Closes and restarts the application cleanly (like a page refresh). "
            "Nothing is lost: favorites, profiles, language, theme and paths are saved."
        ),
        "toast.restart_failed": "Could not restart the application.",
    },
    "es": {
        "settings.restart": "Reiniciar la aplicación",
        "settings.restart_tooltip": (
            "Cierra y reinicia la aplicación correctamente (como una actualización de página). "
            "No se pierde nada: favoritos, perfiles, idioma, tema y rutas se guardan."
        ),
        "toast.restart_failed": "No se pudo reiniciar la aplicación.",
    },
    "de": {
        "settings.restart": "Anwendung neu starten",
        "settings.restart_tooltip": (
            "Schließt und startet die Anwendung sauber neu (wie eine Seitenaktualisierung). "
            "Es geht nichts verloren: Favoriten, Profile, Sprache, Design und Pfade werden gespeichert."
        ),
        "toast.restart_failed": "Die Anwendung konnte nicht neu gestartet werden.",
    },
    "it": {
        "settings.restart": "Riavvia l'applicazione",
        "settings.restart_tooltip": (
            "Chiude e riavvia correttamente l'applicazione (come un aggiornamento della pagina). "
            "Non si perde nulla: preferiti, profili, lingua, tema e percorsi vengono salvati."
        ),
        "toast.restart_failed": "Impossibile riavviare l'applicazione.",
    },
    "nl": {
        "settings.restart": "Applicatie opnieuw starten",
        "settings.restart_tooltip": (
            "Sluit en start de applicatie netjes opnieuw (zoals een paginavernieuwing). "
            "Er gaat niets verloren: favorieten, profielen, taal, thema en paden worden opgeslagen."
        ),
        "toast.restart_failed": "Kan de applicatie niet opnieuw starten.",
    },
    "pl": {
        "settings.restart": "Uruchom ponownie aplikację",
        "settings.restart_tooltip": (
            "Zamyka i ponownie uruchamia aplikację w sposób czysty (jak odświeżenie strony). "
            "Nic nie ginie: ulubione, profile, język, motyw i ścieżki są zapisywane."
        ),
        "toast.restart_failed": "Nie można ponownie uruchomić aplikacji.",
    },
    "pt": {
        "settings.restart": "Reiniciar o aplicativo",
        "settings.restart_tooltip": (
            "Fecha e reinicia o aplicativo corretamente (como uma atualização de página). "
            "Nada se perde: favoritos, perfis, idioma, tema e caminhos são salvos."
        ),
        "toast.restart_failed": "Não foi possível reiniciar o aplicativo.",
    },
    "ru": {
        "settings.restart": "Перезапустить приложение",
        "settings.restart_tooltip": (
            "Закрывает и корректно перезапускает приложение (как обновление страницы). "
            "Ничего не теряется: избранное, профили, язык, тема и пути сохраняются."
        ),
        "toast.restart_failed": "Не удалось перезапустить приложение.",
    },
    "tr": {
        "settings.restart": "Uygulamayı yeniden başlat",
        "settings.restart_tooltip": (
            "Uygulamayı temiz şekilde kapatıp yeniden başlatır (sayfa yenileme gibi). "
            "Hiçbir şey kaybolmaz: favoriler, profiller, dil, tema ve yollar kaydedilir."
        ),
        "toast.restart_failed": "Uygulama yeniden başlatılamadı.",
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
