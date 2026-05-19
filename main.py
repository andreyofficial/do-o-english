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
    5.  UI HELPERS (Button, TextInput, draw_text)
    6.  GAME       (the App class: game loop and every screen)
    7.  ENTRY POINT
"""

# ============================================================
# 1. IMPORTS
# ============================================================

import hashlib        # to turn passwords into a safe-to-store string
import json           # to read the lesson .json files
import random         # to shuffle word-order exercises
import sqlite3        # to remember profiles and progress on disk
from pathlib import Path

import pygame         # the game library


# ============================================================
# 2. CONSTANTS
# ============================================================

# Window size in pixels.
WIDTH = 960
HEIGHT = 700                  # tall enough to fit the 4-field register form
FPS = 60                      # how many times per second we redraw

# Colors are (Red, Green, Blue), each from 0 to 255.
BG_COLOR      = (24, 28, 50)
PANEL_COLOR   = (38, 46, 78)
SOFT_PANEL    = (52, 62, 100)

WHITE         = (245, 248, 255)
MUTED         = (180, 190, 215)
DIM           = (130, 140, 165)

TEACHER_COLOR = (245, 140, 70)
TEACHER_HOVER = (255, 170, 100)
STUDENT_COLOR = (90, 200, 140)
STUDENT_HOVER = (120, 230, 170)
PROFILE_COLOR = (70, 130, 220)
PROFILE_HOVER = (100, 160, 250)
NEUTRAL_COLOR = (95, 105, 125)
NEUTRAL_HOVER = (125, 135, 160)
GOOD_GREEN    = (90, 200, 140)
BAD_RED       = (235, 95, 95)
GOLD          = (245, 200, 80)

# Where to find lessons and where to save progress.
ROOT_DIR    = Path(__file__).resolve().parent
CONTENT_DIR = ROOT_DIR / "content" / "en-a1" / "unit-01-cafe"
DB_PATH     = Path.home() / ".local" / "share" / "do-o-english" / "progress.db"


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

    # Add the password column to old databases that don't have it yet.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "password" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password TEXT NOT NULL DEFAULT ''")

    conn.commit()
    return conn


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


def find_user_for_login(conn, first_name, last_name, password):
    """
    Look up a user by first name + last name + password.
    Returns a dict if we find one, otherwise None.
    """
    row = conn.execute(
        """
        SELECT * FROM users
        WHERE LOWER(first_name) = LOWER(?)
          AND LOWER(last_name) = LOWER(?)
          AND password = ?
        """,
        (first_name.strip(), last_name.strip(), hash_password(password)),
    ).fetchone()
    return dict(row) if row else None


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
        # meta.json may use camelCase or snake_case
        ordered_ids = meta.get("lessonIds") or meta.get("lesson_ids") or []

    ordered_lessons = []
    for lesson_id in ordered_ids:
        if lesson_id in lessons_by_id:
            ordered_lessons.append(lessons_by_id[lesson_id])
    return ordered_lessons


# ============================================================
# 5. UI HELPERS
# ============================================================
# A `Button` is a colored rectangle with a text label. It knows how to
# draw itself and how to tell us when it has been clicked.
#
# A `TextInput` is a one-line text field the player can type in.
# ============================================================

class Button:
    """A clickable rectangle with text on it."""

    def __init__(self, text, x, y, w, h, base_color, hover_color, on_click):
        self.text = text
        self.rect = pygame.Rect(x, y, w, h)
        self.base_color = base_color
        self.hover_color = hover_color
        self.on_click = on_click

    def draw(self, screen, font):
        # Decide which color to use right now.
        mouse_pos = pygame.mouse.get_pos()
        if self.rect.collidepoint(mouse_pos):
            color = self.hover_color
        else:
            color = self.base_color

        # Draw the rectangle.
        pygame.draw.rect(screen, color, self.rect, border_radius=12)

        # Draw the label centered inside the rectangle.
        label_surface = font.render(self.text, True, WHITE)
        label_rect = label_surface.get_rect(center=self.rect.center)
        screen.blit(label_surface, label_rect)

    def is_clicked(self, event):
        """Was this button clicked by the given mouse event?"""
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class TextInput:
    """A simple one-line text field with a label above it."""

    def __init__(self, x, y, w, h, label, max_chars=24, is_password=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.max_chars = max_chars
        self.value = ""
        self.is_focused = False
        self.is_password = is_password   # if True, show dots instead of the real text

    def draw(self, screen, font_label, font_value):
        # Label above the box.
        label_surface = font_label.render(self.label, True, MUTED)
        screen.blit(label_surface, (self.rect.x, self.rect.y - 22))

        # Box background — a bit brighter when this field has focus.
        if self.is_focused:
            box_color = (60, 70, 110)
            border_color = (130, 180, 255)
        else:
            box_color = (45, 53, 90)
            border_color = (75, 85, 115)
        pygame.draw.rect(screen, box_color, self.rect, border_radius=8)
        pygame.draw.rect(screen, border_color, self.rect, width=2, border_radius=8)

        # Decide which text to display in the box.
        if not self.value and not self.is_focused:
            shown = "(type here)"
            text_color = DIM
        else:
            # For passwords show dots, never the real characters.
            if self.is_password:
                shown = "*" * len(self.value)
            else:
                shown = self.value
            if self.is_focused:
                shown += "|"
            text_color = WHITE

        text_surface = font_value.render(shown, True, text_color)
        screen.blit(
            text_surface,
            (self.rect.x + 12, self.rect.y + (self.rect.h - text_surface.get_height()) // 2),
        )

    def handle_event(self, event):
        """
        React to one pygame event. Returns:
          - "tab"     if the player pressed Tab while focused
          - "enter"   if the player pressed Enter while focused
          - None      otherwise
        """
        # Click to focus / unfocus.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.is_focused = self.rect.collidepoint(event.pos)

        # Typing only when focused.
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


def draw_text(screen, text, font, color, x, y, center=True):
    """Draw a single line of text. If center is True, (x, y) is the center."""
    surface = font.render(text, True, color)
    rect = surface.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    screen.blit(surface, rect)


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


# ============================================================
# 6. THE GAME
# ============================================================
# The App class holds everything: the window, the fonts, the current
# screen ("menu", "form", "hub", "lesson", "summary"), and the buttons
# / text inputs that belong to whatever screen we are showing.
# ============================================================

class App:

    def __init__(self):
        # --- Set up pygame ---
        pygame.init()
        pygame.display.set_caption("do-o-english")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.running = True

        # --- Fonts ---
        # SysFont(None, ...) uses pygame's default font, which works everywhere.
        self.font_title = pygame.font.SysFont(None, 64)
        self.font_h2    = pygame.font.SysFont(None, 36)
        self.font_body  = pygame.font.SysFont(None, 26)
        self.font_small = pygame.font.SysFont(None, 20)

        # --- Game data ---
        self.db = open_database()
        self.lessons = load_lessons()
        self.user = None             # the currently logged-in user (dict) or None

        # --- Current screen state ---
        self.scene = "menu"          # "menu" / "form" / "hub" / "lesson" / "summary"
        self.buttons = []            # buttons on the current screen
        self.inputs = []             # text inputs on the current screen
        self.error_text = ""         # red error message under the form

        # Form-specific state
        self.form_role = "student"
        self.form_keys = []          # which input maps to which db column
        self.login_keys = []         # same idea, for the login form

        # Lesson-specific state
        self.current_lesson = None
        self.question_index = 0
        self.correct_count = 0
        self.picked_words = []       # for word_order exercises
        self.feedback_text = ""      # short "Correct!"/"Wrong!" message
        self.feedback_color = WHITE
        self.summary_data = {}

        # Show the menu first.
        self.show_menu()

    # ----------------------------------------------------------
    # SCREEN: MENU
    # ----------------------------------------------------------

    def show_menu(self):
        """Build the main menu — three big buttons: Log in, Teacher, Student."""
        self.scene = "menu"
        self.buttons = []
        self.inputs = []
        self.error_text = ""

        button_w = 360
        button_h = 70
        x = (WIDTH - button_w) // 2

        # 'Log in' is the primary action.
        self.buttons.append(Button(
            "Log in",
            x, 280, button_w, button_h,
            PROFILE_COLOR, PROFILE_HOVER,
            on_click=self.open_login,
        ))
        self.buttons.append(Button(
            "Register as Teacher",
            x, 280 + 90, button_w, button_h,
            TEACHER_COLOR, TEACHER_HOVER,
            on_click=lambda: self.open_form("teacher"),
        ))
        self.buttons.append(Button(
            "Register as Student",
            x, 280 + 180, button_w, button_h,
            STUDENT_COLOR, STUDENT_HOVER,
            on_click=lambda: self.open_form("student"),
        ))

    def draw_menu(self):
        # Header panel
        pygame.draw.rect(self.screen, PANEL_COLOR, (40, 30, WIDTH - 80, 200), border_radius=14)
        draw_text(self.screen, "do-o-english", self.font_title, WHITE, WIDTH // 2, 100)
        draw_text(self.screen, "Learn English the fun way", self.font_body, MUTED, WIDTH // 2, 160)
        # Accent line under the title
        pygame.draw.rect(self.screen, PROFILE_COLOR, (WIDTH // 2 - 130, 192, 260, 3))

        # How many people use this game on this computer?
        total_users = len(list_users(self.db))
        draw_text(
            self.screen,
            f"{total_users} profile(s) on this computer",
            self.font_small, DIM, WIDTH // 2, 250,
        )

        # Footer hint
        draw_text(
            self.screen,
            "Tab / Arrows = next field   ·   Enter = confirm   ·   Esc = back",
            self.font_small, DIM, WIDTH // 2, HEIGHT - 30,
        )

    # ----------------------------------------------------------
    # SCREEN: FORM
    # ----------------------------------------------------------

    def open_form(self, role):
        """Switch to the register form for either teacher or student."""
        self.scene = "form"
        self.form_role = role
        self.buttons = []
        self.inputs = []
        self.error_text = ""

        # Field order depends on the role. Password is always last.
        if role == "teacher":
            field_specs = [
                ("last_name",  "Last name",            False),
                ("first_name", "First name (prename)", False),
                ("class_name", "Class you teach",      False),
                ("password",   "Password",             True),
            ]
        else:
            field_specs = [
                ("class_name", "Your class",           False),
                ("last_name",  "Last name",            False),
                ("first_name", "First name (prename)", False),
                ("password",   "Password",             True),
            ]
        self.form_keys = [key for (key, _, _) in field_specs]

        # Build the four text-input boxes (label sits above the box).
        y = 210
        for (key, label, is_password) in field_specs:
            self.inputs.append(TextInput(
                WIDTH // 2 - 200, y, 400, 42, label,
                max_chars=32, is_password=is_password,
            ))
            y += 78
        self.inputs[0].is_focused = True   # focus the first one

        # Bottom buttons.
        accent = TEACHER_COLOR if role == "teacher" else STUDENT_COLOR
        accent_hover = TEACHER_HOVER if role == "teacher" else STUDENT_HOVER

        self.buttons.append(Button(
            "Back",
            WIDTH // 2 - 200, HEIGHT - 110, 140, 50,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.show_menu,
        ))
        self.buttons.append(Button(
            "Create profile",
            WIDTH // 2 - 40, HEIGHT - 110, 240, 50,
            accent, accent_hover, on_click=self.submit_form,
        ))

    def draw_form(self):
        # Card panel
        pygame.draw.rect(
            self.screen, PANEL_COLOR,
            (60, 50, WIDTH - 120, HEIGHT - 100), border_radius=14,
        )

        # Title in the role's color
        accent = TEACHER_COLOR if self.form_role == "teacher" else STUDENT_COLOR
        title = "Register as Teacher" if self.form_role == "teacher" else "Register as Student"
        draw_text(self.screen, title, self.font_title, accent, WIDTH // 2, 110)
        pygame.draw.rect(self.screen, accent, (WIDTH // 2 - 100, 145, 200, 3))

        # Hint sits comfortably below the accent line and above the first label.
        draw_text(
            self.screen,
            "Fill in your details — Tab to switch field, Enter to confirm.",
            self.font_small, MUTED, WIDTH // 2, 170,
        )

        # The text fields (label + box per field)
        for text_input in self.inputs:
            text_input.draw(self.screen, self.font_small, self.font_body)

        # Error message (in red) just above the bottom buttons
        if self.error_text:
            draw_text(
                self.screen, self.error_text, self.font_body, BAD_RED,
                WIDTH // 2, HEIGHT - 155,
            )

    def focus_next_input(self, direction=1):
        """Move focus to the next (or previous) text field."""
        if not self.inputs:
            return
        # Find which one is currently focused.
        current = 0
        for i, inp in enumerate(self.inputs):
            if inp.is_focused:
                current = i
                break
        # Compute the new index and update focus flags.
        new_index = (current + direction) % len(self.inputs)
        for i, inp in enumerate(self.inputs):
            inp.is_focused = (i == new_index)

    def submit_form(self):
        """Validate the form, save the user, log them in, then go to the hub."""
        values = {}
        missing = []
        for i, key in enumerate(self.form_keys):
            # Don't strip the password on the right because spaces could be intentional,
            # but trim outer whitespace just in case.
            text = self.inputs[i].value.strip()
            if text == "":
                missing.append(self.inputs[i].label)
            values[key] = text

        if missing:
            self.error_text = "Please fill: " + ", ".join(missing)
            return

        # Tiny password sanity check.
        if len(values["password"]) < 3:
            self.error_text = "Password must be at least 3 characters."
            return

        user_id = create_user(
            self.db,
            role=self.form_role,
            first_name=values["first_name"],
            last_name=values["last_name"],
            class_name=values["class_name"],
            password=values["password"],
        )
        self.login(user_id)

    # ----------------------------------------------------------
    # SCREEN: LOGIN
    # ----------------------------------------------------------

    def open_login(self):
        """Switch to the log-in screen (first name + last name + password)."""
        self.scene = "login"
        self.buttons = []
        self.inputs = []
        self.error_text = ""

        self.login_keys = ["first_name", "last_name", "password"]
        field_specs = [
            ("First name (prename)", False),
            ("Last name",            False),
            ("Password",             True),
        ]

        y = 230
        for (label, is_password) in field_specs:
            self.inputs.append(TextInput(
                WIDTH // 2 - 200, y, 400, 42, label,
                max_chars=32, is_password=is_password,
            ))
            y += 78
        self.inputs[0].is_focused = True

        self.buttons.append(Button(
            "Back",
            WIDTH // 2 - 200, HEIGHT - 110, 140, 50,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.show_menu,
        ))
        self.buttons.append(Button(
            "Log in",
            WIDTH // 2 - 40, HEIGHT - 110, 240, 50,
            PROFILE_COLOR, PROFILE_HOVER, on_click=self.submit_login,
        ))

    def draw_login(self):
        # Card panel
        pygame.draw.rect(
            self.screen, PANEL_COLOR,
            (60, 50, WIDTH - 120, HEIGHT - 100), border_radius=14,
        )

        # Title
        draw_text(self.screen, "Log in", self.font_title, WHITE, WIDTH // 2, 130)
        pygame.draw.rect(self.screen, PROFILE_COLOR, (WIDTH // 2 - 80, 165, 160, 3))
        draw_text(
            self.screen,
            "Type your name and password to continue.",
            self.font_small, MUTED, WIDTH // 2, 190,
        )

        # Fields
        for text_input in self.inputs:
            text_input.draw(self.screen, self.font_small, self.font_body)

        # Error message (in red) above the buttons
        if self.error_text:
            draw_text(
                self.screen, self.error_text, self.font_body, BAD_RED,
                WIDTH // 2, HEIGHT - 155,
            )

    def submit_login(self):
        """Try to find the user. If we do, log them in."""
        values = {}
        missing = []
        for i, key in enumerate(self.login_keys):
            text = self.inputs[i].value.strip()
            if text == "":
                missing.append(self.inputs[i].label)
            values[key] = text

        if missing:
            self.error_text = "Please fill: " + ", ".join(missing)
            return

        user = find_user_for_login(
            self.db,
            first_name=values["first_name"],
            last_name=values["last_name"],
            password=values["password"],
        )
        if user is None:
            self.error_text = "Wrong name or password. Please try again."
            # Clear the password so the player can retype it.
            for i, key in enumerate(self.login_keys):
                if key == "password":
                    self.inputs[i].value = ""
            return

        self.login(user["id"])

    # ----------------------------------------------------------
    # SCREEN: HUB (list of lessons)
    # ----------------------------------------------------------

    def login(self, user_id):
        """Mark this user as the active one and go to the hub."""
        for user in list_users(self.db):
            if user["id"] == user_id:
                self.user = user
                break
        self.show_hub()

    def logout(self):
        """Forget the current user and go back to the main menu."""
        self.user = None
        self.show_menu()

    def show_hub(self):
        """Build the hub: a top bar with the user, then a list of lessons."""
        self.scene = "hub"
        self.buttons = []
        self.inputs = []

        done_ids = finished_lesson_ids(self.db, self.user["id"]) if self.user else set()

        # One button per lesson.
        y = 170
        for lesson in self.lessons:
            is_done = lesson["id"] in done_ids
            prefix = "[done] " if is_done else "       "
            label = prefix + lesson["title"]
            color = GOOD_GREEN if is_done else PROFILE_COLOR
            hover = STUDENT_HOVER if is_done else PROFILE_HOVER

            def start_this_lesson(lesson=lesson):
                self.start_lesson(lesson)

            self.buttons.append(Button(
                label, WIDTH // 2 - 240, y, 480, 56,
                color, hover, on_click=start_this_lesson,
            ))
            y += 64

        # Log-out button in the corner.
        self.buttons.append(Button(
            "Log out", 20, HEIGHT - 60, 110, 40,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.logout,
        ))

    def draw_hub(self):
        # Top banner with the user's info
        pygame.draw.rect(self.screen, PANEL_COLOR, (0, 0, WIDTH, 130))
        if self.user:
            name = f"{self.user['first_name']} {self.user['last_name']}"
            role_text = self.user["role"].title()
            class_name = self.user["class_name"]
            xp = self.user["xp"]
            draw_text(
                self.screen,
                f"{name}   ·   {role_text} · class {class_name}",
                self.font_h2, WHITE, WIDTH // 2, 45,
            )
            draw_text(self.screen, f"{xp} XP", self.font_body, GOLD, WIDTH // 2, 80)

        draw_text(self.screen, "Choose a lesson", self.font_h2, MUTED, WIDTH // 2, 145)

    # ----------------------------------------------------------
    # SCREEN: LESSON
    # ----------------------------------------------------------

    def start_lesson(self, lesson):
        """Begin a lesson from question 1."""
        self.scene = "lesson"
        self.current_lesson = lesson
        self.question_index = 0
        self.correct_count = 0
        self.show_question()

    def show_question(self):
        """Build buttons for the current exercise."""
        self.buttons = []
        self.feedback_text = ""
        self.picked_words = []

        exercise = self.current_lesson["exercises"][self.question_index]
        kind = exercise["type"]

        # ---- Most exercises: show a list of "choice" buttons. ----
        if kind in ("multiple_choice", "listen_select", "fill_blank"):
            choices = list(exercise.get("choices", []))
            self.build_choice_buttons(choices, on_pick=self.check_choice_answer)

        # ---- word_order: shuffled words; player taps them in order. ----
        elif kind == "word_order":
            words = list(exercise.get("words", []))
            random.shuffle(words)
            self.build_choice_buttons(words, on_pick=self.pick_word)

        # ---- tap_pairs: too complex for v1 → show a Skip button. ----
        else:
            self.buttons.append(Button(
                "Skip this question",
                WIDTH // 2 - 130, 360, 260, 60,
                NEUTRAL_COLOR, NEUTRAL_HOVER,
                on_click=lambda: self.next_question(correct=False),
            ))

        # Quit-lesson button in the corner
        self.buttons.append(Button(
            "Quit lesson", 20, HEIGHT - 60, 130, 40,
            NEUTRAL_COLOR, NEUTRAL_HOVER, on_click=self.show_hub,
        ))

    def build_choice_buttons(self, choices, on_pick):
        """
        Lay choice buttons out in a 2-column grid, centered on screen.
        `on_pick(index)` is called when a button is clicked.
        """
        cols = 2
        button_w = 320
        button_h = 60
        gap_x = 24
        gap_y = 18
        row_count = (len(choices) + cols - 1) // cols

        total_w = cols * button_w + (cols - 1) * gap_x
        start_x = (WIDTH - total_w) // 2
        start_y = 320

        for i, choice_text in enumerate(choices):
            row = i // cols
            col = i % cols
            x = start_x + col * (button_w + gap_x)
            y = start_y + row * (button_h + gap_y)

            def pick_this(index=i):
                on_pick(index)

            self.buttons.append(Button(
                choice_text, x, y, button_w, button_h,
                PROFILE_COLOR, PROFILE_HOVER, on_click=pick_this,
            ))

    def check_choice_answer(self, choice_index):
        """Check the answer for multiple-choice-like exercises."""
        exercise = self.current_lesson["exercises"][self.question_index]
        correct_answer = exercise.get("answer", 0)

        if exercise["type"] == "fill_blank":
            # The answer is a string; compare with the chosen string.
            chosen_text = exercise["choices"][choice_index]
            is_correct = (chosen_text.strip().lower()
                          == str(correct_answer).strip().lower())
        else:
            # Answer is an index into choices.
            is_correct = (choice_index == int(correct_answer))

        self.next_question(correct=is_correct)

    def pick_word(self, choice_index):
        """
        Used by word_order: the player clicks words one by one. When all
        words are clicked we check the order.
        """
        button = self.buttons[choice_index]
        if button.text in self.picked_words:
            return                              # already used
        self.picked_words.append(button.text)
        # Grey it out so the player sees what's done.
        button.base_color = NEUTRAL_COLOR
        button.hover_color = NEUTRAL_HOVER

        exercise = self.current_lesson["exercises"][self.question_index]
        target_words = list(exercise.get("words", []))
        if len(self.picked_words) == len(target_words):
            is_correct = (self.picked_words == target_words)
            self.next_question(correct=is_correct)

    def next_question(self, correct):
        """Move to the next question, or finish the lesson if we ran out."""
        if correct:
            self.correct_count += 1

        self.question_index += 1
        if self.question_index >= len(self.current_lesson["exercises"]):
            self.finish_lesson()
        else:
            self.show_question()

    def draw_lesson(self):
        exercise = self.current_lesson["exercises"][self.question_index]
        total = len(self.current_lesson["exercises"])

        # Top: lesson title + progress
        pygame.draw.rect(self.screen, PANEL_COLOR, (0, 0, WIDTH, 100))
        draw_text(
            self.screen, self.current_lesson["title"],
            self.font_h2, WHITE, WIDTH // 2, 40,
        )
        draw_text(
            self.screen,
            f"Question {self.question_index + 1} / {total}   ·   {self.correct_count} correct",
            self.font_small, MUTED, WIDTH // 2, 75,
        )

        # The prompt (word-wrapped so it fits on screen).
        prompt = exercise.get("prompt", "")
        lines = wrap_lines(prompt, self.font_body, WIDTH - 160)
        y = 150
        for line in lines:
            draw_text(self.screen, line, self.font_body, WHITE, WIDTH // 2, y)
            y += 32

        # For word_order, show the words the player has picked so far.
        if exercise.get("type") == "word_order":
            chosen = " ".join(self.picked_words) if self.picked_words else "(click words in order)"
            draw_text(self.screen, chosen, self.font_h2, GOLD, WIDTH // 2, 260)

    # ----------------------------------------------------------
    # SCREEN: SUMMARY
    # ----------------------------------------------------------

    def finish_lesson(self):
        """Save the result, give XP, switch to the summary screen."""
        total = len(self.current_lesson["exercises"])
        score = round(100 * self.correct_count / max(total, 1))
        xp = self.current_lesson.get("xpReward", 10)

        if self.user:
            mark_lesson_done(self.db, self.user["id"], self.current_lesson["id"], score)
            add_xp(self.db, self.user["id"], xp)
            self.user["xp"] += xp

        self.summary_data = {
            "title": self.current_lesson["title"],
            "outro": self.current_lesson.get("npcOutro", "Great job!"),
            "correct": self.correct_count,
            "total": total,
            "score": score,
            "xp": xp,
        }
        self.scene = "summary"
        self.buttons = [
            Button(
                "Back to lessons",
                WIDTH // 2 - 130, HEIGHT - 90, 260, 60,
                GOOD_GREEN, STUDENT_HOVER, on_click=self.show_hub,
            )
        ]
        self.inputs = []

    def draw_summary(self):
        data = self.summary_data
        pygame.draw.rect(self.screen, PANEL_COLOR, (80, 80, WIDTH - 160, HEIGHT - 200), border_radius=14)

        draw_text(self.screen, "Lesson complete!", self.font_title, GOOD_GREEN, WIDTH // 2, 150)
        draw_text(self.screen, data["title"], self.font_h2, WHITE, WIDTH // 2, 210)
        draw_text(
            self.screen,
            f"{data['correct']} / {data['total']} correct   ·   Score: {data['score']}%",
            self.font_body, MUTED, WIDTH // 2, 270,
        )
        draw_text(self.screen, f"+{data['xp']} XP", self.font_h2, GOLD, WIDTH // 2, 320)
        # Outro quote (word-wrapped)
        for i, line in enumerate(wrap_lines(data["outro"], self.font_body, WIDTH - 240)):
            draw_text(self.screen, line, self.font_body, MUTED, WIDTH // 2, 370 + i * 32)

    # ----------------------------------------------------------
    # MAIN LOOP
    # ----------------------------------------------------------

    def handle_event(self, event):
        """React to one event from pygame."""
        if event.type == pygame.QUIT:
            self.running = False
            return

        # Pass mouse clicks to every button on the current screen.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in list(self.buttons):
                if button.is_clicked(event):
                    button.on_click()
                    return

        # Any text-input screen (register form OR log-in) — typing + tab/enter/esc.
        if self.scene in ("form", "login"):
            for text_input in self.inputs:
                result = text_input.handle_event(event)
                if result == "tab":
                    self.focus_next_input(direction=1)
                elif result == "enter":
                    if self.scene == "form":
                        self.submit_form()
                    else:
                        self.submit_login()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.show_menu()
                elif event.key == pygame.K_UP:
                    self.focus_next_input(direction=-1)
                elif event.key == pygame.K_DOWN:
                    self.focus_next_input(direction=1)

        # Menu / hub / lesson / summary — Escape goes back one step.
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.scene == "hub":
                self.logout()
            elif self.scene == "lesson":
                self.show_hub()
            elif self.scene == "summary":
                self.show_hub()

    def draw(self):
        """Repaint the whole window for the current scene."""
        self.screen.fill(BG_COLOR)

        if self.scene == "menu":
            self.draw_menu()
        elif self.scene == "form":
            self.draw_form()
        elif self.scene == "login":
            self.draw_login()
        elif self.scene == "hub":
            self.draw_hub()
        elif self.scene == "lesson":
            self.draw_lesson()
        elif self.scene == "summary":
            self.draw_summary()

        # Every screen draws its buttons on top.
        for button in self.buttons:
            button.draw(self.screen, self.font_body)

        pygame.display.flip()

    def run(self):
        """The main game loop."""
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


# ============================================================
# 7. ENTRY POINT
# ============================================================

if __name__ == "__main__":
    App().run()
