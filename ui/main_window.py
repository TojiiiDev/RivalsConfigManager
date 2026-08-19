"""Main window: top bar, page stack, navigation history, search, actions."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.backup_manager import BackupManager, BackupInfo
from app.categories import (
    category_folder_in_path,
    category_of_path,
    ensure_weapon_folder,
    safe_folder_name,
)
from app.config import AppSettings, backups_dir, image_cache_dir, normalize_path, obj_cache_dir, trash_dir
from app.file_manager import FileManager
from app.fleasion import FleasionManager
from app.i18n import set_language as _set_language
from app.i18n import t
from app.image_manager import ImageManager
from app.models import ConfigItem, Node
from app.mod_import import ModImportError, analyze_source, cleanup_staging, install_mod
from app.obj_manager import ObjError, ObjManager
from app.profiles import (
    Profile,
    ProfileEntry,
    ProfileError,
    ProfileManager,
    PROFILE_EXTENSION,
)
from app.recents import RecentEntry, RecentsStore
from app.repair import apply_repair, build_repair_plan
from app.scanner import find_config, find_node, scan_library, validate_library_root
from app.search import (
    FAVORITES_EXCLUDED,
    FAVORITES_ONLY,
    STATUS_ALL,
    SearchState,
    run_search,
)
from app.sync import SyncEngine, walk_configs
from app.trash import Trash, TrashEntry, TrashError
from app.verify import verify_item
from ui.views.add_weapon_dialog import AddWeaponDialog
from ui.widgets.card import (
    STATUS_ACTIVE,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_READY,
)
from ui.views.browse_view import BrowseView
from ui.views.clear_configs_dialog import ClearConfigsDialog
from ui.views.config_view import (
    STATE_ACTIVE,
    STATE_COPIED,
    STATE_INACTIVE,
    ConfigView,
)
from ui.views.favorites_view import FavoritesView
from ui.views.home_view import HomeView
from ui.views.image_dialog import ImageDialog
from ui.views.import_dialog import ImportDialog
from ui.views.profile_dialog import ProfileDialog
from ui.views.profiles_view import ProfilesView
from ui.views.search_view import SearchView
from ui.views.settings_view import SettingsView
from ui.navigation import NavigationHistory
from ui.views.trash_view import TrashView
from ui.views.welcome_view import WelcomeView
from ui.widgets.toast import KIND_ERROR, KIND_SUCCESS, KIND_WARNING, Toast
from ui.icons import (
    chevron_left_icon,
    chevron_right_icon,
    gear_icon,
    plus_icon,
    search_icon,
    star_icon,
    trash_icon,
    users_icon,
)

logger = logging.getLogger(__name__)

PAGE_WELCOME = "welcome"
PAGE_HOME = "home"
PAGE_BROWSE = "browse"
PAGE_CONFIG = "config"
PAGE_SETTINGS = "settings"
PAGE_TRASH = "trash"
PAGE_SEARCH = "search"
PAGE_PROFILES = "profiles"
PAGE_FAVORITES = "favorites"

STATE_HOME = (PAGE_HOME, None)
STATE_SETTINGS = (PAGE_SETTINGS, None)


#: Keyboard shortcuts (v1.3.0) — action key -> (QKeySequence, i18n label).
SHORTCUTS: dict[str, tuple[str, str]] = {
    "open_search": ("Ctrl+F", "shortcuts.open_search"),
    "go_home": ("Ctrl+H", "shortcuts.go_home"),
    "verify_config": ("F5", "shortcuts.verify_config"),
    "toggle_config": ("Ctrl+Shift+Enter", "shortcuts.toggle_config"),
}


class _ScanThread(QThread):
    """Run a library scan off the GUI thread.

    Selecting a large library must never freeze the window (Windows shows
    « Ne répond pas » otherwise). The scan is pure Python + filesystem I/O,
    so it is safe in a worker thread; the payloads carried by the signals
    are plain Python objects (``ScanResult`` / an exception) that cross the
    thread boundary without any Qt GUI call.
    """

    scanned = Signal(object)   # ScanResult
    failed = Signal(object)    # Exception

    def __init__(self, library: Path, parent=None) -> None:
        super().__init__(parent)
        self._library = library

    def run(self) -> None:
        try:
            result = scan_library(self._library)
        except Exception as exc:  # noqa: BLE001 - a worker thread must never die silently
            self.failed.emit(exc)
            return
        self.scanned.emit(result)


def app_icon() -> QIcon:
    """Icon painted at runtime (no external asset required)."""
    size = 256
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#171c26"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, 56, 56)
    p.setBrush(QColor("#4f8cff"))
    p.drawRoundedRect(48, 48, 160, 160, 40, 40)
    p.setFont(QFont("Segoe UI", 76, QFont.DemiBold))
    p.setPen(QColor("#ffffff"))
    p.drawText(pm.rect(), Qt.AlignCenter, "RC")
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Rivals Config Manager v{__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1080, 720)
        self.setMinimumSize(960, 640)

        self.settings = AppSettings.load()
        #: Apply the persisted language before building any widget, so every
        #: text is created in the right language from the start.
        _set_language(self.settings.language)
        #: Apply the persisted theme (hot re-application works too — the
        #: module remembers the active spec for inline styles).
        from ui.theme import apply_theme

        apply_theme(
            QApplication.instance() or QApplication([]),
            self.settings.theme,
            self.settings.custom_theme,
        )
        self.backup_manager = BackupManager(backups_dir())
        self.file_manager = FileManager(self.backup_manager)
        self.image_manager = ImageManager()
        self.obj_manager = ObjManager()
        self.trash = Trash()
        self.fleasion = FleasionManager(self.settings.fleasion_dir, self.backup_manager)
        self.recents = RecentsStore()
        self.profiles = ProfileManager()
        self.root_node: Node | None = None
        self._current_item: ConfigItem | None = None

        self._history = NavigationHistory()
        #: Key of the card whose activation is currently running (prevents
        #: any double/concurrent activation from the card buttons).
        self._card_toggle_busy: str | None = None
        self._fade_effect: QGraphicsOpacityEffect | None = None
        self._fade_anim: QPropertyAnimation | None = None
        #: Background library scan (None when no scan is running).
        self._scan_thread: _ScanThread | None = None

        self._build_ui()
        self._connect()
        self._register_shortcuts()
        self.setAcceptDrops(True)  # drop d'un mod n'importe où dans la fenêtre

        if self.settings.is_configured:
            self.refresh_library(show_error=True)
            self._history.push(STATE_HOME)  # l'accueil est l'état racine
            self._render(STATE_HOME)
            self._auto_sync()
        else:
            self._show_welcome()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        # ---- Top bar --------------------------------------------------- #
        self._back_btn = QPushButton(self)
        self._back_btn.setObjectName("IconButton")
        self._back_btn.setIcon(chevron_left_icon())
        self._back_btn.setIconSize(QSize(22, 22))
        self._back_btn.setToolTip(t("nav.back"))
        self._back_btn.setFixedWidth(44)
        self._back_btn.clicked.connect(self.back)

        self._forward_btn = QPushButton(self)
        self._forward_btn.setObjectName("IconButton")
        self._forward_btn.setIcon(chevron_right_icon())
        self._forward_btn.setIconSize(QSize(22, 22))
        self._forward_btn.setToolTip(t("nav.forward"))
        self._forward_btn.setFixedWidth(44)
        self._forward_btn.clicked.connect(self.forward)

        self._trash_btn = QPushButton(self)
        self._trash_btn.setObjectName("IconButton")
        self._trash_btn.setIcon(trash_icon())
        self._trash_btn.setIconSize(QSize(26, 26))
        self._trash_btn.setToolTip(t("trash.title"))
        self._trash_btn.setFixedWidth(44)
        self._trash_btn.clicked.connect(lambda: self.go((PAGE_TRASH, None)))

        #: Dedicated search page (v1.3.0) — the search experience lives on
        #: its own page; the top-bar field stays the quick-search entry.
        self._search_page_btn = QPushButton(self)
        self._search_page_btn.setObjectName("IconButton")
        self._search_page_btn.setIcon(search_icon())
        self._search_page_btn.setIconSize(QSize(20, 20))
        self._search_page_btn.setToolTip(t("search.page_title"))
        self._search_page_btn.setFixedWidth(44)
        self._search_page_btn.clicked.connect(lambda: self.go((PAGE_SEARCH, None)))

        #: Profiles page (v1.3.0).
        self._profiles_btn = QPushButton(self)
        self._profiles_btn.setObjectName("IconButton")
        self._profiles_btn.setIcon(users_icon())
        self._profiles_btn.setIconSize(QSize(22, 22))
        self._profiles_btn.setToolTip(t("profiles.title"))
        self._profiles_btn.setFixedWidth(44)
        self._profiles_btn.clicked.connect(lambda: self.go((PAGE_PROFILES, None)))

        #: Favorites page (v1.3.2) — a virtual folder of the favourite
        #: configurations (the files stay in their original category).
        self._favorites_btn = QPushButton(self)
        self._favorites_btn.setObjectName("IconButton")
        self._favorites_btn.setIcon(star_icon(filled=True, color="#fbbf24"))
        self._favorites_btn.setIconSize(QSize(20, 20))
        self._favorites_btn.setToolTip(t("favorites.title"))
        self._favorites_btn.setFixedWidth(44)
        self._favorites_btn.clicked.connect(lambda: self.go((PAGE_FAVORITES, None)))

        self._top_title = QLabel(t("nav.home"), self)
        self._top_title.setObjectName("PageTitle")

        self._search = QLineEdit(self)
        self._search.setPlaceholderText(t("search.placeholder"))
        self._search.setClearButtonEnabled(True)
        # Largeur rétrécissable : à fenêtre étroite le champ cède de la
        # place au lieu de chevaucher le bouton « Ajouter une arme ».
        self._search.setMinimumWidth(180)
        self._search.setMaximumWidth(420)
        self._search.setFixedHeight(34)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._run_search)

        self._add_weapon_btn = QPushButton(t("add_weapon.button"), self)
        self._add_weapon_btn.setObjectName("IconButton")
        self._add_weapon_btn.setIcon(plus_icon())
        self._add_weapon_btn.setIconSize(QSize(16, 16))
        self._add_weapon_btn.setToolTip(t("add_weapon.tooltip"))
        self._add_weapon_btn.clicked.connect(self._add_weapon)
        #: Espace réservé quand le bouton est masqué (v1.3.0 contextuel) :
        #: la géométrie de la barre supérieure reste identique, les tests
        #: responsive et la mise en page ne bougent pas d'un pixel.
        self._add_weapon_spacer = QWidget(self)
        self._add_weapon_spacer.setFixedWidth(self._add_weapon_btn.sizeHint().width())
        self._add_weapon_spacer.hide()

        self._settings_btn = QPushButton(self)
        self._settings_btn.setObjectName("IconButton")
        self._settings_btn.setIcon(gear_icon())
        self._settings_btn.setIconSize(QSize(22, 22))
        self._settings_btn.setToolTip(t("settings.title"))
        self._settings_btn.setFixedWidth(44)
        self._settings_btn.clicked.connect(lambda: self.go(STATE_SETTINGS))

        top_bar = QWidget(self)
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 10, 20, 10)
        top_layout.setSpacing(12)
        top_layout.addWidget(self._back_btn)
        top_layout.addWidget(self._forward_btn)
        top_layout.addWidget(self._trash_btn)
        top_layout.addWidget(self._search_page_btn)
        top_layout.addWidget(self._profiles_btn)
        top_layout.addWidget(self._favorites_btn)
        top_layout.addWidget(self._top_title, 1)
        top_layout.addWidget(self._search)
        top_layout.addWidget(self._add_weapon_btn)
        top_layout.addWidget(self._add_weapon_spacer)
        top_layout.addWidget(self._settings_btn)
        self._top_bar = top_bar

        # ---- Pages ------------------------------------------------------- #
        self._stack = QStackedWidget(self)
        self._welcome = WelcomeView(self)
        self._home = HomeView(self)
        self._browse = BrowseView(self)
        self._config = ConfigView(self)
        self._settings = SettingsView(self)
        self._trash_view = TrashView(self)
        self._search_view = SearchView(self)
        self._profiles_view = ProfilesView(self)
        self._favorites_view = FavoritesView(self)

        self._pages = {
            PAGE_WELCOME: self._welcome,
            PAGE_HOME: self._home,
            PAGE_BROWSE: self._browse,
            PAGE_CONFIG: self._config,
            PAGE_SETTINGS: self._settings,
            PAGE_TRASH: self._trash_view,
            PAGE_SEARCH: self._search_view,
            PAGE_PROFILES: self._profiles_view,
            PAGE_FAVORITES: self._favorites_view,
        }
        for page in self._pages.values():
            self._stack.addWidget(page)

        self._toast = Toast(self)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(top_bar)
        root_layout.addWidget(self._stack, 1)

    def _connect(self) -> None:
        self._home.category_clicked.connect(
            lambda node: self.go((PAGE_BROWSE, node))
        )
        self._home.config_clicked.connect(
            lambda item: self.go((PAGE_CONFIG, item))
        )
        self._home.settings_requested.connect(lambda: self.go(STATE_SETTINGS))
        self._home.edit_image_requested.connect(self._edit_image)
        self._home.files_dropped.connect(self._import_dropped)
        self._home.delete_requested.connect(self._delete_card)
        self._home.clear_configs_clicked.connect(self._clear_configs)
        self._home.order_changed.connect(self._save_card_order)
        self._home.card_order = self.settings.card_order
        self._home.toggle_activation_requested.connect(self._on_card_toggle_activation)
        self._home.set_activation_provider(self._card_activation_state)
        self._home.favorite_toggled.connect(self._toggle_favorite)
        self._home.set_favorites_provider(self._is_favorite)
        self._home.set_status_provider(self._smart_status_for)

        self._browse.order_changed.connect(self._save_card_order)
        self._browse.card_order = self.settings.card_order
        self._browse.toggle_activation_requested.connect(self._on_card_toggle_activation)
        self._browse.set_activation_provider(self._card_activation_state)
        self._browse.favorite_toggled.connect(self._toggle_favorite)
        self._browse.set_favorites_provider(self._is_favorite)
        self._browse.set_status_provider(self._smart_status_for)

        self._browse.folder_clicked.connect(
            lambda node: self.go((PAGE_BROWSE, node))
        )
        self._browse.config_clicked.connect(
            lambda item: self.go((PAGE_CONFIG, item))
        )
        self._browse.edit_image_requested.connect(self._edit_image)
        self._browse.delete_requested.connect(self._delete_card)
        self._browse.filters_changed.connect(self._on_filters_changed)
        self._browse.reset_clicked.connect(self._on_reset_filters)

        self._config.activate_clicked.connect(self._activate_current)
        self._config.deactivate_clicked.connect(self._deactivate_current)
        self._config.delete_clicked.connect(self._delete_current)
        self._config.open_source_clicked.connect(self._open_current_source)
        self._config.edit_image_clicked.connect(self._edit_current_image)
        self._config.add_obj_clicked.connect(self._add_current_obj)
        self._config.remove_obj_clicked.connect(self._remove_current_obj)
        self._config.verify_clicked.connect(self._verify_current)
        self._config.repair_clicked.connect(self._repair_current)

        self._trash_view.restore_clicked.connect(self._restore_trash_entry)
        self._trash_view.destroy_clicked.connect(self._destroy_trash_entry)
        self._trash_view.empty_clicked.connect(self._empty_trash)

        self._settings.fleasion_changed.connect(self._set_fleasion_dir)
        self._settings.library_changed.connect(self._set_library_dir)
        self._settings.test_clicked.connect(self._test_connection)
        self._settings.refresh_clicked.connect(lambda: self.refresh_library(show_error=True))
        self._settings.open_fleasion_clicked.connect(lambda: self._open_folder(self.settings.fleasion_dir))
        self._settings.open_library_clicked.connect(lambda: self._open_folder(self.settings.library_dir))
        self._settings.restore_clicked.connect(self._restore_backup)
        self._settings.backup_toggled.connect(self._set_backup_flag)
        self._settings.hot_activation_toggled.connect(self._set_hot_activation_flag)
        self._settings.language_changed.connect(self._set_language)
        self._settings.theme_changed.connect(self._set_theme)

        self._welcome.continue_clicked.connect(self._finish_welcome)
        self._search.textChanged.connect(self._on_search_text)

        # ---- Dedicated search page (v1.3.0) ----------------------------- #
        self._search_view.query_changed.connect(self._on_search_view_query)
        self._search_view.clear_clicked.connect(self._on_search_view_clear)
        self._search_view.config_clicked.connect(self._on_search_view_open)
        self._search_view.edit_image_requested.connect(self._edit_image)
        self._search_view.delete_requested.connect(self._delete_card)
        self._search_view.toggle_activation_requested.connect(self._on_card_toggle_activation)
        self._search_view.set_activation_provider(self._card_activation_state)
        self._search_view.favorite_toggled.connect(self._toggle_favorite)
        self._search_view.set_favorites_provider(self._is_favorite)
        self._search_view.set_status_provider(self._smart_status_for)
        self._search_view.filters_changed.connect(self._on_search_view_filters)
        self._search_view.reset_clicked.connect(self._on_search_view_reset)

        # ---- Profiles (v1.3.0) ----------------------------------------- #
        self._profiles_view.create_clicked.connect(self._create_profile)
        self._profiles_view.capture_clicked.connect(self._save_current_as_profile)
        self._profiles_view.import_into_clicked.connect(self._import_into_profile)
        self._profiles_view.import_clicked.connect(self._import_profile)
        self._profiles_view.apply_clicked.connect(self._apply_profile)
        self._profiles_view.edit_clicked.connect(self._edit_profile)
        self._profiles_view.delete_clicked.connect(self._delete_profile)
        self._profiles_view.export_clicked.connect(self._export_profile)

        # ---- Favorites page (v1.3.2) ---------------------------------- #
        self._favorites_view.config_clicked.connect(
            lambda item: self.go((PAGE_CONFIG, item))
        )
        self._favorites_view.edit_image_requested.connect(self._edit_image)
        self._favorites_view.delete_requested.connect(self._delete_card)
        self._favorites_view.toggle_activation_requested.connect(self._on_card_toggle_activation)
        self._favorites_view.set_activation_provider(self._card_activation_state)
        self._favorites_view.favorite_toggled.connect(self._toggle_favorite)
        self._favorites_view.set_favorites_provider(self._is_favorite)
        self._favorites_view.set_status_provider(self._smart_status_for)

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    def go(self, state: tuple[str, object]) -> None:
        # Explicit navigation always cancels a pending debounced search:
        # clicking a result/folder must never be clobbered by a search-state
        # re-apply that was already scheduled (timing-dependent in tests).
        self._search_timer.stop()
        self._history.push(state)
        self._render(state)

    def back(self) -> None:
        state = self._history.back()
        self._render(state if state is not None else STATE_HOME)

    def forward(self) -> None:
        """Revenir à l'état suivant dans l'historique (comme un navigateur)."""
        state = self._history.forward()
        if state is not None:
            self._render(state)

    def _render(self, state: tuple[str, object]) -> None:
        page_name, payload = state
        self._stack.setCurrentWidget(self._pages[page_name])

        if page_name == PAGE_HOME:
            self._home.set_library(self.root_node)
            self._top_title.setText(t("nav.home"))
        elif page_name == PAGE_BROWSE:
            if isinstance(payload, SearchState):
                self._show_search_state(payload)
            else:
                node = payload
                self._browse.set_node(node)
                self._top_title.setText(node.name)
        elif page_name == PAGE_CONFIG:
            item = payload
            self._current_item = item
            self._config.set_config(item)
            self._config.set_activation_state(self.fleasion.status(item))
            self._top_title.setText(item.name)
            self.recents.record(str(item.path), item.name)
        elif page_name == PAGE_SETTINGS:
            self._settings.set_paths(
                self.settings.fleasion_dir,
                self.settings.library_dir,
                self.settings.backup_before_overwrite,
                self.settings.hot_activation_enabled,
            )
            self._settings.set_language_value(self.settings.language)
            self._settings.set_theme_value(self.settings.theme, self.settings.custom_theme)
            self._top_title.setText(t("settings.title"))
        elif page_name == PAGE_TRASH:
            self._trash_view.set_entries(self.trash.list_entries())
            self._top_title.setText(t("trash.title"))
        elif page_name == PAGE_SEARCH:
            state = payload if isinstance(payload, SearchState) else None
            self._show_search_page(state)
        elif page_name == PAGE_PROFILES:
            self._show_profiles_page()
            self._top_title.setText(t("profiles.title"))
        elif page_name == PAGE_FAVORITES:
            self._show_favorites_page()
            self._top_title.setText(t("favorites.title"))
        # Boutons de navigation : désactivés quand aucune navigation possible.
        self._back_btn.setEnabled(self._history.can_go_back)
        self._forward_btn.setEnabled(self._history.can_go_forward)
        # « Ajouter une arme » : contextuel (v1.3.0) — visible seulement dans
        # une catégorie d'armes (Primary / Secondary / Melee / Utility), et
        # jamais dans Accueil, Recherche, catégories générales ou Profils.
        self._set_add_weapon_context()
        self._fade_in()

    def _set_add_weapon_context(self) -> None:
        """Masque/affiche « Ajouter une arme » selon le contexte.

        Le bouton n'apparaît que dans une catégorie d'armes réelle ou sur la
        page d'une configuration (on y reste dans le contexte de sa
        catégorie) ; jamais dans Accueil, Recherche, catégories générales ou
        Profils. Un spacer de même largeur garde la barre supérieure
        parfaitement stable (aucun décalage des boutons voisins)."""
        state = self._history.current()
        on_config_page = state is not None and state[0] == PAGE_CONFIG
        visible = on_config_page or self._current_category_folder() is not None
        self._add_weapon_btn.setVisible(visible)
        self._add_weapon_spacer.setVisible(not visible)
        self._add_weapon_spacer.setFixedWidth(
            self._add_weapon_btn.width() or self._add_weapon_btn.sizeHint().width()
        )

    def _show_welcome(self) -> None:
        self._top_bar.hide()
        self._stack.setCurrentWidget(self._welcome)
        self._fade_in()

    def _finish_welcome(self, fleasion: Path, library: Path) -> None:
        fleasion = normalize_path(fleasion)
        library = normalize_path(library)
        # The library must be a real, readable folder before anything is
        # saved or scanned — a bad path shows a clear error, never a crash.
        errors = validate_library_root(library)
        if errors:
            self._toast.show_message(
                errors[0] if errors else t("toast.scan_impossible"),
                KIND_ERROR,
                duration_ms=5000,
            )
            return
        self.settings.fleasion_dir = fleasion
        self.settings.library_dir = library
        self.settings.save()
        self._update_fleasion_manager()
        # Scan off the GUI thread: a large library must not freeze the
        # window on first launch. The welcome view stays clean (no top bar)
        # until the scan finishes and the home page takes over.
        self._start_async_scan(show_error=True, on_done=self._finish_first_scan)

    def _finish_first_scan(self, ok: bool) -> None:
        """Home is rendered once the first scan completes (or fails cleanly)."""
        self._top_bar.show()
        self._history.clear()
        self._history.push(STATE_HOME)
        self._render(STATE_HOME)
        if ok:
            self._auto_sync()

    def _fade_in(self) -> None:
        """Fade the page stack in (single effect, strictly managed).

        The effect is applied to the whole QStackedWidget instead of to the
        individual pages: putting a QGraphicsOpacityEffect on a page inside
        a QStackedWidget is a known source of "ghost" rendering on Windows
        (hidden pages can stay composited when their effect is replaced or
        removed mid-animation). Fading one stable widget and cancelling any
        previous fade before starting a new one keeps the animation without
        ever leaving a stale effect behind.
        """
        self._stop_fade()

        effect = QGraphicsOpacityEffect(self._stack)
        self._stack.setGraphicsEffect(effect)
        self._fade_effect = effect

        anim = QPropertyAnimation(effect, b"opacity", effect)
        self._fade_anim = anim
        anim.setDuration(160)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(self._fade_done)
        anim.start()

    def _stop_fade(self) -> None:
        """Cancel any running fade and remove its effect if still installed."""
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None
        if self._fade_effect is not None:
            if self._stack.graphicsEffect() is self._fade_effect:
                self._stack.setGraphicsEffect(None)
                self._stack.update()  # force a repaint: no stale pixels
            self._fade_effect = None

    def _fade_done(self) -> None:
        """Animation finished: remove the effect only if it is still current."""
        self._fade_anim = None
        if self._fade_effect is not None and self._stack.graphicsEffect() is self._fade_effect:
            self._stack.setGraphicsEffect(None)
            self._stack.update()
        self._fade_effect = None

    # ------------------------------------------------------------------ #
    # Library scanning
    # ------------------------------------------------------------------ #
    def refresh_library(self, show_error: bool = False) -> Node | None:
        library = self.settings.library_dir
        if not library:
            if show_error:
                self._toast.show_message(
                    t("toast.no_library"),
                    KIND_WARNING,
                )
            return None

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = scan_library(library)
        except Exception:  # noqa: BLE001 - a scan failure must never crash the UI
            logger.exception("Échec du scan de la bibliothèque : %s", library)
            if show_error:
                self._toast.show_message(
                    t("toast.scan_impossible"),
                    KIND_ERROR,
                )
            return None
        finally:
            QApplication.restoreOverrideCursor()

        if not result.ok:
            self.root_node = None
            if show_error:
                self._toast.show_message(
                    result.errors[0] if result.errors else t("toast.scan_impossible"),
                    KIND_ERROR,
                )
            return None

        self.root_node = result.node
        logger.info("Bibliothèque scannée : %s", library)
        return self.root_node

    def _start_async_scan(self, show_error: bool = False, on_done=None) -> None:
        """Scan the configured library in the background.

        The window stays responsive while a large library is being scanned;
        ``on_done(ok)`` (optional) runs on the GUI thread once the scan
        finishes. Used by the user-initiated folder-selection flows (settings
        browse + first-run welcome) — the startup scan stays synchronous
        because the rest of the window depends on its result immediately.
        """
        library = self.settings.library_dir
        if library is None:
            if show_error:
                self._toast.show_message(t("toast.no_library"), KIND_WARNING)
            if on_done is not None:
                on_done(False)
            return

        if self._scan_thread is not None and self._scan_thread.isRunning():
            # A scan is already running: never stack workers and never block
            # the GUI. The new path is already saved; a manual refresh (or
            # navigating home) re-reads it if the in-flight scan was stale.
            return

        thread = _ScanThread(library, self)
        self._scan_thread = thread
        thread.scanned.connect(
            lambda result: self._on_scan_finished(result, show_error, on_done)
        )
        thread.failed.connect(
            lambda exc: self._on_scan_error(exc, show_error, on_done)
        )
        thread.finished.connect(self._clear_scan_thread)
        thread.start()

    def _on_scan_finished(self, result, show_error: bool, on_done) -> None:
        """GUI-thread callback: apply the background scan result."""
        if not result.ok:
            self.root_node = None
            if show_error:
                self._toast.show_message(
                    result.errors[0] if result.errors else t("toast.scan_impossible"),
                    KIND_ERROR,
                    duration_ms=5000,
                )
            if on_done is not None:
                on_done(False)
            return
        self.root_node = result.node
        logger.info("Bibliothèque scannée : %s", self.settings.library_dir)
        if on_done is not None:
            on_done(True)

    def _on_scan_error(self, exc: Exception, show_error: bool, on_done) -> None:
        """GUI-thread callback: a background scan raised unexpectedly."""
        logger.error("Échec du scan en arrière-plan : %r", exc)
        self.root_node = None
        if show_error:
            self._toast.show_message(t("toast.scan_impossible"), KIND_ERROR, duration_ms=5000)
        if on_done is not None:
            on_done(False)

    def _clear_scan_thread(self) -> None:
        """Clean up the finished scan thread (called from its ``finished``)."""
        thread = self._scan_thread
        self._scan_thread = None
        if thread is not None:
            thread.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Wait for an in-flight scan so a running QThread is never destroyed."""
        thread = self._scan_thread
        if thread is not None and thread.isRunning():
            thread.wait(3000)
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # Activation
    # ------------------------------------------------------------------ #
    def _activate_current(self) -> None:
        """Bouton « Activer » de la page de configuration."""
        item = self._current_item
        if item is None:
            return
        result, real_state = self._run_activation(item)
        self._config.show_result(result, real_state)

    def _run_activation(self, item: ConfigItem) -> tuple[object, str]:
        """Flux d'activation partagé (page de configuration ET bouton des
        cartes) : exactement la même logique Fleasion, avec la même source
        de vérité et le même respect du paramètre hot_activation_enabled.

        Retourne ``(result, real_state)`` où ``real_state`` ne vaut
        ``"active"`` que si l'activation a réellement été confirmée.
        """
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured"),
                KIND_WARNING,
            )
            self.go(STATE_SETTINGS)
            return None, STATE_INACTIVE

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = self.fleasion.activate(
                item,
                self.file_manager,
                self.settings.backup_before_overwrite,
                restart=self.settings.hot_activation_enabled,
            )
        finally:
            QApplication.restoreOverrideCursor()

        # Source de vérité : le résultat intègre déjà la vérification réelle
        # (settings.json relu + confirmation par le log de Fleasion après
        # redémarrage). « ACTIF » n'est affiché QUE si l'activation a été
        # confirmée — jamais de faux succès, même si settings.json contient
        # le nom (Fleasion a pu ne pas recharger).
        real_state = (
            STATE_ACTIVE
            if result.selected
            else STATE_COPIED
            if result.needs_manual_selection and result.ok
            else STATE_INACTIVE
        )

        if real_state == STATE_ACTIVE:
            logger.info("Configuration activée et sélectionnée : %s", item.path)
            self._toast.show_message(
                t("toast.activated", summary=result.summary()), KIND_SUCCESS
            )
        elif result.ok:
            if result.errors:
                # Fichiers copiés mais la sélection n'a pas pu être
                # confirmée : erreur claire, jamais de faux succès.
                logger.info("Activation non confirmée : %s", result.errors)
                self._toast.show_message(
                    "✘ " + "\n".join(result.errors),
                    KIND_ERROR,
                    duration_ms=4500,
                )
            else:
                logger.info("Configuration copiée (sélection manuelle) : %s", item.path)
                self._toast.show_message(
                    t("toast.copied_manual"),
                    KIND_WARNING,
                    duration_ms=4000,
                )
        else:
            logger.warning("Échec d'activation : %s", result.errors)
            self._toast.show_message(
                t("toast.activation_failed"), KIND_ERROR, duration_ms=4000
            )
        return result, real_state

    def _open_current_source(self) -> None:
        item = self._current_item
        if item is not None:
            self._open_folder(item.path.parent)

    # ------------------------------------------------------------------ #
    # Deactivation / deletion
    # ------------------------------------------------------------------ #
    def _deactivate_current(self) -> None:
        """Bouton « Désactiver » de la page de configuration."""
        item = self._current_item
        if item is None:
            return
        outcome, real_state = self._run_deactivation(item)
        self._config.show_deactivate_result(outcome)
        self._config.set_activation_state(real_state)

    def _run_deactivation(self, item: ConfigItem) -> tuple[object, str]:
        """Flux de désactivation partagé (page de configuration ET bouton des
        cartes) : même logique, même source de vérité, même respect du
        paramètre hot_activation_enabled. Retourne ``(outcome, real_state)``.
        """
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured"),
                KIND_WARNING,
            )
            return None, STATE_INACTIVE

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            outcome = self.fleasion.deactivate(
                item,
                self.file_manager,
                self.settings.backup_before_overwrite,
                restart=self.settings.hot_activation_enabled,
            )
            # Source de vérité : relire l'état réel de Fleasion après la
            # désactivation. « Désactivé » n'est affiché que si la relecture
            # confirme que Fleasion ne considère plus la configuration active.
            real_state = self.fleasion.status(item)
        finally:
            QApplication.restoreOverrideCursor()

        if outcome.ok and real_state != STATE_ACTIVE:
            logger.info("Configuration désactivée : %s", item.name)
            self._toast.show_message(
                t("toast.deactivated", summary=outcome.summary()), KIND_SUCCESS
            )
        elif outcome.ok:
            # Les fichiers ont été retirés mais Fleasion considère encore la
            # configuration comme active : pas de faux succès.
            logger.warning(
                "Désactivation non confirmée par Fleasion : %s", item.name
            )
            self._toast.show_message(
                t("toast.still_active"),
                KIND_ERROR,
                duration_ms=4000,
            )
        else:
            logger.warning("Désactivation : %s", outcome.errors)
            first = (
                outcome.errors[0]
                if outcome.errors
                else t("toast.deactivation_partial")
            )
            self._toast.show_message(
                f"✘ {first}", KIND_ERROR, duration_ms=4500
            )
        return outcome, real_state

    # ------------------------------------------------------------------ #
    # Activation directe depuis les cartes (bouton ▶ / ×)
    # ------------------------------------------------------------------ #
    def _card_activation_state(self, item: ConfigItem) -> str:
        """État réel d'une carte pour initialiser son bouton (source de
        vérité : Fleasion, via status())."""
        return self.fleasion.status(item)

    def _smart_status_for(self, item: ConfigItem) -> str:
        """Statut intelligent de la carte (v1.3.0, câblé v1.3.1) : basé sur
        les données réelles — jamais « Prête » si une dépendance obligatoire
        manque.

        * active dans Fleasion → « Active » ;
        * JSON invalide → « Erreur » ;
        * dépendance OBJ/MP3 manquante → « Incomplète » ;
        * sinon → « Prête ».

        L'analyse JSON est mise en cache (chemin + mtime + taille) ;
        l'existence des fichiers est vérifiée à chaque appel (fraîche).
        """
        from app.config_analysis import analyze_item

        if self.fleasion.status(item) == STATE_ACTIVE:
            return STATUS_ACTIVE
        analysis = analyze_item(item)
        if not analysis.valid:
            return STATUS_ERROR
        if analysis.incomplete:
            return STATUS_INCOMPLETE
        return STATUS_READY

    def _on_card_toggle_activation(self, item: ConfigItem) -> None:
        """Clic sur le bouton ▶ / × d'une carte : déclenche EXACTEMENT la
        même logique que les boutons de la page de configuration (activation
        ou désactivation selon l'état réel, avec hot_activation_enabled)."""
        if item is None:
            return
        key = str(item.path)
        if self._card_toggle_busy == key:
            return  # opération déjà en cours : pas de double activation

        current = self.fleasion.status(item)
        self._card_toggle_busy = key
        self._card_grid_set_busy(key, True)
        real_state = current
        try:
            if current == STATE_ACTIVE:
                outcome, real_state = self._run_deactivation(item)
                if (
                    self._current_item is not None
                    and self._current_item.path == item.path
                    and self._stack.currentWidget() is self._config
                ):
                    self._config.show_deactivate_result(outcome)
                    self._config.set_activation_state(real_state)
            else:
                result, real_state = self._run_activation(item)
                if (
                    self._current_item is not None
                    and self._current_item.path == item.path
                    and self._stack.currentWidget() is self._config
                ):
                    self._config.show_result(result, real_state)
        finally:
            self._card_toggle_busy = None
            self._card_grid_set_busy(key, False)
            # Le bouton ne passe en rouge/bleu que selon l'état réel confirmé.
            self._card_grid_set_state(key, real_state)

    def _current_grid(self):
        """La grille visible (accueil, parcours, recherche ou favoris) —
        ``None`` ailleurs."""
        widget = self._stack.currentWidget()
        if widget is self._home:
            return self._home._grid
        if widget is self._browse:
            return self._browse._grid
        if widget is self._search_view:
            return self._search_view._grid
        if widget is self._favorites_view:
            return self._favorites_view._grid
        return None

    def _card_grid_set_busy(self, key: str, busy: bool) -> None:
        grid = self._current_grid()
        if grid is not None:
            grid.set_card_toggle_busy(key, busy)

    def _card_grid_set_state(self, key: str, state: str) -> None:
        grid = self._current_grid()
        if grid is not None:
            grid.set_card_activation_state(key, state)

    def _delete_current(self) -> None:
        """Supprimer : désactive puis déplace vers la corbeille (récupérable)."""
        item = self._current_item
        if item is None:
            return
        if not self._confirm_delete(item):
            return

        # 1. Retirer de l'usage actif (sélection + copies). Réversible.
        deact = self.fleasion.deactivate(
            item, self.file_manager, self.settings.backup_before_overwrite
        )
        if deact.errors:
            self._toast.show_message(
                t("toast.delete_cancelled", errors="\n".join(deact.errors)),
                KIND_ERROR,
                duration_ms=4500,
            )
            return

        # 2. Déplacer vers la corbeille (les fichiers ne sont jamais
        # supprimés, seulement stockés hors de la bibliothèque).
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.trash.delete_item(item)
        except TrashError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        finally:
            QApplication.restoreOverrideCursor()

        logger.info("Configuration déplacée vers la corbeille : %s", item.name)
        self._toast.show_message(
            t("toast.moved_to_trash", name=item.name),
            KIND_SUCCESS,
            duration_ms=4000,
        )
        if self._history.current() == (PAGE_CONFIG, item):
            self._history.back()  # l'entrée config est abandonnée au resync
        self._current_item = None
        self._refresh_and_resync()

    def _confirm_delete(self, item: ConfigItem) -> bool:
        """Confirmation avant suppression (déplacement vers la corbeille)."""
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.delete_title"))
        box.setIcon(QMessageBox.Warning)
        box.setText(t("confirm.delete_text", name=item.name))
        box.setInformativeText(t("confirm.delete_info"))
        delete_btn = box.addButton(
            t("confirm.delete"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is delete_btn

    # ------------------------------------------------------------------ #
    # Card deletion (clic droit sur une carte)
    # ------------------------------------------------------------------ #
    def _delete_card(self, target: Node | ConfigItem) -> None:
        """« Supprimer » (menu clic droit d'une carte) : vérifie le chemin,
        demande confirmation, puis déplace l'élément vers la **Corbeille
        interne de l'application** (jamais de suppression définitive) et
        rafraîchit."""
        if self.settings.library_dir is None:
            self._toast.show_message(
                t("toast.no_library"),
                KIND_WARNING,
            )
            return
        if isinstance(target, Node):
            path = target.path
            count = _count_items(target)
            is_folder = True
        elif isinstance(target, ConfigItem):
            path = target.path
            count = 1
            is_folder = target.is_folder
        else:
            return

        error = self._check_safe_delete(path)
        if error is not None:
            self._toast.show_message(error, KIND_ERROR, duration_ms=4500)
            return
        if not self._confirm_card_delete(path, is_folder, count):
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if isinstance(target, ConfigItem):
                self.trash.delete_item(target)
            else:
                self.trash.delete_path(path, name=path.name)
        except TrashError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        finally:
            QApplication.restoreOverrideCursor()

        logger.info("Élément déplacé vers la Corbeille : %s", path)
        self._toast.show_message(
            t("toast.moved_to_app_trash", name=path.name),
            KIND_SUCCESS,
            duration_ms=4000,
        )
        self._drop_states_for(path)
        self._refresh_and_resync()

    def _check_safe_delete(self, path: Path) -> str | None:
        """Vérifications de sécurité avant suppression. Retourne un message
        d'erreur, ou ``None`` quand le chemin peut être déplacé vers la
        Corbeille."""
        library = self.settings.library_dir
        if library is None:
            return t("toast.no_library")
        try:
            resolved = path.resolve()
            library_resolved = library.resolve()
        except OSError:
            return t("main_window.path_unreadable", path=path)
        if not resolved.exists():
            return t("main_window.item_not_found", path=path)
        # La racine de la bibliothèque n'est jamais supprimée.
        if resolved == library_resolved:
            return t("main_window.root_refused")
        # Tout doit se trouver réellement à l'intérieur de la bibliothèque.
        try:
            resolved.relative_to(library_resolved)
        except ValueError:
            return t("main_window.outside_refused")
        # Défense en profondeur : jamais de suppression dans les dossiers
        # protégés (Fleasion, caches, sauvegardes, corbeille interne).
        for base in (
            self.settings.fleasion_dir,
            image_cache_dir(),
            obj_cache_dir(),
            backups_dir(),
            trash_dir(),
        ):
            if base is None:
                continue
            try:
                resolved.relative_to(Path(base).resolve())
                return t("main_window.protected_refused", path=path)
            except ValueError:
                pass
        return None

    def _confirm_card_delete(self, path: Path, is_folder: bool, count: int) -> bool:
        """Confirmation avant déplacement vers la Corbeille de l'application."""
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.delete_title"))
        box.setIcon(QMessageBox.Warning)
        box.setText(t("confirm.delete_text", name=path.name))
        if is_folder and count > 1:
            info = t("confirm.card_delete_many", count=count)
        elif is_folder:
            info = t("confirm.card_delete_one_folder")
        else:
            info = t("confirm.card_delete_one_config")
        box.setInformativeText(t("confirm.card_delete_info", info=info))
        delete_btn = box.addButton(
            t("confirm.delete"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is delete_btn

    def _drop_states_for(self, path: Path) -> None:
        """Retire de l'historique les états qui référencent l'élément
        supprimé (page config ou dossier ouvert) : aucune carte fantôme ni
        page orpheline après la suppression."""
        deleted = Path(path).resolve()
        kept: list = []
        for page, payload in self._history.states:
            item_path = getattr(payload, "path", None)
            if item_path is not None:
                try:
                    if Path(item_path).resolve() == deleted:
                        continue
                except OSError:
                    pass
            kept.append((page, payload))
        if len(kept) == len(self._history.states):
            return
        new_history = NavigationHistory()
        for state in kept:
            new_history.push(state)
        self._history = new_history

    # ------------------------------------------------------------------ #
    # Clear Configs (configurations du dossier actif de Fleasion)
    # ------------------------------------------------------------------ #
    def _save_card_order(self, folder_key: str, keys: list[str]) -> None:
        """Persist the drag & drop card order of one folder. Display-only:
        only settings.json is written, never the library files."""
        self.settings.set_card_order(folder_key, keys)
        self.settings.save()

    def _clear_configs(self) -> None:
        """« Clear Configs » (bas droite de l'accueil) : sélectionner des
        configurations présentes dans le dossier actif de Fleasion, puis les
        déplacer vers la **Corbeille interne de l'application** (jamais de
        suppression définitive) avec backup de settings.json."""
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured"),
                KIND_WARNING,
            )
            return
        configs = self.fleasion.list_configs()
        if not configs:
            self._toast.show_message(
                t("toast.no_fleasion_configs"),
                KIND_WARNING,
            )
            return
        dialog = ClearConfigsDialog(configs, self)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.selected
        if not selected:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            outcome = self.fleasion.clear_configs(selected, trash=self.trash)
        finally:
            QApplication.restoreOverrideCursor()

        if outcome.errors:
            logger.warning("Clear Configs : %s", outcome.errors)
            self._toast.show_message(
                t("toast.clear_configs_error", errors="\n".join(outcome.errors)),
                KIND_ERROR,
                duration_ms=5000,
            )
        else:
            logger.info("Clear Configs : %s", outcome.summary())
            self._toast.show_message(
                t("toast.clear_configs_ok", summary=outcome.summary()),
                KIND_SUCCESS,
                duration_ms=4000,
            )
            self._refresh_and_resync()

    # ------------------------------------------------------------------ #
    # Trash (corbeille)
    # ------------------------------------------------------------------ #
    def _restore_trash_entry(self, entry: TrashEntry) -> None:
        """Restaurer : remet les fichiers à leur emplacement d'origine.

        Si la destination existe déjà, l'utilisateur choisit explicitement
        entre Remplacer, Garder les deux ou Annuler — jamais d'écrasement
        silencieux. La restauration est limitée aux dossiers autorisés
        (bibliothèque et configs Fleasion)."""
        mode = "replace"
        if self.trash.destination_exists(entry):
            mode = self._ask_restore_conflict(entry)
            if mode is None:
                return
        allowed = [
            root
            for root in (self.settings.library_dir, self.fleasion.detect().config_dir)
            if root is not None
        ]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            restored = self.trash.restore(
                entry,
                self.settings.backup_before_overwrite,
                self.backup_manager,
                mode=mode,
                allowed_roots=allowed,
            )
        except TrashError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._trash_view.set_entries(self.trash.list_entries())
        self.refresh_library(show_error=False)
        logger.info("Élément restauré depuis la corbeille : %s", entry.name)
        self._toast.show_message(
            t("toast.restored", name=entry.name, path=restored), KIND_SUCCESS
        )

    def _ask_restore_conflict(self, entry: TrashEntry) -> str | None:
        """Un élément existe déjà à l'emplacement d'origine : l'utilisateur
        choisit « Remplacer », « Garder les deux » ou « Annuler ».
        Retourne le mode de restauration, ou ``None`` pour annuler."""
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.restore_conflict_title"))
        box.setIcon(QMessageBox.Warning)
        box.setText(t("confirm.restore_conflict_text", name=entry.name))
        box.setInformativeText(t("confirm.restore_conflict_info"))
        replace_btn = box.addButton(
            t("confirm.replace"), QMessageBox.ButtonRole.AcceptRole
        )
        keep_btn = box.addButton(
            t("confirm.keep_both"), QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is replace_btn:
            return "replace"
        if clicked is keep_btn:
            return "keep_both"
        return None

    def _destroy_trash_entry(self, entry: TrashEntry) -> None:
        """Supprimer définitivement un élément de la corbeille (confirmé)."""
        if not self._confirm_destroy(1, entry.name):
            return
        self.trash.destroy(entry)
        self._trash_view.set_entries(self.trash.list_entries())
        logger.info("Élément supprimé définitivement : %s", entry.name)
        self._toast.show_message(t("toast.destroyed"), KIND_SUCCESS)

    def _empty_trash(self) -> None:
        """Vider la corbeille (confirmé)."""
        entries = self.trash.list_entries()
        if not entries:
            self._toast.show_message(t("toast.trash_empty"), KIND_WARNING)
            return
        if not self._confirm_destroy(len(entries), None):
            return
        self.trash.empty()
        self._trash_view.set_entries(self.trash.list_entries())
        logger.info("Corbeille vidée (%d éléments)", len(entries))
        self._toast.show_message(t("toast.trash_emptied"), KIND_SUCCESS)

    def _confirm_destroy(self, count: int, name: str | None) -> bool:
        """Confirmation forte pour une suppression définitive (case à cocher)."""
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.destroy_title"))
        box.setIcon(QMessageBox.Critical)
        if name:
            box.setText(t("confirm.destroy_text", name=name))
        else:
            suffix = "s" if count != 1 else ""
            box.setText(t("confirm.destroy_text_count", count=count, s=suffix))
        box.setInformativeText(t("confirm.destroy_info"))
        checkbox = QCheckBox(t("confirm.destroy_checkbox"), box)
        box.setCheckBox(checkbox)
        destroy_btn = box.addButton(
            t("confirm.destroy_button"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        destroy_btn.setEnabled(False)
        checkbox.toggled.connect(destroy_btn.setEnabled)
        box.exec()
        return box.clickedButton() is destroy_btn and checkbox.isChecked()

    # ------------------------------------------------------------------ #
    # Synchronisation
    # ------------------------------------------------------------------ #
    def _sync_current(self) -> None:
        """« Synchroniser » : compare l'état déclaré avec les fichiers réels
        et corrige les différences pour la configuration courante."""
        item = self._current_item
        if item is None:
            return
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured"),
                KIND_WARNING,
            )
            return

        engine = SyncEngine(self.fleasion, self.file_manager, self.backup_manager)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = engine.sync_item(item, self.settings.backup_before_overwrite)
        finally:
            QApplication.restoreOverrideCursor()

        self._config.show_sync_report(report)
        self._config.set_activation_state(self.fleasion.status(item))
        if report.errors:
            logger.warning("Synchronisation : %s", report.errors)
            self._toast.show_message(
                t("toast.sync_partial"), KIND_ERROR, duration_ms=4000
            )
        else:
            logger.info("Synchronisation : %s", report.summary())
            self._toast.show_message(
                t("toast.synced", summary=report.summary()), KIND_SUCCESS
            )

    def _auto_sync(self) -> None:
        """Synchronisation au démarrage (conservatrice).

        Re-copie les configurations sélectionnées dans Fleasion dont les
        fichiers ont disparu du dossier actif. Ne retire jamais rien.
        """
        if self.root_node is None or not self.settings.fleasion_dir:
            return
        try:
            engine = SyncEngine(self.fleasion, self.file_manager, self.backup_manager)
            report = engine.auto_sync(walk_configs(self.root_node))
        except Exception:  # pragma: no cover - defensive: never block startup
            logger.exception("Synchronisation au démarrage échouée")
            return
        if report.copied:
            logger.info("Synchronisation au démarrage : %s", report.summary())
            self._toast.show_message(
                t("toast.startup_synced", summary=report.summary()),
                KIND_SUCCESS,
                duration_ms=4000,
            )
        elif report.errors:
            logger.warning("Synchronisation au démarrage : %s", report.errors)
            self._toast.show_message(
                t("toast.startup_sync_errors", errors="\n".join(report.errors[:3])),
                KIND_ERROR,
                duration_ms=4000,
            )

    # ------------------------------------------------------------------ #
    # Image management
    # ------------------------------------------------------------------ #
    def _edit_current_image(self) -> None:
        """Open the image dialog for the current configuration."""
        if self._current_item is not None:
            self._edit_image(self._current_item)

    def _edit_image(self, target: Node | ConfigItem) -> None:
        """Open the image dialog for any card (folder or configuration),
        then refresh the library so the card shows the new image."""
        dialog = ImageDialog(target, self.image_manager, self)
        dialog.exec()
        self._refresh_and_resync()

    def _refresh_and_resync(self) -> None:
        """Re-scan the library and re-resolve the current state so cards and
        previews reflect any image change."""
        self.refresh_library(show_error=False)
        if self.root_node is not None and self._history:
            resynced = []
            for page, payload in self._history.states:
                if page == PAGE_BROWSE and isinstance(payload, Node):
                    found = find_node(self.root_node, payload.path)
                    resynced.append((page, found if found is not None else payload))
                elif page == PAGE_CONFIG and isinstance(payload, ConfigItem):
                    found = find_config(self.root_node, payload.path)
                    resynced.append((page, found if found is not None else payload))
                else:
                    resynced.append((page, payload))
            # La pile avant est volontairement abandonnée : ses payloads
            # pourraient référencer d'anciens objets de l'arbre.
            new_history = NavigationHistory()
            for state in resynced:
                new_history.push(state)
            self._history = new_history
            current = self._history.current()
            self._render(current if current is not None else STATE_HOME)
        elif self._history:
            current = self._history.current()
            self._render(current if current is not None else STATE_HOME)
        else:
            if not self._history:
                self._history.push(STATE_HOME)
            self._render(STATE_HOME)

    def _open_folder(self, path: Path | None) -> None:
        if not path or not path.exists():
            self._toast.show_message(t("toast.folder_not_found"), KIND_WARNING)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------ #
    # OBJ management
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # Mod import
    # ------------------------------------------------------------------ #
    def _import_dropped(self, paths: list[Path]) -> None:
        """Fichiers déposés dans la zone de drop : chacun passe par le flux
        d'import normal (analyse → prévisualisation → confirmation)."""
        if self.settings.library_dir is None:
            self._toast.show_message(
                t("toast.no_library"),
                KIND_WARNING,
            )
            return
        for path in paths:
            self._start_mod_import(path)

    def _start_mod_import(self, source: Path) -> None:
        """Analyse puis prévisualisation ; installe après confirmation."""
        try:
            analysis = analyze_source(source)
        except ModImportError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4500)
            return
        try:
            dialog = ImportDialog(
                analysis,
                self.settings.library_dir,
                self,
                library_node=self.root_node,
            )
            if dialog.exec() != QDialog.Accepted:
                return
            self._apply_install_plan(dialog.build_plan())
        finally:
            cleanup_staging(analysis)

    def _add_weapon(self) -> None:
        """« Ajouter une arme » : crée le dossier arme dans la **catégorie
        actuellement parcourue** — le contexte de navigation détermine le
        dossier parent exact. Aucune catégorie n'est jamais créée et, hors
        d'une catégorie d'armes, l'application ne devine pas : elle demande
        d'abord de sélectionner la catégorie."""
        if self.settings.library_dir is None:
            self._toast.show_message(
                t("toast.no_library"),
                KIND_WARNING,
            )
            return
        category_folder = self._current_category_folder()
        if category_folder is None:
            self._toast.show_message(
                t("toast.select_category_first"),
                KIND_WARNING,
                duration_ms=4500,
            )
            return
        try:
            context = str(category_folder.relative_to(self.settings.library_dir))
        except ValueError:
            context = str(category_folder)

        dialog = AddWeaponDialog(self, context_label=context)
        if dialog.exec() != QDialog.Accepted:
            return
        name = safe_folder_name(dialog.weapon)
        if not name:
            self._toast.show_message(
                t("toast.invalid_weapon_name"), KIND_ERROR, duration_ms=4000
            )
            return

        target = category_folder / name
        if target.exists():
            self._toast.show_message(
                t("toast.weapon_exists", name=name),
                KIND_WARNING,
                duration_ms=4000,
            )
            return
        category = category_of_path(category_folder)
        created = ensure_weapon_folder(
            self.settings.library_dir, category or "", name, parent=category_folder
        )
        if created is None:
            self._toast.show_message(
                t("toast.weapon_folder_failed"), KIND_ERROR, duration_ms=4000
            )
            return
        logger.info("Arme ajoutée : %s -> %s", name, created)
        self._toast.show_message(
            t("toast.weapon_added", name=name, context=context),
            KIND_SUCCESS,
        )
        self._refresh_and_resync()

    def _current_category_folder(self) -> Path | None:
        """Le dossier catégorie réel du contexte de navigation courant.

        Parcourt l'état affiché (dossier ou configuration ouverte) et remonte
        au dossier de catégorie (Primary / Secondary / Melee / Utility) le
        plus profond de son chemin. Retourne ``None`` hors d'une catégorie
        d'armes : l'appelant ne doit alors pas deviner.
        """
        if self.settings.library_dir is None:
            return None
        state = self._history.current()
        if state is None:
            return None
        page, payload = state
        if page == PAGE_BROWSE and isinstance(payload, Node):
            path = payload.path
        elif page == PAGE_CONFIG and isinstance(payload, ConfigItem):
            path = payload.path.parent
        else:
            return None
        return category_folder_in_path(self.settings.library_dir, path)

    def _apply_install_plan(self, plan) -> None:
        """Installer le mod (copie dans la bibliothèque) puis rafraîchir."""
        try:
            destination = install_mod(plan, self.backup_manager)
        except ModImportError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4500)
            return
        logger.info("Mod installé : %s -> %s", plan.name, destination)
        self._toast.show_message(
            t("toast.mod_installed", name=plan.name, destination=destination),
            KIND_SUCCESS,
            duration_ms=4000,
        )
        self.refresh_library(show_error=False)

    def _add_current_obj(self) -> None:
        """Pick a local .obj and associate it with the current config."""
        item = self._current_item
        if item is None:
            return
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self,
            t("main_window.choose_obj"),
            str(item.path.parent),
            t("main_window.obj_filter"),
        )
        if not path:
            return
        try:
            self.obj_manager.import_local(item, Path(path))
        except ObjError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(t("toast.obj_associated"), KIND_SUCCESS)
        self._refresh_and_resync()

    def _remove_current_obj(self) -> None:
        item = self._current_item
        if item is None:
            return
        self.obj_manager.remove(item)
        self._toast.show_message(t("toast.obj_removed"), KIND_SUCCESS)
        self._refresh_and_resync()

    # ------------------------------------------------------------------ #
    # Settings actions
    # ------------------------------------------------------------------ #
    def _set_fleasion_dir(self, path: Path) -> None:
        # The Fleasion config folder may not exist yet (it is created on the
        # first activation): only normalize the path, never require it.
        self.settings.fleasion_dir = normalize_path(path)
        self.settings.save()
        self._update_fleasion_manager()

    def _set_library_dir(self, path: Path) -> None:
        # 1. Normalize, then validate BEFORE saving: a bad path shows a clear
        #    error and leaves the previous (working) configuration intact.
        normalized = normalize_path(path)
        errors = validate_library_root(normalized)
        if errors:
            self._toast.show_message(
                errors[0] if errors else t("toast.scan_impossible"),
                KIND_ERROR,
                duration_ms=5000,
            )
            # Revert the on-screen label to the still-saved value so the UI
            # never shows a path that was not accepted.
            self._settings.set_paths(
                self.settings.fleasion_dir,
                self.settings.library_dir,
                self.settings.backup_before_overwrite,
                self.settings.hot_activation_enabled,
            )
            return
        # 2. Save the validated path, then 3. scan off the GUI thread.
        self.settings.library_dir = normalized
        self.settings.save()
        self._start_async_scan(show_error=True)

    def _update_fleasion_manager(self) -> None:
        self.fleasion = FleasionManager(self.settings.fleasion_dir, self.backup_manager)

    def _set_backup_flag(self, enabled: bool) -> None:
        self.settings.backup_before_overwrite = enabled
        self.settings.save()

    def _set_hot_activation_flag(self, enabled: bool) -> None:
        """L'activation à chaud (redémarrage de Fleasion) est un choix de
        l'utilisateur, persisté dans settings.json. Le code du mécanisme
        existe toujours — cette option empêche seulement son déclenchement."""
        self.settings.hot_activation_enabled = enabled
        self.settings.save()

    def _test_connection(self) -> None:
        messages: list[str] = []
        ok = True

        library = self.settings.library_dir
        if library is None:
            messages.append(t("main_window.test_library_unset"))
            ok = False
        elif not library.exists():
            messages.append(t("main_window.test_library_missing", path=library))
            ok = False
        elif not library.is_dir():
            messages.append(t("main_window.test_library_not_dir", path=library))
            ok = False
        else:
            node = self.refresh_library(show_error=False)
            if node is None:
                messages.append(t("main_window.test_library_unreadable"))
                ok = False
            else:
                total = _count_items(node)
                messages.append(
                    t("main_window.test_library_ok", count=total)
                )

        fleasion = self.settings.fleasion_dir
        if fleasion is None:
            messages.append(t("main_window.test_fleasion_unset"))
            ok = False
        elif fleasion.exists() and fleasion.is_dir():
            messages.append(t("main_window.test_fleasion_ok", path=fleasion))
        else:
            messages.append(t("main_window.test_fleasion_missing"))
            ok = False if not fleasion.parent.exists() else ok

        text = "\n".join(messages)
        self._toast.show_message(text, KIND_SUCCESS if ok else KIND_WARNING, duration_ms=4500)

    def _restore_backup(self, backup: BackupInfo) -> None:
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured_short"), KIND_WARNING
            )
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            errors = self.fleasion.restore_backup(backup)
        finally:
            QApplication.restoreOverrideCursor()
        if errors:
            self._toast.show_message(
                t("toast.restore_partial", errors="\n".join(errors)),
                KIND_ERROR,
                duration_ms=4500,
            )
        else:
            count = backup.file_count
            suffix = "s" if count != 1 else ""
            self._toast.show_message(
                t("toast.backup_restored", count=count, s=suffix),
                KIND_SUCCESS,
            )

    # ------------------------------------------------------------------ #
    # Search + filters
    # ------------------------------------------------------------------ #
    def _on_search_text(self, text: str) -> None:
        self._search_timer.start()

    def _run_search(self) -> None:
        """Debounced: apply the current query + filters as a navigable state."""
        state = self._current_search_state()
        if state is None:
            self._maybe_leave_search()
            return
        self._set_search_state(state)

    def _set_search_state(self, state: SearchState) -> None:
        """Show a search state: update it in place when already searching,
        otherwise push a new navigable state (which clears forward)."""
        page = PAGE_SEARCH if self._stack.currentWidget() is self._search_view else PAGE_BROWSE
        current = self._history.current()
        if current is not None and isinstance(current[1], SearchState):
            self._history.replace_current((page, state))
        else:
            self._history.push((page, state))
        self._render((page, state))

    def _maybe_leave_search(self) -> None:
        """The search field is empty/short: leave the search state when we
        are on one (the state is dropped, not kept in the forward stack)."""
        current = self._history.current()
        if current is not None and isinstance(current[1], SearchState):
            self._history.drop_current()
            self._render(self._history.current() or STATE_HOME)

    def _show_search_state(self, state: SearchState) -> None:
        """Render a search state (fresh or restored by back/forward)."""
        if self._search.text() != state.query:
            self._search.blockSignals(True)
            self._search.setText(state.query)
            self._search.blockSignals(False)
        self._browse.set_filters(state.category, state.status)
        results = self._search_results(state)
        self._browse.show_search_results(results, state.query, self.root_node)
        self._top_title.setText(t("nav.search", query=state.query))

    def _search_results(self, state: SearchState) -> list:
        """Query + category + status filters, in-memory (no rescan)."""
        if self.root_node is None:
            return []
        if state.status and state.status != STATUS_ALL:
            engine = SyncEngine(self.fleasion, self.file_manager, self.backup_manager)
            return run_search(self.root_node, state, engine)
        return run_search(self.root_node, state)

    def _on_filters_changed(self) -> None:
        """A filter changed while searching: update the current state."""
        state = self._current_search_state()
        if state is None:
            return
        self._set_search_state(state)

    def _on_reset_filters(self) -> None:
        """« Réinitialiser » : remove the filters, keep the query."""
        self._browse.reset_filters()
        state = self._current_search_state()
        if state is not None:
            self._set_search_state(state)

    # ------------------------------------------------------------------ #
    # Dedicated search page (v1.3.0)
    # ------------------------------------------------------------------ #
    def _show_search_page(self, state: SearchState | None = None) -> None:
        """Render the dedicated search page. Without a query the page shows
        « Récents »; with one it shows the live results (same engine as the
        top-bar quick search — no second logic).

        ``state`` may come from the navigation history (back/forward);
        otherwise the current input + filters are used."""
        self._top_title.setText(t("search.page_title"))
        if state is None:
            state = self._current_search_state()
        if state is None:
            # Empty query: recents mode.
            self._search_view.set_query("")
            self._search_view.show_recents(self.recents.entries())
            return
        self._search_view.set_query(state.query)
        self._search_view.set_filters(state.category, state.status, state.favorites)
        results = self._search_view_results(state)
        self._search_view.show_results(results, state.query, self.root_node)

    def _search_view_results(self, state: SearchState) -> list:
        """Same engine as the quick search, plus the favorites filter."""
        if self.root_node is None:
            return []
        favorite_keys = set(self.settings.favorites)
        if state.status and state.status != STATUS_ALL:
            engine = SyncEngine(self.fleasion, self.file_manager, self.backup_manager)
            return run_search(self.root_node, state, engine, favorite_keys)
        return run_search(self.root_node, state, favorite_keys=favorite_keys)

    def _on_search_view_query(self, text: str) -> None:
        """Debounced: the big bar of the search page changed."""
        self._search.blockSignals(True)
        self._search.setText(text)
        self._search.blockSignals(False)
        self._search_timer.start()

    def _on_search_view_clear(self) -> None:
        """« Effacer » : empty the query, back to the recents mode."""
        self._search.setText("")
        self._search_timer.stop()
        self._show_search_page()

    def _on_search_view_open(self, payload) -> None:
        """A result / recent was clicked on the search page."""
        if isinstance(payload, RecentEntry):
            item = self._resolve_recent(payload)
            if item is None:
                self._toast.show_message(
                    t("toast.item_not_found"), KIND_WARNING, duration_ms=4000
                )
                return
            self.go((PAGE_CONFIG, item))
            return
        if isinstance(payload, Node):
            self.go((PAGE_BROWSE, payload))
            return
        if isinstance(payload, ConfigItem):
            self.go((PAGE_CONFIG, payload))

    def _resolve_recent(self, entry: RecentEntry) -> ConfigItem | None:
        """Resolve a recent's key into a live library item (deleted items
        resolve to ``None`` — the recent is dropped on next render)."""
        if self.root_node is None:
            return None
        try:
            path = Path(entry.key)
        except (OSError, ValueError):
            return None
        return find_config(self.root_node, path)

    def _on_search_view_filters(self) -> None:
        """A filter changed on the search page: update the state in place."""
        state = self._current_search_state()
        if state is None:
            return
        self._history.replace_current((PAGE_SEARCH, state))
        self._show_search_page()

    def _on_search_view_reset(self) -> None:
        """« Réinitialiser » on the search page: drop the filters, keep the
        query."""
        self._search_view.reset_filters()
        state = self._current_search_state()
        if state is None:
            return
        self._history.replace_current((PAGE_SEARCH, state))
        self._show_search_page()

    def _current_search_state(self) -> SearchState | None:
        """The search context matching the active input + filters."""
        if self._stack.currentWidget() is self._search_view:
            query = self._search_view.query_text().strip()
            category, status, favorites = self._search_view.current_filters()
        else:
            query = self._search.text().strip()
            category, status = self._browse.current_filters()
            favorites = None
        if len(query) < 2:
            return None
        return SearchState(query=query, category=category, status=status, favorites=favorites)

    # ------------------------------------------------------------------ #
    # Favorites (v1.3.0)
    # ------------------------------------------------------------------ #
    def _is_favorite(self, key: str) -> bool:
        """Provider des vues : une clé de carte est-elle favorite ?"""
        return key in self.settings.favorites

    def _toggle_favorite(self, target) -> None:
        """Bascule favori/non favori (étoile de carte) + persistance.

        Le statut favori est indépendant du statut Fleasion : une
        configuration peut être favorite + active, favorite + inactive,
        etc. — jamais confondu avec ``enabled_configs``.
        """
        key = str(getattr(target, "path", target))
        favorite = self.settings.toggle_favorite(key)
        self.settings.save()
        grid = self._current_grid()
        if grid is not None:
            grid.set_card_favorite(key, favorite)
        self._toast.show_message(
            t("toast.favorite_added") if favorite else t("toast.favorite_removed"),
            KIND_SUCCESS if favorite else KIND_WARNING,
            duration_ms=2000,
        )
        # La vue Recherche montre aussi des cartes : synchroniser l'étoile.
        if self._stack.currentWidget() is self._search_view:
            card = self._search_view._grid.find_card(key)
            if card is not None:
                card.set_favorite(favorite)
        # La page Favoris est une vue virtuelle : retirer le favori retire
        # la carte de la page (le fichier, lui, n'est jamais touché).
        if self._stack.currentWidget() is self._favorites_view:
            self._show_favorites_page()

    # ------------------------------------------------------------------ #
    # Verification + repair (v1.3.0)
    # ------------------------------------------------------------------ #
    def _verify_current(self) -> None:
        """« Vérifier » : analyse réelle de la configuration courante (JSON,
        dépendances OBJ/MP3, fichiers, catégorie) — jamais de faux succès."""
        item = self._current_item
        if item is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            verification = verify_item(item)
        finally:
            QApplication.restoreOverrideCursor()
        self._config.show_verification(verification)
        if verification.valid:
            self._toast.show_message(
                t("toast.verify_ok"), KIND_SUCCESS, duration_ms=3000
            )
        else:
            self._toast.show_message(
                t("toast.verify_incomplete"), KIND_WARNING, duration_ms=4000
            )

    def _repair_current(self) -> None:
        """« Réparer » : analyse ce qui peut l'être, demande confirmation,
        copie, puis RE-vérifie — « Réparé » n'est affiché que si la
        re-vérification confirme réellement la configuration."""
        item = self._current_item
        if item is None:
            return
        verification = self._config.current_verification() or verify_item(item)
        plan = build_repair_plan(
            item,
            verification,
            library_root=self.settings.library_dir,
            obj_cache=obj_cache_dir(),
        )
        if not plan.possible:
            box = QMessageBox(self)
            box.setWindowTitle(t("repair.title"))
            box.setIcon(QMessageBox.Warning)
            box.setText(t("repair.impossible"))
            box.setInformativeText(plan.explanation)
            box.addButton(t("common.close"), QMessageBox.ButtonRole.AcceptRole)
            box.exec()
            return
        if not self._confirm_repair(plan):
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            errors = apply_repair(plan, self.backup_manager)
        finally:
            QApplication.restoreOverrideCursor()
        # Re-vérification réelle : « Réparé » seulement si elle confirme.
        recheck = verify_item(item)
        self._config.show_verification(recheck)
        if errors:
            self._toast.show_message(
                t("repair.partial", errors="\n".join(errors)),
                KIND_ERROR,
                duration_ms=4500,
            )
        elif recheck.valid:
            self._toast.show_message(t("toast.repair_ok"), KIND_SUCCESS)
            self._refresh_and_resync()
        else:
            self._toast.show_message(t("toast.repair_not_fixed"), KIND_WARNING, duration_ms=4000)

    def _confirm_repair(self, plan) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(t("repair.title"))
        box.setIcon(QMessageBox.Question)
        box.setText(t("repair.confirm_text"))
        box.setInformativeText(plan.explanation)
        repair_btn = box.addButton(
            t("repair.do"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is repair_btn

    # ------------------------------------------------------------------ #
    # Profiles (v1.3.0)
    # ------------------------------------------------------------------ #
    def _show_profiles_page(self) -> None:
        """Render the profiles page: cards + missing-config status."""
        profiles = self.profiles.list_profiles()
        missing = {
            p.name: len(self._profile_missing(p))
            for p in profiles
        }
        self._profiles_view.set_profiles(profiles, missing)

    def _show_favorites_page(self) -> None:
        """Render the Favorites page: a **virtual folder** gathering every
        favourite configuration. The files stay in their original category
        — this is a pure shortcut view, nothing is moved."""
        favorite_keys = set(self.settings.favorites)
        configs = [
            item
            for item in walk_configs(self.root_node)
            if str(item.path) in favorite_keys
        ] if self.root_node is not None else []
        self._favorites_view.set_favorites(configs, self.root_node)

    def _create_profile(self) -> None:
        """« Créer un profil » : captures l'état actuel (configs actives
        Fleasion pré-cochées), l'utilisateur garde le contrôle final."""
        if self.settings.library_dir is None:
            self._toast.show_message(t("toast.no_library"), KIND_WARNING)
            return
        configs = self._all_configs()
        active_keys = self._active_config_keys()
        dialog = ProfileDialog(
            self.settings.library_dir,
            configs,
            active_keys=active_keys,
            profile=None,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            profile = self.profiles.create(
                name=dialog.result_profile().name,
                description=dialog.result_profile().description,
                entries=dialog.result_profile().entries,
            )
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(
            t("toast.profile_created", name=profile.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    def _save_current_as_profile(self) -> None:
        """« Enregistrer comme profil » (v1.3.1) : capture la configuration
        ACTUELLE (configs actives dans Fleasion) en un clic — aucun
        parcours manuel des catégories, aucune sélection skin par skin."""
        if self.settings.library_dir is None or self.root_node is None:
            self._toast.show_message(t("toast.no_library"), KIND_WARNING)
            return
        captured = [
            item
            for item in walk_configs(self.root_node)
            if str(item.path) in self._active_config_keys()
        ]
        if not captured:
            self._toast.show_message(
                t("toast.no_active_configs"), KIND_WARNING, duration_ms=4000
            )
            return
        dialog = ProfileDialog(
            self.settings.library_dir,
            captured,
            capture=captured,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.result_profile()
        try:
            profile = self.profiles.create(
                name=result.name,
                description=result.description,
                entries=result.entries,
            )
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(
            t("toast.profile_created", name=profile.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    def _import_into_profile(self) -> None:
        """« Importer dans un profil » (v1.3.1) : importer une
        configuration (fichier / dossier / ZIP) dans la bibliothèque, puis
        créer un profil contenant cette configuration."""
        if self.settings.library_dir is None:
            self._toast.show_message(t("toast.no_library"), KIND_WARNING)
            return
        path = QFileDialog.getOpenFileName(
            self,
            t("profiles.import_into_dialog"),
            str(Path.home()),
            t("profiles.import_into_filter"),
        )[0]
        if not path:
            return
        from app.mod_import import (
            ModImportError,
            analyze_source,
            cleanup_staging,
            install_mod,
        )

        try:
            analysis = analyze_source(Path(path))
        except ModImportError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4500)
            return
        try:
            dialog = ImportDialog(
                analysis,
                self.settings.library_dir,
                parent=self,
            )
            if dialog.exec() != QDialog.Accepted:
                return
            plan = dialog.build_plan()
            destination = install_mod(plan, self.backup_manager)
        except ModImportError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4500)
            return
        finally:
            cleanup_staging(analysis)
        self.refresh_library(show_error=False)

        item = self._config_item_at(destination)
        if item is None:
            self._toast.show_message(
                t("toast.mod_installed", name=plan.name, destination=destination),
                KIND_SUCCESS,
                duration_ms=4000,
            )
            return
        # Créer le profil contenant cette configuration.
        dialog = ProfileDialog(
            self.settings.library_dir,
            [item],
            capture=[item],
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.result_profile()
        try:
            profile = self.profiles.create(
                name=result.name,
                description=result.description,
                entries=result.entries,
            )
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(
            t("toast.profile_created", name=profile.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    def _config_item_at(self, folder: Path):
        """The library ConfigItem at a folder (after a refresh), or None."""
        if self.root_node is None:
            return None
        from app.scanner import find_node

        node = find_node(self.root_node, folder)
        if node is None:
            return None
        for config in node.configs:
            if config.path == folder:
                return config
        return None

    def _edit_profile(self, profile: Profile) -> None:
        """« Modifier » : same dialog, pre-filled with the profile."""
        if self.settings.library_dir is None:
            return
        configs = self._all_configs()
        dialog = ProfileDialog(
            self.settings.library_dir,
            configs,
            active_keys=set(),
            profile=profile,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.result_profile()
        try:
            self.profiles.update(updated)
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(
            t("toast.profile_updated", name=updated.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    def _delete_profile(self, profile: Profile) -> None:
        """« Supprimer » : confirmation, puis suppression du profil seul
        (jamais des configurations de la bibliothèque)."""
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.profile_delete_title"))
        box.setIcon(QMessageBox.Warning)
        box.setText(t("confirm.profile_delete_text", name=profile.name))
        box.setInformativeText(t("confirm.profile_delete_info"))
        delete_btn = box.addButton(
            t("confirm.delete"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not delete_btn:
            return
        self.profiles.delete(profile.name)
        self._toast.show_message(
            t("toast.profile_deleted", name=profile.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    def _apply_profile(self, profile: Profile) -> None:
        """« Appliquer » : résout les configurations, prévient des
        manquantes, active les présentes via le mécanisme Fleasion existant
        (respecte hot_activation_enabled) et confirme l'état réel — jamais
        un profil « appliqué » sans confirmation."""
        if not self.settings.fleasion_dir:
            self._toast.show_message(
                t("toast.fleasion_not_configured"), KIND_WARNING
            )
            return
        missing = self._profile_missing(profile)
        if missing:
            if not self._confirm_profile_missing(profile, missing):
                return
        present = [
            (entry, item)
            for entry, item in self._profile_items(profile)
            if item is not None
        ]
        applied: list[str] = []
        failed: list[str] = []
        for entry, item in present:
            result, real_state = self._run_activation(item)
            if real_state == STATE_ACTIVE:
                applied.append(entry.name)
            else:
                failed.append(entry.name)
        if applied:
            self._toast.show_message(
                t("toast.profile_applied", name=profile.name),
                KIND_SUCCESS,
                duration_ms=4000,
            )
        elif not failed:
            self._toast.show_message(
                t("toast.profile_nothing_applied"), KIND_WARNING, duration_ms=4000
            )
        if failed:
            self._toast.show_message(
                t("toast.profile_partial", name=profile.name, failed=", ".join(failed)),
                KIND_WARNING,
                duration_ms=4500,
            )
        self._show_profiles_page()

    def _confirm_profile_missing(self, profile: Profile, missing: list[str]) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(t("confirm.profile_missing_title"))
        box.setIcon(QMessageBox.Warning)
        n = len(missing)
        box.setText(
            t("confirm.profile_missing_text_one", name=profile.name)
            if n == 1
            else t("confirm.profile_missing_text_many", name=profile.name, count=n)
        )
        box.setInformativeText(
            t("confirm.profile_missing_info", files="\n".join(f"• {m}" for m in missing))
        )
        continue_btn = box.addButton(
            t("confirm.profile_continue"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(t("confirm.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is continue_btn

    def _export_profile(self, profile: Profile) -> None:
        """« Exporter » : écrit un ``.rcmprofile`` (références logiques
        uniquement — jamais de chemins absolus ni de données personnelles)."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            t("profiles.export_dialog"),
            str(Path.home() / f"{profile.name}{PROFILE_EXTENSION}"),
            f"RCM Profile (*{PROFILE_EXTENSION})",
        )
        if not path:
            return
        try:
            dest = self.profiles.export_profile(profile.name, Path(path))
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4000)
            return
        self._toast.show_message(
            t("toast.profile_exported", path=dest), KIND_SUCCESS, duration_ms=4000
        )

    def _import_profile(self) -> None:
        """« Importer » : lit un ``.rcmprofile`` et l'ajoute aux profils."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("profiles.import_dialog"),
            str(Path.home()),
            f"RCM Profile (*{PROFILE_EXTENSION})",
        )
        if not path:
            return
        try:
            profile = self.profiles.import_profile(Path(path))
        except ProfileError as exc:
            self._toast.show_message(f"✘ {exc}", KIND_ERROR, duration_ms=4500)
            return
        self._toast.show_message(
            t("toast.profile_imported", name=profile.name), KIND_SUCCESS
        )
        self._show_profiles_page()

    # ------------------------------------------------------------------ #
    # Profile helpers
    # ------------------------------------------------------------------ #
    def _all_configs(self) -> list[ConfigItem]:
        """Every configuration of the library (for the profile dialog)."""
        if self.root_node is None:
            return []
        return walk_configs(self.root_node)

    def _active_config_keys(self) -> set[str]:
        """Keys of the configurations currently active in Fleasion (the
        profile's default capture).

        Uses a single ``detect()`` snapshot instead of one ``status()``
        call per configuration — ``status()`` re-detects (reads
        settings.json, walks folders) every time, which froze profile
        creation on large libraries (v1.3.1)."""
        if self.root_node is None:
            return set()
        try:
            info = self.fleasion.detect()
            enabled = set(info.enabled_configs)
        except Exception:
            enabled = set()
        return {
            str(item.path)
            for item in walk_configs(self.root_node)
            if item.name in enabled
        }

    def _profile_items(self, profile: Profile) -> list[tuple[ProfileEntry, ConfigItem | None]]:
        """Resolve each entry against the current library (logical refs)."""
        if self.root_node is None or self.settings.library_dir is None:
            return [(e, None) for e in profile.entries]
        library = Path(self.settings.library_dir)
        resolved: list[tuple[ProfileEntry, ConfigItem | None]] = []
        for entry in profile.entries:
            target = library / entry.rel_path
            item = find_config(self.root_node, target) if target.exists() else None
            resolved.append((entry, item))
        return resolved

    def _profile_missing(self, profile: Profile) -> list[str]:
        """Names of the profile's configurations that no longer exist."""
        return [
            entry.name
            for entry, item in self._profile_items(profile)
            if item is None
        ]

    # ------------------------------------------------------------------ #
    # Theme (v1.3.0)
    # ------------------------------------------------------------------ #
    def _set_theme(self, key: str, custom: dict) -> None:
        """Hot theme switch: persist + apply + re-render the current state."""
        if key != "custom":
            custom = None
        self.settings.theme = key
        self.settings.custom_theme = custom
        self.settings.save()
        from ui.theme import apply_theme

        apply_theme(QApplication.instance() or QApplication([]), key, custom)
        # Les cartes portent des couleurs inline (étoile, bouton ▶ / ×) :
        # re-render l'état courant pour les reconstruire avec le nouveau
        # thème ; navigation et contenu sont conservés.
        current = self._history.current()
        if current is not None:
            self._render(current)
        self._toast.show_message(t("toast.theme_applied"), KIND_SUCCESS, duration_ms=2000)

    # ------------------------------------------------------------------ #
    # Mouse side buttons (précédent / suivant), scoped to this window
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # Drag & drop (importer un mod déposé n'importe où dans la fenêtre)
    # ------------------------------------------------------------------ #
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._has_local_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._has_local_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if not paths:
            event.ignore()
            return
        self._import_dropped(paths)
        event.acceptProposedAction()

    @staticmethod
    def _has_local_files(mime) -> bool:
        return any(url.isLocalFile() and url.toLocalFile() for url in mime.urls())

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """Mouse side buttons navigate like a browser.

        Handled only for plain single presses of the back/forward mouse
        buttons delivered to a widget of *this* window, and only while no
        modal dialog or popup is open — the buttons are never intercepted
        globally (Qt events only concern this application's widgets).
        """
        if event.type() != QEvent.MouseButtonPress:
            return False
        if QApplication.activeModalWidget() is not None:
            return False
        if QApplication.activePopupWidget() is not None:
            return False
        if not isinstance(watched, QWidget) or not self._belongs_to_window(watched):
            return False

        button = event.button()
        if button == Qt.BackButton:
            self.back()
            return True
        if button == Qt.ForwardButton:
            self.forward()
            return True
        return False

    @staticmethod
    def _belongs_to_window(widget: QWidget) -> bool:
        """True when ``widget`` is the main window or one of its children."""
        current = widget
        while current is not None:
            if isinstance(current, MainWindow):
                return True
            current = current.parentWidget()
        return False

    # ------------------------------------------------------------------ #
    # Language (i18n)
    # ------------------------------------------------------------------ #
    def _set_language(self, code: str) -> None:
        """Hot language switch: persist the choice, apply it to every
        widget and re-render the current state (navigation, search query,
        filters and cards are all preserved)."""
        if not code or code == self.settings.language:
            return
        self.settings.language = code
        self.settings.save()
        _set_language(code)
        self._apply_language()

    def _apply_language(self) -> None:
        """Re-apply every static text after a language change."""
        self._back_btn.setToolTip(t("nav.back"))
        self._forward_btn.setToolTip(t("nav.forward"))
        self._trash_btn.setToolTip(t("trash.title"))
        self._search_page_btn.setToolTip(t("search.page_title"))
        self._profiles_btn.setToolTip(t("profiles.title"))
        self._search.setPlaceholderText(t("search.placeholder"))
        self._add_weapon_btn.setText(t("add_weapon.button"))
        self._add_weapon_btn.setToolTip(t("add_weapon.tooltip"))
        self._settings_btn.setToolTip(t("settings.title"))
        self._welcome.retranslate()
        self._home.retranslate()
        self._browse.retranslate()
        self._config.retranslate()
        self._settings.retranslate()
        self._trash_view.retranslate()
        self._search_view.retranslate()
        self._profiles_view.retranslate()
        self._settings.set_language_value(self.settings.language)
        # Re-render the current state: cards, page titles and search are
        # rebuilt with the new language; navigation history is untouched.
        current = self._history.current()
        if current is not None:
            self._render(current)

    # ------------------------------------------------------------------ #
    # Keyboard shortcuts (v1.3.0)
    # ------------------------------------------------------------------ #
    def _register_shortcuts(self) -> None:
        """Register the application shortcuts (single, central table)."""
        from PySide6.QtGui import QKeySequence, QShortcut

        def bind(sequence: str, handler) -> None:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._shortcuts = getattr(self, "_shortcuts", [])
            self._shortcuts.append(shortcut)

        bind(SHORTCUTS["open_search"][0], self._shortcut_open_search)
        bind(SHORTCUTS["go_home"][0], lambda: self.go(STATE_HOME))
        bind(SHORTCUTS["verify_config"][0], self._shortcut_verify)
        bind(SHORTCUTS["toggle_config"][0], self._shortcut_toggle)

    def _shortcut_open_search(self) -> None:
        """Ctrl+F : ouvrir la page Recherche et focus la grande barre."""
        self.go((PAGE_SEARCH, None))
        self._search_view._big_bar.setFocus()

    def _shortcut_verify(self) -> None:
        """F5 : vérifier la configuration sélectionnée (page config)."""
        if self._stack.currentWidget() is self._config and self._current_item is not None:
            self._verify_current()

    def _shortcut_toggle(self) -> None:
        """Ctrl+Shift+Entrée : activer/désactiver la configuration
        sélectionnée (même logique que le bouton de la page config)."""
        if self._stack.currentWidget() is self._config and self._current_item is not None:
            if self.fleasion.status(self._current_item) == STATE_ACTIVE:
                self._deactivate_current()
            else:
                self._activate_current()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Uninstall the event filter so closed windows never intercept
        mouse events (matters when another window is created after)."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if hasattr(self, "_toast") and self._toast.isVisible():
            parent_rect = self.rect()
            x = (parent_rect.width() - self._toast.width()) // 2
            y = parent_rect.height() - self._toast.height() - 36
            self._toast.move(max(x, 16), max(y, 16))


def _count_items(node: Node) -> int:
    total = len(node.configs)
    for sub in node.subdirs:
        total += _count_items(sub)
    return total
