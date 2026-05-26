"""
do-o-english — a beginner-friendly English learning game.

WHAT THIS PROGRAM DOES
  1. Shows a main menu where the player can pick an existing profile
     or register as a Teacher or Student.
  2. Shows a list of lessons.
  3. Plays a lesson: question -> answer choices -> next question -> ...
  4. At the end, shows a "Lesson complete" screen with XP earned.

HOW TO RUN
    pip install pygame
    python main.py

HOW THIS FILE IS ORGANIZED (top to bottom)
    1.  Imports
    2.  CONSTANTS  (colors, sizes, paths)
    3.  DATABASE   (save profiles and progress to a tiny SQLite file)
    4.  CONTENT    (load lesson .json files)
    5.  DRAW HELPERS (gradients, drop shadows, isometric primitives, avatar)
    6.  BACKGROUND  (animated parallax shapes — the "depth" behind every screen)
    7.  UI WIDGETS  (Button, TextInput)
    8.  GAME        (the App class: game loop and every screen)
    9.  ENTRY POINT
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import hashlib        # to turn passwords into a safe-to-store string
import json           # to read the lesson .json files
import math           # for sin/cos animations (the gentle floaty motion)
import os             # to read DOO_WINDOWED env override
import platform       # to pick the right per-platform save folder
import random         # to shuffle word-order exercises and pick particles
import sqlite3        # to remember profiles and progress on disk
import sys            # to detect a PyInstaller-frozen build
import time           # for timestamps used in animations
from pathlib import Path

import pygame         # the game library

# LAN multiplayer plumbing (UDP discovery + TCP host/client).
# Kept in a separate file so this one stays digestible.
from network import (
    APP_TAG,
    ClientPeer,
    HostServer,
    LobbyBeacon,
    LobbyListener,
    local_ips,
)


# ============================================================
# 2. CONSTANTS
# ============================================================

# Window size in pixels.
WIDTH  = 1024
HEIGHT = 720

# Partial credit awarded for a question where the player used a Hint or Skip.
PARTIAL_CREDIT = 0.4
FPS    = 60

# ---- Palette ----------------------------------------------------
# A modern dark UI with playful, Duolingo-ish accent colors.
# Colors are (Red, Green, Blue), each from 0 to 255.

# Background gradient (top -> bottom)
BG_TOP        = (22, 18, 46)
BG_BOTTOM     = (10,  9, 26)
BG_COLOR      = BG_TOP                  # fallback solid color (kept for compatibility)

# Glass cards / panels
PANEL_COLOR   = (38, 36, 70)
PANEL_TOP     = (52, 48, 92)
PANEL_BOTTOM  = (32, 30, 60)
PANEL_BORDER  = (120, 110, 200)
SOFT_PANEL    = (62, 58, 110)

# Text
WHITE         = (244, 246, 255)
MUTED         = (180, 188, 220)
DIM           = (130, 138, 175)
INK_DARK      = (24, 22, 50)

# Accent gradients (used for buttons and highlights). Each is (light, dark).
PROFILE_COLOR  = ( 96, 150, 255)    # blue
PROFILE_HOVER  = (140, 185, 255)
PROFILE_TOP    = (130, 180, 255)
PROFILE_BOT    = ( 60, 110, 220)

TEACHER_COLOR  = (255, 150,  88)    # orange
TEACHER_HOVER  = (255, 185, 130)
TEACHER_TOP    = (255, 180, 120)
TEACHER_BOT    = (225, 110,  60)

STUDENT_COLOR  = (100, 220, 150)    # green
STUDENT_HOVER  = (140, 240, 180)
STUDENT_TOP    = (140, 240, 180)
STUDENT_BOT    = ( 60, 180, 110)

NEUTRAL_COLOR  = (100, 105, 135)
NEUTRAL_HOVER  = (130, 138, 175)
NEUTRAL_TOP    = (118, 124, 160)
NEUTRAL_BOT    = ( 70,  76, 105)

GOOD_GREEN     = STUDENT_COLOR
BAD_RED        = (245, 105, 105)
GOLD           = (250, 200,  90)

# Decorative accent colors for floating shapes and confetti
ACCENT_PURPLE  = (170, 110, 255)
ACCENT_PINK    = (255, 110, 180)
ACCENT_CYAN    = (110, 220, 255)

# Where to find lessons and where to save progress.
#
# When the game runs from source, assets sit alongside `main.py`. When
# PyInstaller bundles us into an .exe, they are unpacked into a temp
# folder pointed at by `sys._MEIPASS`. `_resources_root()` resolves to
# whichever is appropriate so the rest of the code can stay platform-
# agnostic.
def _resources_root():
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent


def _user_data_dir():
    """A writeable per-user folder for the SQLite save file."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / "do-o-english"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "do-o-english"
    return Path.home() / ".local" / "share" / "do-o-english"


ROOT_DIR    = _resources_root()
CONTENT_DIR = ROOT_DIR / "content" / "en-a1" / "unit-01-cafe"
DB_PATH     = _user_data_dir() / "progress.db"

# A single comma-separated list of font names. pygame.SysFont tries them
# in order and falls back to its default if none are installed.
UI_FONT_STACK = "Inter,Segoe UI,Helvetica,DejaVu Sans,Arial"

# ---- Multiplayer constants -----------------------------------------------

MP_DEFAULT_NAME = "Player"
MP_HOST_ID = 0                  # peer id 0 is always the host's own player

MP_MODES = ["race", "coop", "turn"]
MP_MODE_LABELS = {
    "race": "Race — finish first wins",
    "coop": "Co-op — first to click answers for the team",
    "turn": "Turns — players take turns answering",
}

# Only single-click exercise types are supported in coop / turn modes
# (word_order needs N clicks per question; tap_pairs needs pairing,
# both too messy to sync in a first cut). Race uses each player's
# local copy of the lesson so it handles every type.
MP_SINGLECLICK_TYPES = {"multiple_choice", "fill_blank", "listen_select"}

# ---- Shop catalogue ------------------------------------------------------
# `id` is what gets stored in the inventory table; `desc` is shown in the
# shop UI; `use_label` is what the button inside a lesson shows.
SHOP_ITEMS = [
    {
        "id":        "hint",
        "name":      "Hint Token",
        "price":     50,
        "icon":      "?",
        "color":     (90, 195, 255),
        "desc":      "Reveal the correct answer to the current question. Counts as correct.",
        "use_label": "Hint",
    },
    {
        "id":        "skip",
        "name":      "Skip Pass",
        "price":     30,
        "icon":      "»",
        "color":     (250, 200, 90),
        "desc":      "Skip a question you don't want to deal with. Doesn't change your score.",
        "use_label": "Skip",
    },
    {
        "id":        "double_xp",
        "name":      "XP Doubler",
        "price":     120,
        "icon":      "×2",
        "color":     (200, 110, 230),
        "desc":      "Your next lesson rewards twice the usual XP.",
        "use_label": "",
    },
]
SHOP_ITEMS_BY_ID = {item["id"]: item for item in SHOP_ITEMS}


# ============================================================
# 3. DATABASE
# ============================================================
# We use SQLite, which is just a file on disk. We store two tables:
#   users: each profile (name, role, class, xp)
#   done : which lessons each user has finished
# ============================================================

def hash_password(plain_text):
    """
    Turn a password into a long fixed-length string ('hash').
    We never store the real password, only the hash, so even if
    someone reads the file they can't see the original password.
    """
    return hashlib.sha256(plain_text.encode("utf-8")).hexdigest()


def open_database():
    """Open (or create) the SQLite file and make sure the tables exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name  TEXT NOT NULL,
            class_name TEXT NOT NULL,
            password   TEXT NOT NULL DEFAULT '',
            xp         INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS done (
            user_id   INTEGER NOT NULL,
            lesson_id TEXT NOT NULL,
            score     INTEGER NOT NULL,
            UNIQUE(user_id, lesson_id)
        )
    """)
    # Shop inventory — one row per (user, item) with the quantity owned.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id  INTEGER NOT NULL,
            item_id  TEXT    NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_id)
        )
    """)

    # Add the password column to old databases that don't have it yet.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "password" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password TEXT NOT NULL DEFAULT ''")

    conn.commit()
    return conn


def get_inventory(conn, user_id):
    """Return {item_id: quantity} for the given user."""
    rows = conn.execute(
        "SELECT item_id, quantity FROM inventory WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    return {row["item_id"]: int(row["quantity"]) for row in rows}


def add_to_inventory(conn, user_id, item_id, delta=1):
    """Upsert: bump (or create) the inventory row for `item_id` by `delta`."""
    conn.execute(
        """
        INSERT INTO inventory (user_id, item_id, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, item_id) DO UPDATE
            SET quantity = MAX(0, quantity + excluded.quantity)
        """,
        (user_id, item_id, delta),
    )
    conn.commit()


def spend_xp(conn, user_id, amount):
    """Atomically deduct XP if the user has enough. Returns True on success."""
    cur = conn.execute(
        "UPDATE users SET xp = xp - ? WHERE id = ? AND xp >= ?",
        (amount, user_id, amount),
    )
    conn.commit()
    return cur.rowcount > 0


def list_users(conn):
    """Return every saved user as a list of dictionaries."""
    rows = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def create_user(conn, role, first_name, last_name, class_name, password):
    """Save a new user (with hashed password) and return their id."""
    cursor = conn.execute(
        """
        INSERT INTO users (role, first_name, last_name, class_name, password)
        VALUES (?, ?, ?, ?, ?)
        """,
        (role, first_name, last_name, class_name, hash_password(password)),
    )
    conn.commit()
    return cursor.lastrowid


def add_xp(conn, user_id, amount):
    """Give the user some XP."""
    conn.execute("UPDATE users SET xp = xp + ? WHERE id = ?", (amount, user_id))
    conn.commit()


def mark_lesson_done(conn, user_id, lesson_id, score):
    """Remember that this user finished this lesson with this score."""
    conn.execute(
        "INSERT OR REPLACE INTO done (user_id, lesson_id, score) VALUES (?, ?, ?)",
        (user_id, lesson_id, score),
    )
    conn.commit()


def finished_lesson_ids(conn, user_id):
    """Return a set with the lesson ids this user has already finished."""
    rows = conn.execute(
        "SELECT lesson_id FROM done WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {row["lesson_id"] for row in rows}


# ============================================================
# 4. CONTENT — load the .json lessons
# ============================================================

def load_lessons():
    """
    Read every .json lesson in content/en-a1/unit-01-cafe/lessons/ and
    return them in the order listed by meta.json.
    """
    lessons_by_id = {}
    lessons_dir = CONTENT_DIR / "lessons"
    if lessons_dir.exists():
        for json_path in sorted(lessons_dir.glob("*.json")):
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lessons_by_id[data["id"]] = data

    meta_path = CONTENT_DIR / "meta.json"
    ordered_ids = []
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        ordered_ids = meta.get("lessonIds") or meta.get("lesson_ids") or []

    ordered_lessons = []
    for lesson_id in ordered_ids:
        if lesson_id in lessons_by_id:
            ordered_lessons.append(lessons_by_id[lesson_id])
    return ordered_lessons


# ============================================================
# 5. DRAW HELPERS
# ============================================================
# Small reusable functions that build the "polished" look:
#   - gradient fills
#   - rounded panels with soft drop shadows
#   - isometric blocks (the depth in the lesson stage)
#   - a stacked cartoon avatar with shading
# ============================================================

def lerp(a, b, t):
    """Linear blend between two numbers, t in [0, 1]."""
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    """Linear blend between two RGB colors."""
    return (int(lerp(c1[0], c2[0], t)),
            int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def vertical_gradient(width, height, top_color, bottom_color):
    """Return a Surface filled with a smooth top-to-bottom gradient."""
    surf = pygame.Surface((width, height)).convert()
    for y in range(height):
        t = y / max(height - 1, 1)
        c = lerp_color(top_color, bottom_color, t)
        pygame.draw.line(surf, c, (0, y), (width, y))
    return surf


def rounded_gradient_surface(width, height, top, bottom, radius):
    """A rounded-rectangle surface filled with a vertical gradient."""
    g = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(height):
        t = y / max(height - 1, 1)
        c = lerp_color(top, bottom, t)
        pygame.draw.line(g, (*c, 255), (0, y), (width, y))

    mask = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, width, height), border_radius=radius)
    g.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return g


def draw_drop_shadow(surface, rect, *, radius=18, alpha=110, offset=(0, 10), spread=18):
    """
    Paint a soft, blurred drop shadow behind the rectangle `rect`.
    The blur is faked by smoothscaling a small surface up.
    """
    ox, oy = offset
    sw = rect.w + spread * 2
    sh = rect.h + spread * 2
    shadow = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.rect(
        shadow, (0, 0, 0, alpha),
        (spread, spread, rect.w, rect.h),
        border_radius=radius + spread // 2,
    )
    small = pygame.transform.smoothscale(shadow, (max(sw // 4, 1), max(sh // 4, 1)))
    shadow = pygame.transform.smoothscale(small, (sw, sh))
    surface.blit(shadow, (rect.x - spread + ox, rect.y - spread + oy))


def draw_panel(surface, rect, *,
               top=PANEL_TOP, bottom=PANEL_BOTTOM,
               radius=20, border=PANEL_BORDER, border_alpha=70,
               shadow=True, shadow_offset=(0, 12), shadow_alpha=120):
    """A gradient-filled rounded panel with optional shadow + soft border."""
    if shadow:
        draw_drop_shadow(surface, rect, radius=radius, alpha=shadow_alpha,
                         offset=shadow_offset, spread=20)
    panel = rounded_gradient_surface(rect.w, rect.h, top, bottom, radius)
    surface.blit(panel, rect.topleft)
    if border_alpha > 0:
        border_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        pygame.draw.rect(border_surf, (*border, border_alpha),
                         (0, 0, rect.w, rect.h), width=1, border_radius=radius)
        surface.blit(border_surf, rect.topleft)


def draw_glass(surface, rect, *, radius=18, alpha=40):
    """A subtle translucent overlay — useful for highlights on cards."""
    glass = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(glass, (255, 255, 255, alpha),
                     (0, 0, rect.w, rect.h), border_radius=radius)
    surface.blit(glass, rect.topleft)


def draw_text(screen, text, font, color, x, y, center=True):
    """Draw a single line of text. If center is True, (x, y) is the center."""
    surface = font.render(text, True, color)
    rect = surface.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    screen.blit(surface, rect)


def draw_text_with_glow(screen, text, font, color, x, y, *,
                        glow_color=(120, 160, 255), glow_alpha=140, glow_size=4):
    """Render text with a soft colored halo behind it.

    The halo is produced by drawing the text once into a padded surface and
    blurring it via downscale/upscale, so there is no readable ghost copy of
    the text behind the foreground.
    """
    text_surf = font.render(text, True, color)
    rect = text_surf.get_rect(center=(x, y))

    pad = max(6, glow_size * 4)
    g_w = text_surf.get_width() + pad * 2
    g_h = text_surf.get_height() + pad * 2
    glow = pygame.Surface((g_w, g_h), pygame.SRCALPHA)
    glow_text = font.render(text, True, glow_color)
    glow_text.set_alpha(glow_alpha)
    glow.blit(glow_text, (pad, pad))

    shrink = max(2, glow_size)
    small = pygame.transform.smoothscale(
        glow, (max(1, g_w // shrink), max(1, g_h // shrink))
    )
    blurred = pygame.transform.smoothscale(small, (g_w, g_h))

    screen.blit(blurred, (rect.x - pad, rect.y - pad))
    screen.blit(text_surf, rect)


def _ellipsize(text, font, max_width):
    """Trim ``text`` so it renders within ``max_width`` pixels, adding an ellipsis if cut."""
    if not text or font.size(text)[0] <= max_width:
        return text
    ellipsis = "…"
    if font.size(ellipsis)[0] > max_width:
        return ""
    while text and font.size(text + ellipsis)[0] > max_width:
        text = text[:-1]
    return text + ellipsis


def wrap_lines(text, font, max_width):
    """Break a long string into lines that fit in `max_width` pixels."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        attempt = (current + " " + word).strip()
        if font.size(attempt)[0] <= max_width:
            current = attempt
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_button_label(screen, text, font, rect, color=WHITE, pad=16):
    """
    Draw `text` centered inside `rect`. Wraps onto multiple lines if
    needed, and shrinks the font progressively if a long single word
    still wouldn't fit. Stops cleanly at 14pt — anything past that we
    just truncate so the layout never explodes.
    """
    inner_w = max(40, rect.w - pad * 2)
    sizes = (font.get_height(), 20, 18, 16, 14)
    f = font
    lines = wrap_lines(text, f, inner_w)
    for target_pt in sizes[1:]:
        if all(f.size(ln)[0] <= inner_w for ln in lines) and \
                len(lines) * (f.get_height() + 2) <= rect.h - 6:
            break
        f = pygame.font.SysFont(UI_FONT_STACK, target_pt, bold=True)
        lines = wrap_lines(text, f, inner_w)

    line_h = f.get_height() + 2
    total_h = line_h * len(lines)
    y = rect.y + (rect.h - total_h) // 2
    for line in lines:
        surf = f.render(line, True, color)
        screen.blit(surf, surf.get_rect(centerx=rect.centerx, top=y))
        y += line_h


