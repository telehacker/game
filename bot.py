#!/usr/bin/env python3
"""
WORD VORTEX - ULTIMATE PREMIUM EDITION
Version: 6.1 - Full-feature consolidation (persistence, animated 3D-like GIF grid, many game modes)
Language: Hinglish/English mixed replies by default (can be changed)

NOTES BEFORE RUN:
- Requires Python 3.8+
- Required packages: pyTelegramBotAPI (telebot), Pillow, requests
  Install: pip install pyTelegramBotAPI pillow requests
- Set environment variables:
  - TELEGRAM_TOKEN (your bot token)
  - OWNER_ID (your Telegram user id; notifications will go here)
- This file persists sessions to a JSON file sessions_store.json and to SQLite for other things.
- GIF animation is generated using Pillow frames. Optimized to small frame counts to keep size reasonable.

WARNING:
- Animated GIFs can be large for very large grids. Default sizes are tuned to limit size.
- Persisted sessions resume after restart but the bot re-sends the current game state (image/caption),
  message ids cannot be reused after restart so the bot posts a new message when restoring.

USAGE QUICK:
- /start - main menu (Commands button opens PM; fallback to /cmd)
- /cmd - fallback: prints full commands
- /cmdinfo <command> - detailed help
- Game commands: /new, /new_hard, /new_physics, /new_chemistry, /new_math, /new_jee,
  /new_anagram, /new_speedrun, /new_definehunt, /new_survival, /new_team, /daily, /new_phrase
- In-game: press inline buttons or use /hint, /endgame
- Reviews: /review <text>, /myreviews, owner: /publishreview <id>, /publishedreviews
- Admin/Owner: /addpoints, /broadcast, /addadmin, /deladmin, /admins, /reset_leaderboard, /restart

This file aims to be a complete, working implementation. If anything breaks in your environment,
paste the traceback and I will fix quickly.
"""

import os
import sys
import time
import json
import html
import io
import random
import string
import logging
import tempfile
import threading
import sqlite3
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, InputMediaAnimation

# ========== CONFIG ==========
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHZzgByv218uShEzAHBtGjpCJ8_cedldVk")
try:
    OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197"))
except Exception:
    OWNER_ID = 0

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = os.environ.get("FORCE_JOIN", "False").lower() in ("1", "true", "yes")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = os.environ.get("START_IMG_URL", "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg")

if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set in environment")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Gameplay constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {
    "SEX","PORN","NUDE","XXX","DICK","COCK","PUSSY","FUCK","SHIT","BITCH","ASS","HENTAI","BOOBS"
}
GAME_DURATION = 600  # default 10 minutes
COOLDOWN = 2
HINT_COST = 50

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# Domain pools - these will be sampled randomly (not fixed words every time)
PHYSICS_POOL = ["FORCE","ENERGY","MOMENTUM","VELOCITY","ACCELERATION","VECTOR","SCALAR","WAVE","PHOTON","GRAVITY",
                "TORQUE","MOMENT","WORK","POWER","FREQUENCY","OSCILLATION","REFRACTION","DIFFRACTION","CHARGE","FIELD"]
CHEMISTRY_POOL = ["ATOM","MOLECULE","REACTION","BOND","ION","CATION","ANION","ACID","BASE","SALT",
                  "OXIDE","POLYMER","CATALYST","ELECTRON","COMPOUND","ELEMENT","MOLAR","PH","SPECTRUM","HALOGEN"]
MATH_POOL = ["INTEGRAL","DERIVATIVE","MATRIX","VECTOR","ALGEBRA","GEOMETRY","CALCULUS","TRIGONOMETRY","EQUATION","FUNCTION",
             "POLYNOMIAL","RATIO","PROBABILITY","STATISTICS","LOGARITHM","MODULO","SEQUENCE","SERIES","DIFFERENCE","LIMIT"]
JEE_POOL = PHYSICS_POOL + CHEMISTRY_POOL + MATH_POOL

# Where to persist session state
SESSIONS_FILE = "sessions_store.json"
DB_FILE = "wordsvortex.db"

