#!/usr/bin/env python3
"""
WORD VORTEX - COMPLETE BOT
Version: 1.0
- Full consolidated implementation (games, animated GIF grid, menus, commands, reviews, persistence).
- Requirements: Python 3.8+, packages: pyTelegramBotAPI, pillow, requests
    pip install pyTelegramBotAPI pillow requests
- Set environment variables:
    TELEGRAM_TOKEN    - bot token
    OWNER_ID          - your Telegram user id (notifications)
- Run: python bot.py

Notes:
- The grid animation is generated as a GIF (Pillow). If the host blocks large files or GIF fails,
  the bot falls back to static images.
- Sessions are persisted to sessions_store.json; on restart sessions are restored (best-effort).
- If anything fails, check logs printed to stdout / container logs and paste tracebacks here.
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
from datetime import datetime
from typing import Dict, Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ----------------------------
# CONFIG
# ----------------------------
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
    print("ERROR: TELEGRAM_TOKEN env var is required.")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("wordvortex")
logger.setLevel(logging.DEBUG)

# Gameplay constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600  # seconds
COOLDOWN = 2
HINT_COST = 50

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# Domain pools (sample; words selected randomly)
PHYSICS_POOL = ["FORCE","ENERGY","MOMENTUM","VELOCITY","ACCEL","VECTOR","SCALAR","WAVE","PHOTON","GRAVITY",
                "TORQUE","WORK","POWER","FREQUENCY","OSCILLATION","REFRACTION","FIELD","MOTION","INERTIA","PRESSURE"]
CHEMISTRY_POOL = ["ATOM","MOLECULE","REACTION","BOND","ION","CATION","ANION","ACID","BASE","SALT",
                  "OXIDE","POLYMER","CATALYST","ELECTRON","COMPOUND","ELEMENT","MOLAR","PH","SPECTRUM","HALOGEN"]
MATH_POOL = ["INTEGRAL","DERIVATIVE","MATRIX","VECTOR","ALGEBRA","GEOMETRY","CALCULUS","TRIG","EQUATION","FUNCTION",
             "POLYNOMIAL","RATIO","PROBABILITY","STATISTICS","LOG","LIMIT","SEQUENCE","SERIES","AXIOM","THEOREM"]
JEE_POOL = PHYSICS_POOL + CHEMISTRY_POOL + MATH_POOL

# Persistence files
DB_FILE = "wordvortex.db"
SESSIONS_FILE = "sessions_store.json"

# ----------------------------
# DATABASE
# ----------------------------
class DB:
    def __init__(self, path=DB_FILE):
        self.path = path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            join_date TEXT,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100,
            is_banned INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            timestamp TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            review_text TEXT,
            timestamp TEXT,
            published INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_challenges (
            challenge_date TEXT PRIMARY KEY,
            words_json TEXT,
            leaderboard_json TEXT DEFAULT '{}'
        )''')
        conn.commit()
        conn.close()

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

    # daily
    def get_or_create_daily(self):
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT words_json FROM daily_challenges WHERE challenge_date=?", (today,))
        r = c.fetchone()
        if r:
            words = json.loads(r["words_json"])
            conn.close()
            return words, today
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
        r = c.fetchone()
        lb = json.loads(r["leaderboard_json"]) if r and r["leaderboard_json"] else {}
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
        r = c.fetchone()
        conn.close()
        if not r or not r["leaderboard_json"]:
            return []
        lb = json.loads(r["leaderboard_json"])
        sorted_lb = sorted(lb.items(), key=lambda x: x[1]["points"], reverse=True)
        return [(v["username"], v["points"]) for k, v in sorted_lb[:10]]

db = DB()

# ----------------------------
# WORD LIST
# ----------------------------
ALL_WORDS = []
def fetch_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        r = requests.get(url, timeout=8)
        lines = r.text.splitlines()
        ALL_WORDS = [w.upper() for w in lines if 4 <= len(w.strip()) <= 9 and w.isalpha() and w.upper() not in BAD_WORDS]
        logger.info("Loaded external word list, count=%d", len(ALL_WORDS))
    except Exception:
        logger.exception("Failed to fetch words; using fallback list")
        ALL_WORDS = ['PYTHON','JAVA','SCRIPT','ROBOT','SPACE','GALAXY','NEBULA','FUTURE','ENGINE','LOGIC']
fetch_words()

# ----------------------------
# SESSIONS (in-memory, persisted)
# ----------------------------
games: Dict[int, Any] = {}          # chat_id -> session object
team_games: Dict[int, Any] = {}     # chat_id -> team session (if used)

SESSIONS_LOCK = threading.Lock()

def save_sessions():
    try:
        with SESSIONS_LOCK:
            out = {}
            for cid, s in games.items():
                try:
                    out[str(cid)] = {
                        "mode": s.mode,
                        "is_hard": getattr(s, "is_hard", False),
                        "words": getattr(s, "words", []),
                        "found": list(getattr(s, "found", [])),
                        "placements": getattr(s, "placements", {}),
                        "start_time": getattr(s, "start_time", time.time()),
                        "duration": getattr(s, "duration", GAME_DURATION),
                        "players_scores": getattr(s, "players_scores", {}),
                    }
                except Exception:
                    logger.exception("serialize session failed for chat %s", cid)
            for cid, s in team_games.items():
                try:
                    out[str(cid)] = {
                        "mode": s.mode,
                        "is_hard": getattr(s, "is_hard", False),
                        "words": getattr(s, "words", []),
                        "found": list(getattr(s, "found", [])),
                        "placements": getattr(s, "placements", {}),
                        "start_time": getattr(s, "start_time", time.time()),
                        "duration": getattr(s, "duration", GAME_DURATION),
                        "players_scores": getattr(s, "players_scores", {}),
                        "team_a_ids": getattr(s, "team_a_ids", []),
                        "team_b_ids": getattr(s, "team_b_ids", []),
                    }
                except Exception:
                    logger.exception("serialize team session failed for chat %s", cid)
            with open(SESSIONS_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(out, f)
            os.replace(SESSIONS_FILE + ".tmp", SESSIONS_FILE)
            logger.debug("Saved %d sessions", len(out))
    except Exception:
        logger.exception("Failed to save sessions")

def load_sessions():
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("Loaded sessions from disk: %d", len(data))
            return data
    except Exception:
        logger.exception("Failed to load sessions file")
        return {}

def restore_sessions():
    data = load_sessions()
    restored = 0
    for cid_str, info in data.items():
        try:
            cid = int(cid_str)
            mode = info.get("mode", "normal")
            is_hard = info.get("is_hard", False)
            # We'll restore as minimal GameSession-like objects to allow countdown and posting; a full restoration
            # of running message_ids is not safe (message ids invalid after restart), so we re-send a new message on restore.
            s = SimpleRestoredSession(cid, mode, is_hard, info)
            games[cid] = s
            restored += 1
        except Exception:
            logger.exception("Failed to restore session %s", cid_str)
    logger.info("Restored %d sessions", restored)
    return restored

# SimpleRestoredSession provides minimal interface used by code (generate_grid_animation expects attributes)
class SimpleRestoredSession:
    def __init__(self, chat_id, mode, is_hard, info):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.words = info.get("words", [])
        self.found = set(info.get("found", []))
        self.placements = info.get("placements", {})
        self.start_time = info.get("start_time", time.time())
        self.duration = info.get("duration", GAME_DURATION)
        self.players_scores = info.get("players_scores", {})
        self.players_last_guess = {}
        self.grid = self._reconstruct_grid()
        self.message_id = None
        self.active = True
        self.timer_thread = None

    def _reconstruct_grid(self):
        # Build a simple grid containing words at approximate placements; if placements empty,
        # fill random grid
        size = 10 if self.is_hard else 8
        grid = [[' ' for _ in range(size)] for _ in range(size)]
        for w, coords in (self.placements or {}).items():
            for i, (r, c) in enumerate(coords):
                if 0 <= r < size and 0 <= c < size and i < len(w):
                    grid[r][c] = w[i]
        # fill blanks
        for r in range(size):
            for c in range(size):
                if grid[r][c] == ' ':
                    grid[r][c] = random.choice(string.ascii_uppercase)
        return grid

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + "-"*(len(w)-1)
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

# start with restore
restore_sessions()

# persist thread (safe start after games defined)
def periodic_persist_loop():
    while True:
        try:
            save_sessions()
        except Exception:
            logger.exception("periodic_persist error")
        time.sleep(25)

_persist_thread = threading.Thread(target=periodic_persist_loop, daemon=True)
_persist_thread.start()

# ----------------------------
# IMAGE ANIMATION (GIF) GENERATOR
# ----------------------------
def generate_grid_animation(grid, placements=None, found=None, is_hard=False, frames=6, max_size=720):
    """Generate an animated GIF (BytesIO) that simulates a subtle 3D/light sweep and draws found lines."""
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    # Basic sizing
    cell = 60 if (rows <= 8 and cols <= 8) else 48
    header_h = 90
    padding = 20
    width = cols * cell + padding*2
    height = header_h + rows * cell + padding*2 + 40
    # scale down if too large
    scale = 1.0
    max_dim = max(width, height)
    if max_dim > max_size:
        scale = max_size / max_dim
        cell = max(20, int(cell * scale))
        width = cols * cell + padding*2
        height = header_h + rows * cell + padding*2 + 40

    # fonts
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        letter_font = ImageFont.truetype(font_path, int(cell * 0.6))
        header_font = ImageFont.truetype(font_path, 28)
        small_font = ImageFont.truetype(font_path, 14)
    except Exception:
        letter_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    frames_images = []

    for f in range(frames):
        img = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(img)
        # header
        draw.rectangle([0,0,width,header_h], fill="#eef6fb")
        title = "WORD VORTEX"
        tw, th = draw.textsize(title, font=header_font)
        draw.text(((width-tw)/2, 18), title, fill="#0b66c3", font=header_font)
        # grid origin
        gx = padding
        gy = header_h + padding
        # light sweep center moving horizontally
        cx = int(width * (0.15 + 0.7 * (f / max(1, frames - 1))))
        cy = gy + int((rows*cell) * 0.25)
        # draw cells with slight skew effect
        for r in range(rows):
            for c in range(cols):
                x = gx + c*cell
                y = gy + r*cell
                draw.rectangle([x, y, x+cell, y+cell], outline="#2f80d7", width=2)
                ch = grid[r][c]
                bw, bh = draw.textsize(ch, font=letter_font)
                draw.text((x + (cell - bw)/2, y + (cell - bh)/2 - 2), ch, fill="#1b2b3a", font=letter_font)
        # simulate light sweep: radial white gradient with low alpha
        light = Image.new("L", (width, height), 0)
        ld = ImageDraw.Draw(light)
        maxr = max(width, height)
        for rr in range(0, maxr, 20):
            alpha = max(0, 150 - int(150 * rr / maxr))
            ld.ellipse([cx-rr, cy-rr, cx+rr, cy+rr], fill=alpha)
        light = light.filter(ImageFilter.GaussianBlur(radius=20))
        overlay = Image.new("RGBA", (width, height), (255,255,255,0))
        overlay.putalpha(light)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        # draw found word lines
        if placements and found:
            for word, coords in placements.items():
                if word in found and coords:
                    first = coords[0]; last = coords[-1]
                    x1 = gx + first[1]*cell + cell//2
                    y1 = gy + first[0]*cell + cell//2
                    x2 = gx + last[1]*cell + cell//2
                    y2 = gy + last[0]*cell + cell//2
                    draw.line([(x1,y1),(x2,y2)], fill="#ff4757", width=6)
                    r_rad = max(4, cell//10)
                    draw.ellipse([x1-r_rad, y1-r_rad, x1+r_rad, y1+r_rad], fill="#ff4757")
                    draw.ellipse([x2-r_rad, y2-r_rad, x2+r_rad, y2+r_rad], fill="#ff4757")
        frames_images.append(img.convert("P", palette=Image.ADAPTIVE))

    bio = io.BytesIO()
    try:
        frames_images[0].save(bio, format="GIF", save_all=True, append_images=frames_images[1:], duration=120, loop=0, optimize=True)
    except Exception:
        # fallback static JPEG
        bio = io.BytesIO()
        frames_images[0].convert("RGB").save(bio, format="JPEG", quality=90)
    bio.seek(0)
    return bio

# ----------------------------
# GRID RENDER & SESSION CLASSES
# ----------------------------
class GameSession:
    def __init__(self, chat_id:int, is_hard:bool=False, duration:int=GAME_DURATION, word_pool=None, mode:str="normal"):
        self.chat_id = chat_id
        self.is_hard = is_hard
        self.mode = mode
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.duration = duration
        self.start_time = time.time()
        self.last_activity = time.time()
        self.words = []
        self.found = set()
        self.grid = []
        self.placements = {}
        self.players_scores = {}
        self.players_last_guess = {}
        self.message_id = None
        self.active = True
        self.word_pool = word_pool
        self.timer_thread = None
        self.generate()

    def generate(self):
        pool = []
        if self.word_pool:
            pool = [w.upper() for w in self.word_pool if 4 <= len(w) <= 12]
        else:
            pool = ALL_WORDS[:] if len(ALL_WORDS) >= self.word_count else (ALL_WORDS * 2)
        try:
            self.words = random.sample(pool, self.word_count)
        except Exception:
            self.words = [random.choice(pool) for _ in range(self.word_count)]
        # build empty grid and place words
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        self.placements = {}
        for word in sorted_words:
            placed = False
            attempts = 0
            while not placed and attempts < 400:
                attempts += 1
                r = random.randint(0, self.size-1)
                c = random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r,c,dr,dc,word):
                    coords = []
                    for i, ch in enumerate(word):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr, cc))
                    self.placements[word] = coords
                    placed = True
            if not placed:
                # fallback scanning placement
                for rr in range(self.size):
                    for cc in range(self.size):
                        for dr, dc in dirs:
                            if self._can_place(rr, cc, dr, dc, word):
                                coords = []
                                for i, ch in enumerate(word):
                                    rrr, ccc = rr + i*dr, cc + i*dc
                                    self.grid[rrr][ccc] = ch
                                    coords.append((rrr, ccc))
                                self.placements[word] = coords
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
                        break
        # fill blanks
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == ' ':
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def _can_place(self, r,c,dr,dc,word):
        for i in range(len(word)):
            rr, cc = r + i*dr, c + i*dc
            if not (0 <= rr < self.size and 0 <= cc < self.size):
                return False
            if self.grid[rr][cc] != ' ' and self.grid[rr][cc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + "-"*(len(w)-1)
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

    def start_timer(self):
        if self.timer_thread and self.timer_thread.is_alive():
            return
        self.timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self.timer_thread.start()

    def _timer_loop(self):
        try:
            while self.active:
                elapsed = time.time() - self.start_time
                remaining = int(self.duration - elapsed)
                if remaining <= 0:
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! Game ended.")
                    except Exception:
                        pass
                    end_game_session(self.chat_id, "timeout")
                    break
                # update caption every 10s
                if self.message_id:
                    mins = remaining // 60
                    secs = remaining % 60
                    caption = (f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if self.is_hard else 'Normal'} | {self.mode}\n"
                               f"⏱ Time Left: {mins}:{secs:02d}\n\n{self.get_hint_text()}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
                    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                               InlineKeyboardButton("📊 Score", callback_data="game_score"))
                    try:
                        safe_edit_caption(self.chat_id, self.message_id, caption, reply_markup=markup)
                    except Exception:
                        logger.exception("Failed to safe_edit_caption in timer loop")
                time.sleep(10)
        except Exception:
            logger.exception("Timer loop exception")
        finally:
            self.active = False

# Minimal other session subclasses (Anagram/Speedrun/Definition/Survival/Team/Phrase/Daily)
# For brevity these are thin wrappers that set mode and adapt generate; main guess logic handles 'mode' differences.
class AnagramSession:
    def __init__(self, chat_id, duration=300):
        self.chat_id = chat_id
        self.mode = "anagram"
        self.is_hard = False
        self.duration = duration
        self.start_time = time.time()
        self.words = []
        self.scrambled = {}
        self.found = set()
        self.players_scores = {}
        self.players_last_guess = {}
        self.message_id = None
        self.active = True
        self.timer_thread = None
        self.generate()

    def generate(self):
        pool = ALL_WORDS[:] if len(ALL_WORDS) >= 6 else (ALL_WORDS * 2)
        self.words = random.sample(pool, min(6, len(pool)))
        self.scrambled = {}
        for w in self.words:
            letters = list(w)
            random.shuffle(letters)
            self.scrambled[w] = ''.join(letters)

    def get_hint_text(self):
        lines = []
        for w in self.words:
            if w in self.found:
                lines.append(f"✅ {w}")
            else:
                lines.append(f"🔤 {self.scrambled[w]}")
        return "\n".join(lines)

class SpeedrunSession(GameSession):
    def __init__(self, chat_id):
        super().__init__(chat_id, is_hard=False, duration=180, word_pool=None, mode="speedrun")
        self.word_count = 12

class DefinitionHuntSession(GameSession):
    def __init__(self, chat_id):
        super().__init__(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode="definehunt")
        self.definitions = {}
        self._fetch_definitions()

    def _fetch_definitions(self):
        for w in self.words:
            try:
                r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w.lower()}", timeout=4)
                d = r.json()
                if isinstance(d, list) and d:
                    meanings = d[0].get("meanings", [])
                    defs = meanings[0].get("definitions", []) if meanings else []
                    self.definitions[w] = defs[0].get("definition", "...") if defs else "..."
                else:
                    self.definitions[w] = "..."
            except Exception:
                self.definitions[w] = "..."
    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ {w}")
            else:
                hints.append(f"📖 {self.definitions.get(w, '...')[:40]}...")
        return "\n".join(hints)

class SurvivalSession(GameSession):
    def __init__(self, chat_id):
        super().__init__(chat_id, is_hard=False, duration=300, word_pool=None, mode="survival")
        self.round = 1

class TeamGameSession(GameSession):
    def __init__(self, chat_id):
        super().__init__(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode="team")
        self.team_a_ids = []
        self.team_b_ids = []
        self.team_a_score = 0
        self.team_b_score = 0

class HiddenPhraseSession(GameSession):
    def __init__(self, chat_id):
        super().__init__(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode="phrase")
        # override words with a phrase set
        phrases = [["WORD","SEARCH","PUZZLE"], ["BRAIN","GAME","FUN"], ["HARD","WORK","WIN"]]
        phrase = random.choice(phrases)
        self.words = phrase
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        # place phrase words
        self.placements = {}
        dirs = [(0,1),(1,0),(1,1),(0,-1),( -1,0),(-1,-1),(1,-1),(-1,1)]
        for w in self.words:
            placed = False
            for attempt in range(300):
                r = random.randint(0, self.size-1)
                c = random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r,c,dr,dc,w):
                    coords = []
                    for i,ch in enumerate(w):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr,cc))
                    self.placements[w] = coords
                    placed = True
                    break
            if not placed:
                # ignore placement failure; grid fill will handle
                pass
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == ' ':
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

class DailyPuzzleSession(GameSession):
    def __init__(self, chat_id, words):
        super().__init__(chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None, mode="daily")
        self.words = words
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        # place words similarly to GameSession
        dirs = [(0,1),(1,0),(1,1),(-1,0),(0,-1),(-1,-1),(1,-1),(-1,1)]
        self.placements = {}
        for w in self.words:
            placed = False
            for _ in range(300):
                r = random.randint(0, self.size-1); c = random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r,c,dr,dc,w):
                    coords = []
                    for i,ch in enumerate(w):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr,cc))
                    self.placements[w] = coords
                    placed = True
                    break
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == ' ':
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

# ----------------------------
# HELPERS: safe editing and sending
# ----------------------------
def safe_edit_caption(chat_id, message_id, caption, reply_markup=None):
    try:
        bot.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        bot.edit_message_text(caption, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except Exception:
        pass
    return False

def send_animation_or_photo(chat_id, bio, caption, reply_markup=None):
    """Try send_animation, fallback to send_photo, fallback to send_message"""
    try:
        sent = bot.send_animation(chat_id, bio, caption=caption, reply_markup=reply_markup)
        return sent
    except Exception:
        logger.exception("send_animation failed, trying photo fallback")
    try:
        bio.seek(0)
        sentp = bot.send_photo(chat_id, bio, caption=caption, reply_markup=reply_markup)
        return sentp
    except Exception:
        logger.exception("send_photo fallback failed, sending text")
    try:
        bot.send_message(chat_id, caption, reply_markup=reply_markup)
    except Exception:
        logger.exception("send_message fallback failed")

# ----------------------------
# MENU & CALLBACKS
# ----------------------------
COMMANDS_TEXT = """🤖 Word Vortex - Commands (use /cmd or Commands button)
Games:
 /new, /new_hard, /new_physics, /new_chemistry, /new_math, /new_jee
 /new_anagram, /new_speedrun, /new_definehunt, /new_survival, /new_team, /daily, /new_phrase

