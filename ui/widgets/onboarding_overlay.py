"""Interactive first-launch tutorial overlay (v1.3.8, reworked in v1.3.10).

An independent UI layer above the existing application: while the tutorial
runs, the current step's target(s) are highlighted with a rounded
spotlight and the rest of the interface is lightly dimmed (the
application stays perfectly visible). A compact themed bubble explains the
step, shows ``current / total`` and offers Précédent / Suivant / Terminer.
The final state is a « Vous êtes prêt ! » card with a « Compris » button.

**Positioning is never fixed** — the spotlight is always recomputed from
the REAL global geometry of the target widgets (``mapToGlobal`` /
``mapFromGlobal``), and the overlay is **self-healing**: after every
trigger (start, step change, show, resize, page render, window
maximize/restore/fullscreen, layout change) the target rectangle is
recomputed over and over — a short settle loop plus a light polling
safety net — until it stops changing. Whatever timing quirk the real
event loop has (deferred layouts, window-manager animations, DPI), the
spotlight converges to the true target and never keeps an old window's
size. The bubble is placed automatically (right, left, below, above)
within the window and never hides the target; a small arrow connects it.

The overlay consumes mouse events (the application is not interactive
while a step is explained); the tutorial advances through its own
buttons, never by clicking the explained element.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygon, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from ui.theme import RADIUS, theme_color

#: Minimum distance from the window edges (px).
_MARGIN = 16
#: Gap between the spotlight and the bubble (px).
_GAP = 14
#: Spotlight padding around the target widgets (px).
_PADDING = 10
#: Maximum bubble width (px).
_MAX_BUBBLE_W = 360
#: Voile (1.3.10) — base RGB du voile. Toujours SEMI-transparent : on
#: assombrit l'application pour la mettre en valeur, on ne la cache pas.
_VEIL_RGB = (8, 10, 15)
#: Opacité du voile au loin (≈55 % — dans la fourchette 50–65 % demandée).
_VEIL_ALPHA = 140
#: Opacité du voile juste AUTOUR du spotlight (plus clair : l'élément
#: important est « éclairé », le reste de la fenêtre est légèrement plus
#: sombre — effet spot, jamais un rectangle noir opaque).
_VEIL_ALPHA_NEAR = 80
#: Arrow half-width / height (px).
_ARROW = 9
#: Delay between two settle passes (ms) — lets the layout finish settling.
_SETTLE_DELAY_MS = 40
#: Maximum number of consecutive settle passes per trigger.
_MAX_SETTLE_PASSES = 10
#: Light periodic re-check while the tutorial is visible (safety net for
#: any unanticipated layout change; cheap, a few geometry reads).
_POLL_INTERVAL_MS = 200

#: Bubble placement relative to the target.
_BELOW = 0   # bubble is below the target → arrow points up
_ABOVE = 1   # bubble is above the target → arrow points down
_RIGHT = 2   # bubble is on the right → arrow points left
_LEFT = 3    # bubble is on the left → arrow points right


class _Bubble(QFrame):
    """The speech bubble: painted rounded translucent card + soft shadow +
    arrow pointing at the target (theme colors), with the step text and
    controls inside."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._arrow_side = _BELOW
        self.setObjectName("OnboardingBubble")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._title = QLabel(self)
        self._title.setObjectName("OnboardingBubbleTitle")
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"font-size: 12.5pt; font-weight: 700; color: {theme_color('text')};"
            "background: transparent; border: none;"
        )

        self._body = QLabel(self)
        self._body.setObjectName("OnboardingBubbleBody")
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"font-size: 10.5pt; color: {theme_color('text_dim')};"
            "background: transparent; border: none;"
        )

        self._progress = QLabel(self)
        self._progress.setObjectName("OnboardingBubbleProgress")
        self._progress.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._progress.setStyleSheet(
            f"font-size: 9pt; font-weight: 600; color: {theme_color('text_dim')};"
            "background: transparent; border: none;"
        )

        self._prev_btn = QPushButton(self)
        self._prev_btn.setObjectName("OnboardingBubbleButton")
        self._next_btn = QPushButton(self)
        self._next_btn.setObjectName("PrimaryButton")
        self._got_it_btn = QPushButton(self)
        self._got_it_btn.setObjectName("PrimaryButton")

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header.addWidget(self._title, 1)
        header.addWidget(self._progress, 0)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        buttons.addWidget(self._prev_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._next_btn)
        buttons.addWidget(self._got_it_btn)

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(10)
        self._layout.addLayout(header)
        self._layout.addWidget(self._body)
        self._layout.addLayout(buttons)
        self._apply_arrow_margins()

    # ------------------------------------------------------------------ #
    def set_arrow(self, side: int) -> None:
        self._arrow_side = side
        self._apply_arrow_margins()
        self.update()

    def _apply_arrow_margins(self) -> None:
        """Give extra space on the arrow side so the triangle never
        overlaps the text/buttons."""
        top = _ARROW + 6 if self._arrow_side == _BELOW else 14
        bottom = _ARROW + 6 if self._arrow_side == _ABOVE else 14
        left = _ARROW + 8 if self._arrow_side == _RIGHT else 18
        right = _ARROW + 8 if self._arrow_side == _LEFT else 18
        self._layout.setContentsMargins(left, top, right, bottom)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        bg = QColor(theme_color("card"))
        bg.setAlpha(246)  # légèrement translucide : on devine l'app derrière
        border = QColor(theme_color("border"))
        # Ombre douce simulée (contour élargi sombre) — léger, jamais un
        # effet lourd qui ralentirait l'application.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 70))
        painter.drawRoundedRect(QRect(2, 3, rect.width() - 4, rect.height() - 3),
                                RADIUS, RADIUS)
        # Corps de la bulle.
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(QRect(1, 1, rect.width() - 2, rect.height() - 2),
                                RADIUS, RADIUS)
        triangle = self._arrow(rect)
        if triangle:
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawPolygon(triangle)

    def _arrow(self, rect: QRect) -> QPolygon:
        cx, cy = rect.center().x(), rect.center().y()
        if self._arrow_side == _BELOW:
            return QPolygon([QPoint(cx - _ARROW, 0), QPoint(cx + _ARROW, 0), QPoint(cx, _ARROW)])
        if self._arrow_side == _ABOVE:
            return QPolygon([QPoint(cx - _ARROW, rect.height()),
                             QPoint(cx + _ARROW, rect.height()),
                             QPoint(cx, rect.height() - _ARROW)])
        if self._arrow_side == _RIGHT:
            return QPolygon([QPoint(0, cy - _ARROW), QPoint(0, cy + _ARROW), QPoint(_ARROW, cy)])
        if self._arrow_side == _LEFT:
            return QPolygon([QPoint(rect.width(), cy - _ARROW),
                             QPoint(rect.width(), cy + _ARROW),
                             QPoint(rect.width() - _ARROW, cy)])
        return QPolygon()