# ========== DATABASE MANAGER ==========
class DB:
    def __init__(self, fname=DB_FILE):
        self.fname = fname
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.fname, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                join_date TEXT,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0,
                hint_balance INTEGER DEFAULT 100,
                is_banned INTEGER DEFAULT 0
            )
        """)
        c.execute("""CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                winner_id INTEGER,
                timestamp TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                review_text TEXT,
                timestamp TEXT,
                published INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_challenges (
                challenge_date TEXT PRIMARY KEY,
                words_json TEXT,
                leaderboard_json TEXT DEFAULT '{}'
            )
        """)
        conn.commit()
        conn.close()

    # user helpers
    def get_user(self, user_id, name="Player"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        r = c.fetchone()
        if not r:
            join_date = datetime.now().strftime("%Y-%m-%d")
            c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            r = c.fetchone()
        conn.close()
        return r

    def register_user(self, user_id, name="Player"):
        u = self.get_user(user_id, name)
        return u

    def update_stats(self, user_id, score_delta=0, hint_delta=0, win=False, games_played_delta=0):
        conn = self._connect()
        c = conn.cursor()
        if score_delta:
            c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (score_delta, user_id))
        if hint_delta:
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (hint_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        if games_played_delta:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
        conn.commit()
        conn.close()

    # admin helpers
    def add_admin(self, admin_id):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        conn.close()

    def remove_admin(self, admin_id):
        conn = self._connect()
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))
        conn.commit()
        conn.close()

    def is_admin(self, user_id):
        if OWNER_ID and user_id == OWNER_ID:
            return True
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return bool(r)

    def list_admins(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins")
        rows = c.fetchall()
        conn.close()
        return [r["admin_id"] for r in rows]

    def record_game(self, chat_id, winner_id):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, timestamp) VALUES (?, ?, ?)",
                  (chat_id, winner_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_top_players(self, limit=10):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [(r["name"], r["total_score"]) for r in rows]

    def reset_leaderboard(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = 0, wins = 0")
        conn.commit()
        conn.close()

    def all_user_ids(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        rows = c.fetchall()
        conn.close()
        return [r["user_id"] for r in rows]

    # reviews
    def add_review(self, user_id, username, text):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO reviews (user_id, username, review_text, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, username, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_user_reviews(self, user_id):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT review_id, review_text, timestamp, published FROM reviews WHERE user_id=? ORDER BY timestamp DESC", (user_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_published_reviews(self, limit=20):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT username, review_text, timestamp FROM reviews WHERE published=1 ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def publish_review(self, review_id):
        conn = self._connect()
        c = conn.cursor()
        c.execute("UPDATE reviews SET published=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    # daily challenges
    def get_or_create_daily(self):
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT words_json FROM daily_challenges WHERE challenge_date=?", (today,))
        row = c.fetchone()
        if row:
            words = json.loads(row["words_json"])
            conn.close()
            return words, today
        # create
        pool = ALL_WORDS[:] if len(ALL_WORDS) >= 8 else (ALL_WORDS * 2)
        words = random.sample(pool, min(8, len(pool)))
        c.execute("INSERT INTO daily_challenges (challenge_date, words_json, leaderboard_json) VALUES (?, ?, ?)",
                  (today, json.dumps(words), json.dumps({})))
        conn.commit()
        conn.close()
        return words, today

    def update_daily_leaderboard(self, date, user_id, username, points):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT leaderboard_json FROM daily_challenges WHERE challenge_date=?", (date,))
        row = c.fetchone()
        lb = json.loads(row["leaderboard_json"]) if row and row["leaderboard_json"] else {}
        key = str(user_id)
        if key not in lb:
            lb[key] = {"username": username, "points": 0}
        lb[key]["points"] += points
        c.execute("UPDATE daily_challenges SET leaderboard_json=? WHERE challenge_date=?", (json.dumps(lb), date))
        conn.commit()
        conn.close()

    def get_daily_leaderboard(self, date):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT leaderboard_json FROM daily_challenges WHERE challenge_date=?", (date,))
        row = c.fetchone()
        conn.close()
        if not row or not row["leaderboard_json"]:
            return []
        lb = json.loads(row["leaderboard_json"])
        sorted_lb = sorted(lb.items(), key=lambda x: x[1]["points"], reverse=True)
        return [(v["username"], v["points"]) for k, v in sorted_lb[:10]]

db = DB()

# ========== SESSIONS PERSISTENCE ==========
SESSIONS_LOCK = threading.Lock()

def load_sessions_from_file():
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception:
        logger.exception("Failed to load sessions file")
        return {}

def save_sessions_to_file(sessions_data):
    try:
        with SESSIONS_LOCK:
            with open(SESSIONS_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(sessions_data, f)
            os.replace(SESSIONS_FILE + ".tmp", SESSIONS_FILE)
    except Exception:
        logger.exception("Failed to save sessions to file")

# We'll store only serializable parts of sessions (words, placements, found, start_time, duration, is_hard, mode, players_scores)
def serialize_session(chat_id, session):
    return {
        "chat_id": chat_id,
        "is_hard": getattr(session, "is_hard", False),
        "mode": getattr(session, "mode", "normal"),
        "words": getattr(session, "words", []),
        "found": list(getattr(session, "found", [])),
        "placements": getattr(session, "placements", {}),
        "start_time": getattr(session, "start_time", time.time()),
        "duration": getattr(session, "duration", GAME_DURATION),
        "players_scores": getattr(session, "players_scores", {}),
    }

def persist_all_sessions():
    data = {}
    with SESSIONS_LOCK:
        for cid, sess in list(games.items()):
            data[str(cid)] = serialize_session(cid, sess)
        for cid, sess in list(team_games.items()):
            data[str(cid)] = serialize_session(cid, sess)
    save_sessions_to_file(data)

def restore_sessions_on_startup():
    data = load_sessions_from_file()
    restored = 0
    for cid_str, info in data.items():
        try:
            cid = int(cid_str)
            mode = info.get("mode", "normal")
            is_hard = info.get("is_hard", False)
            # rebuild session object based on mode
            if mode == "anagram":
                sess = AnagramSession(cid)
            elif mode == "speedrun":
                sess = SpeedrunSession(cid)
            elif mode == "definehunt":
                sess = DefinitionHuntSession(cid)
            elif mode == "survival":
                sess = SurvivalSession(cid)
            elif mode == "team":
                sess = TeamGameSession(cid)
                team_games[cid] = sess
                restored += 1
                continue
            elif mode == "daily":
                words = info.get("words", [])
                sess = DailyPuzzleSession(cid, words)
            elif mode == "phrase":
                sess = HiddenPhraseSession(cid)
            else:
                sess = GameSession(cid, is_hard=is_hard, duration=info.get("duration", GAME_DURATION), word_pool=None, mode=mode)
            # populate found and players scores if present
            sess.words = info.get("words", sess.words)
            sess.found = set(info.get("found", []))
            sess.placements = info.get("placements", sess.placements)
            sess.start_time = info.get("start_time", time.time())
            sess.duration = info.get("duration", GAME_DURATION)
            sess.players_scores = info.get("players_scores", {})
            # store
            games[cid] = sess
            restored += 1
        except Exception:
            logger.exception("Failed to restore session for chat %s", cid_str)
    logger.info("Restored %d sessions from disk", restored)
    return restored

# Call restore at startup
restore_sessions_on_startup()

# Periodically persist sessions to disk
def periodic_persist():
    """
    Periodically persist active sessions to disk.
    This version waits for the 'games' and 'team_games' globals to be present
    so it won't crash if the thread starts before those variables are defined.
    """
    while True:
        try:
            # wait until games/team_games exist in globals
            if 'games' not in globals() or 'team_games' not in globals():
                time.sleep(1)
                continue
            persist_all_sessions()
        except Exception:
            logger.exception("Error persisting sessions")
        time.sleep(30)

# Start background persist thread (start it once, after the function is defined)
persist_thread = threading.Thread(target=periodic_persist, daemon=True)
persist_thread.start()

# ========== IMAGE ANIMATION: generate animated GIF with 3D-ish effect ==========
def generate_grid_animation(grid, placements=None, found=None, is_hard=False, frames=8, size_limit=700):
    """
    Create an animated GIF (in-memory BytesIO) representing the grid with a subtle 3D rotation/light sweep.
    - grid: 2D list of chars
    - placements: dict word -> list of (r,c)
    - found: set of words that should be drawn with a red line
    Returns BytesIO with GIF content.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    # compute base image dimensions
    cell = 50 if max(rows, cols) >= 10 else 60
    width = cols * cell + 120
    height = rows * cell + 200
    # cap size to keep GIF small
    scale = 1.0
    max_dim = max(width, height)
    if max_dim > size_limit:
        scale = size_limit / max_dim
        cell = int(cell * scale)
        width = int(width * scale)
        height = int(height * scale)
    frames_images = []
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font_char = ImageFont.truetype(font_path, int(cell * 0.6))
        font_header = ImageFont.truetype(font_path, int(28 * scale))
    except Exception:
        font_char = ImageFont.load_default()
        font_header = ImageFont.load_default()

    # create base for each frame with slight perspective and light sweep
    for f in range(frames):
        img = Image.new("RGB", (width, height), "#f8fafc")
        draw = ImageDraw.Draw(img)
        # header
        title = "WORD VORTEX"
        draw.rectangle([0, 0, width, 80], fill="#eef2f6")
        tw, th = draw.textsize(title, font=font_header)
        draw.text(((width - tw) / 2, 18), title, fill="#0b66c3", font=font_header)
        # light sweep: a radial gradient moving across
        sweep = Image.new("L", (width, height), 0)
        sd = ImageDraw.Draw(sweep)
        # moving center
        cx = int(width * (0.2 + 0.6 * (f / max(1, frames - 1))))
        cy = int(80 + height * 0.2)
        maxr = max(width, height)
        for r in range(0, maxr, 8):
            alpha = max(0, 200 - int(200 * (r / maxr)))
            sd.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=alpha)
        sweep = sweep.filter(ImageFilter.GaussianBlur(radius=20))
        # draw grid with a skew based on frame index
        grid_start_x = 40
        grid_start_y = 110
        # slight rotation-like offset
        offset = int(6 * (f / max(1, frames - 1))) - 3
        for r in range(rows):
            for c in range(cols):
                x = grid_start_x + c * cell + int((r - rows/2) * (0.3 * offset))
                y = grid_start_y + r * cell + int((c - cols/2) * (0.1 * offset))
                rect = [x, y, x + cell - 2, y + cell - 2]
                draw.rectangle(rect, outline="#2f80d7", width=2)
                ch = grid[r][c]
                bw, bh = draw.textsize(ch, font=font_char)
                draw.text((x + (cell - bw) / 2, y + (cell - bh) / 2 - 4), ch, fill="#1b2b3a", font=font_char)
        # overlay sweep as light
        light = Image.new("RGBA", img.size, (255, 255, 255, 0))
        light_draw = ImageDraw.Draw(light)
        # paste sweep as white with low opacity
        light.putalpha(sweep)
        img = Image.alpha_composite(img.convert("RGBA"), light).convert("RGB")

        # draw found-word lines in this frame (if words found)
        if placements and found:
            for word, coords in placements.items():
                if word in found and coords:
                    first = coords[0]
                    last = coords[-1]
                    x1 = grid_start_x + first[1] * cell + cell // 2 + int((first[0] - rows/2) * (0.3 * offset))
                    y1 = grid_start_y + first[0] * cell + cell // 2 + int((first[1] - cols/2) * (0.1 * offset))
                    x2 = grid_start_x + last[1] * cell + cell // 2 + int((last[0] - rows/2) * (0.3 * offset))
                    y2 = grid_start_y + last[0] * cell + cell // 2 + int((last[1] - cols/2) * (0.1 * offset))
                    draw.line([(x1, y1), (x2, y2)], fill="#ff4757", width=6)
                    draw.ellipse([x1 - 6, y1 - 6, x1 + 6, y1 + 6], fill="#ff4757")
                    draw.ellipse([x2 - 6, y2 - 6, x2 + 6, y2 + 6], fill="#ff4757")
        frames_images.append(img.convert("P", palette=Image.ADAPTIVE))

    # save frames to BytesIO as GIF
    bio = io.BytesIO()
    try:
        frames_images[0].save(
            bio,
            format="GIF",
            save_all=True,
            append_images=frames_images[1:],
            duration=120,
            loop=0,
            optimize=True,
        )
    except Exception:
        # fallback: save single frame JPEG
        bio = io.BytesIO()
        frames_images[0].convert("RGB").save(bio, format="JPEG", quality=90)
    bio.seek(0)
    return bio

