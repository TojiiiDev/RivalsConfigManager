"""Vector icons painted at runtime — no emoji, no external assets.

All icons share the same stroke style (color, width, round caps) so the
interface looks consistent. Each function returns a :class:`QIcon` ready to
be set on a button.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

#: Icon stroke color, matching the theme's TEXT_DIM.
STROKE = "#9aa7bd"
WIDTH = 3


def _canvas(size: int = 44, color: str = STROKE, width: int = WIDTH) -> tuple[QPixmap, QPainter, QPen]:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    return pm, p, pen


def _finish(p: QPainter, pm: QPixmap) -> QIcon:
    p.end()
    return QIcon(pm)


def chevron_left_icon() -> QIcon:
    pm, p, pen = _canvas()
    path = QPainterPath()
    path.moveTo(28, 14)
    path.lineTo(17, 22)
    path.lineTo(28, 30)
    p.drawPath(path)
    return _finish(p, pm)


def chevron_right_icon() -> QIcon:
    pm, p, pen = _canvas()
    path = QPainterPath()
    path.moveTo(16, 14)
    path.lineTo(27, 22)
    path.lineTo(16, 30)
    p.drawPath(path)
    return _finish(p, pm)


def gear_icon() -> QIcon:
    """Engrenage moderne (UI/UX phase) : 12 dents arrondies autour d'un
    anneau, centre évidé — plus lisible que l'ancienne version."""
    pm, p, pen = _canvas()
    cx, cy = 22.0, 22.0
    r_ring, r_teeth_outer = 7.4, 11.2
    # Dents : segments épais à cap ronds, à partir du bord externe de
    # l'anneau.
    for i in range(12):
        a = math.radians(i * 30)
        dx, dy = math.cos(a), math.sin(a)
        p.drawLine(
            QPointF(cx + dx * (r_ring + 1.2), cy + dy * (r_ring + 1.2)),
            QPointF(cx + dx * r_teeth_outer, cy + dy * r_teeth_outer),
        )
    # Anneau central.
    p.drawEllipse(QRectF(cx - r_ring, cy - r_ring, r_ring * 2, r_ring * 2))
    # Centre évidé.
    p.setBrush(QColor(STROKE))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(cx - 2.1, cy - 2.1, 4.2, 4.2))
    return _finish(p, pm)


def play_icon(color: str = "#ffffff") -> QIcon:
    """Triangle « play » (plein, blanc par défaut) pour le bouton
    d'activation des cartes — jamais d'emoji."""
    pm, p, pen = _canvas(color=color)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawPolygon(QPolygonF([QPointF(17, 14), QPointF(30, 22), QPointF(17, 30)]))
    return _finish(p, pm)


def close_icon(color: str = "#ffffff") -> QIcon:
    """Croix « X » (trait blanc par défaut) pour le bouton de désactivation
    des cartes — jamais d'emoji."""
    pm, p, pen = _canvas(color=color)
    p.drawLine(QPointF(16, 16), QPointF(28, 28))
    p.drawLine(QPointF(28, 16), QPointF(16, 28))
    return _finish(p, pm)


def plus_icon() -> QIcon:
    pm, p, pen = _canvas()
    p.drawLine(QPointF(22, 13), QPointF(22, 31))
    p.drawLine(QPointF(13, 22), QPointF(31, 22))
    return _finish(p, pm)


def star_icon(filled: bool = False, color: str = STROKE) -> QIcon:
    """Étoile (favori) — contour ou pleine selon ``filled``."""
    pm, p, pen = _canvas(color=color)
    cx, cy = 22.0, 22.0
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = 10.0 if i % 2 == 0 else 4.6
        points.append(QPointF(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    if filled:
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF(points))
    else:
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(QPolygonF(points))
    return _finish(p, pm)


def search_icon() -> QIcon:
    """Loupe : cercle + manche."""
    pm, p, pen = _canvas()
    p.drawEllipse(QRectF(13, 13, 16, 16))
    p.drawLine(QPointF(26, 26), QPointF(32, 32))
    return _finish(p, pm)


def users_icon() -> QIcon:
    """Profils : deux silhouettes (cercle tête + arc épaules)."""
    pm, p, pen = _canvas()
    # Première silhouette (gauche)
    p.drawEllipse(QRectF(14, 12, 8, 8))
    p.drawArc(QRectF(9, 22, 18, 16), 180 * 16, 180 * 16)
    # Seconde silhouette (droite, légèrement décalée)
    p.drawEllipse(QRectF(25, 10, 7, 7))
    p.drawArc(QRectF(21, 19, 15, 16), 180 * 16, 180 * 16)
    return _finish(p, pm)


def wrench_icon() -> QIcon:
    """Clé à molette — utilisée par le bouton Réparer."""
    pm, p, pen = _canvas()
    # Corps arrondi de la clé
    p.drawLine(QPointF(15, 29), QPointF(29, 15))
    # Tête ouverte
    p.drawArc(QRectF(13, 13, 14, 14), 40 * 16, 260 * 16)
    p.drawLine(QPointF(12, 19), QPointF(12, 25))
    p.drawLine(QPointF(28, 19), QPointF(28, 25))
    return _finish(p, pm)


def refresh_icon() -> QIcon:
    """Flèche circulaire (recharger) — utilisée par le bouton
    « Recharger l'application » (v1.3.5)."""
    pm, p, pen = _canvas()
    # Cercle ouvert en haut à droite.
    p.drawArc(QRectF(13, 13, 18, 18), 30 * 16, 300 * 16)
    # Pointe de flèche à l'extrémité de l'arc.
    path = QPainterPath()
    path.moveTo(29, 9)
    path.lineTo(32, 15)
    path.lineTo(26, 17)
    p.drawPath(path)
    return _finish(p, pm)


def check_icon() -> QIcon:
    """Coche simple — statut « valide / présent »."""
    pm, p, pen = _canvas()
    path = QPainterPath()
    path.moveTo(13, 22)
    path.lineTo(19, 28)
    path.lineTo(31, 15)
    p.drawPath(path)
    return _finish(p, pm)


def trash_icon() -> QIcon:
    """Corbeille : icône vectorielle peinte à l'exécution (pas d'emoji)."""
    pm, p, pen = _canvas()
    # Couvercle
    p.drawLine(QPointF(11, 15), QPointF(33, 15))
    # Anse
    p.drawRoundedRect(QRectF(16, 10, 12, 6), 3, 3)
    # Corps
    p.drawRoundedRect(QRectF(12, 15, 20, 22), 4, 4)
    # Rainures
    p.drawLine(QPointF(18, 20), QPointF(18, 31))
    p.drawLine(QPointF(26, 20), QPointF(26, 31))
    return _finish(p, pm)


def edit_icon() -> QIcon:
    """Crayon (Mode Éditeur) — icône discrète du bouton admin."""
    pm, p, pen = _canvas()
    # Corps du crayon (diagonale).
    p.drawLine(QPointF(15, 29), QPointF(29, 15))
    # Pointe (triangle) en bas à gauche.
    tip = QPainterPath()
    tip.moveTo(15, 29)
    tip.lineTo(13, 32)
    tip.lineTo(16, 31)
    tip.closeSubpath()
    p.drawPath(tip)
    # Gomme (petit trait) en haut à droite.
    p.drawLine(QPointF(29, 15), QPointF(32, 12))
    return _finish(p, pm)