# ---- Isometric primitives (the "3D" feel) ----------------------

def draw_iso_cube(surface, cx, cy, size, hue):
    """A small isometric cube of color `hue` floating in the scene."""
    top   = hue
    right = tuple(int(c * 0.78) for c in hue)
    left  = tuple(int(c * 0.55) for c in hue)
    s = size
    top_quad   = [(cx, cy - s), (cx + s, cy - s // 2),
                  (cx, cy),     (cx - s, cy - s // 2)]
    left_quad  = [(cx - s, cy - s // 2), (cx, cy),
                  (cx, cy + s),          (cx - s, cy + s // 2)]
    right_quad = [(cx, cy), (cx + s, cy - s // 2),
                  (cx + s, cy + s // 2), (cx, cy + s)]
    pygame.draw.polygon(surface, left,  left_quad)
    pygame.draw.polygon(surface, right, right_quad)
    pygame.draw.polygon(surface, top,   top_quad)


def draw_avatar(surface, cx, cy, t=0.0, mood="happy"):
    """
    A small cartoon "barista" character built from stacked, shaded shapes.
    Pseudo-3D: head sphere with bright highlight, body capsule with gradient,
    and a soft ellipse shadow underneath.
    """
    bob = math.sin(t * 2.4) * 4

    # Shadow on the floor
    shadow = pygame.Surface((160, 30), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 110), (0, 0, 160, 30))
    surface.blit(shadow, (cx - 80, cy + 96))

    # Body — gradient capsule
    body_rect = pygame.Rect(cx - 46, cy + bob - 6, 92, 104)
    body = rounded_gradient_surface(body_rect.w, body_rect.h,
                                    (140, 200, 255), (50, 100, 210), 40)
    surface.blit(body, body_rect.topleft)

    # Body highlight stripe (fake specular)
    hl = pygame.Surface((34, 60), pygame.SRCALPHA)
    pygame.draw.ellipse(hl, (255, 255, 255, 60), (0, 0, 34, 60))
    surface.blit(hl, (cx - 30, cy + bob + 8))

    # Apron emblem
    pygame.draw.circle(surface, (255, 235, 200), (cx, cy + bob + 50), 12)
    pygame.draw.circle(surface, (220, 170, 110), (cx, cy + bob + 50), 12, 2)

    # Head — sphere with shading
    head_cx, head_cy, r = cx, cy + bob - 38, 38
    pygame.draw.circle(surface, (255, 220, 180), (head_cx, head_cy), r)
    pygame.draw.circle(surface, (255, 240, 215), (head_cx - 10, head_cy - 10), r - 10)
    pygame.draw.circle(surface, (210, 165, 120), (head_cx, head_cy), r, 2)

    # Hair / cap
    cap_rect = pygame.Rect(head_cx - r, head_cy - r - 6, r * 2, r + 4)
    cap_surf = pygame.Surface(cap_rect.size, pygame.SRCALPHA)
    pygame.draw.ellipse(cap_surf, (60, 60, 120, 255),
                        (0, 0, cap_rect.w, cap_rect.h))
    cap_clip = pygame.Surface(cap_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(cap_clip, (255, 255, 255, 255),
                     (0, 0, cap_rect.w, cap_rect.h // 2 + 2))
    cap_surf.blit(cap_clip, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surface.blit(cap_surf, cap_rect.topleft)

    # Eyes
    eye_y = head_cy + 2
    if mood == "sad":
        pygame.draw.arc(surface, (35, 25, 55), (head_cx - 16, eye_y - 6, 12, 12), 0.2, 2.9, 2)
        pygame.draw.arc(surface, (35, 25, 55), (head_cx +  4, eye_y - 6, 12, 12), 0.2, 2.9, 2)
    else:
        pygame.draw.circle(surface, (35, 25, 55), (head_cx - 11, eye_y), 4)
        pygame.draw.circle(surface, (35, 25, 55), (head_cx + 11, eye_y), 4)
        # Eye highlights
        pygame.draw.circle(surface, (255, 255, 255), (head_cx - 10, eye_y - 1), 1)
        pygame.draw.circle(surface, (255, 255, 255), (head_cx + 12, eye_y - 1), 1)

    # Mouth
    if mood == "sad":
        pygame.draw.arc(surface, (70, 40, 80), (head_cx - 12, eye_y + 14, 24, 12), 3.4, 6.0, 2)
    else:
        pygame.draw.arc(surface, (90, 45, 80), (head_cx - 12, eye_y + 6, 24, 14), 3.4, 6.0, 3)


def draw_grass_mound(surface, cx, cy, w=560, h=86):
    """
    A bright Duolingo-style grass hill the character stands on.
    Built from three stacked ellipses for cheap rim-lighting.
    """
    # Soft ground shadow (blurred via downscale/upscale).
    sh = pygame.Surface((w + 80, 34), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (0, 0, 0, 140), (0, 0, w + 80, 34))
    small = pygame.transform.smoothscale(sh, ((w + 80) // 4, 9))
    sh = pygame.transform.smoothscale(small, (w + 80, 34))
    surface.blit(sh, (cx - (w + 80) // 2, cy + h // 2 - 14))

    pygame.draw.ellipse(surface, (38, 120, 60),
                        (cx - w // 2, cy - h // 2, w, h))
    pygame.draw.ellipse(surface, (95, 210, 110),
                        (cx - w // 2 + 6, cy - h // 2 - 6, w - 12, h - 6))
    pygame.draw.ellipse(surface, (170, 245, 150),
                        (cx - w // 3, cy - h // 2 + 2, w * 2 // 3, h // 5))


def draw_leaf(surface, cx, cy, size=14, color=(110, 220, 110), tilt_deg=0):
    """A tiny stylized leaf — sprinkled around the grass for charm."""
    leaf = pygame.Surface((size * 3, size * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(leaf, color, (0, 0, size * 3, size * 2))
    pygame.draw.line(leaf, (50, 140, 70),
                     (size // 2, size), (size * 3 - size // 2, size), 2)
    rot = pygame.transform.rotate(leaf, tilt_deg)
    surface.blit(rot, rot.get_rect(center=(cx, cy)).topleft)


def draw_speech_bubble(surface, anchor, text, font, *,
                       max_width=260, padding=14, radius=18,
                       tail_side="left",
                       bubble_color=(255, 255, 255),
                       outline_color=(40, 40, 60),
                       text_color=(40, 40, 60)):
    """
    A white rounded speech bubble with a triangular tail pointing toward
    `anchor` (x, y). `tail_side="left"` puts the bubble to the RIGHT of
    the anchor (the tail sticks out of its LEFT side toward the character).
    """
    lines = wrap_lines(text, font, max_width)
    if not lines:
        return
    line_h = font.get_height() + 2
    content_w = max(font.size(line)[0] for line in lines)
    bw = content_w + padding * 2
    bh = line_h * len(lines) + padding * 2 - 2

    if tail_side == "left":
        bx = anchor[0] + 26
        by = anchor[1] - bh // 2
    else:
        bx = anchor[0] - 26 - bw
        by = anchor[1] - bh // 2

    rect = pygame.Rect(bx, by, bw, bh)
    draw_drop_shadow(surface, rect, radius=radius,
                     alpha=110, offset=(0, 8), spread=14)
    pygame.draw.rect(surface, bubble_color, rect, border_radius=radius)
    pygame.draw.rect(surface, outline_color, rect, width=2, border_radius=radius)

    # Triangular tail — drawn slightly overlapping the bubble so the seam hides.
    if tail_side == "left":
        tip = (anchor[0] + 6, anchor[1])
        top = (bx + 6, anchor[1] - 14)
        bot = (bx + 6, anchor[1] + 14)
        pygame.draw.polygon(surface, bubble_color, [tip, top, bot])
        pygame.draw.line(surface, outline_color, tip, top, 2)
        pygame.draw.line(surface, outline_color, tip, bot, 2)
        # Cover the bubble's left edge inside the tail mouth.
        pygame.draw.line(surface, bubble_color,
                         (bx + 1, anchor[1] - 13),
                         (bx + 1, anchor[1] + 13), 4)
    else:
        tip = (anchor[0] - 6, anchor[1])
        top = (bx + bw - 6, anchor[1] - 14)
        bot = (bx + bw - 6, anchor[1] + 14)
        pygame.draw.polygon(surface, bubble_color, [tip, top, bot])
        pygame.draw.line(surface, outline_color, tip, top, 2)
        pygame.draw.line(surface, outline_color, tip, bot, 2)
        pygame.draw.line(surface, bubble_color,
                         (bx + bw - 1, anchor[1] - 13),
                         (bx + bw - 1, anchor[1] + 13), 4)

    y = by + padding
    for line in lines:
        surf = font.render(line, True, text_color)
        surface.blit(surf, (bx + padding, y))
        y += line_h


# ---- Duo-style reaction lines ----------------------------------
DUO_LINES = {
    "default": [
        "You got this!",
        "Take your time.",
        "Pick the right one!",
        "Read carefully…",
        "Let's go!",
    ],
    "happy": [
        "Boom! Nailed it.",
        "Excellent work!",
        "You're on fire!",
        "Nice one!",
        "Yes! Keep going.",
    ],
    "sad": [
        "Oof, not quite.",
        "It happens — keep going!",
        "Almost! Try the next one.",
        "Don't give up!",
        "No worries, you'll get it.",
    ],
}


def _load_face_sprite(filename_candidates, target_height=220):
    """
    Try each filename in order, load the first one that exists,
    crop it to its non-transparent bounding box (so PNGs with different
    canvas sizes still feel the same size on screen), and rescale to
    `target_height` pixels. Returns None if nothing loads.
    """
    for name in filename_candidates:
        path = ROOT_DIR / name
        if not path.exists():
            continue
        try:
            img = pygame.image.load(str(path)).convert_alpha()
        except Exception:
            continue
        # get_bounding_rect() returns the smallest rect containing all
        # non-transparent pixels. For RGB images without alpha it just
        # returns the whole image, which is fine.
        bbox = img.get_bounding_rect()
        if bbox.w > 0 and bbox.h > 0:
            cropped = pygame.Surface(bbox.size, pygame.SRCALPHA)
            cropped.blit(img, (0, 0), bbox)
        else:
            cropped = img
        w, h = cropped.get_size()
        if h == 0:
            return None
        scale = target_height / h
        return pygame.transform.smoothscale(
            cropped, (max(1, int(w * scale)), target_height)
        )
    return None


def draw_xp_gem(surface, cx, cy, size=14, t=0.0):
    """A small floating diamond — used as decoration around XP labels."""
    bob = math.sin(t * 3) * 2
    cy += bob
    pts = [(cx, cy - size), (cx + size * 3 // 4, cy),
           (cx, cy + size), (cx - size * 3 // 4, cy)]
    pygame.draw.polygon(surface, (250, 200, 90), pts)
    pygame.draw.polygon(surface, (255, 230, 150),
                        [(cx, cy - size), (cx + size * 3 // 8, cy - size // 4),
                         (cx, cy), (cx - size * 3 // 8, cy - size // 4)])
    pygame.draw.polygon(surface, (180, 130, 30), pts, 2)


# ============================================================
# 6. BACKGROUND — animated parallax shapes
# ============================================================

class AnimatedBackground:
    """
    A slowly drifting field of soft blobs and small isometric cubes.
    Drawn behind every screen to give the whole app a sense of depth.
    """

    def __init__(self, width, height):
        self.width  = width
        self.height = height
        self.gradient = vertical_gradient(width, height, BG_TOP, BG_BOTTOM)
        # Pre-render a star/glow layer once, for cheap parallax.
        self._stars = pygame.Surface((width, height), pygame.SRCALPHA)
        for _ in range(110):
            x = random.randint(0, width)
            y = random.randint(0, height)
            r = random.choice([1, 1, 1, 2, 2, 3])
            alpha = random.randint(40, 140)
            pygame.draw.circle(self._stars, (220, 220, 255, alpha), (x, y), r)

        # Floating "blob" particles (warm/cool soft circles)
        palette = [
            (90, 130, 240),
            (170, 110, 255),
            (255, 110, 180),
            (110, 220, 255),
            (90,  200, 150),
        ]
        self.blobs = []
        for _ in range(14):
            self.blobs.append({
                "x":     random.uniform(0, width),
                "y":     random.uniform(0, height),
                "r":     random.randint(60, 160),
                "color": random.choice(palette),
                "alpha": random.randint(14, 30),
                "vx":    random.uniform(-6, 6),
                "vy":    random.uniform(-4, 4),
                "phase": random.uniform(0, math.tau),
            })

        # Small floating iso cubes (rare, twinkly)
        cube_palette = [ACCENT_PURPLE, ACCENT_PINK, ACCENT_CYAN, GOLD]
        self.cubes = []
        for _ in range(8):
            self.cubes.append({
                "x":     random.uniform(0, width),
                "y":     random.uniform(0, height),
                "size":  random.randint(6, 12),
                "color": random.choice(cube_palette),
                "vx":    random.uniform(-8, 8),
                "vy":    random.uniform(-6, 6),
                "phase": random.uniform(0, math.tau),
            })

    def update(self, dt):
        for b in self.blobs:
            b["x"] = (b["x"] + b["vx"] * dt) % self.width
            b["y"] = (b["y"] + b["vy"] * dt) % self.height
            b["phase"] += dt * 0.6
        for c in self.cubes:
            c["x"] = (c["x"] + c["vx"] * dt) % self.width
            c["y"] = (c["y"] + c["vy"] * dt) % self.height
            c["phase"] += dt * 1.2

    def draw(self, surface):
        surface.blit(self.gradient, (0, 0))
        surface.blit(self._stars, (0, 0))

        blob_layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for b in self.blobs:
            pulse = math.sin(b["phase"]) * 0.15 + 1.0
            r = int(b["r"] * pulse)
            pygame.draw.circle(blob_layer, (*b["color"], b["alpha"]),
                               (int(b["x"]), int(b["y"])), r)
        # Soft blur on the blob layer
        small = pygame.transform.smoothscale(
            blob_layer, (self.width // 4, self.height // 4))
        blob_layer = pygame.transform.smoothscale(small, (self.width, self.height))
        surface.blit(blob_layer, (0, 0))

        for c in self.cubes:
            bob = math.sin(c["phase"]) * 4
            draw_iso_cube(surface, int(c["x"]), int(c["y"] + bob),
                          c["size"], c["color"])


# ============================================================
# 7. UI WIDGETS — Button & TextInput
# ============================================================

def _choose_choice_grid(choices, font, *, narrow=False, words=False):
    """
    Decide how to lay out an answer-button grid so long text doesn't
    spill into its neighbour. Returns (cols, button_w, button_h).
      - `narrow=True` shrinks widths to leave room for the MP scoreboard.
      - `words=True` (used by `word_order`) packs short word tokens into
        a tighter grid (2–5 cols, never more than 4 rows) so long
        sentences don't blow past the bottom of the screen.
    """
    if words and choices:
        widest = max(font.size(w)[0] for w in choices)
        btn_w = max(110, min(220, widest + 48))
        # Use the fewest cols that keep us under 4 rows.
        n = len(choices)
        for cols in (2, 3, 4, 5):
            if (n + cols - 1) // cols <= 4:
                break
        return cols, btn_w, 50

    short_w  = 260 if narrow else 300
    wide_w   = 560 if narrow else 640
    threshold = short_w - 28          # text-pixels that fit in a short button
    long = any(font.size(c)[0] > threshold for c in choices)
    if long or len(choices) <= 3:
        return 1, wide_w, 76          # one column, 2-line capable height
    return 2, short_w, 56


def _grade_choice(exercise, choice_index):
    """
    True if `choice_index` is the right answer for `exercise`. Handles
    both numeric-index answers (multiple_choice / listen_select) and
    string answers (fill_blank, matched case-insensitively).
    """
    answer = exercise.get("answer", 0)
    if exercise.get("type") == "fill_blank":
        chosen = exercise["choices"][choice_index]
        return chosen.strip().lower() == str(answer).strip().lower()
    return choice_index == int(answer)


class Button:
    """
    A raised, gradient-filled, clickable rectangle with a label.
    Three styles:
      - "primary"  : large accent button (CTA)
      - "ghost"    : translucent secondary button
      - "card"     : full-width lesson card (used on the hub)
    """

    def __init__(self, text, x, y, w, h, base_color, hover_color, on_click,
                 *, style="primary", icon=None, sub_text="", badge=""):
        self.text         = text
        self.sub_text     = sub_text
        self.badge        = badge          # small label, e.g. "DONE"
        self.icon         = icon           # short string drawn as a circular icon
        self.rect         = pygame.Rect(x, y, w, h)
        self.base_color   = base_color
        self.hover_color  = hover_color
        self.on_click     = on_click
        self.style        = style
        self._pressed     = False
        self._press_t     = 0.0            # remaining bounce time after release
        self._hover_t     = 0.0            # smoothed hover factor in [0, 1]

    # ---- color helpers --------------------------------------------------
    def _top_bottom(self, hovered):
        """Pick the (top, bottom) gradient colors for this button."""
        if self.base_color == PROFILE_COLOR:   t, b = PROFILE_TOP, PROFILE_BOT
        elif self.base_color == TEACHER_COLOR: t, b = TEACHER_TOP, TEACHER_BOT
        elif self.base_color == STUDENT_COLOR: t, b = STUDENT_TOP, STUDENT_BOT
        elif self.base_color == NEUTRAL_COLOR: t, b = NEUTRAL_TOP, NEUTRAL_BOT
        elif self.base_color == GOOD_GREEN:    t, b = STUDENT_TOP, STUDENT_BOT
        else:
            t = tuple(min(255, c + 30) for c in self.base_color)
            b = tuple(max(  0, c - 30) for c in self.base_color)
        if hovered:
            t = lerp_color(t, (255, 255, 255), 0.18)
            b = lerp_color(b, (255, 255, 255), 0.08)
        return t, b

    # ---- main drawing ---------------------------------------------------
    def draw(self, screen, font):
        mouse_pos = pygame.mouse.get_pos()
        eliminated = getattr(self, "_eliminated", False)
        hovered = (not eliminated) and self.rect.collidepoint(mouse_pos)

        # Smooth hover and press animation
        target = 1.0 if hovered else 0.0
        self._hover_t += (target - self._hover_t) * 0.25
        if self._press_t > 0:
            self._press_t = max(0.0, self._press_t - 1 / FPS)

        # When held down OR within the small post-click bounce, sink the button.
        sink = 0
        if self._pressed and hovered:
            sink = 4
        elif self._press_t > 0:
            sink = int(4 * self._press_t)
        # Hover lift (a tiny upward float)
        lift = int(-2 * self._hover_t)

        draw_rect = self.rect.move(0, sink + lift)

        if self.style == "ghost":
            self._draw_ghost(screen, font, draw_rect, hovered)
        elif self.style == "card":
            self._draw_card(screen, font, draw_rect, hovered)
        else:
            self._draw_primary(screen, font, draw_rect, hovered)

        # Visually mark an eliminated answer: dim overlay + strikethrough.
        if eliminated:
            radius = max(14, draw_rect.h // 2)
            overlay = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(overlay, (10, 10, 20, 160),
                             (0, 0, draw_rect.w, draw_rect.h),
                             border_radius=radius)
            screen.blit(overlay, draw_rect.topleft)
            # Red strikethrough across the middle.
            mid_y = draw_rect.centery
            pygame.draw.line(screen, (220, 90, 90),
                             (draw_rect.x + 24, mid_y),
                             (draw_rect.right - 24, mid_y), 3)

    def _draw_primary(self, screen, font, rect, hovered):
        radius = max(14, rect.h // 2)
        draw_drop_shadow(screen, rect, radius=radius,
                         alpha=160 if hovered else 130,
                         offset=(0, 8 if hovered else 6), spread=14)
        top, bot = self._top_bottom(hovered)
        body = rounded_gradient_surface(rect.w, rect.h, top, bot, radius)
        screen.blit(body, rect.topleft)
        gloss = pygame.Surface((rect.w - 8, rect.h // 2), pygame.SRCALPHA)
        pygame.draw.rect(gloss, (255, 255, 255, 55),
                         (0, 0, rect.w - 8, rect.h // 2),
                         border_radius=radius - 4)
        screen.blit(gloss, (rect.x + 4, rect.y + 3))
        border = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(border, (255, 255, 255, 60),
                         (0, 0, rect.w, rect.h), width=1, border_radius=radius)
        screen.blit(border, rect.topleft)
        _draw_button_label(screen, self.text, font, rect)

    def _draw_ghost(self, screen, font, rect, hovered):
        radius = max(14, rect.h // 2)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        alpha = 80 if hovered else 50
        pygame.draw.rect(bg, (255, 255, 255, alpha),
                         (0, 0, rect.w, rect.h), border_radius=radius)
        pygame.draw.rect(bg, (255, 255, 255, 120),
                         (0, 0, rect.w, rect.h), width=1, border_radius=radius)
        screen.blit(bg, rect.topleft)
        _draw_button_label(screen, self.text, font, rect)

    def _draw_card(self, screen, font, rect, hovered):
        radius = 18
        draw_drop_shadow(screen, rect, radius=radius,
                         alpha=140 if hovered else 110,
                         offset=(0, 10), spread=22)
        # Background card (cool dark)
        top = lerp_color(PANEL_TOP, self.base_color, 0.20 if hovered else 0.08)
        bot = lerp_color(PANEL_BOTTOM, self.base_color, 0.06)
        body = rounded_gradient_surface(rect.w, rect.h, top, bot, radius)
        screen.blit(body, rect.topleft)

        # Accent stripe down the left edge
        stripe = pygame.Surface((6, rect.h - 24), pygame.SRCALPHA)
        pygame.draw.rect(stripe, (*self.base_color, 230),
                         (0, 0, 6, rect.h - 24), border_radius=3)
        screen.blit(stripe, (rect.x + 14, rect.y + 12))

        # Icon bubble (a circle with one character/emoji-ish)
        if self.icon:
            ic_cx = rect.x + 56
            ic_cy = rect.centery
            pygame.draw.circle(screen, lerp_color(self.base_color, (0, 0, 0), 0.4),
                               (ic_cx + 2, ic_cy + 2), 22)
            pygame.draw.circle(screen, self.base_color, (ic_cx, ic_cy), 22)
            pygame.draw.circle(screen, lerp_color(self.base_color, (255, 255, 255), 0.6),
                               (ic_cx - 6, ic_cy - 6), 6)
            ic_font = pygame.font.SysFont(UI_FONT_STACK, 22, bold=True)
            label = ic_font.render(self.icon, True, INK_DARK)
            screen.blit(label, label.get_rect(center=(ic_cx, ic_cy + 1)))

        # Reserve right-side area for the badge / chevron so text never collides.
        if self.badge:
            badge_font = pygame.font.SysFont(UI_FONT_STACK, 14, bold=True)
            bw = badge_font.size(self.badge)[0] + 22
            right_reserve = bw + 28
        else:
            right_reserve = 44

        text_x = rect.x + 96
        max_text_w = max(80, rect.right - text_x - right_reserve)

        # Title
        title_font = pygame.font.SysFont(UI_FONT_STACK, 22, bold=True)
        title_text = _ellipsize(self.text, title_font, max_text_w)
        title = title_font.render(title_text, True, WHITE)
        screen.blit(title, (text_x, rect.y + 14))
        # Subtitle
        if self.sub_text:
            sub_font = pygame.font.SysFont(UI_FONT_STACK, 16)
            sub_text = _ellipsize(self.sub_text, sub_font, max_text_w)
            sub = sub_font.render(sub_text, True, MUTED)
            screen.blit(sub, (text_x, rect.y + 42))

        # Badge (e.g. "DONE") on the right
        if self.badge:
            bh = 26
            bx = rect.right - bw - 16
            by = rect.centery - bh // 2
            pygame.draw.rect(screen, GOOD_GREEN, (bx, by, bw, bh), border_radius=13)
            txt = badge_font.render(self.badge, True, INK_DARK)
            screen.blit(txt, txt.get_rect(center=(bx + bw // 2, by + bh // 2)))
        else:
            # Chevron ">" to suggest the card is clickable
            cx = rect.right - 28
            cy = rect.centery
            pygame.draw.polygon(screen, MUTED,
                                [(cx, cy - 8), (cx + 8, cy), (cx, cy + 8)])

        # Hover border glow
        if hovered:
            border = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(border, (*self.base_color, 180),
                             (0, 0, rect.w, rect.h), width=2, border_radius=radius)
            screen.blit(border, rect.topleft)

    # ---- event helpers --------------------------------------------------
    def handle_event(self, event):
        """Track press/release so we can render the bounce."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._pressed = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._pressed and self.rect.collidepoint(event.pos):
                self._pressed = False
                self._press_t = 0.18
                return True
            self._pressed = False
        return False


class TextInput:
    """A rounded, glowing single-line text field with a label above it."""

    def __init__(self, x, y, w, h, label, max_chars=24, is_password=False):
        self.rect        = pygame.Rect(x, y, w, h)
        self.label       = label
        self.max_chars   = max_chars
        self.value       = ""
        self.is_focused  = False
        self.is_password = is_password
        self._caret_t    = 0.0   # for blinking caret

    def update(self, dt):
        self._caret_t = (self._caret_t + dt) % 1.0

    def draw(self, screen, font_label, font_value):
        # Label above the box.
        label_surface = font_label.render(self.label, True, MUTED)
        screen.blit(label_surface, (self.rect.x, self.rect.y - 24))

        # Soft shadow underneath (more pronounced on focus)
        draw_drop_shadow(screen, self.rect, radius=14,
                         alpha=150 if self.is_focused else 80,
                         offset=(0, 5 if self.is_focused else 3), spread=12)

        # Box background — a bit brighter when this field has focus.
        if self.is_focused:
            top = (62, 58, 110)
            bot = (44, 42,  86)
            border = (140, 200, 255, 230)
        else:
            top = (46, 44,  86)
            bot = (32, 30,  62)
            border = (95, 100, 150, 130)
        body = rounded_gradient_surface(self.rect.w, self.rect.h, top, bot, 14)
        screen.blit(body, self.rect.topleft)

        border_surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(border_surf, border,
                         (0, 0, self.rect.w, self.rect.h),
                         width=2, border_radius=14)
        screen.blit(border_surf, self.rect.topleft)

        # Decide which text to display in the box.
        if not self.value and not self.is_focused:
            shown = "(type here)"
            text_color = DIM
        else:
            if self.is_password:
                shown = "*" * len(self.value)
            else:
                shown = self.value
            if self.is_focused and self._caret_t < 0.5:
                shown += "|"
            text_color = WHITE

        text_surface = font_value.render(shown, True, text_color)
        screen.blit(
            text_surface,
            (self.rect.x + 14,
             self.rect.y + (self.rect.h - text_surface.get_height()) // 2),
        )

    def handle_event(self, event):
        """
        React to one pygame event. Returns:
          - "tab"     if the player pressed Tab while focused
          - "enter"   if the player pressed Enter while focused
          - None      otherwise
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.is_focused = self.rect.collidepoint(event.pos)

        if event.type == pygame.KEYDOWN and self.is_focused:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key == pygame.K_TAB:
                return "tab"
            elif event.key == pygame.K_RETURN:
                return "enter"
            elif event.unicode and event.unicode.isprintable():
                if len(self.value) < self.max_chars:
                    self.value += event.unicode
        return None


# ============================================================
# 8. THE GAME
# ============================================================
# The App class holds everything: the window, the fonts, the current
# screen ("menu", "form", "hub", "lesson", "summary"), and the buttons
# / text inputs that belong to whatever screen we are showing.
# ============================================================

class App:

    @staticmethod
    def _make_display(fullscreen):
        """Create the logical 1024×720 display surface.

        With `SCALED`, pygame keeps the canvas at WIDTH×HEIGHT internally
        and letterbox-scales it onto the real display. Mouse events are
        translated to logical coordinates automatically, so all of the
        existing drawing/hit-testing code is unaffected.
        """
        flags = pygame.SCALED
        if fullscreen:
            flags |= pygame.FULLSCREEN
        try:
            return pygame.display.set_mode((WIDTH, HEIGHT), flags)
        except pygame.error:
            # Some headless backends don't support SCALED — fall back.
            return pygame.display.set_mode((WIDTH, HEIGHT))

    def _toggle_fullscreen(self):
        """F11 — flip between fullscreen and a 1024×720 window."""
        self.fullscreen = not self.fullscreen
        self.screen = self._make_display(self.fullscreen)

    def __init__(self):
        # --- Set up pygame ---
        pygame.init()
        pygame.display.set_caption("do-o-english")
        # Boot in fullscreen by default. SCALED tells pygame to keep a
        # 1024×720 logical canvas and letterbox-scale it to the real
        # display, so the rest of the codebase keeps using fixed coords
        # and mouse events get translated automatically. The user can
        # press F11 to toggle to a 1024×720 window.
        self.fullscreen = os.environ.get("DOO_WINDOWED") != "1"
        self.screen = self._make_display(self.fullscreen)
        self.clock = pygame.time.Clock()
        self.running = True

        # --- Fonts ---
        self.font_title = pygame.font.SysFont(UI_FONT_STACK, 64, bold=True)
        self.font_h2    = pygame.font.SysFont(UI_FONT_STACK, 32, bold=True)
        self.font_body  = pygame.font.SysFont(UI_FONT_STACK, 22)
        self.font_bold  = pygame.font.SysFont(UI_FONT_STACK, 22, bold=True)
        self.font_small = pygame.font.SysFont(UI_FONT_STACK, 16)
        self.font_huge  = pygame.font.SysFont(UI_FONT_STACK, 84, bold=True)

        # --- Game data ---
        self.db = open_database()
        self.lessons = load_lessons()
        # Single anonymous local "Player" profile — no login UI.
        # Progress and XP still persist to the same SQLite file.
        self.user = self._ensure_local_user()

        # --- Current screen state ---
        self.scene = "hub"           # "hub" / "lesson" / "summary"
        self.buttons = []            # buttons on the current screen
        self.inputs = []             # kept around so existing draw code stays happy

        # Lesson-specific state
        self.current_lesson = None
        self.question_index = 0
        self.correct_count = 0.0
        self.picked_words = []
        self.feedback_text = ""
        self.feedback_color = WHITE
        self.feedback_t = 0.0           # remaining time to flash the avatar mood
        self.avatar_mood = "happy"      # "happy" / "sad"
        self.hint_used_this_q = False   # set by _use_hint, caps the question's credit
        self.pending_advance = None     # {t: float, correct: bool} during reveal pause
        self.summary_data = {}

        # Visual extras
        self.background = AnimatedBackground(WIDTH, HEIGHT)
        self.start_time = time.time()
        self.confetti = []              # list of dicts for the summary screen

        # What the Duolingo-style character is currently "saying" in
        # the speech bubble next to them, and which line set it came from.
        self.speech_text = ""
        self.speech_mood = "default"

        # ---- Multiplayer state ----
        # All of this is None / default until the player opens the lobby.
        self.mp_role: str | None = None         # "host" | "client" | None
        self.mp_player_name = MP_DEFAULT_NAME
        self.mp_server: HostServer | None = None
        self.mp_beacon: LobbyBeacon | None = None
        self.mp_listener: LobbyListener | None = None
        self.mp_client: ClientPeer | None = None
        # Players in the room. Each is {"id", "name", "score", "progress",
        # "finished"}. "id" 0 is the host's own player.
        self.mp_players: list[dict] = []
        self.mp_self_id = MP_HOST_ID
        self.mp_mode = "race"
        self.mp_lesson_pick = 0                  # host's lesson index choice
        self.mp_lesson: dict | None = None       # full lesson dict in play
        self.mp_question_index = 0
        self.mp_current_player_id = MP_HOST_ID
        self.mp_recent_feedback = ""
        self.mp_recent_feedback_t = 0.0
        self.mp_summary: dict | None = None
        self._mp_hosts_cache: list = []
        self._mp_hosts_refresh_t = 0.0

        # Main character — three face sprites loaded from disk.
        # We try the *png.png variants first (transparent background), then
        # the plain ones, and fall back to the hand-drawn avatar if none load.
        self.face_sprites = {
            "happy":   _load_face_sprite(
                ["happyfacepng.png",   "happyface.png"],   target_height=220),
            "sad":     _load_face_sprite(
                ["sadfacepng.png",     "sadface.png"],     target_height=220),
            "default": _load_face_sprite(
                ["defaultfacepng.png", "defaultface.png",
                 "Defaultface.png"],                       target_height=220),
        }

        self.show_hub()

    def now(self):
        """Seconds since the app started — handy for animations."""
        return time.time() - self.start_time

    def _ensure_local_user(self):
        """
        Return the first user in the local database, or create a single
        anonymous 'Player' profile if the file is empty. There is no
        login screen anymore — this is just where XP and 'lessons done'
        get saved between runs.

        The DB on disk may have come from an older / different version of
        the app that adds extra NOT NULL columns. We build the INSERT
        dynamically from PRAGMA so we only fill columns that actually
        exist, with safe defaults for the ones we know about.
        """
        users = list_users(self.db)
        if users:
            return users[0]

        cols = [row["name"] for row in self.db.execute("PRAGMA table_info(users)")]
        defaults = {
            "name":             "Player",
            "role":             "student",
            "first_name":       "Player",
            "last_name":        "",
            "class_name":       "",
            "password":         "",
            "xp":               0,
            "streak":           0,
            "hearts":           5,
            "daily_goal":       20,
            "xp_today":         0,
            "last_active_date": "",
        }
        insert_cols = [c for c in cols if c in defaults]
        placeholders = ", ".join("?" for _ in insert_cols)
        sql = f"INSERT INTO users ({', '.join(insert_cols)}) VALUES ({placeholders})"
        self.db.execute(sql, [defaults[c] for c in insert_cols])
        self.db.commit()

        users = list_users(self.db)
        return users[0] if users else None

    def quit_app(self):
        """Exit the game cleanly (used by the Quit button + Esc on the hub)."""
        self.running = False

    # ---- removed: MENU / FORM / LOGIN ----
    # The app used to start with a Log in / Register screen. We took those
    # out — the game now boots straight into the hub using a single local
    # "Player" profile (see _ensure_local_user). Progress and XP still save.

    # ----------------------------------------------------------
    # SCREEN: HUB (list of lessons)
    # ----------------------------------------------------------

    def show_hub(self):
        """Build the hub: a top bar with the user, then a list of lesson cards."""
        self.scene = "hub"
        self.buttons = []
        self.inputs = []

        done_ids = finished_lesson_ids(self.db, self.user["id"]) if self.user else set()

        # Lesson cards
        card_w = 560
        card_h = 80
        x = (WIDTH - card_w) // 2
        y = 200
        gap = 14
        icon_palette = [PROFILE_COLOR, ACCENT_PURPLE, STUDENT_COLOR, TEACHER_COLOR, ACCENT_PINK]

        for i, lesson in enumerate(self.lessons):
            is_done = lesson["id"] in done_ids
            color = icon_palette[i % len(icon_palette)]
            sub = lesson.get("npcIntro", "")
            if len(sub) > 68:
                sub = sub[:65] + "…"
            icon = str(i + 1)

            def start_this_lesson(lesson=lesson):
                self.start_lesson(lesson)

            self.buttons.append(Button(
                lesson["title"], x, y, card_w, card_h,
                color, color,
                on_click=start_this_lesson,
                style="card",
                icon=icon,
                sub_text=sub,
                badge="DONE" if is_done else "",
            ))
            y += card_h + gap

        # Bottom action bar — all three share the same baseline + height.
        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h
        mp_w, shop_w, quit_w = 170, 160, 120
        gap = 16
        mp_x = WIDTH - 24 - mp_w
        shop_x = mp_x - gap - shop_w
        self.buttons.append(Button(
            "Shop", shop_x, bar_y, shop_w, bar_h,
            TEACHER_COLOR, TEACHER_HOVER,
            on_click=self.show_shop,
        ))
        self.buttons.append(Button(
            "Multiplayer", mp_x, bar_y, mp_w, bar_h,
            ACCENT_PURPLE, ACCENT_PURPLE,
            on_click=self.show_lobby,
        ))
        self.buttons.append(Button(
            "Quit", 24, bar_y, quit_w, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.quit_app,
            style="ghost",
        ))

    def _draw_xp_chip(self, banner, xp):
        """Pill-shaped XP counter pinned to the right edge of a banner.

        The chip auto-sizes around the text and the gem, and the label
        is vertically centred. The previous version drew the text with
        `center=False` at the chip's centerline, so the bottom of every
        glyph spilled past the chip — that overhang read as a 'ghost'
        duplicate of the text against the dark background.
        """
        xp_text = f"{xp} XP"
        text_w, text_h = self.font_bold.size(xp_text)
        gem_w = 36          # gem + padding on the left
        pad_x = 22          # padding on the right of the text
        chip_w = gem_w + text_w + pad_x
        chip_h = max(44, text_h + 14)
        chip_rect = pygame.Rect(
            banner.right - chip_w - 24,
            banner.centery - chip_h // 2,
            chip_w, chip_h,
        )
        chip = pygame.Surface(chip_rect.size, pygame.SRCALPHA)
        radius = chip_h // 2
        pygame.draw.rect(chip, (250, 200, 90, 40),
                         (0, 0, chip_rect.w, chip_rect.h), border_radius=radius)
        pygame.draw.rect(chip, (250, 200, 90, 200),
                         (0, 0, chip_rect.w, chip_rect.h), width=1,
                         border_radius=radius)
        self.screen.blit(chip, chip_rect.topleft)

        draw_xp_gem(self.screen, chip_rect.x + 20, chip_rect.centery, 10,
                    t=self.now())

        text_surf = self.font_bold.render(xp_text, True, GOLD)
        text_rect = text_surf.get_rect(
            midleft=(chip_rect.x + gem_w, chip_rect.centery))
        self.screen.blit(text_surf, text_rect)

    def draw_hub(self):
        # Top banner panel
        banner = pygame.Rect(40, 30, WIDTH - 80, 120)
        draw_panel(self.screen, banner, radius=22,
                   top=lerp_color(PANEL_TOP, PROFILE_COLOR, 0.18),
                   bottom=PANEL_BOTTOM)
        draw_glass(self.screen, banner, radius=22, alpha=22)

        # Small happy-face badge as the app's mascot on the left.
        face = self.face_sprites.get("default") or self.face_sprites.get("happy")
        text_x = banner.x + 32
        if face is not None:
            badge_h = banner.h - 32
            scale = badge_h / face.get_height()
            mini_w = max(1, int(face.get_width() * scale))
            mini = pygame.transform.smoothscale(face, (mini_w, badge_h))
            self.screen.blit(mini, (banner.x + 20, banner.y + 16))
            text_x = banner.x + 20 + mini_w + 16

        # Title + tagline, left-aligned to the right of the mascot so they
        # never overlap the face or the XP chip on the right.
        title_surf = self.font_h2.render("do-o-english", True, WHITE)
        title_center = (text_x + title_surf.get_width() // 2,
                        banner.centery - 12)
        draw_text_with_glow(self.screen, "do-o-english",
                            self.font_h2, WHITE,
                            title_center[0], title_center[1],
                            glow_color=ACCENT_PURPLE, glow_alpha=130, glow_size=3)
        draw_text(self.screen, "Pick a lesson and let's go.",
                  self.font_small, MUTED,
                  text_x, banner.centery + 22, center=False)

        # XP chip on the right
        xp = self.user["xp"] if self.user else 0
        self._draw_xp_chip(banner, xp)

        # Section heading just under the banner
        draw_text(self.screen, "Choose a lesson",
                  self.font_h2, WHITE, WIDTH // 2, 178)

    # ----------------------------------------------------------
    # SCREEN: LESSON
    # ----------------------------------------------------------

    def start_lesson(self, lesson):
        """Begin a lesson from question 1."""
        self.scene = "lesson"
        self.current_lesson = lesson
        self.question_index = 0
        self.correct_count = 0.0
        self.feedback_t = 0.0
        self.avatar_mood = "default"
        self.hint_used_this_q = False
        self.pending_advance = None
        self.speech_text = lesson.get("npcIntro", "Let's learn!")
        self.speech_mood = "default"
        self.show_question()

    def show_question(self):
        """Build buttons for the current exercise."""
        self.buttons = []
        self.feedback_text = ""
        self.picked_words = []

        # Rotate the speech bubble for new questions (keep the lesson intro
        # for question 1 so the npcIntro still gets shown).
        if self.question_index > 0:
            self.speech_text = random.choice(DUO_LINES["default"])
            self.speech_mood = "default"

        exercise = self.current_lesson["exercises"][self.question_index]
        kind = exercise["type"]

        if kind in ("multiple_choice", "listen_select", "fill_blank"):
            choices = list(exercise.get("choices", []))
            self.build_choice_buttons(choices, on_pick=self.check_choice_answer)
        elif kind == "word_order":
            words = list(exercise.get("words", []))
            random.shuffle(words)
            self.build_choice_buttons(words, on_pick=self.pick_word, words=True)
        else:
            self.buttons.append(Button(
                "Skip this question",
                WIDTH // 2 - 130, HEIGHT - 200, 260, 58,
                NEUTRAL_COLOR, NEUTRAL_HOVER,
                on_click=lambda: self.next_question(correct=False),
            ))

        # Bottom action bar — Quit lesson + inventory tools all share a baseline.
        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h
        gap = 12
        self.buttons.append(Button(
            "Quit lesson", 24, bar_y, 140, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.show_hub,
            style="ghost",
        ))

        # Inventory-driven Hint + Skip buttons (only show when owned).
        inv = get_inventory(self.db, self.user["id"]) if self.user else {}
        x = 24 + 140 + gap
        for item in (SHOP_ITEMS_BY_ID["hint"], SHOP_ITEMS_BY_ID["skip"]):
            qty = inv.get(item["id"], 0)
            if qty <= 0:
                continue
            label = f"{item['use_label']} ({qty})"
            handler = (self._use_hint if item["id"] == "hint"
                       else self._use_skip)
            w = 130
            btn = Button(
                label, x, bar_y, w, bar_h,
                item["color"], item["color"],
                on_click=handler, style="ghost",
            )
            btn._inv_btn = item["id"]
            self.buttons.append(btn)
            x += w + gap

    def _use_hint(self):
        """Nudge the player without giving the answer away.

        - multiple_choice / listen_select / fill_blank: greys out and
          disables one wrong answer button. Speech bubble names which
          option was eliminated.
        - word_order: tells the player the *first* word of the sentence.

        Using a hint marks the question as hinted, which caps the
        possible score for that question at 0.4 (see `next_question`).
        """
        if not self.user or not self.current_lesson:
            return
        if self.hint_used_this_q:
            return  # don't burn a second token on the same question
        inv = get_inventory(self.db, self.user["id"])
        if inv.get("hint", 0) <= 0:
            return

        exercise = self.current_lesson["exercises"][self.question_index]
        kind = exercise.get("type")

        if kind in ("multiple_choice", "listen_select", "fill_blank"):
            correct_index = self._correct_choice_index(exercise)
            wrong_btns = [b for b in self.buttons
                          if getattr(b, "_choice_index", None) is not None
                          and b._choice_index != correct_index
                          and not getattr(b, "_eliminated", False)]
            if not wrong_btns:
                self.speech_text = "Already narrowed down — make a choice!"
                self.speech_mood = "default"
                return
            victim = random.choice(wrong_btns)
            victim._eliminated = True
            victim.on_click    = lambda: None    # disable click
            self.speech_text = f'Hint: it\'s not "{victim.text}".'
            self.speech_mood = "default"

        elif kind == "word_order":
            words = list(exercise.get("words", []))
            if not words:
                self.speech_text = "No hint available for this question."
                self.speech_mood = "default"
                return
            self.speech_text = f'Hint: it starts with "{words[0]}".'
            self.speech_mood = "default"

        else:
            self.speech_text = "No hint available for this question."
            self.speech_mood = "default"
            return

        # Charge the token + remember that this question is now capped.
        add_to_inventory(self.db, self.user["id"], "hint", -1)
        self.hint_used_this_q = True
        for btn in self.buttons:
            if getattr(btn, "_inv_btn", None) == "hint":
                btn.text = f"Hint ({inv.get('hint', 0) - 1})"

    def _answer_text_for(self, exercise):
        """Human-readable answer string for the speech bubble hint."""
        kind = exercise.get("type")
        if kind in ("multiple_choice", "listen_select"):
            try:
                return exercise["choices"][int(exercise.get("answer", 0))]
            except (KeyError, IndexError, ValueError):
                return None
        if kind == "fill_blank":
            return str(exercise.get("answer", "")) or None
        if kind == "word_order":
            words = exercise.get("answer") or exercise.get("words") or []
            return " ".join(words) if words else None
        return None

    def _correct_choice_index(self, exercise):
        """Return the index of the correct button — None for non-button types."""
        kind = exercise.get("type")
        if kind in ("multiple_choice", "listen_select"):
            try:
                return int(exercise.get("answer", 0))
            except (TypeError, ValueError):
                return None
        if kind == "fill_blank":
            ans = str(exercise.get("answer", "")).strip().lower()
            for i, c in enumerate(exercise.get("choices", [])):
                if str(c).strip().lower() == ans:
                    return i
        return None

    def _use_skip(self):
        """Consume one Skip Pass — advance with partial credit (0.4)."""
        if not self.user:
            return
        inv = get_inventory(self.db, self.user["id"])
        if inv.get("skip", 0) <= 0:
            return
        add_to_inventory(self.db, self.user["id"], "skip", -1)
        self.correct_count += PARTIAL_CREDIT
        self.question_index += 1
        self.speech_text = f"Skipped! +{PARTIAL_CREDIT:.1f} pts."
        self.speech_mood = "default"
        self.hint_used_this_q = False
        if self.question_index >= len(self.current_lesson["exercises"]):
            self.finish_lesson()
        else:
            self.show_question()

    def build_choice_buttons(self, choices, on_pick, *,
                             panel_cx=None, words=False):
        """
        Lay answer buttons out in a grid that fits the text:
          - 2 columns of 300px when all choices are short
          - 1 column of 640px for long sentences (no neighbour overflow)
          - 2–5 columns of narrow buttons for word_order, capped at 4 rows
        Each button passes ITSELF (not an index) to `on_pick`, which lets
        word-order dedupe on the button identity — needed for sentences
        like "I was wondering if I could…" where a word appears twice.
        """
        cx = WIDTH // 2 if panel_cx is None else panel_cx
        cols, btn_w, btn_h = _choose_choice_grid(
            choices, self.font_bold, words=words)
        rows = (len(choices) + cols - 1) // cols
        gap_x, gap_y = 20, 12
        total_w = cols * btn_w + (cols - 1) * gap_x
        x0 = cx - total_w // 2
        y0 = HEIGHT - 90 - rows * btn_h - (rows - 1) * gap_y

        for i, text in enumerate(choices):
            r, c = divmod(i, cols)
            btn = Button(
                text, x0 + c * (btn_w + gap_x), y0 + r * (btn_h + gap_y),
                btn_w, btn_h, PROFILE_COLOR, PROFILE_HOVER, on_click=None,
            )
            btn._choice_index = i
            btn.on_click = (lambda b=btn: on_pick(b))
            self.buttons.append(btn)

    def check_choice_answer(self, button):
        """Grade a click on a multiple-choice / fill-blank / listen-select button.

        We don't advance immediately — we light up the buttons so the
        player can see what was right and what they picked, then schedule
        the actual advance after a short reveal pause.
        """
        if self.pending_advance:
            return  # already revealing the answer
        exercise = self.current_lesson["exercises"][self.question_index]
        is_correct = _grade_choice(exercise, button._choice_index)
        correct_index = self._correct_choice_index(exercise)
        self._reveal_choice_buttons(clicked=button, correct_index=correct_index)
        self._schedule_advance(is_correct)

    def pick_word(self, button):
        """Used by word_order: the player clicks word buttons one by one."""
        if self.pending_advance:
            return
        if getattr(button, "_word_picked", False):
            return
        button._word_picked = True
        self.picked_words.append(button.text)
        button.base_color = NEUTRAL_COLOR
        button.hover_color = NEUTRAL_HOVER

        exercise = self.current_lesson["exercises"][self.question_index]
        target_words = list(exercise.get("words", []))
        if len(self.picked_words) == len(target_words):
            is_correct = (self.picked_words == target_words)
            # Recolour every word button so the order reads correct/wrong.
            for b in self.buttons:
                if getattr(b, "_choice_index", None) is None:
                    continue
                b.on_click = lambda: None
                b.base_color  = GOOD_GREEN if is_correct else BAD_RED
                b.hover_color = b.base_color
            if not is_correct:
                # Reveal the right order so the lesson stays educational.
                self.speech_text = (
                    f'Correct order: "{" ".join(target_words)}".')
                self.speech_mood = "sad"
            self._schedule_advance(is_correct)

    # ---- Reveal helpers -------------------------------------------------

    def _reveal_choice_buttons(self, clicked, correct_index):
        """Light up choice buttons: clicked → green/red, correct → green."""
        for b in self.buttons:
            ci = getattr(b, "_choice_index", None)
            if ci is None:
                continue
            b.on_click = lambda: None       # lock out further clicks
            if ci == correct_index:
                b.base_color  = GOOD_GREEN
                b.hover_color = STUDENT_HOVER
            elif b is clicked:
                b.base_color  = BAD_RED
                b.hover_color = BAD_RED

    def _schedule_advance(self, correct):
        """Show feedback for ~0.7s, then advance the lesson."""
        self.avatar_mood = "happy" if correct else "sad"
        self.feedback_t = 0.7
        # Don't overwrite a wrong-answer 'Correct order' hint set above.
        if correct or self.speech_mood != "sad":
            self.speech_text = random.choice(DUO_LINES[self.avatar_mood])
            self.speech_mood = self.avatar_mood
        self.pending_advance = {"t": 0.7, "correct": correct}

    def next_question(self, correct):
        """Move to the next question, or finish the lesson if we ran out.

        The mood flash + speech bubble are set by `_schedule_advance` at
        click time so the reveal animation runs *before* the screen flips.
        """
        # Buttons-with-no-reveal callers (the "Skip this question" fallback)
        # still want some feedback, so fall back to the old behaviour if
        # nobody set up the flash yet.
        if self.feedback_t <= 0:
            mood = "happy" if correct else "sad"
            self.avatar_mood = mood
            self.feedback_t = 0.6
            self.speech_text = random.choice(DUO_LINES[mood])
            self.speech_mood = mood

        if correct:
            # A hinted question is capped at the partial-credit value.
            self.correct_count += (PARTIAL_CREDIT if self.hint_used_this_q
                                   else 1)
        self.hint_used_this_q = False
        self.pending_advance = None

        self.question_index += 1
        if self.question_index >= len(self.current_lesson["exercises"]):
            self.finish_lesson()
        else:
            self.show_question()

    def draw_face_character(self, cx, cy, mood, target_h=None):
        """
        Draw the main character Duolingo-style: a soft ground shadow plus
        one of the three face PNGs, with a happy jump or angry-shake
        reaction. Falls back to the drawn cartoon avatar if no images.
        `target_h` overrides the sprite's natural height — lessons use a
        smaller character so it never overlaps the answer area.
        """
        sprite = (self.face_sprites.get(mood)
                  or self.face_sprites.get("default"))
        if sprite is None:
            draw_avatar(self.screen, cx, cy, t=self.now(), mood=mood)
            return

        # Optionally rescale to `target_h` once per draw.
        if target_h is not None and abs(sprite.get_height() - target_h) > 2:
            scale = target_h / sprite.get_height()
            sprite = pygame.transform.smoothscale(
                sprite,
                (max(1, int(sprite.get_width() * scale)), target_h),
            )

        # Idle bob for everyone.
        t = self.now()
        bob = math.sin(t * 2.4) * 6
        dx = 0
        dy = 0
        scale = 1.0

        # Reactions only play while feedback_t is counting down.
        if self.feedback_t > 0:
            # Map 0..1 progress through the reaction (1 = just happened).
            p = self.feedback_t / 0.6
            if mood == "happy":
                # Quick squash+stretch jump.
                dy = int(-30 * math.sin(p * math.pi))   # up then back down
                scale = 1.0 + 0.18 * math.sin(p * math.pi)
            elif mood == "sad":
                # Side-to-side shake + slight shrink.
                dx = int(math.sin(t * 40) * 8 * p)
                scale = 1.0 - 0.05 * p

        # Apply scale (cheap: smoothscale only when scale != 1).
        if abs(scale - 1.0) > 0.01:
            sw = max(1, int(sprite.get_width() * scale))
            sh = max(1, int(sprite.get_height() * scale))
            sprite_to_blit = pygame.transform.smoothscale(sprite, (sw, sh))
        else:
            sprite_to_blit = sprite

        rect = sprite_to_blit.get_rect(center=(cx + dx, int(cy + bob + dy)))

        # Ground shadow — scaled to the *current* sprite so the mini avatar
        # in the multiplayer banner doesn't get a stadium-sized shadow.
        ground_y = cy + sprite.get_height() // 2 - 8
        base_w = sprite.get_width()
        sw_shadow = max(24, int(base_w * (0.85 - abs(dy) * 0.004)))
        sh_shadow = max(6, int(sprite.get_height() * 0.16 - abs(dy) * 0.05))
        shadow = pygame.Surface((sw_shadow, sh_shadow), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 140 - min(80, abs(dy) * 2)),
                            (0, 0, sw_shadow, sh_shadow))
        self.screen.blit(shadow,
                         (cx - sw_shadow // 2, ground_y - sh_shadow // 2))

        self.screen.blit(sprite_to_blit, rect.topleft)
        return rect   # return for the speech bubble to anchor to

    def draw_lesson(self):
        exercise = self.current_lesson["exercises"][self.question_index]
        total = len(self.current_lesson["exercises"])

        # ---- Top banner: lesson title + progress ----
        banner = pygame.Rect(30, 24, WIDTH - 60, 80)
        draw_panel(self.screen, banner, radius=20,
                   top=lerp_color(PANEL_TOP, PROFILE_COLOR, 0.20),
                   bottom=PANEL_BOTTOM,
                   shadow=True, shadow_offset=(0, 8), shadow_alpha=100)
        draw_glass(self.screen, banner, radius=20, alpha=18)

        draw_text(self.screen, self.current_lesson["title"],
                  self.font_h2, WHITE, banner.centerx, banner.y + 26)

        # Progress bar
        pb_w = 480
        pb_h = 10
        pb_rect = pygame.Rect(banner.centerx - pb_w // 2, banner.y + 54, pb_w, pb_h)
        pb_bg = pygame.Surface(pb_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(pb_bg, (255, 255, 255, 40),
                         (0, 0, pb_rect.w, pb_rect.h), border_radius=pb_h // 2)
        self.screen.blit(pb_bg, pb_rect.topleft)
        frac = self.question_index / max(total, 1)
        fill_w = max(0, int(pb_rect.w * frac))
        if fill_w > 0:
            fill = rounded_gradient_surface(fill_w, pb_h,
                                            STUDENT_TOP, STUDENT_BOT, pb_h // 2)
            self.screen.blit(fill, pb_rect.topleft)

        # Progress label
        score_str = (f"{self.correct_count:.1f}" if self.correct_count % 1
                     else f"{int(self.correct_count)}")
        label = f"Question {self.question_index + 1} / {total}   ·   {score_str} correct"
        draw_text(self.screen, label, self.font_small, MUTED,
                  banner.centerx, banner.y + 72)

        # ---- Prompt card (the question) ----
        # Leave a ~360px strip on the right so the character AND its speech
        # bubble both sit out of the way of the prompt and the answer column.
        char_zone_left = WIDTH - 360
        card_w = char_zone_left - 60
        prompt_text = exercise.get("prompt", "")
        prompt_lines = wrap_lines(prompt_text, self.font_body, card_w - 40)
        ph = 60 + 30 * len(prompt_lines)
        if exercise.get("type") == "word_order":
            ph += 30                        # extra row for the picked-words preview
        prompt_card = pygame.Rect(30, 122, card_w, ph)
        draw_panel(self.screen, prompt_card, radius=18,
                   top=(60, 56, 110), bottom=(38, 34, 80),
                   border=ACCENT_PURPLE, border_alpha=120,
                   shadow_offset=(0, 8), shadow_alpha=100)

        tag_label = {
            "multiple_choice": "Multiple choice",
            "listen_select":   "Listen & pick",
            "fill_blank":      "Fill the blank",
            "word_order":      "Order the words",
            "tap_pairs":       "Match pairs",
        }.get(exercise.get("type", ""), "Question")
        tag_w = self.font_small.size(tag_label)[0] + 20
        tag_rect = pygame.Rect(prompt_card.x + 16, prompt_card.y + 14, tag_w, 22)
        pygame.draw.rect(self.screen, ACCENT_PURPLE, tag_rect, border_radius=11)
        draw_text(self.screen, tag_label, self.font_small, INK_DARK,
                  tag_rect.centerx, tag_rect.centery)

        y = prompt_card.y + 50
        for line in prompt_lines:
            draw_text(self.screen, line, self.font_body, WHITE,
                      prompt_card.centerx, y)
            y += 30

        if exercise.get("type") == "word_order":
            chosen = " ".join(self.picked_words) if self.picked_words else "(click words in order)"
            draw_text(self.screen, chosen, self.font_bold, GOLD,
                      prompt_card.centerx, prompt_card.bottom - 22)

        # ---- Compact character + speech bubble in the top-right ----
        # (Sits in the reserved 360px right strip — never overlaps the
        # prompt card on the left or the centered answer column below.)
        mood = self.avatar_mood if self.feedback_t > 0 else "default"
        char_cx = WIDTH - 110
        char_cy = 200
        char_rect = self.draw_face_character(char_cx, char_cy, mood, target_h=140)

        if self.speech_text:
            anchor_x = (char_rect.left + 6 if char_rect is not None
                        else char_cx - 60)
            anchor_y = (char_rect.centery if char_rect is not None
                        else char_cy)
            outline = {"happy":   (60, 170, 90),
                       "sad":     (210, 90, 90),
                       "default": (40, 40, 60)}.get(self.speech_mood, (40, 40, 60))
            draw_speech_bubble(
                self.screen, (anchor_x, anchor_y),
                self.speech_text, self.font_small,
                max_width=180, tail_side="right",
                outline_color=outline,
            )

    # ----------------------------------------------------------
    # SCREEN: SUMMARY
    # ----------------------------------------------------------

    def finish_lesson(self):
        """Save the result, give XP, switch to the summary screen."""
        total = len(self.current_lesson["exercises"])
        score = round(100 * self.correct_count / max(total, 1))
        xp = self.current_lesson.get("xpReward", 10)

        # Consume an XP Doubler if the user owns one.
        doubled = False
        if self.user:
            inv = get_inventory(self.db, self.user["id"])
            if inv.get("double_xp", 0) > 0:
                add_to_inventory(self.db, self.user["id"], "double_xp", -1)
                xp *= 2
                doubled = True
            mark_lesson_done(self.db, self.user["id"], self.current_lesson["id"], score)
            add_xp(self.db, self.user["id"], xp)
            self.user["xp"] += xp

        correct_str = (f"{self.correct_count:.1f}" if self.correct_count % 1
                       else f"{int(self.correct_count)}")
        self.summary_data = {
            "title":       self.current_lesson["title"],
            "outro":       self.current_lesson.get("npcOutro", "Great job!"),
            "correct":     self.correct_count,
            "correct_str": correct_str,
            "total":       total,
            "score":       score,
            "xp":          xp,
            "doubled":     doubled,
        }
        self.scene = "summary"
        btn_w, btn_h = 260, 56
        self.buttons = [
            Button(
                "Back to lessons",
                WIDTH // 2 - btn_w // 2, HEIGHT - 24 - btn_h, btn_w, btn_h,
                GOOD_GREEN, STUDENT_HOVER, on_click=self.show_hub,
            )
        ]
        self.inputs = []

        # Spawn celebratory confetti if the player did well.
        self.confetti = []
        if score >= 60:
            colors = [PROFILE_COLOR, STUDENT_COLOR, TEACHER_COLOR,
                      ACCENT_PURPLE, ACCENT_PINK, GOLD]
            for _ in range(120):
                self.confetti.append({
                    "x":      random.uniform(0, WIDTH),
                    "y":      random.uniform(-HEIGHT, -10),
                    "vy":     random.uniform(60, 180),
                    "vx":     random.uniform(-30, 30),
                    "size":   random.randint(4, 9),
                    "color":  random.choice(colors),
                    "rot":    random.uniform(0, math.tau),
                    "spin":   random.uniform(-3, 3),
                })

    def draw_summary(self):
        data = self.summary_data
        # Confetti behind the card
        for c in self.confetti:
            x, y = int(c["x"]), int(c["y"])
            if 0 <= x <= WIDTH and 0 <= y <= HEIGHT:
                size = c["size"]
                # Draw a small rotated diamond as confetti
                pts = [
                    (x + math.cos(c["rot"]) * size,           y + math.sin(c["rot"]) * size),
                    (x + math.cos(c["rot"] + math.pi/2) * size, y + math.sin(c["rot"] + math.pi/2) * size),
                    (x + math.cos(c["rot"] + math.pi)   * size, y + math.sin(c["rot"] + math.pi)   * size),
                    (x + math.cos(c["rot"] - math.pi/2) * size, y + math.sin(c["rot"] - math.pi/2) * size),
                ]
                pygame.draw.polygon(self.screen, c["color"], pts)

        panel = pygame.Rect(110, 90, WIDTH - 220, HEIGHT - 230)
        draw_panel(self.screen, panel, radius=26,
                   top=lerp_color(PANEL_TOP, STUDENT_COLOR, 0.10),
                   bottom=PANEL_BOTTOM, shadow_offset=(0, 14), shadow_alpha=140)
        draw_glass(self.screen, panel, radius=26, alpha=20)

        # Trophy circle
        tx, ty = WIDTH // 2, panel.y + 90
        pygame.draw.circle(self.screen, lerp_color(GOLD, (0, 0, 0), 0.4),
                           (tx + 3, ty + 4), 46)
        pygame.draw.circle(self.screen, GOLD, (tx, ty), 46)
        pygame.draw.circle(self.screen, lerp_color(GOLD, (255, 255, 255), 0.65),
                           (tx - 12, ty - 12), 14)
        tro_font = pygame.font.SysFont(UI_FONT_STACK, 44, bold=True)
        tro = tro_font.render("★", True, INK_DARK)
        self.screen.blit(tro, tro.get_rect(center=(tx, ty + 3)))

        draw_text_with_glow(self.screen, "Lesson complete!",
                            self.font_title, WHITE,
                            WIDTH // 2, panel.y + 180,
                            glow_color=STUDENT_COLOR, glow_alpha=140, glow_size=3)
        draw_text(self.screen, data["title"], self.font_h2, MUTED,
                  WIDTH // 2, panel.y + 230)

        # Stat row: correct/total, score%, +XP
        row_y = panel.y + 290
        stat_w = 180
        gap = 20
        total_w = stat_w * 3 + gap * 2
        x0 = WIDTH // 2 - total_w // 2

        stats = [
            (f"{data['correct_str']} / {data['total']}", "Correct",       PROFILE_COLOR),
            (f"{data['score']}%",                    "Score",         STUDENT_COLOR),
            (f"+{data['xp']}",                       "XP earned",     GOLD),
        ]
        for i, (value, label, color) in enumerate(stats):
            r = pygame.Rect(x0 + i * (stat_w + gap), row_y, stat_w, 78)
            stat_surf = pygame.Surface(r.size, pygame.SRCALPHA)
            pygame.draw.rect(stat_surf, (*color, 30),
                             (0, 0, r.w, r.h), border_radius=18)
            pygame.draw.rect(stat_surf, (*color, 180),
                             (0, 0, r.w, r.h), width=1, border_radius=18)
            self.screen.blit(stat_surf, r.topleft)
            draw_text(self.screen, value, self.font_h2, WHITE,
                      r.centerx, r.y + 26)
            draw_text(self.screen, label, self.font_small, MUTED,
                      r.centerx, r.y + 58)

        # Outro quote (word-wrapped) inside a soft sub-card
        outro_lines = wrap_lines(data["outro"], self.font_body, panel.w - 120)
        oh = 40 + 26 * len(outro_lines)
        outro_rect = pygame.Rect(panel.x + 60, row_y + 110, panel.w - 120, oh)
        sub = pygame.Surface(outro_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(sub, (255, 255, 255, 18),
                         (0, 0, outro_rect.w, outro_rect.h), border_radius=14)
        pygame.draw.rect(sub, (255, 255, 255, 60),
                         (0, 0, outro_rect.w, outro_rect.h), width=1, border_radius=14)
        self.screen.blit(sub, outro_rect.topleft)
        for i, line in enumerate(outro_lines):
            draw_text(self.screen, line, self.font_body, MUTED,
                      outro_rect.centerx, outro_rect.y + 22 + i * 26)

    # ----------------------------------------------------------
    # SCREEN: SHOP
    # ----------------------------------------------------------

    def show_shop(self):
        self.scene = "shop"
        self.buttons = []
        self.inputs = []
        self._refresh_shop_buttons()
        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h
        self.buttons.append(Button(
            "Back",
            24, bar_y, 120, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.show_hub,
            style="ghost",
        ))

    def _refresh_shop_buttons(self):
        """Rebuild the per-item Buy buttons (called after a purchase)."""
        # Drop any existing buy buttons (we tag them).
        self.buttons = [b for b in self.buttons
                        if not getattr(b, "_shop_buy_btn", False)]
        inv = get_inventory(self.db, self.user["id"]) if self.user else {}
        xp = self.user["xp"] if self.user else 0
        for i, item in enumerate(SHOP_ITEMS):
            owned = inv.get(item["id"], 0)
            can_afford = xp >= item["price"]
            label = f"Buy  ·  {item['price']} XP"
            if not can_afford:
                label = f"Need {item['price']} XP"
            base = STUDENT_COLOR if can_afford else NEUTRAL_COLOR
            hov  = STUDENT_HOVER if can_afford else NEUTRAL_HOVER
            row_y = 180 + i * 130
            row_right = WIDTH - 60          # mirrors `row` rect in draw_shop
            btn_w = 200
            btn = Button(
                label,
                row_right - 20 - btn_w, row_y + 36, btn_w, 50,
                base, hov,
                on_click=(lambda it=item: self._buy_item(it["id"]))
                         if can_afford else (lambda: None),
            )
            btn._shop_buy_btn = True
            btn._shop_item_index = i  # used for layout in draw_shop
            self.buttons.append(btn)

    def _buy_item(self, item_id):
        item = SHOP_ITEMS_BY_ID.get(item_id)
        if not item or not self.user:
            return
        if spend_xp(self.db, self.user["id"], item["price"]):
            self.user["xp"] -= item["price"]
            add_to_inventory(self.db, self.user["id"], item_id, +1)
            self._refresh_shop_buttons()

    def draw_shop(self):
        banner = pygame.Rect(40, 30, WIDTH - 80, 110)
        draw_panel(self.screen, banner, radius=22,
                   top=lerp_color(PANEL_TOP, TEACHER_COLOR, 0.20),
                   bottom=PANEL_BOTTOM)
        draw_glass(self.screen, banner, radius=22, alpha=20)
        draw_text_with_glow(self.screen, "Shop", self.font_title, WHITE,
                            banner.x + 100, banner.centery,
                            glow_color=TEACHER_COLOR, glow_alpha=140, glow_size=3)
        draw_text(self.screen, "Spend your XP on helpful boosts.",
                  self.font_small, MUTED,
                  banner.x + 100, banner.bottom - 22, center=False)

        # XP chip on the right of the banner.
        xp = self.user["xp"] if self.user else 0
        self._draw_xp_chip(banner, xp)

        # Item rows.
        inv = get_inventory(self.db, self.user["id"]) if self.user else {}
        for i, item in enumerate(SHOP_ITEMS):
            row = pygame.Rect(60, 180 + i * 130, WIDTH - 120, 110)
            draw_panel(self.screen, row, radius=18,
                       top=PANEL_TOP, bottom=PANEL_BOTTOM,
                       shadow_offset=(0, 6), shadow_alpha=90)
            # Icon bubble on the left.
            icx, icy = row.x + 56, row.centery
            pygame.draw.circle(self.screen,
                               lerp_color(item["color"], (0, 0, 0), 0.4),
                               (icx + 2, icy + 2), 30)
            pygame.draw.circle(self.screen, item["color"], (icx, icy), 30)
            pygame.draw.circle(self.screen,
                               lerp_color(item["color"], (255, 255, 255), 0.5),
                               (icx - 8, icy - 8), 8)
            icon_font = pygame.font.SysFont(UI_FONT_STACK, 26, bold=True)
            draw_text(self.screen, item["icon"], icon_font, INK_DARK,
                      icx, icy + 1)
            # Name + description.
            draw_text(self.screen, item["name"], self.font_h2, WHITE,
                      row.x + 110, row.y + 30, center=False)
            for j, line in enumerate(
                    wrap_lines(item["desc"], self.font_small, row.w - 460)):
                draw_text(self.screen, line, self.font_small, MUTED,
                          row.x + 110, row.y + 64 + j * 18, center=False)
            # Owned counter — sits to the LEFT of the Buy button (220 + 20 gap).
            owned = inv.get(item["id"], 0)
            owned_text = f"Owned: {owned}"
            owned_w = self.font_bold.size(owned_text)[0]
            draw_text(self.screen, owned_text,
                      self.font_bold, GOOD_GREEN if owned else MUTED,
                      row.right - 240 - owned_w - 12, row.y + 28, center=False)

    # ----------------------------------------------------------
    # MULTIPLAYER — lobby, room, in-game, summary
    # ----------------------------------------------------------

    # ---- Lobby ---------------------------------------------------------

    def show_lobby(self):
        """Show the multiplayer lobby (lists nearby hosts, plus 'Host' button)."""
        self._teardown_multiplayer()  # nuke any previous session
        self.scene = "lobby"
        self.buttons = []
        self.inputs = []
        self.mp_role = None
        self.mp_input_value = self.mp_player_name

        # Listen for beacons so we can list nearby hosts.
        self.mp_listener = LobbyListener()
        try:
            self.mp_listener.start()
        except Exception:
            self.mp_listener = None

        # Name input at the top of the lobby.
        self.mp_name_input = TextInput(
            WIDTH // 2 - 200, 180, 400, 44, "Your name", max_chars=18,
        )
        self.mp_name_input.value = self.mp_player_name
        self.inputs.append(self.mp_name_input)

        # Persistent buttons (Host + Back). Per-host "Join" buttons are
        # rebuilt every refresh inside _refresh_lobby_hosts.
        self.buttons.append(Button(
            "Host a game",
            WIDTH // 2 - 160, 252, 320, 56,
            TEACHER_COLOR, TEACHER_HOVER,
            on_click=self._host_game,
        ))
        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h
        self.buttons.append(Button(
            "Back",
            24, bar_y, 120, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self._lobby_back,
            style="ghost",
        ))

        self._mp_hosts_cache = []
        self._mp_hosts_refresh_t = 0.0
        self._refresh_lobby_hosts(force=True)

    def _lobby_back(self):
        self._teardown_multiplayer()
        self.show_hub()

    def _refresh_lobby_hosts(self, force=False):
        """Rebuild the per-host 'Join' buttons if the host list changed."""
        if not self.mp_listener:
            return
        hosts = self.mp_listener.hosts()
        key = tuple((h["host_id"], h["name"], h["addr"], h["tcp_port"]) for h in hosts)
        prev_key = tuple((h["host_id"], h["name"], h["addr"], h["tcp_port"])
                         for h in self._mp_hosts_cache)
        if not force and key == prev_key:
            return
        self._mp_hosts_cache = hosts

        # Drop any existing per-host buttons (we tag them with `_mp_host_btn`).
        self.buttons = [b for b in self.buttons if not getattr(b, "_mp_host_btn", False)]
        # Rebuild.
        y = 380
        for host in hosts[:6]:
            join_btn = Button(
                f"Join — {host['name']}  ({host['addr']})",
                WIDTH // 2 - 280, y, 560, 56,
                PROFILE_COLOR, PROFILE_HOVER,
                on_click=lambda h=host: self._join_game(h),
            )
            join_btn._mp_host_btn = True
            self.buttons.append(join_btn)
            y += 64

    def draw_lobby(self):
        # Header panel
        banner = pygame.Rect(40, 30, WIDTH - 80, 110)
        draw_panel(self.screen, banner, radius=22,
                   top=lerp_color(PANEL_TOP, ACCENT_PURPLE, 0.20),
                   bottom=PANEL_BOTTOM)
        draw_glass(self.screen, banner, radius=22, alpha=20)
        draw_text_with_glow(self.screen, "Multiplayer Lobby",
                            self.font_h2, WHITE,
                            WIDTH // 2, banner.y + 44,
                            glow_color=ACCENT_PURPLE, glow_alpha=130, glow_size=3)
        ips = ", ".join(local_ips()) or "no LAN address"
        draw_text(self.screen, f"You're on  {ips}",
                  self.font_small, MUTED, WIDTH // 2, banner.bottom - 22)

        # Name input
        self.mp_name_input.draw(self.screen, self.font_small, self.font_body)
        # Remember whatever's typed so it sticks when we switch screens.
        self.mp_player_name = (self.mp_name_input.value.strip()
                               or MP_DEFAULT_NAME)

        # "Nearby games" heading
        draw_text(self.screen, "Nearby games on your WiFi",
                  self.font_h2, WHITE, WIDTH // 2, 348)
        if not self._mp_hosts_cache:
            draw_text(self.screen, "Looking… ask a friend to click 'Host a game'.",
                      self.font_small, DIM, WIDTH // 2, 400)

    # ---- Host / Join ---------------------------------------------------

    def _host_game(self):
        """Become the host of a new LAN game and enter the room screen."""
        self.mp_player_name = self._current_name_input() or MP_DEFAULT_NAME
        # Stop the lobby listener — we don't need it once we're hosting.
        if self.mp_listener:
            try: self.mp_listener.stop()
            except Exception: pass
            self.mp_listener = None

        self.mp_server = HostServer()
        try:
            self.mp_server.start()
        except OSError as e:
            print(f"[mp] host start failed: {e}")
            return
        self.mp_beacon = LobbyBeacon(self.mp_player_name, self.mp_server.tcp_port)
        try:
            self.mp_beacon.start()
        except Exception as e:
            print(f"[mp] beacon start failed: {e}")

        self.mp_role = "host"
        self.mp_self_id = MP_HOST_ID
        # Initial roster: just the host.
        self.mp_players = [self._new_player(MP_HOST_ID, self.mp_player_name)]
        self.show_room()

    def _join_game(self, host):
        """Connect as a client to the given host (a row from LobbyListener)."""
        self.mp_player_name = self._current_name_input() or MP_DEFAULT_NAME
        if self.mp_listener:
            try: self.mp_listener.stop()
            except Exception: pass
            self.mp_listener = None

        self.mp_client = ClientPeer(host["addr"], host["tcp_port"],
                                    self.mp_player_name)
        if not self.mp_client.start():
            self.mp_client = None
            print(f"[mp] could not connect to {host['addr']}:{host['tcp_port']}")
            return
        self.mp_role = "client"
        self.mp_players = [self._new_player(MP_HOST_ID, host["name"]),
                           self._new_player(-1, self.mp_player_name)]
        # self_id will be set when the host sends us the lobby roster.
        self.mp_self_id = -1
        self.show_room()

    # ---- Room (waiting screen) ----------------------------------------

    def _new_player(self, pid, name):
        return {"id": pid, "name": name, "score": 0, "progress": 0, "finished": False}

    def show_room(self):
        self.scene = "room"
        self.buttons = []
        self.inputs = []

        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h

        if self.mp_role == "host":
            # Centered two-up row of pickers above the primary action.
            pick_w, gap = 240, 16
            row_y = bar_y - 70 - 50
            picks_x0 = WIDTH // 2 - pick_w - gap // 2
            self.buttons.append(Button(
                "Change lesson",
                picks_x0, row_y, pick_w, 50,
                PROFILE_COLOR, PROFILE_HOVER,
                on_click=self._cycle_lesson,
                style="ghost",
            ))
            self.buttons.append(Button(
                "Change mode",
                picks_x0 + pick_w + gap, row_y, pick_w, 50,
                PROFILE_COLOR, PROFILE_HOVER,
                on_click=self._cycle_mode,
                style="ghost",
            ))
            # Primary action sits centered just above the bottom bar.
            start_w, start_h = 320, 56
            self.buttons.append(Button(
                "Start game",
                WIDTH // 2 - start_w // 2, bar_y - start_h - 14, start_w, start_h,
                STUDENT_COLOR, STUDENT_HOVER,
                on_click=self._host_start_game,
            ))

        self.buttons.append(Button(
            "Leave room",
            24, bar_y, 140, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self._leave_room,
            style="ghost",
        ))

    def _leave_room(self):
        self._teardown_multiplayer()
        self.show_hub()

    def _cycle_lesson(self):
        if not self.lessons:
            return
        self.mp_lesson_pick = (self.mp_lesson_pick + 1) % len(self.lessons)

    def _cycle_mode(self):
        i = MP_MODES.index(self.mp_mode) if self.mp_mode in MP_MODES else 0
        self.mp_mode = MP_MODES[(i + 1) % len(MP_MODES)]

    def draw_room(self):
        banner = pygame.Rect(40, 30, WIDTH - 80, 80)
        draw_panel(self.screen, banner, radius=18,
                   top=lerp_color(PANEL_TOP, ACCENT_PURPLE, 0.18),
                   bottom=PANEL_BOTTOM)
        draw_glass(self.screen, banner, radius=18, alpha=18)
        host_name = self.mp_players[0]["name"] if self.mp_players else "?"
        title = f"{host_name}'s room" if self.mp_role == "client" else f"Your room ({host_name})"
        draw_text(self.screen, title, self.font_h2, WHITE,
                  banner.centerx, banner.centery)

        # Players card
        roster = pygame.Rect(60, 130, WIDTH - 120, 240)
        draw_panel(self.screen, roster, radius=18,
                   top=PANEL_TOP, bottom=PANEL_BOTTOM)
        draw_text(self.screen, "Players in the room",
                  self.font_h2, WHITE,
                  roster.centerx, roster.y + 24)
        y = roster.y + 60
        for p in self.mp_players:
            chip = pygame.Rect(roster.x + 24, y, roster.w - 48, 36)
            tint = (255, 255, 255, 20)
            pygame.draw.rect(self.screen,
                             lerp_color(PANEL_TOP, ACCENT_PURPLE, 0.15),
                             chip, border_radius=12)
            badge = "HOST" if p["id"] == MP_HOST_ID else ""
            label = p["name"] + ("  (you)" if p["id"] == self.mp_self_id else "")
            draw_text(self.screen, label, self.font_bold, WHITE,
                      chip.x + 18, chip.centery, center=False)
            if badge:
                bw = self.font_small.size(badge)[0] + 16
                br = pygame.Rect(chip.right - bw - 14,
                                 chip.centery - 12, bw, 24)
                pygame.draw.rect(self.screen, GOLD, br, border_radius=12)
                draw_text(self.screen, badge, self.font_small, INK_DARK,
                          br.centerx, br.centery)
            y += 44

        # Lesson + mode summary
        info = pygame.Rect(60, 390, WIDTH - 120, 110)
        draw_panel(self.screen, info, radius=18, top=PANEL_TOP, bottom=PANEL_BOTTOM)
        lesson_title = "—"
        if self.lessons:
            lesson_title = self.lessons[self.mp_lesson_pick % len(self.lessons)]["title"]
        draw_text(self.screen, f"Lesson:  {lesson_title}",
                  self.font_bold, WHITE,
                  info.x + 28, info.y + 36, center=False)
        draw_text(self.screen, f"Mode:    {MP_MODE_LABELS.get(self.mp_mode, self.mp_mode)}",
                  self.font_body, MUTED,
                  info.x + 28, info.y + 72, center=False)

        if self.mp_role == "client":
            draw_text(self.screen, "Waiting for host to start…",
                      self.font_body, DIM, WIDTH // 2, HEIGHT - 180)

    # ---- Host actions: start the game ---------------------------------

    def _host_start_game(self):
        if self.mp_role != "host" or not self.lessons:
            return
        lesson = self.lessons[self.mp_lesson_pick % len(self.lessons)]
        # Drop exercises that aren't safe for coop/turn modes.
        if self.mp_mode in ("coop", "turn"):
            ex = [e for e in lesson["exercises"]
                  if e.get("type") in MP_SINGLECLICK_TYPES]
            if not ex:
                return
            lesson = dict(lesson)
            lesson["exercises"] = ex

        self.mp_lesson = lesson
        self.mp_question_index = 0
        self.mp_current_player_id = self.mp_players[0]["id"]
        for p in self.mp_players:
            p["score"] = 0; p["progress"] = 0; p["finished"] = False
        self.mp_server.broadcast({
            "type":   "start",
            "lesson": lesson,
            "mode":   self.mp_mode,
            "players": [{"id": p["id"], "name": p["name"]} for p in self.mp_players],
            "current_player_id": self.mp_current_player_id,
        })
        self.show_mp_lesson()

    # ---- Multiplayer lesson scene -------------------------------------

    def show_mp_lesson(self):
        self.scene = "mp_lesson"
        self.buttons = []
        self.inputs = []
        self.avatar_mood = "default"
        self.feedback_t = 0.0
        self.speech_text = self.mp_lesson.get("npcIntro", "Let's go!") if self.mp_lesson else ""
        self.speech_mood = "default"
        self.picked_words = []
        # Persistent leave button (kept across question changes).
        bar_h = 46
        bar_y = HEIGHT - 24 - bar_h
        leave_btn = Button(
            "Leave game", 24, bar_y, 140, bar_h,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self._leave_room,
            style="ghost",
        )
        leave_btn._mp_persistent = True
        self.buttons.append(leave_btn)
        self._build_mp_choice_buttons()

    def _current_mp_question(self):
        if not self.mp_lesson:
            return None
        if self.mp_question_index >= len(self.mp_lesson["exercises"]):
            return None
        return self.mp_lesson["exercises"][self.mp_question_index]

    def _build_mp_choice_buttons(self):
        """Rebuild the answer buttons for the current question."""
        # Keep only the buttons explicitly marked persistent (Leave game).
        self.buttons = [b for b in self.buttons
                        if getattr(b, "_mp_persistent", False)]

        ex = self._current_mp_question()
        if ex is None:
            return
        kind = ex.get("type")

        # In coop/turn we only do single-click exercise types. Race uses
        # the local lesson runner so all types work as buttons here.
        if self.mp_mode == "turn" and self.mp_self_id != self.mp_current_player_id:
            # Show the question but disable input.
            return

        # Center the answer grid in the left ~75% of the screen so the
        # scoreboard sidebar on the right stays readable.
        panel_cx = (WIDTH - 280) // 2
        builder = lambda items, picker: self._build_mp_grid(items, picker, panel_cx)

        if kind in ("multiple_choice", "listen_select", "fill_blank"):
            builder(list(ex.get("choices", [])), self._mp_pick_choice)
        elif kind == "word_order" and self.mp_mode == "race":
            words = list(ex.get("words", []))
            random.shuffle(words)
            self.picked_words = []
            self._build_mp_grid(words, self._mp_pick_word, panel_cx, words=True)
        else:
            # word_order / tap_pairs in coop/turn are too clicky to sync,
            # and tap_pairs has no real grader. Skip cleanly.
            self._race_advance(correct=False)

    def _build_mp_grid(self, items, on_pick, panel_cx, *, words=False):
        """Multiplayer answer grid — same builder as single-player but
        shifted left to leave room for the scoreboard."""
        cols, btn_w, btn_h = _choose_choice_grid(
            items, self.font_bold, narrow=True, words=words)
        rows = (len(items) + cols - 1) // cols
        gap_x, gap_y = 20, 14
        total_w = cols * btn_w + (cols - 1) * gap_x
        x0 = panel_cx - total_w // 2
        y0 = HEIGHT - 90 - rows * btn_h - (rows - 1) * gap_y
        for i, text in enumerate(items):
            r, c = divmod(i, cols)
            btn = Button(
                text, x0 + c * (btn_w + gap_x), y0 + r * (btn_h + gap_y),
                btn_w, btn_h, PROFILE_COLOR, PROFILE_HOVER, on_click=None,
            )
            btn._choice_index = i
            btn.on_click = (lambda b=btn: on_pick(b))
            self.buttons.append(btn)

    # -- Click handlers driven by the local UI --

    def _mp_pick_choice(self, button):
        """The local player clicked an answer button."""
        index = button._choice_index
        if self.mp_role == "host":
            self._host_apply_answer(self.mp_self_id, index)
        else:
            # Client routes the answer through the host.
            # In race mode we also need to advance locally so the UI moves.
            if self.mp_client:
                self.mp_client.send({"type": "answer", "choice": index,
                                      "question_index": self.mp_question_index})
            if self.mp_mode == "race":
                self._race_local_apply(index)

    def _mp_pick_word(self, button):
        # Word-order only happens in race mode (each client plays its
        # own copy). We dedupe per-button so sentences with repeated
        # words like "I" or "the" still work.
        if getattr(button, "_word_picked", False):
            return
        button._word_picked = True
        self.picked_words.append(button.text)
        button.base_color = NEUTRAL_COLOR
        button.hover_color = NEUTRAL_HOVER
        ex = self._current_mp_question()
        target = list(ex.get("words", []))
        if len(self.picked_words) == len(target):
            correct = self.picked_words == target
            self._race_advance(correct=correct)

    # -- Race-mode local advance (used by host AND each client) --

    def _race_local_apply(self, choice):
        ex = self._current_mp_question()
        if ex is not None:
            self._race_advance(correct=_grade_choice(ex, choice))

    def _race_advance(self, correct):
        """Move this player to the next question (race mode only)."""
        # Visual feedback
        self.avatar_mood = "happy" if correct else "sad"
        self.feedback_t = 0.6
        self.speech_text = random.choice(DUO_LINES["happy" if correct else "sad"])
        self.speech_mood = "happy" if correct else "sad"

        # Update local player record
        me = self._mp_player(self.mp_self_id)
        if me is not None:
            if correct:
                me["score"] += 1
            me["progress"] = self.mp_question_index + 1

        self.mp_question_index += 1
        total = len(self.mp_lesson["exercises"]) if self.mp_lesson else 0
        done = self.mp_question_index >= total

        if me is not None and done:
            me["finished"] = True

        # Tell the host (or ourselves) what just happened.
        progress_msg = {
            "type":           "progress",
            "question_index": self.mp_question_index,
            "score":          me["score"] if me else 0,
            "finished":       done,
        }
        if self.mp_role == "client" and self.mp_client:
            self.mp_client.send(progress_msg)
        elif self.mp_role == "host":
            # Host can update its own player + broadcast scoreboard.
            self._host_broadcast_scoreboard()
            if all(p["finished"] for p in self.mp_players):
                self._host_end_game()
                return

        if not done:
            self.picked_words = []
            self._build_mp_choice_buttons()
        elif self.mp_role == "client":
            # Wait for the host to declare the game over (scoreboard sidebar
            # stays visible). Clear the answer buttons.
            self.buttons = [b for b in self.buttons
                            if getattr(b, "_mp_persistent", False)]
            self.speech_text = "Waiting for the others to finish…"
            self.speech_mood = "default"

    # -- Host-authoritative apply (coop/turn) and race --

    def _host_apply_answer(self, player_id, choice):
        if self.mp_role != "host" or not self.mp_lesson:
            return

        # RACE: host plays its own copy too — route through race_local_apply
        # (which already updates host scoreboard + broadcasts).
        if self.mp_mode == "race":
            if player_id == self.mp_self_id:
                self._race_local_apply(choice)
            return

        # COOP / TURN: validate the answer for the SHARED current question.
        ex = self._current_mp_question()
        if ex is None:
            return
        if self.mp_mode == "turn" and player_id != self.mp_current_player_id:
            return  # not your turn

        ok = _grade_choice(ex, choice)

        # Update score + advance shared question.
        scorer = self._mp_player(player_id)
        if ok and scorer is not None:
            scorer["score"] += 1
        for p in self.mp_players:
            p["progress"] = self.mp_question_index + 1

        self.mp_question_index += 1
        # Rotate turn for "turn" mode.
        if self.mp_mode == "turn" and self.mp_players:
            ids = [p["id"] for p in self.mp_players]
            try:
                ci = ids.index(self.mp_current_player_id)
            except ValueError:
                ci = 0
            self.mp_current_player_id = ids[(ci + 1) % len(ids)]

        # Broadcast the result.
        self.mp_server.broadcast({
            "type":          "answered",
            "by_id":         player_id,
            "correct":       ok,
            "next_index":    self.mp_question_index,
            "current_player_id": self.mp_current_player_id,
        })
        self._host_broadcast_scoreboard()

        # Local feedback on the host too.
        self.mp_recent_feedback = (
            f"{self._name_of(player_id)} — "
            + ("Correct!" if ok else "Wrong.")
        )
        self.mp_recent_feedback_t = 1.6
        self.avatar_mood = "happy" if ok else "sad"
        self.feedback_t = 0.6
        self.speech_text = random.choice(DUO_LINES["happy" if ok else "sad"])
        self.speech_mood = "happy" if ok else "sad"

        # End or rebuild buttons for the new question.
        if self.mp_question_index >= len(self.mp_lesson["exercises"]):
            for p in self.mp_players:
                p["finished"] = True
            self.mp_server.broadcast({
                "type":  "show_question",
                "question_index": self.mp_question_index,
                "current_player_id": self.mp_current_player_id,
            })
            self._host_end_game()
        else:
            self.mp_server.broadcast({
                "type": "show_question",
                "question_index": self.mp_question_index,
                "current_player_id": self.mp_current_player_id,
            })
            self._build_mp_choice_buttons()

    def _host_broadcast_scoreboard(self):
        if not self.mp_server:
            return
        self.mp_server.broadcast({
            "type": "scoreboard",
            "players": [dict(p) for p in self.mp_players],
        })

    def _host_end_game(self):
        if self.mp_server:
            self.mp_server.broadcast({
                "type": "game_over",
                "players": [dict(p) for p in self.mp_players],
            })
        self._enter_mp_summary([dict(p) for p in self.mp_players])

    # ---- MP summary scene --------------------------------------------

    def _enter_mp_summary(self, players):
        # Sort by score desc, then by progress desc, then name.
        players = sorted(players,
                         key=lambda p: (-int(p.get("score", 0)),
                                        -int(p.get("progress", 0)),
                                         p.get("name", "")))
        self.mp_summary = {"players": players}
        # Award a little XP for the local player based on their score (host
        # writes XP for itself only; clients write XP for themselves only).
        me = next((p for p in players if p["id"] == self.mp_self_id), None)
        if me and self.user:
            xp = int(me.get("score", 0)) * 2
            if xp > 0:
                add_xp(self.db, self.user["id"], xp)
                self.user["xp"] += xp
        self.show_mp_summary()

    def show_mp_summary(self):
        self.scene = "mp_summary"
        self.buttons = []
        self.inputs = []
        btn_w, btn_h = 260, 56
        self.buttons.append(Button(
            "Back to hub",
            WIDTH // 2 - btn_w // 2, HEIGHT - 24 - btn_h, btn_w, btn_h,
            STUDENT_COLOR, STUDENT_HOVER,
            on_click=self._leave_room,
        ))

    def draw_mp_summary(self):
        panel = pygame.Rect(110, 90, WIDTH - 220, HEIGHT - 230)
        draw_panel(self.screen, panel, radius=24,
                   top=lerp_color(PANEL_TOP, GOLD, 0.10),
                   bottom=PANEL_BOTTOM)
        draw_glass(self.screen, panel, radius=24, alpha=18)
        draw_text_with_glow(self.screen, "Final scoreboard",
                            self.font_title, WHITE,
                            WIDTH // 2, panel.y + 70,
                            glow_color=GOLD, glow_alpha=140, glow_size=3)
        if not self.mp_summary:
            return
        y = panel.y + 150
        for i, p in enumerate(self.mp_summary["players"]):
            row = pygame.Rect(panel.x + 60, y, panel.w - 120, 56)
            tint = (255, 255, 255, 22 if i else 70)
            color = GOLD if i == 0 else (
                (192, 192, 200) if i == 1 else
                ((205, 127, 50) if i == 2 else MUTED))
            pygame.draw.rect(self.screen,
                             lerp_color(PANEL_TOP, color, 0.18),
                             row, border_radius=14)
            rank_font = pygame.font.SysFont(UI_FONT_STACK, 26, bold=True)
            draw_text(self.screen, f"#{i + 1}", rank_font, color,
                      row.x + 30, row.centery)
            draw_text(self.screen, p["name"], self.font_h2, WHITE,
                      row.x + 80, row.centery, center=False)
            draw_text(self.screen, f"{p['score']} correct",
                      self.font_bold, GOLD,
                      row.right - 40, row.centery, center=False)
            y += 64

    # ---- Drawing the MP lesson scene -----------------------------------

    def draw_mp_lesson(self):
        # Reuse a lot of the look from draw_lesson but with a scoreboard.
        ex = self._current_mp_question()
        total = len(self.mp_lesson["exercises"]) if self.mp_lesson else 0

        # Top banner with lesson title + mode (extra tall so the avatar fits).
        banner = pygame.Rect(30, 24, WIDTH - 60, 80)
        draw_panel(self.screen, banner, radius=18,
                   top=lerp_color(PANEL_TOP, ACCENT_PURPLE, 0.18),
                   bottom=PANEL_BOTTOM, shadow_offset=(0, 6), shadow_alpha=100)
        draw_glass(self.screen, banner, radius=18, alpha=16)

        # Mini mood avatar in the left side of the banner. Lives where
        # there's free space and never overlaps the answer grid.
        mood = self.avatar_mood if self.feedback_t > 0 else "default"
        self.draw_face_character(banner.x + 50, banner.centery, mood, target_h=56)

        lesson_title = self.mp_lesson["title"] if self.mp_lesson else ""
        draw_text(self.screen, f"{lesson_title}  ·  {MP_MODE_LABELS[self.mp_mode].split(' — ')[0]}",
                  self.font_h2, WHITE, banner.centerx, banner.y + 26)
        idx_label = (f"Question {min(self.mp_question_index + 1, total)} / {total}"
                     if total else "Loading…")
        draw_text(self.screen, idx_label, self.font_small, MUTED,
                  banner.centerx, banner.y + 58)

        # Question panel (sits under the banner, left of scoreboard)
        if ex is not None:
            prompt = ex.get("prompt", "")
            lines = wrap_lines(prompt, self.font_body, WIDTH - 460)
            ph = 60 + 28 * len(lines)
            qcard = pygame.Rect(40, banner.bottom + 14, WIDTH - 340, ph)
            draw_panel(self.screen, qcard, radius=16,
                       top=(60, 56, 110), bottom=(38, 34, 80),
                       border=ACCENT_PURPLE, border_alpha=120,
                       shadow_offset=(0, 6), shadow_alpha=90)
            y = qcard.y + 36
            for line in lines:
                draw_text(self.screen, line, self.font_body, WHITE,
                          qcard.centerx, y)
                y += 28
            if ex.get("type") == "word_order" and self.mp_mode == "race":
                chosen = " ".join(self.picked_words) or "(click words in order)"
                draw_text(self.screen, chosen, self.font_bold, GOLD,
                          qcard.centerx, qcard.bottom - 20)

        # Turn indicator (centered under the question card)
        if self.mp_mode == "turn" and self.mp_current_player_id is not None:
            who = self._name_of(self.mp_current_player_id)
            tag = f"{'Your' if self.mp_current_player_id == self.mp_self_id else who + chr(0x27) + 's'} turn"
            y_tag = (qcard.bottom if ex is not None else banner.bottom) + 18
            draw_text(self.screen, tag, self.font_bold,
                      STUDENT_COLOR if self.mp_current_player_id == self.mp_self_id
                      else MUTED,
                      (WIDTH - 280) // 2, y_tag)

        # Scoreboard sidebar on the right (lined up with the banner bottom)
        side = pygame.Rect(WIDTH - 280, banner.bottom + 14, 250, HEIGHT - 200)
        draw_panel(self.screen, side, radius=18,
                   top=PANEL_TOP, bottom=PANEL_BOTTOM)
        draw_text(self.screen, "Scoreboard", self.font_h2, WHITE,
                  side.centerx, side.y + 28)
        y = side.y + 68
        for p in self.mp_players:
            color = STUDENT_COLOR if p["id"] == self.mp_self_id else WHITE
            line = f"{p['name']}"
            if p["id"] == MP_HOST_ID:
                line += "  ★"
            draw_text(self.screen, line, self.font_bold, color,
                      side.x + 18, y, center=False)
            sub = f"{p['score']} pts"
            if total:
                sub += f"  ·  {p['progress']}/{total}"
            if p.get("finished"):
                sub += "  ·  done"
            draw_text(self.screen, sub, self.font_small, MUTED,
                      side.x + 18, y + 22, center=False)
            y += 50

        # Toast for the host's "X answered correctly" feedback
        if self.mp_recent_feedback_t > 0 and self.mp_recent_feedback:
            toast = pygame.Rect(side.x - 240, side.bottom - 50, 220, 38)
            tw_color = (STUDENT_COLOR if "Correct" in self.mp_recent_feedback
                        else BAD_RED)
            pygame.draw.rect(self.screen, lerp_color(PANEL_TOP, tw_color, 0.4),
                             toast, border_radius=14)
            draw_text(self.screen, self.mp_recent_feedback,
                      self.font_small, WHITE, toast.centerx, toast.centery)

    # ---- Helpers -------------------------------------------------------

    def _current_name_input(self):
        """Return the trimmed name typed in the lobby, if the input exists."""
        inp = getattr(self, "mp_name_input", None)
        if inp is not None:
            return inp.value.strip()
        return self.mp_player_name.strip() if self.mp_player_name else ""

    def _mp_player(self, pid):
        for p in self.mp_players:
            if p["id"] == pid:
                return p
        return None

    def _name_of(self, pid):
        p = self._mp_player(pid)
        return p["name"] if p else "?"

    def _teardown_multiplayer(self):
        for thing_attr in ("mp_beacon", "mp_listener", "mp_server", "mp_client"):
            thing = getattr(self, thing_attr, None)
            if thing:
                try:
                    thing.stop()
                except Exception:
                    pass
            setattr(self, thing_attr, None)
        self.mp_role = None
        self.mp_players = []
        self.mp_self_id = MP_HOST_ID
        self.mp_lesson = None
        self.mp_question_index = 0
        self.mp_summary = None

    # ---- Network event pump (called every frame from update()) --------

    def _pump_network(self):
        if self.mp_server:
            while True:
                try:
                    ev = self.mp_server.events.get_nowait()
                except Exception:
                    break
                self._handle_host_event(ev)
        if self.mp_client:
            while True:
                try:
                    ev = self.mp_client.events.get_nowait()
                except Exception:
                    break
                self._handle_client_event(ev)

    def _handle_host_event(self, ev):
        kind = ev.get("kind")
        if kind == "join":
            # Real name comes in the "hello" message.
            self.mp_players.append(self._new_player(ev["peer_id"], "…"))
            self._host_send_lobby()
        elif kind == "leave":
            pid = ev["peer_id"]
            self.mp_players = [p for p in self.mp_players if p["id"] != pid]
            self._host_send_lobby()
        elif kind == "msg":
            msg = ev.get("msg", {})
            pid = ev["peer_id"]
            t = msg.get("type")
            if t == "hello":
                name = str(msg.get("name", "Player")).strip() or "Player"
                self.mp_server.set_peer_name(pid, name)
                p = self._mp_player(pid)
                if p:
                    p["name"] = name
                self._host_send_lobby()
            elif t == "progress":
                # Race mode: a client just finished a question.
                p = self._mp_player(pid)
                if p:
                    p["progress"] = int(msg.get("question_index", p["progress"]))
                    p["score"]    = int(msg.get("score", p["score"]))
                    p["finished"] = bool(msg.get("finished", p["finished"]))
                self._host_broadcast_scoreboard()
                if self.mp_lesson and all(pp["finished"] for pp in self.mp_players):
                    self._host_end_game()
            elif t == "answer":
                self._host_apply_answer(pid, msg.get("choice"))

    def _host_send_lobby(self):
        if not self.mp_server:
            return
        roster = [{"id": p["id"], "name": p["name"]} for p in self.mp_players]
        self.mp_server.broadcast({"type": "lobby", "players": roster,
                                  "host_id": MP_HOST_ID})

    def _handle_client_event(self, ev):
        kind = ev.get("kind")
        if kind == "disconnected" or kind == "error":
            # Connection lost — drop back to the lobby with a quick message.
            self._teardown_multiplayer()
            self.show_lobby()
            return
        if kind != "msg":
            return
        msg = ev.get("msg", {})
        t = msg.get("type")

        if t == "lobby":
            players = msg.get("players", [])
            # Reconcile local roster. Self id = the one whose name == ours
            # and whose id is not the host's.
            self.mp_players = [self._new_player(p["id"], p["name"]) for p in players]
            # Identify ourselves by name match (and id != host).
            for p in players:
                if p["id"] != MP_HOST_ID and p["name"] == self.mp_player_name:
                    self.mp_self_id = p["id"]
                    break

        elif t == "start":
            self.mp_lesson = msg.get("lesson")
            self.mp_mode   = msg.get("mode", "race")
            self.mp_question_index = 0
            self.mp_current_player_id = msg.get("current_player_id", MP_HOST_ID)
            # Reset scores in our local roster.
            for p in self.mp_players:
                p["score"] = 0; p["progress"] = 0; p["finished"] = False
            self.show_mp_lesson()

        elif t == "scoreboard":
            players = msg.get("players", [])
            # Replace local roster scores (keep ids/names aligned).
            self.mp_players = [self._new_player(p["id"], p["name"])
                               | {"score": int(p.get("score", 0)),
                                  "progress": int(p.get("progress", 0)),
                                  "finished": bool(p.get("finished", False))}
                               for p in players]

        elif t == "show_question":
            self.mp_question_index = int(msg.get("question_index", 0))
            self.mp_current_player_id = msg.get("current_player_id", MP_HOST_ID)
            self.picked_words = []
            if (self.mp_lesson and
                    self.mp_question_index < len(self.mp_lesson["exercises"])):
                self._build_mp_choice_buttons()
            else:
                self.buttons = [b for b in self.buttons
                                if getattr(b, "_mp_persistent", False)]

        elif t == "answered":
            ok = bool(msg.get("correct", False))
            who = self._name_of(int(msg.get("by_id", MP_HOST_ID)))
            self.mp_recent_feedback = f"{who} — {'Correct!' if ok else 'Wrong.'}"
            self.mp_recent_feedback_t = 1.6
            self.avatar_mood = "happy" if ok else "sad"
            self.feedback_t = 0.6
            self.speech_text = random.choice(DUO_LINES["happy" if ok else "sad"])
            self.speech_mood = "happy" if ok else "sad"

        elif t == "game_over":
            self._enter_mp_summary(msg.get("players", []))

    # ----------------------------------------------------------
    # MAIN LOOP
    # ----------------------------------------------------------

    def handle_event(self, event):
        """React to one event from pygame."""
        if event.type == pygame.QUIT:
            self.running = False
            return

        # F11 toggles between fullscreen and a 1024×720 window.
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        # Let buttons see press/release events so they animate properly,
        # and fire the click callback when the release lands inside them.
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and event.button == 1:
            fired = False
            for button in list(self.buttons):
                if button.handle_event(event) and not fired:
                    button.on_click()
                    fired = True
            if event.type == pygame.MOUSEBUTTONDOWN and not fired:
                # Pass the click to text inputs so they can take focus.
                pass

        # Pass events to any text input on the current screen so clicks
        # focus the right one and key presses go to the focused field.
        if self.inputs and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            for inp in self.inputs:
                inp.handle_event(event)

        # Esc closes things one level up.
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.scene == "hub":
                self.quit_app()
            elif self.scene == "lesson":
                self.show_hub()
            elif self.scene == "summary":
                self.show_hub()
            elif self.scene == "lobby":
                self._lobby_back()
            elif self.scene == "shop":
                self.show_hub()
            elif self.scene in ("room", "mp_lesson", "mp_summary"):
                self._leave_room()

    def update(self, dt):
        """Per-frame animation updates (background drift, confetti, etc.)."""
        self.background.update(dt)

        if self.feedback_t > 0:
            self.feedback_t = max(0.0, self.feedback_t - dt)
        if self.mp_recent_feedback_t > 0:
            self.mp_recent_feedback_t = max(0.0, self.mp_recent_feedback_t - dt)

        # Lesson reveal pause: after a click, wait a moment so the player
        # sees the right/wrong colours, then advance.
        if self.pending_advance:
            self.pending_advance["t"] -= dt
            if self.pending_advance["t"] <= 0:
                correct = self.pending_advance["correct"]
                self.pending_advance = None
                self.next_question(correct=correct)

        for inp in self.inputs:
            inp.update(dt)

        # Drain any pending multiplayer events on every frame.
        self._pump_network()

        # Refresh the nearby-hosts list periodically while we're in the lobby.
        if self.scene == "lobby":
            self._mp_hosts_refresh_t += dt
            if self._mp_hosts_refresh_t >= 0.5:
                self._mp_hosts_refresh_t = 0.0
                self._refresh_lobby_hosts()

        if self.scene == "summary" and self.confetti:
            for c in self.confetti:
                c["vy"] += 80 * dt           # gentle gravity
                c["y"]  += c["vy"] * dt
                c["x"]  += c["vx"] * dt
                c["rot"] += c["spin"] * dt
            # Drop confetti that has fallen below the screen.
            self.confetti = [c for c in self.confetti if c["y"] < HEIGHT + 40]

    def draw(self):
        """Repaint the whole window for the current scene."""
        self.background.draw(self.screen)

        if self.scene == "hub":
            self.draw_hub()
        elif self.scene == "lesson":
            self.draw_lesson()
        elif self.scene == "summary":
            self.draw_summary()
        elif self.scene == "shop":
            self.draw_shop()
        elif self.scene == "lobby":
            self.draw_lobby()
        elif self.scene == "room":
            self.draw_room()
        elif self.scene == "mp_lesson":
            self.draw_mp_lesson()
        elif self.scene == "mp_summary":
            self.draw_mp_summary()

        # Every screen draws its buttons on top.
        for button in self.buttons:
            button.draw(self.screen, self.font_bold)

        pygame.display.flip()

    def run(self):
        """The main game loop."""
        last = time.time()
        while self.running:
            now = time.time()
            dt = now - last
            last = now

            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


# ============================================================
# 9. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    App().run()