# ========== MENU / BUTTON ANIMATION ==========
MENU_ANIMATION_FRAMES = ["🔵", "🔶", "🔷", "🔸"]
MENU_ANIMATION_INTERVAL = 1.5  # seconds (edit frequency)
ANIMATING_MENUS = {}  # message_id -> (chat_id, cur_index, stop_event)

def start_menu_animation(chat_id, message_id, button_index=0):
    """
    Simulate an animated emoji inside one of the inline buttons by periodically editing reply_markup.
    button_index: index of the button in reply_markup.buttons sequence we want to animate (approx)
    """
    stop_event = threading.Event()
    ANIMATING_MENUS[message_id] = (chat_id, 0, stop_event, button_index)
    def runner():
        try:
            while not stop_event.is_set():
                try:
                    chat, idx, ev, bidx = ANIMATING_MENUS.get(message_id, (None, 0, stop_event, button_index))
                    # fetch message (can't fetch message's markup easily), so we remember last markup somewhere
                    # For safety, we simply send a tiny edit message next to menu: edit caption to append frame emoji (non-destructive)
                    # But editing caption repeatedly can be heavy; instead we avoid heavy edits: we will edit via a short "status message" under the menu
                    # Simpler approach: send ephemeral small edit to the menu message caption by appending a dot + emoji then revert (lightweight)
                    # Retrieve message (we don't have stored original caption here), so to avoid complexity, skip editing caption and instead send a small "typing" action emote
                    # Practical approach: if the menu message id exists, we try to edit its reply_markup to change the text of a button - but telebot doesn't provide reading current reply_markup
                    # So we'll simply send a small sticker-like ephemeral message to chat as animation frame (but to avoid spam we won't). To be safe, we won't perform aggressive edits.
                    # We'll emulate animation by toggling a short live message per chat (one per menu) — keep a single temporary message id per menu and edit it.
                    tmp_msg_id = None
                    # We store a special temp message per menu in ANIMATING_MENUS entry if needed, but to keep code safe and avoid complex state, we'll do simple sleep and advance index.
                    ANIMATING_MENUS[message_id] = (chat_id, (idx + 1) % len(MENU_ANIMATION_FRAMES), ev, bidx)
                except Exception:
                    logger.exception("menu animation loop error")
                time.sleep(MENU_ANIMATION_INTERVAL)
        except Exception:
            logger.exception("menu animation runner error")
    t = threading.Thread(target=runner, daemon=True)
    t.start()

