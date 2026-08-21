"""Add the v1.3.8 onboarding translation keys to every language file.

Re-dumps each file with the exact original formatting
(``json.dumps(..., ensure_ascii=False, indent=4)`` + trailing newline, LF),
so the only diff is the added keys. The i18n parity test then verifies the
10 languages match exactly.
"""
from __future__ import annotations

import json

TRANS = {
    "fr": {
        "onboarding.language.title": "Choisissez votre langue",
        "onboarding.language.body": (
            "L'application est disponible en plusieurs langues. "
            "Vous pourrez la changer à tout moment dans les Paramètres."
        ),
        "onboarding.continue": "Continuer",
        "onboarding.step_add.title": "Ajouter vos fichiers",
        "onboarding.step_add.body": (
            "Glissez-déposez vos fichiers ici pour les ajouter. "
            "Vous pouvez également cliquer pour parcourir vos fichiers."
        ),
        "onboarding.step_nav.title": "Navigation",
        "onboarding.step_nav.body": (
            "Utilisez ces boutons pour revenir en arrière ou avancer dans votre navigation."
        ),
        "onboarding.step_trash.title": "Corbeille",
        "onboarding.step_trash.body": (
            "Retrouvez ici les configurations supprimées et gérez votre corbeille."
        ),
        "onboarding.step_profiles.title": "Profils",
        "onboarding.step_profiles.body": (
            "Créez et appliquez rapidement vos profils de configurations."
        ),
        "onboarding.step_home.title": "Accueil",
        "onboarding.step_home.body": (
            "Revenez ici pour retrouver toutes vos catégories et configurations."
        ),
        "onboarding.step_favorites.title": "Favoris",
        "onboarding.step_favorites.body": "Retrouvez ici toutes vos configurations favorites.",
        "onboarding.step_search.title": "Recherche",
        "onboarding.step_search.body": (
            "Recherchez rapidement une configuration, une arme, un skin, "
            "un charm ou tout autre élément."
        ),
        "onboarding.step_settings.title": "Paramètres",
        "onboarding.step_settings.body": (
            "Retrouvez ici vos préférences, votre langue, votre thème "
            "et les options de l'application."
        ),
        "onboarding.done.title": "Vous êtes prêt !",
        "onboarding.done.body": (
            "Vous connaissez maintenant les principales fonctions de RivalsConfigManager."
        ),
        "onboarding.next": "Suivant",
        "onboarding.prev": "Précédent",
        "onboarding.finish": "Terminer",
        "onboarding.got_it": "Compris",
        "onboarding.progress": "{current} / {total}",
    },
    "en": {
        "onboarding.language.title": "Choose your language",
        "onboarding.language.body": (
            "The app is available in several languages. "
            "You can change it at any time in Settings."
        ),
        "onboarding.continue": "Continue",
        "onboarding.step_add.title": "Add your files",
        "onboarding.step_add.body": (
            "Drag and drop your files here to add them. "
            "You can also click to browse your files."
        ),
        "onboarding.step_nav.title": "Navigation",
        "onboarding.step_nav.body": (
            "Use these buttons to go back or forward in your navigation."
        ),
        "onboarding.step_trash.title": "Trash",
        "onboarding.step_trash.body": (
            "Find your deleted configurations here and manage your trash."
        ),
        "onboarding.step_profiles.title": "Profiles",
        "onboarding.step_profiles.body": (
            "Quickly create and apply your configuration profiles."
        ),
        "onboarding.step_home.title": "Home",
        "onboarding.step_home.body": (
            "Come back here to find all your categories and configurations."
        ),
        "onboarding.step_favorites.title": "Favorites",
        "onboarding.step_favorites.body": "Find all your favorite configurations here.",
        "onboarding.step_search.title": "Search",
        "onboarding.step_search.body": (
            "Quickly search for a configuration, a weapon, a skin, "
            "a charm or anything else."
        ),
        "onboarding.step_settings.title": "Settings",
        "onboarding.step_settings.body": (
            "Find your preferences, language, theme and application options here."
        ),
        "onboarding.done.title": "You're all set!",
        "onboarding.done.body": (
            "You now know the main features of RivalsConfigManager."
        ),
        "onboarding.next": "Next",
        "onboarding.prev": "Previous",
        "onboarding.finish": "Finish",
        "onboarding.got_it": "Got it",
        "onboarding.progress": "{current} / {total}",
    },
    "es": {
        "onboarding.language.title": "Elige tu idioma",
        "onboarding.language.body": (
            "La aplicación está disponible en varios idiomas. "
            "Puedes cambiarlo en cualquier momento en Ajustes."
        ),
        "onboarding.continue": "Continuar",
        "onboarding.step_add.title": "Añade tus archivos",
        "onboarding.step_add.body": (
            "Arrastra y suelta tus archivos aquí para añadirlos. "
            "También puedes hacer clic para explorar tus archivos."
        ),
        "onboarding.step_nav.title": "Navegación",
        "onboarding.step_nav.body": (
            "Usa estos botones para volver atrás o avanzar en tu navegación."
        ),
        "onboarding.step_trash.title": "Papelera",
        "onboarding.step_trash.body": (
            "Encuentra aquí tus configuraciones eliminadas y gestiona tu papelera."
        ),
        "onboarding.step_profiles.title": "Perfiles",
        "onboarding.step_profiles.body": (
            "Crea y aplica rápidamente tus perfiles de configuración."
        ),
        "onboarding.step_home.title": "Inicio",
        "onboarding.step_home.body": (
            "Vuelve aquí para encontrar todas tus categorías y configuraciones."
        ),
        "onboarding.step_favorites.title": "Favoritos",
        "onboarding.step_favorites.body": "Encuentra aquí todas tus configuraciones favoritas.",
        "onboarding.step_search.title": "Búsqueda",
        "onboarding.step_search.body": (
            "Busca rápidamente una configuración, un arma, un skin, "
            "un charm o cualquier otro elemento."
        ),
        "onboarding.step_settings.title": "Ajustes",
        "onboarding.step_settings.body": (
            "Encuentra aquí tus preferencias, idioma, tema y opciones de la aplicación."
        ),
        "onboarding.done.title": "¡Estás listo!",
        "onboarding.done.body": (
            "Ahora conoces las funciones principales de RivalsConfigManager."
        ),
        "onboarding.next": "Siguiente",
        "onboarding.prev": "Anterior",
        "onboarding.finish": "Terminar",
        "onboarding.got_it": "Entendido",
        "onboarding.progress": "{current} / {total}",
    },
    "de": {
        "onboarding.language.title": "Wähle deine Sprache",
        "onboarding.language.body": (
            "Die App ist in mehreren Sprachen verfügbar. "
            "Du kannst sie jederzeit in den Einstellungen ändern."
        ),
        "onboarding.continue": "Weiter",
        "onboarding.step_add.title": "Dateien hinzufügen",
        "onboarding.step_add.body": (
            "Ziehe deine Dateien hierher, um sie hinzuzufügen. "
            "Du kannst auch klicken, um deine Dateien zu durchsuchen."
        ),
        "onboarding.step_nav.title": "Navigation",
        "onboarding.step_nav.body": (
            "Verwende diese Schaltflächen, um in deiner Navigation zurück- oder vorwärtszugehen."
        ),
        "onboarding.step_trash.title": "Papierkorb",
        "onboarding.step_trash.body": (
            "Hier findest du gelöschte Konfigurationen und verwaltest deinen Papierkorb."
        ),
        "onboarding.step_profiles.title": "Profile",
        "onboarding.step_profiles.body": (
            "Erstelle und wende deine Konfigurationsprofile schnell an."
        ),
        "onboarding.step_home.title": "Startseite",
        "onboarding.step_home.body": (
            "Komm hierher zurück, um alle deine Kategorien und Konfigurationen zu finden."
        ),
        "onboarding.step_favorites.title": "Favoriten",
        "onboarding.step_favorites.body": "Hier findest du alle deine Lieblingskonfigurationen.",
        "onboarding.step_search.title": "Suche",
        "onboarding.step_search.body": (
            "Suche schnell nach einer Konfiguration, einer Waffe, einem Skin, "
            "einem Charm oder einem anderen Element."
        ),
        "onboarding.step_settings.title": "Einstellungen",
        "onboarding.step_settings.body": (
            "Hier findest du deine Einstellungen, Sprache, Thema und App-Optionen."
        ),
        "onboarding.done.title": "Du bist bereit!",
        "onboarding.done.body": (
            "Du kennst jetzt die wichtigsten Funktionen von RivalsConfigManager."
        ),
        "onboarding.next": "Weiter",
        "onboarding.prev": "Zurück",
        "onboarding.finish": "Fertig",
        "onboarding.got_it": "Verstanden",
        "onboarding.progress": "{current} / {total}",
    },
    "it": {
        "onboarding.language.title": "Scegli la tua lingua",
        "onboarding.language.body": (
            "L'app è disponibile in più lingue. "
            "Puoi cambiarla in qualsiasi momento nelle Impostazioni."
        ),
        "onboarding.continue": "Continua",
        "onboarding.step_add.title": "Aggiungi i tuoi file",
        "onboarding.step_add.body": (
            "Trascina qui i tuoi file per aggiungerli. "
            "Puoi anche fare clic per sfogliare i tuoi file."
        ),
        "onboarding.step_nav.title": "Navigazione",
        "onboarding.step_nav.body": (
            "Usa questi pulsanti per tornare indietro o avanzare nella navigazione."
        ),
        "onboarding.step_trash.title": "Cestino",
        "onboarding.step_trash.body": (
            "Trova qui le configurazioni eliminate e gestisci il tuo cestino."
        ),
        "onboarding.step_profiles.title": "Profilo",
        "onboarding.step_profiles.body": (
            "Crea e applica rapidamente i tuoi profili di configurazione."
        ),
        "onboarding.step_home.title": "Home",
        "onboarding.step_home.body": (
            "Torna qui per trovare tutte le tue categorie e configurazioni."
        ),
        "onboarding.step_favorites.title": "Preferiti",
        "onboarding.step_favorites.body": "Trova qui tutte le tue configurazioni preferite.",
        "onboarding.step_search.title": "Ricerca",
        "onboarding.step_search.body": (
            "Cerca rapidamente una configurazione, un'arma, una skin, "
            "un charm o qualsiasi altro elemento."
        ),
        "onboarding.step_settings.title": "Impostazioni",
        "onboarding.step_settings.body": (
            "Trova qui le tue preferenze, lingua, tema e opzioni dell'app."
        ),
        "onboarding.done.title": "Sei pronto!",
        "onboarding.done.body": (
            "Ora conosci le funzioni principali di RivalsConfigManager."
        ),
        "onboarding.next": "Avanti",
        "onboarding.prev": "Indietro",
        "onboarding.finish": "Fine",
        "onboarding.got_it": "Capito",
        "onboarding.progress": "{current} / {total}",
    },
    "nl": {
        "onboarding.language.title": "Kies je taal",
        "onboarding.language.body": (
            "De app is beschikbaar in meerdere talen. "
            "Je kunt deze op elk moment wijzigen in Instellingen."
        ),
        "onboarding.continue": "Doorgaan",
        "onboarding.step_add.title": "Voeg je bestanden toe",
        "onboarding.step_add.body": (
            "Sleep je bestanden hierheen om ze toe te voegen. "
            "Je kunt ook klikken om door je bestanden te bladeren."
        ),
        "onboarding.step_nav.title": "Navigatie",
        "onboarding.step_nav.body": (
            "Gebruik deze knoppen om terug of vooruit te gaan in je navigatie."
        ),
        "onboarding.step_trash.title": "Prullenbak",
        "onboarding.step_trash.body": (
            "Vind hier je verwijderde configuraties en beheer je prullenbak."
        ),
        "onboarding.step_profiles.title": "Profielen",
        "onboarding.step_profiles.body": (
            "Maak en pas snel je configuratieprofielen toe."
        ),
        "onboarding.step_home.title": "Home",
        "onboarding.step_home.body": (
            "Kom hier terug om al je categorieën en configuraties te vinden."
        ),
        "onboarding.step_favorites.title": "Favorieten",
        "onboarding.step_favorites.body": "Vind hier al je favoriete configuraties.",
        "onboarding.step_search.title": "Zoeken",
        "onboarding.step_search.body": (
            "Zoek snel een configuratie, wapen, skin, charm of een ander element."
        ),
        "onboarding.step_settings.title": "Instellingen",
        "onboarding.step_settings.body": (
            "Vind hier je voorkeuren, taal, thema en app-opties."
        ),
        "onboarding.done.title": "Je bent klaar!",
        "onboarding.done.body": (
            "Je kent nu de belangrijkste functies van RivalsConfigManager."
        ),
        "onboarding.next": "Volgende",
        "onboarding.prev": "Vorige",
        "onboarding.finish": "Afronden",
        "onboarding.got_it": "Begrepen",
        "onboarding.progress": "{current} / {total}",
    },
    "pl": {
        "onboarding.language.title": "Wybierz język",
        "onboarding.language.body": (
            "Aplikacja jest dostępna w kilku językach. "
            "Możesz go zmienić w dowolnym momencie w Ustawieniach."
        ),
        "onboarding.continue": "Kontynuuj",
        "onboarding.step_add.title": "Dodaj swoje pliki",
        "onboarding.step_add.body": (
            "Przeciągnij i upuść pliki tutaj, aby je dodać. "
            "Możesz też kliknąć, aby przeglądać swoje pliki."
        ),
        "onboarding.step_nav.title": "Nawigacja",
        "onboarding.step_nav.body": (
            "Użyj tych przycisków, aby cofnąć się lub przejść dalej w nawigacji."
        ),
        "onboarding.step_trash.title": "Kosz",
        "onboarding.step_trash.body": (
            "Znajdziesz tutaj usunięte konfiguracje i zarządzisz koszem."
        ),
        "onboarding.step_profiles.title": "Profile",
        "onboarding.step_profiles.body": (
            "Szybko twórz i stosuj swoje profile konfiguracji."
        ),
        "onboarding.step_home.title": "Strona główna",
        "onboarding.step_home.body": (
            "Wróć tutaj, aby znaleźć wszystkie swoje kategorie i konfiguracje."
        ),
        "onboarding.step_favorites.title": "Ulubione",
        "onboarding.step_favorites.body": "Znajdziesz tutaj wszystkie swoje ulubione konfiguracje.",
        "onboarding.step_search.title": "Szukaj",
        "onboarding.step_search.body": (
            "Szybko wyszukaj konfigurację, broń, skin, charm lub inny element."
        ),
        "onboarding.step_settings.title": "Ustawienia",
        "onboarding.step_settings.body": (
            "Znajdziesz tutaj swoje preferencje, język, motyw i opcje aplikacji."
        ),
        "onboarding.done.title": "Jesteś gotowy!",
        "onboarding.done.body": (
            "Znasz już główne funkcje RivalsConfigManager."
        ),
        "onboarding.next": "Dalej",
        "onboarding.prev": "Wstecz",
        "onboarding.finish": "Zakończ",
        "onboarding.got_it": "Rozumiem",
        "onboarding.progress": "{current} / {total}",
    },
    "pt": {
        "onboarding.language.title": "Escolha o seu idioma",
        "onboarding.language.body": (
            "O aplicativo está disponível em vários idiomas. "
            "Você pode alterá-lo a qualquer momento nas Configurações."
        ),
        "onboarding.continue": "Continuar",
        "onboarding.step_add.title": "Adicione seus arquivos",
        "onboarding.step_add.body": (
            "Arraste e solte seus arquivos aqui para adicioná-los. "
            "Você também pode clicar para navegar pelos seus arquivos."
        ),
        "onboarding.step_nav.title": "Navegação",
        "onboarding.step_nav.body": (
            "Use estes botões para voltar ou avançar na sua navegação."
        ),
        "onboarding.step_trash.title": "Lixeira",
        "onboarding.step_trash.body": (
            "Encontre aqui suas configurações excluídas e gerencie sua lixeira."
        ),
        "onboarding.step_profiles.title": "Perfis",
        "onboarding.step_profiles.body": (
            "Crie e aplique rapidamente seus perfis de configuração."
        ),
        "onboarding.step_home.title": "Início",
        "onboarding.step_home.body": (
            "Volte aqui para encontrar todas as suas categorias e configurações."
        ),
        "onboarding.step_favorites.title": "Favoritos",
        "onboarding.step_favorites.body": "Encontre aqui todas as suas configurações favoritas.",
        "onboarding.step_search.title": "Pesquisa",
        "onboarding.step_search.body": (
            "Pesquise rapidamente uma configuração, uma arma, uma skin, "
            "um charm ou qualquer outro elemento."
        ),
        "onboarding.step_settings.title": "Configurações",
        "onboarding.step_settings.body": (
            "Encontre aqui suas preferências, idioma, tema e opções do aplicativo."
        ),
        "onboarding.done.title": "Você está pronto!",
        "onboarding.done.body": (
            "Agora você conhece as principais funções do RivalsConfigManager."
        ),
        "onboarding.next": "Próximo",
        "onboarding.prev": "Anterior",
        "onboarding.finish": "Concluir",
        "onboarding.got_it": "Entendi",
        "onboarding.progress": "{current} / {total}",
    },
    "ru": {
        "onboarding.language.title": "Выберите язык",
        "onboarding.language.body": (
            "Приложение доступно на нескольких языках. "
            "Вы можете изменить его в любое время в настройках."
        ),
        "onboarding.continue": "Продолжить",
        "onboarding.step_add.title": "Добавьте свои файлы",
        "onboarding.step_add.body": (
            "Перетащите файлы сюда, чтобы добавить их. "
            "Вы также можете нажать, чтобы просмотреть свои файлы."
        ),
        "onboarding.step_nav.title": "Навигация",
        "onboarding.step_nav.body": (
            "Используйте эти кнопки, чтобы вернуться назад или перейти вперед."
        ),
        "onboarding.step_trash.title": "Корзина",
        "onboarding.step_trash.body": (
            "Здесь вы найдете удаленные конфигурации и сможете управлять корзиной."
        ),
        "onboarding.step_profiles.title": "Профили",
        "onboarding.step_profiles.body": (
            "Быстро создавайте и применяйте свои профили конфигураций."
        ),
        "onboarding.step_home.title": "Главная",
        "onboarding.step_home.body": (
            "Вернитесь сюда, чтобы найти все свои категории и конфигурации."
        ),
        "onboarding.step_favorites.title": "Избранное",
        "onboarding.step_favorites.body": "Здесь вы найдете все свои избранные конфигурации.",
        "onboarding.step_search.title": "Поиск",
        "onboarding.step_search.body": (
            "Быстро найдите конфигурацию, оружие, скин, чарм или другой элемент."
        ),
        "onboarding.step_settings.title": "Настройки",
        "onboarding.step_settings.body": (
            "Здесь вы найдете свои предпочтения, язык, тему и параметры приложения."
        ),
        "onboarding.done.title": "Вы готовы!",
        "onboarding.done.body": (
            "Теперь вы знаете основные функции RivalsConfigManager."
        ),
        "onboarding.next": "Далее",
        "onboarding.prev": "Назад",
        "onboarding.finish": "Завершить",
        "onboarding.got_it": "Понятно",
        "onboarding.progress": "{current} / {total}",
    },
    "tr": {
        "onboarding.language.title": "Dilinizi seçin",
        "onboarding.language.body": (
            "Uygulama birçok dilde mevcuttur. "
            "İstediğiniz zaman Ayarlar'dan değiştirebilirsiniz."
        ),
        "onboarding.continue": "Devam et",
        "onboarding.step_add.title": "Dosyalarınızı ekleyin",
        "onboarding.step_add.body": (
            "Dosyalarınızı eklemek için buraya sürükleyip bırakın. "
            "Ayrıca tıklayarak dosyalarınıza göz atabilirsiniz."
        ),
        "onboarding.step_nav.title": "Gezinme",
        "onboarding.step_nav.body": (
            "Gezinmenizde geri gitmek veya ileri gitmek için bu düğmeleri kullanın."
        ),
        "onboarding.step_trash.title": "Çöp kutusu",
        "onboarding.step_trash.body": (
            "Silinen yapılandırmalarınızı burada bulun ve çöp kutunuzu yönetin."
        ),
        "onboarding.step_profiles.title": "Profiller",
        "onboarding.step_profiles.body": (
            "Yapılandırma profillerinizi hızlıca oluşturun ve uygulayın."
        ),
        "onboarding.step_home.title": "Ana sayfa",
        "onboarding.step_home.body": (
            "Tüm kategorilerinizi ve yapılandırmalarınızı bulmak için buraya geri dönün."
        ),
        "onboarding.step_favorites.title": "Favoriler",
        "onboarding.step_favorites.body": "Tüm favori yapılandırmalarınızı burada bulun.",
        "onboarding.step_search.title": "Arama",
        "onboarding.step_search.body": (
            "Bir yapılandırmayı, silahı, skin'i, charm'ı veya başka bir öğeyi hızlıca arayın."
        ),
        "onboarding.step_settings.title": "Ayarlar",
        "onboarding.step_settings.body": (
            "Tercihlerinizi, dilinizi, temanızı ve uygulama seçeneklerinizi burada bulun."
        ),
        "onboarding.done.title": "Hazırsınız!",
        "onboarding.done.body": (
            "Artık RivalsConfigManager'ın ana işlevlerini biliyorsunuz."
        ),
        "onboarding.next": "İleri",
        "onboarding.prev": "Geri",
        "onboarding.finish": "Bitir",
        "onboarding.got_it": "Anladım",
        "onboarding.progress": "{current} / {total}",
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