class OnboardingOverlay(QWidget):
    """Dim + spotlight + bubble over the whole window (see module doc)."""

    completed = Signal()  # the user clicked « Compris »

    def __init__(self, parent: QWidget, steps: list[dict]) -> None:
        super().__init__(parent)
        self._steps = list(steps)
        self._index = 0           # 0..len(steps)-1 ; len(steps) = done state
        self._target: QRect = QRect()
        self._bubble_side = _BELOW
        self._settle_passes = 0

        self._bubble = _Bubble(self)
        self._bubble._prev_btn.clicked.connect(self.previous)
        self._bubble._next_btn.clicked.connect(self.next)
        self._bubble._got_it_btn.clicked.connect(self.finish)

        # Apparition douce de la bulle à chaque changement d'étape (très
        # légère, sans effet sur le positionnement).
        self._bubble_opacity = QGraphicsOpacityEffect(self._bubble)
        self._bubble_opacity.setOpacity(1.0)
        self._bubble.setGraphicsEffect(self._bubble_opacity)
        self._bubble_fade = QPropertyAnimation(self._bubble_opacity, b"opacity", self)
        self._bubble_fade.setDuration(200)
        self._bubble_fade.setEasingCurve(QEasingCurve.OutCubic)

        # Filet de sécurité : tant que le tutoriel est visible, on revérifie
        # périodiquement la géométrie réelle des cibles (aucun changement de
        # layout, de page ou de fenêtre ne peut laisser le spotlight décalé).
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_tick)

        # Vraie transparence : l'overlay ne peint JAMAIS de fond opaque
        # (le style / le QSS le ferait sinon avec la couleur de fond du
        # thème, et l'interface derrière serait masquée). Seul le voile
        # translucide est dessiné, avec un véritable trou pour le spotlight
        # — jamais de WA_StyledBackground ni d'autoFillBackground ici.
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    @property
    def step_count(self) -> int:
        return len(self._steps)

    @property
    def current_step(self) -> int:
        return self._index

    @property
    def bubble(self) -> _Bubble:
        return self._bubble

    @property
    def spotlight_rect(self) -> QRect:
        """The spotlight rectangle actually painted for the current step
        (the real target, in overlay coordinates — never a fixed value)."""
        return QRect(self._target)

    def start(self) -> None:
        self._settle_passes = 0
        self.setGeometry(self.parentWidget().rect())
        self._index = 0
        self._refresh(animate_bubble=True)
        self.show()
        self.raise_()
        self._poll_timer.start()

    def next(self) -> None:
        if self._index < len(self._steps):
            self._index += 1
            self._settle_passes = 0
            self._refresh(animate_bubble=True)

    def previous(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._settle_passes = 0
            self._refresh(animate_bubble=True)

    def finish(self) -> None:
        self.completed.emit()

    def retranslate(self) -> None:
        self._refresh()

    def refresh(self) -> None:
        """Recompute everything now — called by the main window after a
        page render or any layout change."""
        if self.isVisible():
            self._settle_passes = 0
            self._refresh()

    # ------------------------------------------------------------------ #
    # Geometry — always from the REAL widget geometry, never fixed values
    # ------------------------------------------------------------------ #
    def target_rect(self, step_index: int) -> QRect:
        """Union of a step's target widgets, converted into overlay
        coordinates from their global screen geometry."""
        step = self._steps[step_index]
        union = QRect()
        for widget in step.get("targets", ()):
            if widget is None or not widget.isVisible():
                continue  # une cible cachée n'étire jamais le spotlight
            top_left = self.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
            bottom_right = self.mapFromGlobal(
                widget.mapToGlobal(QPoint(widget.width(), widget.height()))
            )
            union = union.united(QRect(top_left, bottom_right))
        if union.isNull():
            return QRect()
        return union.adjusted(-_PADDING, -_PADDING, _PADDING, _PADDING)

    def _refresh(self, animate_bubble: bool = False) -> None:
        done = self._index >= len(self._steps)
        new_target = QRect() if done else self.target_rect(self._index)
        changed = new_target != self._target
        self._target = new_target
        self._update_bubble(done)
        if animate_bubble:
            self._fade_bubble_in()
        self.update()
        # Boucle de stabilisation : tant que la géométrie change (layout en
        # cours de stabilisation), on recalcule jusqu'à convergence.
        if changed and self.isVisible() and self._settle_passes < _MAX_SETTLE_PASSES:
            self._settle_passes += 1
            QTimer.singleShot(_SETTLE_DELAY_MS, self._settle_tick)

    def _settle_tick(self) -> None:
        if self.isVisible():
            self._refresh()

    def _poll_tick(self) -> None:
        if self.isVisible():
            self._refresh()

    def _fade_bubble_in(self) -> None:
        """Petite apparition douce de la bulle (sans toucher à sa position
        ni à celle du spotlight — rien n'est jamais décalé)."""
        self._bubble_fade.stop()
        self._bubble_opacity.setOpacity(0.0)
        self._bubble_fade.setStartValue(0.0)
        self._bubble_fade.setEndValue(1.0)
        self._bubble_fade.start()

    def _update_bubble(self, done: bool) -> None:
        bubble = self._bubble
        overlay = self.rect()
        width = max(220, min(_MAX_BUBBLE_W, overlay.width() - 2 * _MARGIN))

        # Content for this state.
        if done:
            bubble._title.setText(t("onboarding.done.title"))
            bubble._body.setText(t("onboarding.done.body"))
            bubble._progress.setText(t("onboarding.progress",
                                       current=len(self._steps), total=len(self._steps)))
            bubble._prev_btn.hide()
            bubble._next_btn.hide()
            bubble._got_it_btn.setText(t("onboarding.got_it"))
            bubble._got_it_btn.show()
            bubble.set_arrow(_ABOVE)  # no target → no arrow used
        else:
            step = self._steps[self._index]
            bubble._title.setText(t(step["title"]))
            bubble._body.setText(t(step["body"]))
            bubble._progress.setText(t("onboarding.progress",
                                       current=self._index + 1, total=len(self._steps)))
            bubble._prev_btn.setText(t("onboarding.prev"))
            bubble._prev_btn.setEnabled(self._index > 0)
            bubble._prev_btn.show()
            is_last = self._index == len(self._steps) - 1
            bubble._next_btn.setText(t("onboarding.finish") if is_last else t("onboarding.next"))
            bubble._next_btn.show()
            bubble._got_it_btn.hide()

        bubble.setFixedWidth(width)
        bubble.adjustSize()
        height = bubble.height()

        if done:
            x = max(_MARGIN, (overlay.width() - width) // 2)
            y = max(_MARGIN, overlay.height() // 3)
            bubble.move(x, y)
            return

        # Placement intelligent : droite → gauche → dessous → dessus, selon
        # l'espace réellement disponible dans la fenêtre (jamais de
        # coordonnée fixe ; la bulle ne masque jamais la cible).
        target = self._target
        if target.isNull():
            bubble.move(max(_MARGIN, overlay.width() - width - _MARGIN), _MARGIN)
            return
        m = _MARGIN
        gap = _GAP
        y = self._clamp(target.center().y() - height // 2, m, overlay.height() - m - height)
        if target.right() + gap + width <= overlay.width() - m:
            bubble.set_arrow(_RIGHT)
            bubble.move(target.right() + gap, y)
            return
        if target.left() - gap - width >= m:
            bubble.set_arrow(_LEFT)
            bubble.move(target.left() - gap - width, y)
            return
        x = self._clamp(target.center().x() - width // 2, m, overlay.width() - m - width)
        if target.bottom() + gap + height <= overlay.height() - m:
            bubble.set_arrow(_BELOW)
            bubble.move(x, target.bottom() + gap)
            return
        if target.top() - gap - height >= m:
            bubble.set_arrow(_ABOVE)
            bubble.move(x, target.top() - gap - height)
            return
        bubble.set_arrow(_ABOVE)
        bubble.move(x, self._clamp(target.bottom() + gap, m, overlay.height() - m - height))

    @staticmethod
    def _clamp(value: int, low: int, high: int) -> int:
        return max(low, min(value, high))

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Voile SEMI-transparent : l'application reste parfaitement visible
        # derrière le tutoriel (on la montre, on ne la cache pas). Un
        # dégradé radial éclaircit légèrement la zone autour du spotlight :
        # l'élément important semble « éclairé » pendant que le reste de la
        # fenêtre est doucement assombri — jamais un rectangle noir opaque.
        if self._target.isNull():
            painter.fillRect(self.rect(), QColor(*_VEIL_RGB, _VEIL_ALPHA))
            return
        # Spotlight = VRAI trou : le voile est la surface de l'overlay MOINS
        # la zone ciblée (soustraction de chemins). Le trou n'est pas
        # « effacé après coup » — il n'est tout simplement jamais peint :
        # l'overlay ne possède aucun pixel à l'intérieur, donc l'interface
        # derrière reste parfaitement visible. Ni noir, ni gris, ni
        # semi-transparent à l'intérieur.
        veil = QPainterPath()
        veil.addRect(self.rect())
        hole = QPainterPath()
        hole.addRoundedRect(self._target, RADIUS, RADIUS)
        veil = veil.subtracted(hole)
        center = self._target.center()
        w, h = self.width(), self.height()
        radius = max(
            math.hypot(center.x(), center.y()),
            math.hypot(center.x() - w, center.y()),
            math.hypot(center.x(), center.y() - h),
            math.hypot(center.x() - w, center.y() - h),
        ) or 1.0
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, QColor(*_VEIL_RGB, _VEIL_ALPHA_NEAR))
        gradient.setColorAt(0.55, QColor(*_VEIL_RGB, _VEIL_ALPHA))
        gradient.setColorAt(1.0, QColor(*_VEIL_RGB, _VEIL_ALPHA))
        painter.setPen(Qt.NoPen)
        painter.fillPath(veil, QBrush(gradient))
        # Halo doux de la couleur d'accent du thème : un large halo très
        # léger + le contour net autour de l'OUVERTURE — la cible ressort,
        # le thème est conservé.
        accent = QColor(theme_color("accent"))
        for alpha, width, grow in ((16, 12, 9), (36, 7, 5), (90, 3, 2), (235, 2, 0)):
            color = QColor(accent)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, width))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                self._target.adjusted(-grow, -grow, grow, grow),
                RADIUS + grow, RADIUS + grow,
            )

    # ------------------------------------------------------------------ #
    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._settle_passes = 0
        self.setGeometry(self.parentWidget().rect())
        self._refresh()
        self._poll_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        self._poll_timer.stop()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        if not self.isVisible():
            return
        # L'overlay couvre TOUJOURS toute la fenêtre, quelle que soit sa
        # taille (fenêtre normale, maximisée, plein écran, restaurée).
        self.setGeometry(self.parentWidget().rect())
        self._settle_passes = 0
        self._refresh()
        # Un second passage différé + la boucle de stabilisation absorbent
        # les mises en page différées (la zone de dépôt termine de se
        # redimensionner juste après le resize).
        QTimer.singleShot(0, self._refresh)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        event.accept()  # the application stays inert while a step explains

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        event.accept()