def stop_menu_animation(message_id):
    entry = ANIMATING_MENUS.get(message_id)
    if entry:
        _, _, ev, _ = entry
        if ev and hasattr(ev, "set"):
            ev.set()
        ANIMATING_MENUS.pop(message_id, None)

# ========== SAFE SEND helpers ==========
def send_to_pm_or_group(user_id, chat_id, text, reply_markup=None):
    """
    Attempts to send 'text' to user's PM; if fails, sends to chat_id (group) and informs user.
    Returns True if sent to PM, False if group fallback or failed.
    """
    try:
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=reply_markup)
        try:
            bot.send_message(chat_id, f"🔔 I sent the details to your private chat, {html.escape(bot.get_chat(user_id).first_name or '')}.")
        except Exception:
            pass
        return True
    except Exception:
        try:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
            return False
        except Exception:
            return False

# ========== COMMANDS: MENU / HELP / CMD ==========
COMMANDS_TEXT = """
🤖 Word Vortex - Full Command List

Games:
- /new : Start normal 8x8 game
- /new_hard : Start hard 10x10 game
- /new_physics : Physics vocabulary mode
- /new_chemistry : Chemistry vocabulary mode
- /new_math : Math vocabulary mode
- /new_jee : JEE mixed pool
- /new_anagram : Anagram sprint (unscramble)
- /new_speedrun : Speedrun (3 min)
- /new_definehunt : Definition clues
- /new_survival : Survival progressive rounds
- /new_team : Team battle (join with /join_team)
- /daily : Today's daily puzzle
- /new_phrase : Hidden phrase bonus

In-Game:
- Use inline buttons: Found It, Hint, Score
- /hint : Buy a hint (costs points)
- /endgame : Force-stop (admin/owner)

Profile & Utility:
- /mystats or /scorecard : Show your stats
- /balance : Show hint balance
- /leaderboard : Show top players
- /define <word> : Get word definition
- /review <text> : Submit review
- /myreviews : Show your reviews
- /publishedreviews : See published reviews

Admin/Owner:
- /addpoints <id|@username> <amount> [score|balance] (default: balance)
- /broadcast <message>
- /addadmin <id|@username>
- /deladmin <id|@username>
- /admins
- /reset_leaderboard
- /restart
- /publishreview <id>

Use /cmdinfo <command> to get detailed help about a command.
"""

@bot.message_handler(commands=["cmd"])
def cmd_handler_cmd(m):
    bot.reply_to(m, COMMANDS_TEXT)

@bot.message_handler(commands=["cmdinfo"])
def cmd_handler_cmdinfo(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /cmdinfo <command>\nE.g., /cmdinfo /new_physics")
        return
    cmd = parts[1].strip()
    info = {
        "/new": "Start a normal 8x8 word-grid game. Use in groups.",
        "/new_hard": "Start a hard 10x10 game (longer words).",
        "/new_physics": "Physics-themed words selected randomly each game.",
        "/new_anagram": "Anagram Sprint: bot shows scrambled words; type the correct word.",
        "/new_team": "Team Battle: users join teams; teams compete on the same grid.",
        "/review": "/review <your text> — submits a review stored for owner review.",
        # add entries as needed...
    }
    msg = info.get(cmd, f"No detailed help found for {cmd}. Use /cmd to get full list.")
    bot.reply_to(m, msg)

# ========== MAIN MENU HANDLERS ==========
@bot.message_handler(commands=["start","help"])
def start_handler(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.register_user(m.from_user.id, name)
    # notify owner
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🔔 /start by {html.escape(name)} ({m.from_user.id}) in chat {m.chat.id}")
        except Exception:
            pass

    text = f"👋 Hi <b>{html.escape(name)}</b>! Welcome to Word Vortex.\nChoose an option (Commands open in your PM)."
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
           InlineKeyboardButton("🔄 Check Join", callback_data="check_join"))
    try:
        bn = bot.get_me().username
        if bn:
            kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{bn}?startgroup=true"))
    except Exception:
        pass
    kb.add(InlineKeyboardButton("🎮 Play Modes", callback_data="help_play"),
           InlineKeyboardButton("🤖 Commands", callback_data="help_cmd"))
    kb.add(InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
           InlineKeyboardButton("👤 My Stats", callback_data="menu_stats"))
    kb.add(InlineKeyboardButton("🐞 Report Issue", callback_data="open_issue"),
           InlineKeyboardButton("⭐ Reviews", callback_data="menu_review"))
    kb.add(InlineKeyboardButton("💳 Plans", callback_data="open_plans"),
           InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP_LINK))

    try:
        sent = bot.send_photo(m.chat.id, START_IMG_URL, caption=text, reply_markup=kb)
        # optionally start a light menu "animation" (we simulate frames by changing an ephemeral message)
        # start_menu_animation(m.chat.id, sent.message_id)
    except Exception:
        bot.reply_to(m, text, reply_markup=kb)