In-game:
 Found It (button) -> ForceReply to type the word
 /hint -> buy hint (-50)
 /endgame -> admin/owner only

Profile:
 /mystats, /scorecard, /balance, /leaderboard

Reviews:
 /review <text>, /myreviews, /publishedreviews

Owner/Admin:
 /addpoints <id|@username> <amount> [score|balance]
 /broadcast <message>, /addadmin, /deladmin, /admins
 /reset_leaderboard, /publishreview <id>, /restart
 /cmdinfo <command> - detailed help
"""

@bot.message_handler(commands=["cmd"])
def cmd_cmd(m):
    bot.reply_to(m, COMMANDS_TEXT)

@bot.message_handler(commands=["cmdinfo"])
def cmd_cmdinfo(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /cmdinfo <command>")
        return
    key = parts[1].strip().lower()
    info_map = {
        "/new": "Start an 8x8 standard game. Use in groups.",
        "/new_hard": "Start a 10x10 hard game.",
        "/new_physics": "Physics-specific words (random selection).",
        "/new_anagram": "Anagram Sprint: solve scrambled words quickly.",
        "/new_team": "Start team battle; players use /join_team to join.",
        "/review": "Submit review: /review <text>",
    }
    bot.reply_to(m, info_map.get(key, f"No detailed help for {key}. Use /cmd for full list."))

@bot.message_handler(commands=["start","help"])
def start_menu(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.get_user(m.from_user.id, name)
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🔔 /start used by {name} ({m.from_user.id}) chat {m.chat.id}")
        except Exception:
            pass
    txt = f"👋 Hello <b>{html.escape(name)}</b>!\nWelcome to Word Vortex. Click a button."
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
    kb.add(InlineKeyboardButton("💳 Plans", callback_data="open_plans"))
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=kb)
    except Exception:
        bot.reply_to(m, txt, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    logger.debug("Callback from %s in chat %s data=%s", c.from_user.id, c.message.chat.id, c.data)
    data = c.data
    cid = c.message.chat.id
    uid = c.from_user.id

    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

    def pm_or_group(msg, markup=None):
        try:
            bot.send_message(uid, msg, parse_mode="HTML", reply_markup=markup)
            try:
                bot.send_message(cid, f"🔔 I sent details to your private chat.")
            except:
                pass
            return True
        except Exception:
            try:
                bot.send_message(cid, msg, parse_mode="HTML", reply_markup=markup)
                return False
            except Exception:
                try:
                    bot.answer_callback_query(c.id, "❌ Could not open. Start a private chat with me.", show_alert=True)
                except:
                    pass
                return False

    if data == "check_join":
        if is_subscribed(uid):
            try:
                bot.delete_message(cid, c.message.message_id)
            except:
                pass
            start_menu(c.message)
            try:
                bot.answer_callback_query(c.id, "✅ Verified!")
            except:
                pass
        else:
            try:
                bot.answer_callback_query(c.id, "❌ You haven't joined yet!", show_alert=True)
            except:
                pass
        return

    if data == "help_play":
        txt = ("<b>Game Modes</b>\n" +
               "/new - Normal\n/new_hard - Hard\n/new_physics - Physics\n/new_chemistry - Chemistry\n/new_math - Math\n/new_jee - JEE\n/new_anagram - Anagram\n/new_speedrun - Speedrun\n/new_definehunt - Definition Hunt\n/new_survival - Survival\n/new_team - Team Battle\n/daily - Daily Puzzle\n/new_phrase - Hidden Phrase\n")
        pm_or_group(txt)
        return

    if data == "help_cmd":
        pm_or_group(COMMANDS_TEXT)
        return

    if data == "menu_lb":
        top = db.get_top_players()
        txt = "🏆 <b>Leaderboard</b>\n\n"
        for i, (n, s) in enumerate(top, 1):
            txt += f"{i}. {html.escape(n)} - {s} pts\n"
        pm_or_group(txt)
        return

    if data == "menu_stats":
        user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_pts = 0
        if cid in games:
            session_pts = games[cid].players_scores.get(uid, 0)
        txt = (f"📋 <b>Your Stats</b>\nName: {html.escape(user['name'])}\nTotal Score: {user['total_score']}\nWins: {user['wins']}\nGames: {user['games_played']}\nSession Points: {session_pts}\nHint Balance: {user['hint_balance']}")
        pm_or_group(txt)
        return

    if data == "open_plans":
        txt = "💳 Plans:\n" + "\n".join([f"- {p['points']} pts : ₹{p['price_rs']}" for p in PLANS])
        pm_or_group(txt)
        return

    if data == "open_issue":
        try:
            bot.send_message(uid, f"@{c.from_user.username or c.from_user.first_name} Please type your issue below or use /issue <text>:", reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "✍️ Prompt sent to your PM.")
        except:
            try:
                bot.send_message(cid, "Please type your issue here:", reply_markup=ForceReply(selective=True))
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
            txt = "You have no reviews. Use /review <text> to submit."
        pm_or_group(txt)
        return

    # in-game callbacks
    if data in ("game_guess", "game_hint", "game_score"):
        # forward to the same logic as buttons (handled in code that sends inline buttons)
        if data == "game_guess":
            try:
                username = c.from_user.username or c.from_user.first_name
                reply = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
                bot.register_next_step_handler(reply, process_word_guess)
                bot.answer_callback_query(c.id, "✍️ Type your guess.")
            except Exception:
                bot.answer_callback_query(c.id, "❌ Could not open input", show_alert=True)
            return
        if data == "game_hint":
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
            bot.answer_callback_query(c.id, "Hint revealed.")
            return
        if data == "game_score":
            if cid not in games:
                bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                return
            game = games[cid]
            if not game.players_scores:
                bot.answer_callback_query(c.id, "No scores yet.", show_alert=True)
                return
            lb = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
            rows = []
            for i, (uid2, pts) in enumerate(lb, 1):
                u = db.get_user(uid2, "Player")
                rows.append((i, u["name"], pts))
            # send as image
            img = draw_leaderboard_image(rows[:10])
            try:
                bot.send_photo(cid, img, caption="Session Leaderboard")
                bot.answer_callback_query(c.id, "Leaderboard shown.")
            except:
                bot.answer_callback_query(c.id, "❌ Couldn't show leaderboard.", show_alert=True)
            return

    # default
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

# ----------------------------
# LEADERBOARD IMAGE
# ----------------------------
def draw_leaderboard_image(rows):
    width = 700
    height = max(120, 60 + 40 * len(rows))
    img = Image.new("RGB", (width, height), "#081028")
    d = ImageDraw.Draw(img)
    try:
        fpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        title_font = ImageFont.truetype(fpath, 26)
        row_font = ImageFont.truetype(fpath, 20)
    except:
        title_font = ImageFont.load_default()
        row_font = ImageFont.load_default()
    d.text((20, 10), "Session Leaderboard", fill="#ffd700", font=title_font)
    y = 50
    for idx, name, pts in rows:
        d.text((20, y), f"{idx}. {name}", fill="#fff", font=row_font)
        d.text((520, y), f"{pts} pts", fill="#7be495", font=row_font)
        y += 40
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio

# ----------------------------
# START / SEND GAME GRID (animation)
# ----------------------------
def send_grid_for_session(session, starter_id=None):
    try:
        img_bio = generate_grid_animation(session.grid, placements=session.placements, found=session.found, is_hard=session.is_hard, frames=8)
        caption = (f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if session.is_hard else 'Normal'} | {session.mode}\n"
                   f"⏱ Time Limit: {session.duration//60} min\n\n{session.get_hint_text()}")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                   InlineKeyboardButton("📊 Score", callback_data="game_score"))
        sent = send_animation_or_photo(session.chat_id, img_bio, caption, reply_markup=markup)
        # if send_animation_or_photo returned a message-like object set message_id where available
        try:
            if sent and hasattr(sent, "message_id"):
                session.message_id = sent.message_id
            else:
                session.message_id = None
        except Exception:
            session.message_id = None
    except Exception:
        logger.exception("Failed to send grid for session")
        try:
            bot.send_message(session.chat_id, f"Game started. Words:\n{session.get_hint_text()}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess")))
        except Exception:
            logger.exception("Failed to post fallback start message")

# ----------------------------
# START GAME wrapper
# ----------------------------
def start_game(chat_id:int, starter_id:int, mode:str="normal"):
    if chat_id in games:
        bot.send_message(chat_id, "⚠️ A game is already active here. Use /endgame to stop it.")
        return
    if mode == "normal":
        s = GameSession(chat_id, is_hard=False, word_pool=None, mode="normal")
    elif mode == "hard":
        s = GameSession(chat_id, is_hard=True, mode="hard")
    elif mode == "physics":
        s = GameSession(chat_id, is_hard=False, mode="physics", word_pool=PHYSICS_POOL)
    elif mode == "chemistry":
        s = GameSession(chat_id, is_hard=False, mode="chemistry", word_pool=CHEMISTRY_POOL)
    elif mode == "math":
        s = GameSession(chat_id, is_hard=False, mode="math", word_pool=MATH_POOL)
    elif mode == "jee":
        s = GameSession(chat_id, is_hard=False, mode="jee", word_pool=JEE_POOL)
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
        s = GameSession(chat_id, is_hard=False, mode=mode)
    games[chat_id] = s
    # update starter stats
    db.update_stats(starter_id, games_played_delta=1)
    send_grid_for_session(s, starter_id)
    try:
        s.start_timer()
    except Exception:
        logger.exception("Failed to start timer for session")
    save_sessions()
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🎮 Game started: chat={chat_id} mode={mode} starter={starter_id}")
        except Exception:
            pass

# ----------------------------
# COMMANDS: start games (simple wrappers)
# ----------------------------
@bot.message_handler(commands=["new"])
def cmd_new(m): start_game(m.chat.id, m.from_user.id, mode="normal")

@bot.message_handler(commands=["new_hard"])
def cmd_new_hard(m): start_game(m.chat.id, m.from_user.id, mode="hard")

@bot.message_handler(commands=["new_physics"])
def cmd_new_physics(m): start_game(m.chat.id, m.from_user.id, mode="physics")

@bot.message_handler(commands=["new_chemistry"])
def cmd_new_chem(m): start_game(m.chat.id, m.from_user.id, mode="chemistry")

@bot.message_handler(commands=["new_math"])
def cmd_new_math(m): start_game(m.chat.id, m.from_user.id, mode="math")

@bot.message_handler(commands=["new_jee"])
def cmd_new_jee(m): start_game(m.chat.id, m.from_user.id, mode="jee")

@bot.message_handler(commands=["new_anagram"])
def cmd_new_anagram(m): start_game(m.chat.id, m.from_user.id, mode="anagram")

@bot.message_handler(commands=["new_speedrun"])
def cmd_new_speedrun(m): start_game(m.chat.id, m.from_user.id, mode="speedrun")

@bot.message_handler(commands=["new_definehunt"])
def cmd_new_definehunt(m): start_game(m.chat.id, m.from_user.id, mode="definehunt")

@bot.message_handler(commands=["new_survival"])
def cmd_new_survival(m): start_game(m.chat.id, m.from_user.id, mode="survival")

@bot.message_handler(commands=["new_team"])
def cmd_new_team(m):
    start_game(m.chat.id, m.from_user.id, mode="team")
    bot.send_message(m.chat.id, "Team battle started. Players: use /join_team to join.")

@bot.message_handler(commands=["daily"])
def cmd_daily(m): start_game(m.chat.id, m.from_user.id, mode="daily")

@bot.message_handler(commands=["new_phrase"])
def cmd_phrase(m): start_game(m.chat.id, m.from_user.id, mode="phrase")

# ----------------------------
# Team join / assign
# ----------------------------
@bot.message_handler(commands=["join_team"])
def cmd_join_team(m):
    cid = m.chat.id
    if cid not in games or not isinstance(games[cid], TeamGameSession):
        bot.reply_to(m, "No team battle active here.")
        return
    s = games[cid]
    uid = m.from_user.id
    if uid in s.team_a_ids or uid in s.team_b_ids:
        bot.reply_to(m, "You're already in a team.")
        return
    if len(s.team_a_ids) <= len(s.team_b_ids):
        s.team_a_ids.append(uid)
        bot.reply_to(m, "You joined Team A.")
    else:
        s.team_b_ids.append(uid)
        bot.reply_to(m, "You joined Team B.")
    save_sessions()

@bot.message_handler(commands=["teamadd"])
def cmd_teamadd(m):
    if not db.is_admin(m.from_user.id):
        bot.reply_to(m, "Only admin/owner can assign teams.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /teamadd <@username|id> <A|B>")
        return
    target = parts[1]; team = parts[2].upper()
    if team not in ("A","B"):
        bot.reply_to(m, "Team must be A or B.")
        return
    try:
        if target.startswith("@"):
            ch = bot.get_chat(target); tid = ch.id
        else:
            tid = int(target)
    except:
        bot.reply_to(m, "Could not resolve user.")
        return
    cid = m.chat.id
    if cid not in games or not isinstance(games[cid], TeamGameSession):
        bot.reply_to(m, "No team game here.")
        return
    s = games[cid]
    if tid in s.team_a_ids: s.team_a_ids.remove(tid)
    if tid in s.team_b_ids: s.team_b_ids.remove(tid)
    if team == "A": s.team_a_ids.append(tid)
    else: s.team_b_ids.append(tid)
    bot.reply_to(m, f"Assigned user to Team {team}")
    save_sessions()

# ----------------------------
# Hint, endgame, scorecard
# ----------------------------
@bot.message_handler(commands=["hint"])
def cmd_hint(m):
    cid = m.chat.id; uid = m.from_user.id
    if cid not in games:
        bot.reply_to(m, "No active game here.")
        return
    user = db.get_user(uid, m.from_user.first_name)
    if user["hint_balance"] < HINT_COST:
        bot.reply_to(m, f"Insufficient balance. You need {HINT_COST} pts.")
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
        bot.reply_to(m, "No active game here.")
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
           f"Name: {html.escape(u['name'])}\nTotal Score: {u['total_score']}\nWins: {u['wins']}\n"
           f"Session Points: {session_points}\nHint Balance: {u['hint_balance']}")
    bot.reply_to(m, txt)

@bot.message_handler(commands=["balance"])
def cmd_balance(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"💰 Your hint balance: {u['hint_balance']} pts")

@bot.message_handler(commands=["leaderboard"])
def cmd_leaderboard(m):
    top = db.get_top_players()
    txt = "🏆 Top Players\n\n"
    for i, (n, s) in enumerate(top, 1):
        txt += f"{i}. {html.escape(n)} - {s} pts\n"
    bot.reply_to(m, txt)

# ----------------------------
# addpoints, broadcast, admins
# ----------------------------
@bot.message_handler(commands=["addpoints"])
def cmd_addpoints(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]")
        return
    target = parts[1]; amount = 0
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be integer"); return
    mode = parts[3].lower() if len(parts) >= 4 else "balance"
    try:
        if target.startswith("@"):
            ch = bot.get_chat(target); tid = ch.id
        else:
            tid = int(target)
    except:
        bot.reply_to(m, "Could not resolve user"); return
    db.get_user(tid, getattr(ch, "username", "Player") if "ch" in locals() else "Player")
    if mode == "score":
        db.update_stats(tid, score_delta=amount)
        bot.reply_to(m, f"Added {amount} to score of {tid}")
    else:
        db.update_stats(tid, hint_delta=amount)
        bot.reply_to(m, f"Added {amount} to hint balance of {tid}")
    try:
        bot.send_message(tid, f"💸 You received {amount} pts ({mode}) from the owner.")
    except:
        pass

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can broadcast.")
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /broadcast <message>"); return
    msg = parts[1]
    users = db.all_user_ids()
    success = 0; failed = 0
    for uid in users:
        try:
            bot.send_message(uid, msg); success += 1
        except:
            failed += 1
    bot.reply_to(m, f"Broadcast done. success={success}, failed={failed}")

@bot.message_handler(commands=["addadmin","deladmin","admins"])
def cmd_admins(m):
    if m.text.startswith("/addadmin"):
        if m.from_user.id != OWNER_ID:
            bot.reply_to(m, "Owner only."); return
        parts = m.text.split()
        if len(parts) < 2: bot.reply_to(m, "Usage: /addadmin <id|@username>"); return
        target = parts[1]
        try:
            if target.startswith("@"):
                ch = bot.get_chat(target); aid = ch.id
            else:
                aid = int(target)
        except:
            bot.reply_to(m, "Could not resolve user"); return
        db.add_admin(aid); bot.reply_to(m, f"Added admin {aid}"); return
    if m.text.startswith("/deladmin"):
        if m.from_user.id != OWNER_ID:
            bot.reply_to(m, "Owner only."); return
        parts = m.text.split()
        if len(parts) < 2: bot.reply_to(m, "Usage: /deladmin <id|@username>"); return
        target = parts[1]
        try:
            if target.startswith("@"):
                ch = bot.get_chat(target); aid = ch.id
            else:
                aid = int(target)
        except:
            bot.reply_to(m, "Could not resolve user"); return
        db.remove_admin(aid); bot.reply_to(m, f"Removed admin {aid}"); return
    if m.text.startswith("/admins"):
        admins = db.list_admins()
        txt = "Admins:\n" + "\n".join(str(a) for a in admins)
        if OWNER_ID: txt += f"\nOwner: {OWNER_ID}"
        bot.reply_to(m, txt); return

# ----------------------------
# Reviews & define
# ----------------------------
@bot.message_handler(commands=["review"])
def cmd_review(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /review <text>"); return
    db.add_review(m.from_user.id, m.from_user.username or m.from_user.first_name or str(m.from_user.id), parts[1])
    bot.reply_to(m, "Thanks! Review saved.")

@bot.message_handler(commands=["myreviews"])
def cmd_myreviews(m):
    rows = db.get_user_reviews(m.from_user.id)
    if not rows:
        bot.reply_to(m, "You have no reviews."); return
    txt = "Your reviews:\n\n"
    for r in rows:
        txt += f"ID {r['review_id']}: {r['review_text'][:120]}... - {'Published' if r['published'] else 'Pending'}\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["publishedreviews"])
def cmd_publishedreviews(m):
    rows = db.get_published_reviews(40)
    if not rows:
        bot.reply_to(m, "No published reviews yet."); return
    txt = "Published reviews:\n\n"
    for r in rows:
        txt += f"{html.escape(r['username'])}: {r['review_text']}\n---\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["publishreview"])
def cmd_publishreview(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only."); return
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /publishreview <id>"); return
    try:
        rid = int(parts[1])
    except:
        bot.reply_to(m, "Invalid id"); return
    db.publish_review(rid); bot.reply_to(m, f"Published review {rid}")

@bot.message_handler(commands=["define"])
def cmd_define(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /define <word>"); return
    word = parts[1].strip()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=6)
        d = r.json()
        if isinstance(d, list) and d:
            defs = d[0].get("meanings", [])[0].get("definitions", [])
            if defs:
                definition = defs[0].get("definition", "No definition")
                example = defs[0].get("example", "")
                txt = f"📚 <b>{word}</b>\n{html.escape(definition)}"
                if example: txt += f"\n\n<i>Example:</i> {html.escape(example)}"
                bot.reply_to(m, txt); return
        bot.reply_to(m, f"No definition found for {word}")
    except Exception:
        logger.exception("define failed")
        bot.reply_to(m, "Error fetching definition")

# ----------------------------
# test animation utility (debug)
# ----------------------------
@bot.message_handler(commands=["test_anim"])
def cmd_test_anim(m):
    try:
        grid = [['A','B','C','D','E','F'],
                ['G','H','I','J','K','L'],
                ['M','N','O','P','Q','R'],
                ['S','T','U','V','W','X'],
                ['Y','Z','A','B','C','D'],
                ['E','F','G','H','I','J']]
        placements = {'ABC': [(0,0),(0,1),(0,2)], 'MNO': [(2,0),(2,1),(2,2)]}
        found = set()
        bio = generate_grid_animation(grid, placements=placements, found=found, is_hard=False, frames=6)
        bio.seek(0)
        bot.send_animation(m.chat.id, bio, caption="Test animated grid GIF")
    except Exception:
        logger.exception("test_anim failed")
        bot.reply_to(m, "Failed to generate test animation; check server logs.")

# ----------------------------
# Core guess processing (handles different modes roughly)
# ----------------------------
def process_word_guess(m):
    cid = m.chat.id
    if cid not in games:
        bot.reply_to(m, "No active game here.")
        return
    text = (m.text or "").strip().upper()
    if not text:
        return
    session = games[cid]
    uid = m.from_user.id
    uname = m.from_user.first_name or m.from_user.username or "Player"
    last = session.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        bot.reply_to(m, f"⏳ Wait {COOLDOWN}s between guesses."); return
    session.players_last_guess[uid] = now
    try:
        bot.delete_message(cid, m.message_id)
    except:
        pass

    # Anagram mode special handling
    if getattr(session, "mode", "") == "anagram":
        # session.scrambled expected
        found_word = None
        for orig, scr in session.scrambled.items():
            if text == orig:
                found_word = orig; break
        if not found_word:
            bot.reply_to(m, f"❌ {html.escape(uname)} — '{html.escape(text)}' is incorrect.")
            return
        if found_word in session.found:
            bot.reply_to(m, f"⚠️ {found_word} already found."); return
        session.found.add(found_word)
        pts = FIRST_BLOOD_POINTS if len(session.found) == 1 else FINISHER_POINTS if len(session.found) == len(session.words) else NORMAL_POINTS
        session.players_scores[uid] = session.players_scores.get(uid, 0) + pts
        db.update_stats(uid, score_delta=pts)
        bot.send_message(cid, f"✅ {html.escape(uname)} solved {found_word} (+{pts} pts)")
        if len(session.found) == len(session.words):
            end_game_session(cid, "win", uid)
        return

    # normal grid modes
    if text in session.words:
        if text in session.found:
            bot.send_message(cid, f"⚠️ {text} already found."); return
        session.found.add(text)
        session.last_activity = time.time()
        if len(session.found) == 1:
            pts = FIRST_BLOOD_POINTS
        elif len(session.found) == len(session.words):
            pts = FINISHER_POINTS
        else:
            pts = NORMAL_POINTS
        session.players_scores[uid] = session.players_scores.get(uid, 0) + pts
        db.update_stats(uid, score_delta=pts)
        notify = bot.send_message(cid, f"✨ {html.escape(uname)} found <code>{text}</code> (+{pts} pts)")
        try:
            threading.Timer(4, lambda: bot.delete_message(cid, notify.message_id)).start()
        except:
            pass
        # regenerate animation & send
        try:
            bio = generate_grid_animation(session.grid, placements=session.placements, found=session.found, is_hard=session.is_hard, frames=8)
            bio.seek(0)
            send_animation_or_photo(cid, bio, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if session.is_hard else 'Normal'}\nWords:\n{session.get_hint_text()}"),
                                   reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                                                                           InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                                                                           InlineKeyboardButton("📊 Score", callback_data="game_score")))
        except Exception:
            logger.exception("Failed to send updated animation")
        if len(session.found) == len(session.words):
            end_game_session(cid, "win", uid)
    else:
        try:
            err = bot.send_message(cid, f"❌ {html.escape(uname)} — '{html.escape(text)}' is not in the list.")
            threading.Timer(3, lambda: bot.delete_message(cid, err.message_id)).start()
        except:
            pass

# ----------------------------
# end game
# ----------------------------
def end_game_session(cid, reason, winner_id=None):
    if cid not in games:
        return
    s = games[cid]
    s.active = False
    if reason == "win" and winner_id:
        db.update_stats(winner_id, win=True)
        db.record_game(cid, winner_id)
        standings = sorted(s.players_scores.items(), key=lambda x: x[1], reverse=True)
        txt = f"🏆 GAME OVER — All words found!\n"
        try:
            winner = db.get_user(winner_id, "Player")
            txt += f"MVP: {html.escape(winner['name'])}\n\n"
        except:
            pass
        txt += "Standings:\n"
        for i, (uid, pts) in enumerate(standings, 1):
            u = db.get_user(uid, "Player")
            txt += f"{i}. {html.escape(u['name'])} - {pts} pts\n"
        bot.send_message(cid, txt)
    elif reason == "stopped":
        bot.send_message(cid, "🛑 Game stopped manually.")
    elif reason == "timeout":
        found_count = len(s.found)
        remaining = [w for w in s.words if w not in s.found]
        txt = f"⏰ Time's up! Found {found_count}/{len(s.words)}\nRemaining: {', '.join(remaining) if remaining else 'None'}"
        bot.send_message(cid, txt)
    try:
        del games[cid]
    except:
        pass
    save_sessions()

# ----------------------------
# Start polling
# ----------------------------
if __name__ == "__main__":
    logger.info("Starting Word Vortex bot...")
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=5)
    except KeyboardInterrupt:
        logger.info("Shutdown requested, saving sessions...")
        save_sessions()
        sys.exit(0)
    except Exception:
        logger.exception("Polling crashed, restarting in 5s")
        time.sleep(5)
        os.execv(sys.executable, [sys.executable] + sys.argv)