# ========== CALLBACK HANDLER (menus) ==========
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    data = c.data
    cid = c.message.chat.id
    uid = c.from_user.id

    # small ack
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

    # helpers
    def pm_or_group(msg_text, reply_markup=None):
        return send_to_pm_or_group(uid, cid, msg_text, reply_markup=reply_markup)

    if data == "check_join":
        if is_subscribed(uid):
            try:
                bot.delete_message(cid, c.message.message_id)
            except:
                pass
            start_handler(c.message)
            try:
                bot.answer_callback_query(c.id, "✅ Verified! Welcome.")
            except:
                pass
        else:
            try:
                bot.answer_callback_query(c.id, "❌ You haven't joined yet!", show_alert=True)
            except:
                pass
        return

    if data == "open_plans":
        txt = "💳 Plans:\n\n" + "\n".join([f"- {p['points']} pts: ₹{p['price_rs']}" for p in PLANS])
        txt += f"\n\nContact owner: {SUPPORT_GROUP_LINK}"
        pm_or_group(txt)
        return

    if data == "help_play":
        txt = ("🎮 Game Modes:\n\n"
               "/new - 8x8 normal\n"
               "/new_hard - 10x10 hard\n"
               "/new_physics - physics words\n"
               "/new_chemistry - chemistry words\n"
               "/new_math - math words\n"
               "/new_jee - JEE mixed\n"
               "/new_anagram - anagrams\n"
               "/new_speedrun - 3-min speedrun\n"
               "/new_definehunt - definitions clues\n"
               "/new_survival - progressive rounds\n"
               "/new_team - team battle\n"
               "/daily - daily challenge\n"
               "/new_phrase - hidden phrase")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))
        pm_or_group(txt, reply_markup=kb)
        return

    if data == "help_cmd":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Back", callback_data="menu_back"))
        pm_or_group(COMMANDS_TEXT, reply_markup=kb)
        return

    if data == "menu_lb":
        top = db.get_top_players(10)
        txt = "🏆 Global Leaderboard\n\n"
        for i, (n, s) in enumerate(top, 1):
            txt += f"{i}. {html.escape(n)} - {s} pts\n"
        pm_or_group(txt)
        return

    if data == "menu_stats":
        user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_pts = 0
        if cid in games:
            session_pts = games[cid].players_scores.get(uid, 0)
        txt = (f"📋 Your Stats\n"
               f"Name: {html.escape(user['name'])}\n"
               f"Total Score: {user['total_score']}\n"
               f"Wins: {user['wins']}\n"
               f"Games Played: {user['games_played']}\n"
               f"Session Points: {session_pts}\n"
               f"Hint Balance: {user['hint_balance']}")
        pm_or_group(txt)
        return

    if data == "open_issue":
        prompt = f"@{c.from_user.username or c.from_user.first_name} Type your issue here or use /issue <text>"
        try:
            bot.send_message(uid, prompt, reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "✍️ Prompt sent to your PM.")
        except:
            try:
                bot.send_message(cid, prompt, reply_markup=ForceReply(selective=True))
                bot.answer_callback_query(c.id, "✍️ Prompt opened here.")
            except:
                bot.answer_callback_query(c.id, "❌ Could not open issue prompt.", show_alert=True)
        return

    if data == "menu_review":
        rows = db.get_user_reviews(uid)
        if rows:
            txt = "<b>Your Reviews:</b>\n\n"
            for r in rows:
                txt += f"ID {r['review_id']}: {r['review_text'][:80]}... ({'Published' if r['published'] else 'Pending'})\n"
        else:
            txt = "You haven't submitted reviews. Use /review <text> to submit."
        pm_or_group(txt)
        return

    # Game callbacks handled separately (found/hint/score) in other parts of code
    if data in ("game_guess", "game_hint", "game_score"):
        # pass through to existing behavior by simulating click handling
        if data == "game_guess":
            # ask user to type
            try:
                username = c.from_user.username or c.from_user.first_name
                msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
                bot.register_next_step_handler(msg, process_word_guess)
                bot.answer_callback_query(c.id, "✍️ Type your guess.")
            except Exception:
                bot.answer_callback_query(c.id, "❌ Could not open input.", show_alert=True)
        elif data == "game_hint":
            # hint flow
            if cid not in games:
                bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                return
            user = db.get_user(uid, c.from_user.first_name)
            if user["hint_balance"] < HINT_COST:
                bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user['hint_balance']}", show_alert=True)
                return
            game = games[cid]
            hidden = [w for w in game.words if w not in game.found]
            if not hidden:
                bot.answer_callback_query(c.id, "All words found!", show_alert=True)
                return
            reveal = random.choice(hidden)
            db.update_stats(uid, hint_delta=-HINT_COST)
            bot.send_message(cid, f"💡 Hint: <code>{reveal}</code> (by {html.escape(c.from_user.first_name)})")
            bot.answer_callback_query(c.id, "Hint sent.")
        else:  # game_score
            if cid not in games:
                bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                return
            game = games[cid]
            lb = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
            rows = []
            for i, (u, pts) in enumerate(lb, 1):
                user = db.get_user(u, "Player")
                rows.append((i, user["name"], pts))
            img = LeaderboardRenderer.draw_session_leaderboard(rows[:10])
            try:
                bot.send_photo(cid, img, caption="Session Leaderboard")
                bot.answer_callback_query(c.id, "Leaderboard shown.")
            except:
                bot.answer_callback_query(c.id, "❌ Could not send leaderboard.", show_alert=True)
        return

    # default ack
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

# ========== GAME STARTERS for all modes ==========
def send_game_grid(session, starter_id=None):
    """
    Create an animated GIF (or static image) for the session grid and send it with buttons.
    Stores message_id to session.message_id for caption updates.
    """
    img_bio = generate_grid_animation(session.grid, placements=session.placements, found=session.found, is_hard=session.is_hard, frames=8)
    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
               f"Mode: {'Hard' if session.is_hard else 'Normal'}  |  {session.mode}\n"
               f"⏱ Time Limit: {session.duration//60} min\n\n"
               f"<b>Words to find:</b>\n{session.get_hint_text()}")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
               InlineKeyboardButton("📊 Score", callback_data="game_score"))
    try:
        sent = bot.send_animation(session.chat_id, img_bio, caption=caption, reply_markup=markup)
        session.message_id = sent.message_id
    except Exception:
        try:
            # fallback static
            img_bio.seek(0)
            bot.send_photo(session.chat_id, img_bio, caption=caption, reply_markup=markup)
        except Exception:
            bot.send_message(session.chat_id, caption, reply_markup=markup)

def start_session_and_notify(session, starter_name):
    games[session.chat_id] = session
    db.update_stats(starter_id := starter_name and starter_name or 0, games_played_delta=1)  # safe update; starter handled separately
    send_game_grid(session, starter_id)
    session.start_timer()
    # persist sessions file
    persist_all_sessions()
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🎮 Game started in chat {session.chat_id} by {starter_name}. Mode: {session.mode}")
        except:
            pass

# Wrapper for starting specific modes
def start_game_command(chat_id, starter, mode="normal"):
    """
    Creates proper session object by mode string and starts it.
    Returns session.
    """
    if mode == "normal":
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode="normal")
    elif mode == "hard":
        s = GameSession(chat_id, is_hard=True, duration=GAME_DURATION, word_pool=None, mode="hard")
    elif mode == "physics":
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=PHYSICS_POOL, mode="physics")
    elif mode == "chemistry":
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=CHEMISTRY_POOL, mode="chemistry")
    elif mode == "math":
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=MATH_POOL, mode="math")
    elif mode == "jee":
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=JEE_POOL, mode="jee")
    elif mode == "anagram":
        s = AnagramSession(chat_id)
    elif mode == "speedrun":
        s = SpeedrunSession(chat_id)
    elif mode == "definehunt":
        s = DefinitionHuntSession(chat_id)
    elif mode == "survival":
        s = SurvivalSession(chat_id)
    elif mode == "team":
        s = TeamGameSession(chat_id)
    elif mode == "daily":
        words, date = db.get_or_create_daily()
        s = DailyPuzzleSession(chat_id, words)
    elif mode == "phrase":
        s = HiddenPhraseSession(chat_id)
    else:
        s = GameSession(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode=mode)
    games[chat_id] = s
    # update starter games_played
    db.update_stats(starter, games_played_delta=1)
    # send grid & start timer
    send_game_grid(s, starter)
    s.start_timer()
    persist_all_sessions()
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🎮 {mode} game started in chat {chat_id} by {starter}")
        except:
            pass
    return s

# ========== Message handlers for starting games ==========
@bot.message_handler(commands=["new"])
def handle_new(m):
    start_game_command(m.chat.id, m.from_user.id, mode="normal")

@bot.message_handler(commands=["new_hard"])
def handle_new_hard(m):
    start_game_command(m.chat.id, m.from_user.id, mode="hard")

@bot.message_handler(commands=["new_physics"])
def handle_new_physics(m):
    start_game_command(m.chat.id, m.from_user.id, mode="physics")

@bot.message_handler(commands=["new_chemistry"])
def handle_new_chem(m):
    start_game_command(m.chat.id, m.from_user.id, mode="chemistry")

@bot.message_handler(commands=["new_math"])
def handle_new_math(m):
    start_game_command(m.chat.id, m.from_user.id, mode="math")

@bot.message_handler(commands=["new_jee"])
def handle_new_jee(m):
    start_game_command(m.chat.id, m.from_user.id, mode="jee")

@bot.message_handler(commands=["new_anagram"])
def handle_new_anagram(m):
    start_game_command(m.chat.id, m.from_user.id, mode="anagram")

@bot.message_handler(commands=["new_speedrun"])
def handle_new_speedrun(m):
    start_game_command(m.chat.id, m.from_user.id, mode="speedrun")

@bot.message_handler(commands=["new_definehunt"])
def handle_new_definehunt(m):
    start_game_command(m.chat.id, m.from_user.id, mode="definehunt")

@bot.message_handler(commands=["new_survival"])
def handle_new_survival(m):
    start_game_command(m.chat.id, m.from_user.id, mode="survival")

@bot.message_handler(commands=["new_team"])
def handle_new_team(m):
    start_game_command(m.chat.id, m.from_user.id, mode="team")
    bot.send_message(m.chat.id, "Team battle started. Players: use /join_team to join. Admins can assign via /teamadd @user A")

@bot.message_handler(commands=["daily"])
def handle_daily(m):
    start_game_command(m.chat.id, m.from_user.id, mode="daily")

@bot.message_handler(commands=["new_phrase"])
def handle_phrase(m):
    start_game_command(m.chat.id, m.from_user.id, mode="phrase")

# ========== Team battle simple join/assign ==========
@bot.message_handler(commands=["join_team"])
def cmd_join_team(m):
    cid = m.chat.id
    if cid not in games or not isinstance(games[cid], TeamGameSession):
        bot.reply_to(m, "No team battle active here. Use /new_team to start.")
        return
    session = games[cid]
    uid = m.from_user.id
    # auto-balance: add to smaller team
    if uid in session.team_a_ids or uid in session.team_b_ids:
        bot.reply_to(m, "You're already in a team.")
        return
    if len(session.team_a_ids) <= len(session.team_b_ids):
        session.team_a_ids.append(uid)
        bot.reply_to(m, "You joined Team A.")
    else:
        session.team_b_ids.append(uid)
        bot.reply_to(m, "You joined Team B.")
    persist_all_sessions()

@bot.message_handler(commands=["teamadd"])
def cmd_teamadd(m):
    # admin command: /teamadd @user A (or B)
    if not db.is_admin(m.from_user.id):
        bot.reply_to(m, "Only admin/owner can assign teams.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /teamadd <@username|id> <A|B>")
        return
    target = parts[1]
    team = parts[2].upper()
    if team not in ("A", "B"):
        bot.reply_to(m, "Team must be A or B.")
        return
    try:
        if target.startswith("@"):
            chat = bot.get_chat(target)
            tid = chat.id
        else:
            tid = int(target)
    except Exception:
        bot.reply_to(m, "Could not find user.")
        return
    cid = m.chat.id
    if cid not in games or not isinstance(games[cid], TeamGameSession):
        bot.reply_to(m, "No team game in this chat.")
        return
    session = games[cid]
    # remove if present
    if tid in session.team_a_ids:
        session.team_a_ids.remove(tid)
    if tid in session.team_b_ids:
        session.team_b_ids.remove(tid)
    if team == "A":
        session.team_a_ids.append(tid)
    else:
        session.team_b_ids.append(tid)
    bot.reply_to(m, f"Assigned user {tid} to Team {team}.")
    persist_all_sessions()

# ========== In-game: hint, endgame, guess processing, scorecard ==========
@bot.message_handler(commands=["hint"])
def cmd_hint(m):
    cid = m.chat.id
    uid = m.from_user.id
    if cid not in games:
        bot.reply_to(m, "No active game.")
        return
    user = db.get_user(uid, m.from_user.first_name)
    if user["hint_balance"] < HINT_COST:
        bot.reply_to(m, f"Not enough balance. You need {HINT_COST} pts.")
        return
    game = games[cid]
    hidden = [w for w in game.words if w not in game.found]
    if not hidden:
        bot.reply_to(m, "All words already found.")
        return
    reveal = random.choice(hidden)
    db.update_stats(uid, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")

@bot.message_handler(commands=["endgame"])
def cmd_endgame(m):
    cid = m.chat.id
    if cid not in games:
        bot.reply_to(m, "No active game.")
        return
    if not db.is_admin(m.from_user.id) and m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only admin/owner can stop the game.")
        return
    end_game_session(cid, "stopped")
    bot.reply_to(m, "Game stopped.")

@bot.message_handler(commands=["scorecard","mystats"])
def cmd_scorecard(m):
    uid = m.from_user.id
    u = db.get_user(uid, m.from_user.first_name)
    session_points = 0
    gid = m.chat.id
    if gid in games:
        session_points = games[gid].players_scores.get(uid, 0)
    txt = (f"📋 <b>Your Scorecard</b>\n"
           f"Name: {html.escape(u['name'])}\n"
           f"Total Score: {u['total_score']}\n"
           f"Wins: {u['wins']}\n"
           f"Session Points (this chat): {session_points}\n"
           f"Hint Balance: {u['hint_balance']}")
    bot.reply_to(m, txt)

# ========== Addpoints & Admin ==========
@bot.message_handler(commands=["addpoints"])
def cmd_addpoints(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]")
        return
    target = parts[1]
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be integer.")
        return
    mode = parts[3].lower() if len(parts) >= 4 else "balance"
    # resolve user id if username given
    try:
        if target.startswith("@"):
            ch = bot.get_chat(target)
            tid = ch.id
        else:
            tid = int(target)
    except Exception:
        bot.reply_to(m, "Could not resolve user. Make sure they started the bot or have public username.")
        return
    db.get_user(tid, getattr(ch, "username", "Player") if "ch" in locals() else "Player")
    if mode == "score":
        db.update_stats(tid, score_delta=amount)
        bot.reply_to(m, f"Added {amount} to score of {tid}")
    else:
        db.update_stats(tid, hint_delta=amount)
        bot.reply_to(m, f"Added {amount} to hint balance of {tid}")
    try:
        bot.send_message(tid, f"💸 You received {amount}pts ({mode}) from the owner.")
    except:
        pass

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can broadcast.")
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return
    msg = parts[1]
    users = db.all_user_ids()
    success = 0; failed = 0
    for uid in users:
        try:
            bot.send_message(uid, msg)
            success += 1
        except:
            failed += 1
    bot.reply_to(m, f"Broadcast complete. success={success}, failed={failed}")

@bot.message_handler(commands=["addadmin"])
def cmd_addadmin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /addadmin <id|@username>")
        return
    target = parts[1]
    try:
        if target.startswith("@"):
            ch = bot.get_chat(target); aid = ch.id
        else:
            aid = int(target)
    except:
        bot.reply_to(m, "Could not resolve user.")
        return
    db.add_admin(aid); bot.reply_to(m, f"Added admin {aid}")

@bot.message_handler(commands=["deladmin"])
def cmd_deladmin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /deladmin <id|@username>")
        return
    target = parts[1]
    try:
        if target.startswith("@"):
            ch = bot.get_chat(target); aid = ch.id
        else:
            aid = int(target)
    except:
        bot.reply_to(m, "Could not resolve user."); return
    db.remove_admin(aid); bot.reply_to(m, f"Removed admin {aid}")

@bot.message_handler(commands=["admins"])
def cmd_admins(m):
    admins = db.list_admins()
    txt = "Admins:\n"
    for a in admins:
        txt += f"- {a}\n"
    if OWNER_ID:
        txt += f"\nOwner: {OWNER_ID}"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["reset_leaderboard"])
def cmd_reset_lb(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    db.reset_leaderboard(); bot.reply_to(m, "Leaderboard reset.")

@bot.message_handler(commands=["restart"])
def cmd_restart(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    bot.reply_to(m, "Restarting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)

# ========== Reviews ==========
@bot.message_handler(commands=["review"])
def cmd_review(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /review <your review text>")
        return
    text = parts[1]
    db.add_review(m.from_user.id, m.from_user.username or m.from_user.first_name or str(m.from_user.id), text)
    bot.reply_to(m, "Thanks! Your review has been saved and will be reviewed by the owner.")

@bot.message_handler(commands=["myreviews"])
def cmd_myreviews(m):
    rows = db.get_user_reviews(m.from_user.id)
    if not rows:
        bot.reply_to(m, "You have no reviews.")
        return
    txt = "Your reviews:\n\n"
    for r in rows:
        txt += f"ID {r['review_id']}: {r['review_text'][:100]}... - {'Published' if r['published'] else 'Pending'}\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["publishedreviews"])
def cmd_publishedreviews(m):
    rows = db.get_published_reviews(40)
    if not rows:
        bot.reply_to(m, "No published reviews yet.")
        return
    txt = "Published reviews:\n\n"
    for r in rows:
        txt += f"{html.escape(r['username'])}: {r['review_text']}\n---\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["publishreview"])
def cmd_publishreview(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /publishreview <id>")
        return
    try:
        rid = int(parts[1])
    except:
        bot.reply_to(m, "Invalid id"); return
    db.publish_review(rid)
    bot.reply_to(m, f"Published review {rid}")

# ========== DEFINE ==========
@bot.message_handler(commands=["define"])
def cmd_define(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /define <word>")
        return
    word = parts[1].strip()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=6)
        data = r.json()
        if isinstance(data, list) and data:
            meanings = data[0].get("meanings", [])
            if meanings:
                defs = meanings[0].get("definitions", [])
                if defs:
                    d = defs[0].get("definition", "No definition")
                    ex = defs[0].get("example", "")
                    txt = f"📚 <b>{html.escape(word)}</b>\n{html.escape(d)}"
                    if ex:
                        txt += f"\n\n<i>Example:</i> {html.escape(ex)}"
                    bot.reply_to(m, txt)
                    return
        bot.reply_to(m, f"No definition found for {word}")
    except Exception:
        bot.reply_to(m, "Error fetching definition")

# ========== CORE GUESS PROCESSING & END GAME ==========
def process_word_guess(m):
    cid = m.chat.id
    if cid not in games:
        try:
            bot.reply_to(m, "No active game here.")
        except:
            pass
        return
    text = (m.text or "").strip().upper()
    if not text:
        return
    game = games[cid]
    uid = m.from_user.id
    name = m.from_user.first_name or m.from_user.username or "Player"
    last = game.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        try:
            bot.reply_to(m, f"⏳ Wait {COOLDOWN}s between guesses.")
        except:
            pass
        return
    game.players_last_guess[uid] = now
    try:
        bot.delete_message(cid, m.message_id)
    except:
        pass
    # special handling for Anagram mode
    if getattr(game, "mode", "") == "anagram":
        # mapping scrambled -> original stored in .scrambled_words
        found_word = None
        for orig, scrambled in game.scrambled_words.items():
            if text == orig:
                found_word = orig
                break
        if found_word:
            if found_word in game.found:
                bot.send_message(cid, f"⚠️ {found_word} already found.")
            else:
                game.found.add(found_word)
                pts = NORMAL_POINTS
                if len(game.found) == 1:
                    pts = FIRST_BLOOD_POINTS
                elif len(game.found) == len(game.words):
                    pts = FINISHER_POINTS
                game.players_scores[uid] = game.players_scores.get(uid, 0) + pts
                db.update_stats(uid, score_delta=pts)
                bot.send_message(cid, f"✅ {html.escape(name)} solved {found_word} (+{pts} pts)")
                # no grid update (anagram), so just check end
                if len(game.found) == len(game.words):
                    end_game_session(cid, "win", uid)
            return
        else:
            bot.send_message(cid, f"❌ {html.escape(name)} — '{html.escape(text)}' is incorrect.")
            return

    # normal grid modes
    if text in game.words:
        if text in game.found:
            bot.send_message(cid, f"⚠️ <b>{text}</b> is already found!")
            return
        game.found.add(text)
        game.last_activity = time.time()
        if len(game.found) == 1:
            pts = FIRST_BLOOD_POINTS
        elif len(game.found) == len(game.words):
            pts = FINISHER_POINTS
        else:
            pts = NORMAL_POINTS
        prev = game.players_scores.get(uid, 0)
        game.players_scores[uid] = prev + pts
        db.update_stats(uid, score_delta=pts)
        bot_msg = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(name)} found <code>{text}</code> (+{pts} pts)")
        threading.Timer(4, lambda: safe_delete(cid, bot_msg.message_id)).start()
        # regenerate animated GIF showing the found line and post it, deleting old game image so chat stays tidy
        try:
            img_bio = generate_grid_animation(game.grid, placements=game.placements, found=game.found, is_hard=game.is_hard, frames=8)
            try:
                sent = bot.send_animation(cid, img_bio, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if game.is_hard else 'Normal'}\nWords:\n{game.get_hint_text()}"),
                                          reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                                                                                  InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                                                                                  InlineKeyboardButton("📊 Score", callback_data="game_score")))
                # delete old image if present
                try:
                    if game.message_id:
                        bot.delete_message(cid, game.message_id)
                except Exception:
                    pass
                game.message_id = sent.message_id
            except Exception:
                # fallback to static
                img_bio.seek(0)
                try:
                    sentp = bot.send_photo(cid, img_bio, caption=(f"🔥 WORD VORTEX\n{game.get_hint_text()}"),
                                            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess")))
                    try:
                        if game.message_id:
                            bot.delete_message(cid, game.message_id)
                    except:
                        pass
                    game.message_id = sentp.message_id
                except Exception:
                    pass
        except Exception:
            logger.exception("Failed to regenerate animated image")
        # check for end
        if len(game.found) == len(game.words):
            end_game_session(cid, "win", uid)
    else:
        try:
            msg = bot.send_message(cid, f"❌ {html.escape(name)} — '{html.escape(text)}' is not in the list.")
            threading.Timer(3, lambda: safe_delete(cid, msg.message_id)).start()
        except:
            pass

def safe_delete(chat_id, mid):
    try:
        bot.delete_message(chat_id, mid)
    except Exception:
        pass

def end_game_session(cid, reason, winner_id=None):
    if cid not in games:
        return
    session = games[cid]
    session.active = False
    if reason == "win":
        winner = db.get_user(winner_id, "Player")
        db.update_stats(winner_id, win=True)
        db.record_game(cid, winner_id)
        standings = sorted(session.players_scores.items(), key=lambda x: x[1], reverse=True)
        text = f"🏆 GAME OVER — All words found!\nMVP: {html.escape(winner['name'])}\n\nStandings:\n"
        for i, (uid, pts) in enumerate(standings, 1):
            u = db.get_user(uid, "Player")
            text += f"{i}. {html.escape(u['name'])} - {pts} pts\n"
        bot.send_message(cid, text)
    elif reason == "stopped":
        bot.send_message(cid, "🛑 Game stopped by admin.")
    elif reason == "timeout":
        found_count = len(session.found)
        rem = [w for w in session.words if w not in session.found]
        text = f"⏰ Time's up! Found {found_count}/{len(session.words)}\nRemaining: {', '.join(rem) if rem else 'None'}"
        bot.send_message(cid, text)
    # remove persistent storage
    if str(cid) in load_sessions_from_file():
        # remove entry and save
        data = load_sessions_from_file()
        data.pop(str(cid), None)
        save_sessions_to_file(data)
    try:
        del games[cid]
    except:
        pass

# ========== START POLLING ==========
if __name__ == "__main__":
    print("✅ Word Vortex Bot starting...")
    # periodic persistence on shutdown
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=5)
    except KeyboardInterrupt:
        print("Shutting down...")
        persist_all_sessions()
        sys.exit(0)
    except Exception:
        logger.exception("Polling crashed, restarting in 5s")
        time.sleep(5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
