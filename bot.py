#!/usr/bin/env python3
"""
WORDS GRID ROBOT - ULTIMATE PREMIUM EDITION
Version: 6.0 - All requested features consolidated:
- Multiple game modes (normal, hard, physics, chemistry, math, jee, anagram, speedrun, definehunt, survival, team battle, daily, phrase)
- Timers, image updates with found-word lines, scoreboard image
- Commands button fixed (sends full command list to user's PM). Fallback: /cmd shows commands if button can't.
- Reviews system (/review, owner can list/ack/publish)
- /cmdinfo <command> for per-command help/usage
- Broadcast, add-to-group button, owner notifications, admin management
- /addpoints default -> hint balance; use 'score' to add to score
- /reset_leaderboard, /restart, safe edit/send fallbacks
- DB persistence (SQLite) for users, admins, game_history, reviews, daily_challenges, team_sessions, settings
- Robust fallbacks to avoid "Could not open commands" errors

Usage:
- Deploy with TELEGRAM_TOKEN and OWNER_ID environment variables set.
- Owner should /restart after updating code.
- Primary fallback for commands: click "Commands" in menu (sends to PM). If PM blocked use /cmd.

Note: This file is long because it implements many features. Read header comments and command list below for how to use each command.
"""

import os
import sys
import time
import html
import io
import random
import string
import logging
import tempfile
import threading
import sqlite3
import json
from datetime import datetime, date
from typing import List, Tuple, Dict, Optional

import requests
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# -------------------------
# CONFIG
# -------------------------
app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHnIoKHGijL6WN7tYLStJil8ZIMBDsXnpA")
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN environment variable not set.")
    sys.exit(1)

try:
    OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
except Exception:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = os.environ.get("FORCE_JOIN", "False").lower() in ("1", "true", "yes")

SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = os.environ.get("START_IMG_URL", "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Gameplay constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {
    "SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT",
    "BITCH", "ASS", "HENTAI", "BOOBS"
}
GAME_DURATION = 600  # seconds default (can be changed per-mode)
COOLDOWN = 2
HINT_COST = 50

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# Word pools: additional curated pools will be extended from remote + static lists
PHYSICS_WORDS = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "ACCEL", "VECTOR", "SCALAR", "WAVE", "PHOTON", "GRAVITY"]
CHEMISTRY_WORDS = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "CATION", "ANION", "ACID", "BASE", "SALT"]
MATH_WORDS = ["INTEGRAL", "DERIVATIVE", "MATRIX", "VECTOR", "CALCULUS", "LIMIT", "PROB", "MODULUS", "ALGORITHM", "LEMMA"]
JEE_WORDS = ["KINEMATICS", "ELECTROSTATICS", "THERMODYNAMICS", "INTEGRAL", "DIFFERENTIAL", "MATRIX", "VECTOR"]

# -------------------------
# DATABASE LAYER
# -------------------------
DB_PATH = os.environ.get("WORDS_DB", "wordsgrid_v6.db")


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        # users
        c.execute(
            """CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                join_date TEXT,
                games_played INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                total_score INTEGER DEFAULT 0,
                hint_balance INTEGER DEFAULT 100,
                is_banned INTEGER DEFAULT 0
            )"""
        )
        # admins
        c.execute("""CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)""")
        # game_history
        c.execute(
            """CREATE TABLE IF NOT EXISTS game_history (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                winner_id INTEGER,
                mode TEXT,
                timestamp TEXT
            )"""
        )
        # reviews
        c.execute(
            """CREATE TABLE IF NOT EXISTS reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                text TEXT,
                created_at TEXT,
                approved INTEGER DEFAULT 0
            )"""
        )
        # daily challenges
        c.execute(
            """CREATE TABLE IF NOT EXISTS daily_challenges (
                day TEXT PRIMARY KEY,
                puzzle_json TEXT,
                created_at TEXT
            )"""
        )
        # team sessions
        c.execute(
            """CREATE TABLE IF NOT EXISTS team_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                data_json TEXT,
                created_at TEXT
            )"""
        )
        # settings (small key-value)
        c.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        conn.commit()
        conn.close()

    # user helpers
    def get_user(self, user_id: int, name: str = "Player"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            join_date = time.strftime("%Y-%m-%d")
            c.execute(
                "INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)",
                (user_id, name, join_date),
            )
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
        conn.close()
        return row  # tuple, indices as in create

    def register_user(self, user_id: int, name: str = "Player"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if row:
            conn.close()
            return row, False
        join_date = time.strftime("%Y-%m-%d")
        c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row, True

    def update_stats(self, user_id: int, score_delta: int = 0, hint_delta: int = 0, win: bool = False, games_played_delta: int = 0):
        conn = self._connect()
        c = conn.cursor()
        if score_delta != 0:
            c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (score_delta, user_id))
        if hint_delta != 0:
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (hint_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        if games_played_delta != 0:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
        conn.commit()
        conn.close()

    # admin helpers
    def add_admin(self, admin_id: int):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        conn.close()

    def remove_admin(self, admin_id: int):
        conn = self._connect()
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))
        conn.commit()
        conn.close()

    def is_admin(self, user_id: int) -> bool:
        if OWNER_ID and user_id == OWNER_ID:
            return True
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return bool(r)

    def list_admins(self) -> List[int]:
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins")
        data = [r[0] for r in c.fetchall()]
        conn.close()
        return data

    def record_game(self, chat_id: int, winner_id: int, mode: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, mode, timestamp) VALUES (?, ?, ?, ?)",
                  (chat_id, winner_id, mode, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_top_players(self, limit: int = 10) -> List[Tuple[str, int]]:
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def reset_leaderboard(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = 0, wins = 0")
        conn.commit()
        conn.close()

    def get_all_users(self) -> List[int]:
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        data = [r[0] for r in c.fetchall()]
        conn.close()
        return data

    # reviews
    def add_review(self, user_id: int, username: str, text: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO reviews (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, username, text, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_reviews(self, approved: Optional[int] = None):
        conn = self._connect()
        c = conn.cursor()
        if approved is None:
            c.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM reviews WHERE approved=? ORDER BY created_at DESC", (approved,))
        rows = c.fetchall()
        conn.close()
        return rows

    def approve_review(self, review_id: int):
        conn = self._connect()
        c = conn.cursor()
        c.execute("UPDATE reviews SET approved=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    # daily challenge
    def set_daily(self, day: str, puzzle_json: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO daily_challenges (day, puzzle_json, created_at) VALUES (?, ?, ?)",
                  (day, puzzle_json, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_daily(self, day: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT puzzle_json FROM daily_challenges WHERE day=?", (day,))
        r = c.fetchone()
        conn.close()
        return r[0] if r else None

    # team sessions
    def save_team_session(self, chat_id: int, data_json: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO team_sessions (chat_id, data_json, created_at) VALUES (?, ?, ?)", (chat_id, data_json, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_team_sessions(self, chat_id: Optional[int] = None):
        conn = self._connect()
        c = conn.cursor()
        if chat_id:
            c.execute("SELECT * FROM team_sessions WHERE chat_id=? ORDER BY created_at DESC", (chat_id,))
        else:
            c.execute("SELECT * FROM team_sessions ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        return rows


db = Database()

# -------------------------
# WORD SOURCE
# -------------------------
ALL_WORDS: List[str] = []


def fetch_remote_wordlist(timeout=8):
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        r = requests.get(url, timeout=timeout)
        lines = r.text.splitlines()
        words = [w.strip().upper() for w in lines if w.strip()]
        words = [w for w in words if w.isalpha() and 4 <= len(w) <= 12 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info(f"Fetched {len(ALL_WORDS)} words from remote list.")
            return
    except Exception:
        logger.exception("Remote wordlist fetch failed")
    # fallback
    fallback = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "SPACE", "GALAXY", "NEBULA", "FUTURE", "MATRIX", "VECTOR"]
    ALL_WORDS = fallback
    logger.info("Using fallback wordlist.")


fetch_remote_wordlist()

# -------------------------
# IMAGE UTILITIES
# -------------------------
class GridRendererUtil:
    @staticmethod
    def draw_grid_image(grid: List[List[str]], placements: Dict[str, List[Tuple[int, int]]], found: set, is_hard=False, title="WORD VORTEX", version="v6.0"):
        cell_size = 56 if is_hard else 56
        header_h = 94
        footer_h = 44
        pad = 24
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        width = cols * cell_size + pad * 2
        height = header_h + footer_h + rows * cell_size + pad * 2
        img = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(img)
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(fp):
                fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            header_font = ImageFont.truetype(fp, 36)
            letter_font = ImageFont.truetype(fp, 30)
            small_font = ImageFont.truetype(fp, 14)
        except Exception:
            header_font = ImageFont.load_default()
            letter_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        # header
        draw.rectangle([0, 0, width, header_h], fill="#eef6fb")
        tbox = draw.textbbox((0, 0), title, font=header_font)
        draw.text(((width - (tbox[2] - tbox[0])) / 2, 18), title, fill="#1f6feb", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        draw.text((pad, header_h - 26), mode_text, fill="#6b7280", font=small_font)

        grid_start_y = header_h + pad
        # draw grid and letters
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell_size
                y = grid_start_y + r * cell_size
                draw.rectangle([x, y, x + cell_size, y + cell_size], outline="#2b90d9", width=2)
                ch = grid[r][c]
                bb = draw.textbbox((0, 0), ch, font=letter_font)
                draw.text((x + (cell_size - (bb[2] - bb[0])) / 2, y + (cell_size - (bb[3] - bb[1])) / 2 - 4), ch, fill="#222", font=letter_font)

        # draw found lines
        try:
            if placements and found:
                for w, coords in placements.items():
                    if w in found and coords:
                        a = coords[0]; b = coords[-1]
                        x1 = pad + a[1] * cell_size + cell_size / 2
                        y1 = grid_start_y + a[0] * cell_size + cell_size / 2
                        x2 = pad + b[1] * cell_size + cell_size / 2
                        y2 = grid_start_y + b[0] * cell_size + cell_size / 2
                        # shadow
                        draw.line([(x1, y1), (x2, y2)], fill="#ffffff", width=8)
                        draw.line([(x1, y1), (x2, y2)], fill="#ff4757", width=5)
                        r_end = 6
                        draw.ellipse([x1 - r_end, y1 - r_end, x1 + r_end, y1 + r_end], fill="#ff4757")
                        draw.ellipse([x2 - r_end, y2 - r_end, x2 + r_end, y2 + r_end], fill="#ff4757")
        except Exception:
            logger.exception("Error drawing lines")

        # footer
        draw.text((pad, height - footer_h + 12), f"Made by @Ruhvaan", fill="#95a5a6", font=small_font)
        draw.text((width - 120, height - footer_h + 12), version, fill="#95a5a6", font=small_font)

        bio = io.BytesIO()
        img.save(bio, "JPEG", quality=90)
        bio.seek(0)
        try:
            bio.name = "grid.jpg"
        except Exception:
            pass
        return bio


class LeaderboardImage:
    @staticmethod
    def draw_rows(rows: List[Tuple[int, str, int]]):
        width = 700
        height = max(120, 60 + 40 * len(rows))
        img = Image.new("RGB", (width, height), "#071123")
        draw = ImageDraw.Draw(img)
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            title_f = ImageFont.truetype(fp, 26)
            row_f = ImageFont.truetype(fp, 20)
        except Exception:
            title_f = ImageFont.load_default()
            row_f = ImageFont.load_default()
        draw.text((20, 8), "Session Leaderboard", fill="#ffd700", font=title_f)
        y = 48
        for idx, name, pts in rows:
            draw.text((20, y), f"{idx}. {name}", fill="#fff", font=row_f)
            draw.text((520, y), f"{pts} pts", fill="#7be495", font=row_f)
            y += 36
        bio = io.BytesIO()
        img.save(bio, "PNG", quality=90)
        bio.seek(0)
        try:
            bio.name = "leaders.png"
        except Exception:
            pass
        return bio

# -------------------------
# HELPERS & SAFETY
# -------------------------


def is_subscribed(user_id: int) -> bool:
    if not FORCE_JOIN:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if not CHANNEL_USERNAME:
        return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ("creator", "administrator", "member")
    except Exception:
        logger.debug("Subscription check failed; allowing by default.")
        return True


def safe_edit_message(caption: str, cid: int, mid: int, reply_markup=None) -> bool:
    try:
        bot.edit_message_caption(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        bot.edit_message_text(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except Exception:
        pass
    try:
        bot.send_message(cid, caption, reply_markup=reply_markup, parse_mode="HTML")
        try:
            bot.delete_message(cid, mid)
        except Exception:
            pass
        return True
    except Exception:
        logger.exception("safe_edit_message: all attempts failed")
        return False


def safe_send_pm_first(uid: int, text: str, reply_markup=None) -> bool:
    """
    Try to send a long message to user PM first (for Commands). If succeeds, returns True.
    Otherwise try to send to caller chat (group) and return whether that succeeded.
    """
    try:
        bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception:
        logger.debug("PM send failed, will fallback to group.")
    return False


def ensure_user_registered(uid: int, name: str):
    try:
        db.register_user(uid, name)
    except Exception:
        logger.exception("User register failed")


def short_user_text(user_row) -> str:
    # user_row: tuple from DB
    return f"{user_row[1]} (ID: {user_row[0]})"


# -------------------------
# COMMANDS & MENU
# -------------------------
COMMANDS_FULL_TEXT = """
🤖 Word Vortex - Full Command List

User commands:
- /start, /help : open main menu
- /cmd : open commands (fallback if button not working)
- /ping : check bot latency
- /new : start normal game (8x8)
- /new_hard : start hard game (10x10)
- /new_physics : start physics pool game
- /new_chemistry : start chemistry pool game
- /new_math : start math pool game
- /new_jee : start JEE-level pool game
- /new_anagram : Anagram Sprint (fast text-only rounds)
- /new_speedrun : Speedrun (max words in limited time)
- /new_definehunt : Definition Hunt (clues are definitions)
- /new_survival : Survival progressive rounds
- /new_team : Team Battle (players /join_team then admin starts /start_team)
- /new_daily : Start or view daily challenge (seeded puzzle)
- /new_phrase : Hidden Phrase mode (bonus phrase words)
- /hint : buy a hint (costs points)
- /scorecard, /mystats : view personal stats
- /balance : view hint balance
- /leaderboard : global top players
- /scorecard : session scorecard

Review & support:
- /review <text> : submit a review/feedback (owner will see)
- /issue <text> : report issue to owner

Dictionary:
- /define <word> : get definition (from dictionaryapi.dev)

Per-command help:
- /cmdinfo <command> : detailed description & usage of a command

Owner/Admin (owner-only unless specified):
- /addpoints <id|@username> <amount> [score|balance] : default adds to hint balance
- /addadmin <id|@username> : add admin
- /deladmin <id|@username> : remove admin
- /admins : list admins
- /reset_leaderboard : zero scores & wins
- /broadcast <message> : send message to all users
- /show_settings : show bot settings
- /set_hint_cost <amount> : change hint cost
- /toggle_force_join : toggle channel join requirement
- /set_start_image <url> : set start image
- /restart : restart bot
- /list_reviews [pending|all] : owner review moderation
- /approve_review <id> : approve (owner)
"""

CMDINFO = {
    "new": {
        "usage": "/new (in group)",
        "desc": "Start a normal 8x8 word-grid game. Use in a group chat. Image + inline buttons appear.",
        "who": "Anyone in group",
        "why": "Standard round for groups."
    },
    "new_physics": {
        "usage": "/new_physics",
        "desc": "Start a game using random physics vocabulary (words chosen randomly each run).",
        "who": "Anyone in group",
        "why": "Focused practice on physics terms."
    },
    # ... further entries will be added programmatically in code below
}


def build_main_menu_markup():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}") if CHANNEL_USERNAME else InlineKeyboardButton("📢 Join Channel", url=SUPPORT_GROUP_LINK),
        InlineKeyboardButton("🔄 Check Join", callback_data="check_join"),
    )
    # add-to-group
    try:
        me = bot.get_me().username
        if me:
            kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{me}?startgroup=true"))
    except Exception:
        pass
    kb.add(
        InlineKeyboardButton("🎮 Play Game", callback_data="help_play"),
        InlineKeyboardButton("🤖 Commands", callback_data="help_cmd"),
    )
    kb.add(
        InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
        InlineKeyboardButton("👤 My Stats", callback_data="menu_stats"),
    )
    kb.add(
        InlineKeyboardButton("🐞 Report Issue", callback_data="open_issue"),
        InlineKeyboardButton("💳 Buy Points", callback_data="open_plans"),
    )
    kb.add(InlineKeyboardButton("✍️ Review", callback_data="open_review"))
    kb.add(InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))
    return kb


@bot.message_handler(commands=["start", "help"])
def cmd_start(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    ensure_user_registered(m.from_user.id, name)
    # notify owner
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🔔 /start used by {html.escape(name)} (ID: {m.from_user.id}) in chat {m.chat.id}")
        except Exception:
            logger.exception("Owner notify failed")
    txt = f"👋 <b>Hello, {html.escape(name)}!</b>\n\nWelcome to Word Vortex — choose an option below. Click a button to open that section (Commands open in your private chat)."
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=build_main_menu_markup())
    except Exception:
        bot.reply_to(m, txt, reply_markup=build_main_menu_markup())


@bot.message_handler(commands=["cmd"])
def cmd_cmd(m):
    # fallback if Commands button doesn't work
    try:
        sent_pm = False
        try:
            bot.send_message(m.from_user.id, COMMANDS_FULL_TEXT, parse_mode="HTML")
            sent_pm = True
        except Exception:
            sent_pm = False
        if sent_pm:
            bot.reply_to(m, "✔️ I sent the commands list to your private chat.")
        else:
            bot.reply_to(m, COMMANDS_FULL_TEXT)
    except Exception:
        logger.exception("cmd fallback failed")
        bot.reply_to(m, "❌ Could not show commands.")


@bot.message_handler(commands=["cmdinfo"])
def cmd_cmdinfo(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /cmdinfo <command>\nExample: /cmdinfo new_physics")
        return
    key = parts[1].strip().lstrip("/").lower()
    info = CMDINFO.get(key)
    if not info:
        bot.reply_to(m, f"No info available for '{key}'. Try /cmd for full list.")
        return
    txt = f"<b>/{key}</b>\n\nUsage: {info.get('usage')}\n\nDescription: {info.get('desc')}\n\nWho: {info.get('who')}\nWhy: {info.get('why')}"
    bot.reply_to(m, txt)


# -------------------------
# CALLBACK HANDLER (robust)
# -------------------------
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    cid = c.message.chat.id
    mid = c.message.message_id
    uid = c.from_user.id
    data = c.data

    def pm_first_send(text: str, reply_markup=None):
        # try pm first
        try:
            bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
            try:
                bot.answer_callback_query(c.id, "I sent the details to your private chat.")
            except:
                pass
            # inform group lightly (non-intrusive)
            try:
                bot.send_message(cid, f"🔔 {c.from_user.first_name}, I sent details to your PM.")
            except:
                pass
            return True
        except Exception:
            logger.debug("PM send failed; fallback to group")
        # fallback to group
        try:
            bot.send_message(cid, text, parse_mode="HTML", reply_markup=reply_markup)
            try:
                bot.answer_callback_query(c.id, "Opened here.")
            except:
                pass
            return True
        except Exception:
            try:
                bot.answer_callback_query(c.id, "❌ Could not open. Please start a private chat with the bot and try /cmd.", show_alert=True)
            except:
                pass
            return False

    # check join
    if data == "check_join":
        if is_subscribed(uid):
            try:
                bot.delete_message(cid, mid)
            except Exception:
                pass
            cmd_start(c.message)
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

    # open_issue
    if data == "open_issue":
        prompt = f"@{c.from_user.username or c.from_user.first_name} Please describe your issue (use /issue <text>)."
        try:
            bot.send_message(uid, prompt, reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "I sent you a private prompt.")
            return
        except Exception:
            pass
        try:
            bot.send_message(cid, prompt, reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "Opened in group.")
            return
        except Exception:
            bot.answer_callback_query(c.id, "❌ Could not open issue prompt.", show_alert=True)
            return

    # open_plans
    if data == "open_plans":
        txt = "💳 Points Plans:\n\n"
        for p in PLANS:
            txt += f"- {p['points']} pts : ₹{p['price_rs']}\n"
        txt += f"\nTo buy, contact the owner: {SUPPORT_GROUP_LINK}"
        pm_first_send(txt)
        return

    # help_play
    if data == "help_play":
        txt = ("<b>How to Play</b>\n\n"
               "1) Start a game in a group using /new or /new_physics etc.\n"
               "2) The bot sends a grid image with a list of masked words.\n"
               "3) Click 'Found It' and type the word. Correct guesses update score and image.\n\n"
               "Scoring: First blood, normal, finisher points apply.")
        pm_first_send(txt)
        return

    # help_cmd - send full commands list to user's PM (fixed behavior)
    if data == "help_cmd":
        pm_first_send(COMMANDS_FULL_TEXT)
        return

    # menu_lb
    if data == "menu_lb":
        top = db.get_top_players(10)
        txt = "🏆 Global Leaderboard\n\n"
        for i, (name, score) in enumerate(top, 1):
            txt += f"{i}. <b>{html.escape(name)}</b> - {score} pts\n"
        pm_first_send(txt)
        return

    # menu_stats
    if data == "menu_stats":
        user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_points = 0
        if c.message.chat.id in games:
            session_points = games[c.message.chat.id].players_scores.get(uid, 0)
        txt = (f"📋 <b>Your Stats</b>\nName: {html.escape(user[1])}\nTotal Score: {user[5]}\nWins: {user[4]}\n"
               f"Games Played: {user[3]}\nSession Points: {session_points}\nHint Balance: {user[6]}")
        pm_first_send(txt)
        return

    # open_review (shortcut)
    if data == "open_review":
        try:
            bot.send_message(uid, "✍️ Please send your review using /review <your text>", reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "I sent you a private prompt to submit a review.")
        except Exception:
            try:
                bot.send_message(cid, "✍️ Use /review <text> to submit a review.")
                bot.answer_callback_query(c.id, "Prompt opened here.")
            except:
                bot.answer_callback_query(c.id, "❌ Could not open.", show_alert=True)
        return

    # Game callbacks left to game logic handlers (game_guess, game_hint, game_score)
    if data in ("game_guess", "game_hint", "game_score"):
        # forward to game callback flows: reuse earlier patterns
        if data == "game_guess":
            if c.message.chat.id not in games:
                try: bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                except: pass
                return
            try:
                username = c.from_user.username or c.from_user.first_name
                msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
                bot.register_next_step_handler(msg, process_word_guess)
                bot.answer_callback_query(c.id, "✍️ Type your guess.")
            except Exception:
                bot.answer_callback_query(c.id, "❌ Could not open input.", show_alert=True)
            return
        if data == "game_hint":
            if c.message.chat.id not in games:
                try: bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                except: pass
                return
            game = games[c.message.chat.id]
            user_row = db.get_user(uid, c.from_user.first_name)
            if user_row and user_row[6] < HINT_COST:
                try: bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user_row[6]}", show_alert=True)
                except: pass
                return
            hidden = [w for w in game.words if w not in game.found]
            if not hidden:
                try: bot.answer_callback_query(c.id, "All words found!", show_alert=True)
                except: pass
                return
            reveal = random.choice(hidden)
            db.update_stats(uid, score_delta=0, hint_delta=-HINT_COST)
            try:
                bot.send_message(cid, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)\nBy {html.escape(c.from_user.first_name)}")
                bot.answer_callback_query(c.id, "Hint revealed.")
            except Exception:
                bot.answer_callback_query(c.id, "❌ Could not send hint.", show_alert=True)
            return
        if data == "game_score":
            if c.message.chat.id not in games:
                try: bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
                except: pass
                return
            game = games[c.message.chat.id]
            if not game.players_scores:
                try: bot.answer_callback_query(c.id, "No scores yet.", show_alert=True)
                except: pass
                return
            leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
            rows = []
            for i, (uid_score, pts) in enumerate(leaderboard, 1):
                user = db.get_user(uid_score, "Player")
                rows.append((i, user[1], pts))
            img = LeaderboardImage.draw_rows(rows[:10])
            try:
                bot.send_photo(cid, img, caption="📊 Session Leaderboard")
                bot.answer_callback_query(c.id, "Leaderboard shown.")
            except:
                txt = "📊 Session Leaderboard\n\n"
                for idx, name, pts in rows[:10]:
                    txt += f"{idx}. {html.escape(name)} - {pts} pts\n"
                pm_first_send(txt)
            return

    # default ack
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass


# -------------------------
# GAME MODES IMPLEMENTATION
# -------------------------
def start_game_session(chat_id: int, starter_id: int, mode: str = "default", is_hard: bool = False, word_pool: Optional[List[str]] = None, duration: Optional[int] = None):
    """
    Create a GameSession object for chat and start it.
    Mode values: default, hard, physics, chemistry, math, jee, anagram, speedrun, definehunt, survival, team, daily, phrase
    """
    if duration is None:
        duration = GAME_DURATION
    session = GameSession(chat_id, mode=mode, is_hard=is_hard, duration=duration, word_pool=word_pool)
    games[chat_id] = session
    # register starter and update stats
    try:
        db.register_user(starter_id, "Player")
        db.update_stats(starter_id, games_played_delta=1)
    except Exception:
        logger.exception("Starter registration/update failed")
    # render image or initial message depending on mode
    if mode in ("anagram",):
        # text-only anagram start
        try:
            txt = f"🎯 <b>Anagram Sprint Started!</b>\nTime: {duration//60} minutes\n\nSolve the anagrams quickly!\n"
            txt += "Anagrams:\n"
            for idx, an in enumerate(session.anagrams, 1):
                txt += f"{idx}. <code>{an['jumbled']}</code>\n"
            sent = bot.send_message(chat_id, txt)
            session.message_id = sent.message_id
        except Exception:
            logger.exception("Failed to start anagram session")
    elif mode in ("speedrun",):
        try:
            img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
            caption = f"⚡ <b>Speedrun</b>\nFind as many words as you can in {duration//60} min.\n\nWords to find are free-form (no masked list)."
            sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                InlineKeyboardButton("📊 Score", callback_data="game_score"),
            ))
            session.message_id = sent.message_id
        except Exception:
            logger.exception("Failed to start speedrun")
    elif mode in ("definehunt",):
        # definitions provided
        try:
            caption = f"🧠 <b>Definition Hunt</b>\nFind words from definitions listed in PM (or group)."
            # send definitions to PM of starter and to group summary
            send_defs = "\n".join([f"{i+1}. {d}" for i, d in enumerate(session.definitions)])
            try:
                bot.send_message(starter_id, f"Definitions for this round:\n\n{send_defs}")
            except:
                bot.send_message(chat_id, "Definitions have been posted to group due to PM failure.")
                bot.send_message(chat_id, send_defs)
            img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
            sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                InlineKeyboardButton("📊 Score", callback_data="game_score"),
            ))
            session.message_id = sent.message_id
        except Exception:
            logger.exception("Failed to start definehunt")
    else:
        # standard grid modes: default, physics, chemistry, math, jee, phrase, survival, team, daily
        try:
            img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
            caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
                       f"Mode: {mode} {'(Hard)' if is_hard else ''}\n"
                       f"⏱ Time Limit: {session.duration//60} minutes\n\n"
                       f"<b>Words to find:</b>\n{session.get_hint_text()}")
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
            markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                       InlineKeyboardButton("📊 Score", callback_data="game_score"))
            sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=markup)
            session.message_id = sent.message_id
        except Exception:
            logger.exception("Failed to start grid session")


class GameSession:
    """
    Represents a game session in a chat. Supports many modes.
    """

    def __init__(self, chat_id: int, mode: str = "default", is_hard: bool = False, duration: int = GAME_DURATION, word_pool: Optional[List[str]] = None):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.duration = duration
        self.start_time = time.time()
        self.last_activity = time.time()
        self.grid: List[List[str]] = []
        self.placements: Dict[str, List[Tuple[int, int]]] = {}
        self.words: List[str] = []
        self.found: set = set()
        self.players_scores: Dict[int, int] = {}
        self.players_last_guess: Dict[int, float] = {}
        self.message_id: Optional[int] = None
        self.timer_thread: Optional[threading.Thread] = None
        self.active = True

        # special-mode fields
        self.anagrams: List[Dict] = []  # for anagram mode: list of {word, jumbled}
        self.definitions: List[str] = []  # for definehunt: definitions

        # choose word pool
        pool = []
        if word_pool:
            pool = [w.upper() for w in word_pool if w.isalpha() and 3 <= len(w) <= 12]
        else:
            # choose based on mode or ALL_WORDS
            if mode == "physics":
                pool = PHYSICS_WORDS[:]
            elif mode == "chemistry":
                pool = CHEMISTRY_WORDS[:]
            elif mode == "math":
                pool = MATH_WORDS[:]
            elif mode == "jee":
                pool = JEE_WORDS[:]
            elif mode == "phrase":
                # phrase: select words forming a phrase (we will pick multiple words)
                pool = ALL_WORDS[:]
            elif mode == "anagram":
                pool = ALL_WORDS[:]
            elif mode == "speedrun":
                pool = ALL_WORDS[:]
            elif mode == "definehunt":
                pool = ALL_WORDS[:]
            else:
                pool = ALL_WORDS[:]

        # generate session content depending on mode
        if mode == "anagram":
            self._prepare_anagram(pool)
        elif mode == "definehunt":
            self._prepare_definehunt(pool)
        elif mode == "speedrun":
            self._prepare_speedrun(pool)
        elif mode == "survival":
            self._prepare_survival(pool)
        elif mode == "phrase":
            self._prepare_phrase(pool)
        else:
            self._prepare_grid(pool)

        # start timer thread
        self.start_timer()

    # -------------------------
    # session preparation helpers
    # -------------------------
    def _prepare_grid(self, pool: List[str]):
        # select unique words
        choices = pool[:] if pool else ALL_WORDS[:]
        if len(choices) < self.word_count:
            choices = choices * ((self.word_count // len(choices)) + 1)
        self.words = random.sample(choices, self.word_count)
        self.grid = [[" " for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        for w in sorted_words:
            placed = False
            for _ in range(400):
                r = random.randint(0, self.size - 1)
                c = random.randint(0, self.size - 1)
                dr, dc = random.choice(dirs)
                if self._can_place(r, c, dr, dc, w):
                    coords = []
                    for i, ch in enumerate(w):
                        rr, cc = r + i * dr, c + i * dc
                        self.grid[rr][cc] = ch
                        coords.append((rr, cc))
                    self.placements[w] = coords
                    placed = True
                    break
            if not placed:
                # try scanning
                for rr in range(self.size):
                    for cc in range(self.size):
                        for dr, dc in dirs:
                            if self._can_place(rr, cc, dr, dc, w):
                                coords = []
                                for i, ch in enumerate(w):
                                    rrr, ccc = rr + i * dr, cc + i * dc
                                    self.grid[rrr][ccc] = ch
                                    coords.append((rrr, ccc))
                                self.placements[w] = coords
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
                        break
        # fill blanks
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == " ":
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def _prepare_anagram(self, pool: List[str]):
        # anagram round: we create jumbled words list
        choices = [w for w in pool if 4 <= len(w) <= 10]
        if len(choices) < 8:
            choices = choices * 5
        selected = random.sample(choices, 8)
        self.anagrams = []
        for w in selected:
            j = list(w)
            random.shuffle(j)
            jumbled = "".join(j)
            # ensure jumbled not equals original
            if jumbled == w:
                jumbled = "".join(random.sample(j, len(j)))
            self.anagrams.append({"word": w, "jumbled": jumbled})
        # session uses text-only; no grid required

    def _prepare_definehunt(self, pool: List[str]):
        # pick words and fetch short definitions for them using dictionaryapi.dev
        choices = [w for w in pool if 4 <= len(w) <= 10]
        if len(choices) < 6:
            choices = choices * 3
        selected = random.sample(choices, 6)
        self.words = [w.upper() for w in selected]
        self.definitions = []
        for w in self.words:
            try:
                r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w.lower()}", timeout=6)
                data = r.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings", [])
                    if meanings:
                        defs = meanings[0].get("definitions", [])
                        if defs:
                            definition = defs[0].get("definition", "")
                            self.definitions.append(definition[:220])
                            continue
            except Exception:
                logger.debug("Definition fetch failed for " + w)
            # fallback masked hint
            self.definitions.append(f"Starts with {w[0]} and length {len(w)}")
        # still have a grid for optional visual support
        self._prepare_grid(self.words)

    def _prepare_speedrun(self, pool: List[str]):
        # speedrun will reuse grid but may allow smaller words
        self.word_count = 20 if not self.is_hard else 30
        # reduce minimum length to include small words
        choices = [w for w in pool if 3 <= len(w) <= 8]
        if len(choices) < self.word_count:
            choices = choices * ((self.word_count // max(1, len(choices))) + 2)
        self.words = random.sample(choices, self.word_count)
        self._prepare_grid(self.words)

    def _prepare_survival(self, pool: List[str]):
        # survival starts with few short words; subsequent rounds will be managed by the session
        self.word_count = 4
        choices = [w for w in pool if 3 <= len(w) <= 6]
        if len(choices) < self.word_count:
            choices = choices * 3
        self.words = random.sample(choices, self.word_count)
        self._prepare_grid(self.words)
        # survival state fields
        self.survival_round = 1

    def _prepare_phrase(self, pool: List[str]):
        # pick consecutive words that could form a short phrase: pick small words and nearby semantically; approximate
        words = [w for w in pool if 3 <= len(w) <= 7]
        if len(words) < 6:
            words = words * 3
        phrase_len = random.choice([3, 4, 5])
        phrase_words = random.sample(words, phrase_len)
        self.words = phrase_words + random.sample([w for w in pool if w not in phrase_words], self.word_count - phrase_len)
        self._prepare_grid(self.words)
        self.phrase = " ".join(phrase_words)

    # -------------------------
    # utility helpers
    # -------------------------
    def _can_place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            rr = r + i * dr
            cc = c + i * dc
            if not (0 <= rr < self.size and 0 <= cc < self.size):
                return False
            if self.grid[rr][cc] != " " and self.grid[rr][cc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + "-" * (len(w) - 1)
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

    def start_timer(self):
        if self.timer_thread and self.timer_thread.is_alive():
            return
        self.timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self.timer_thread.start()

    def _timer_worker(self):
        try:
            while self.active:
                rem = int(self.duration - (time.time() - self.start_time))
                if rem <= 0:
                    # timeout
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! The game has ended.")
                    except Exception:
                        logger.exception("Timer notify error")
                    try:
                        end_game_session(self.chat_id, "timeout")
                    except Exception:
                        logger.exception("End session on timeout failed")
                    break
                # update caption periodically if message_id exists
                if self.message_id:
                    mins = rem // 60
                    secs = rem % 60
                    cap = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
                           f"Mode: {self.mode} {'(Hard)' if self.is_hard else ''}\n"
                           f"⏱ Time Left: {mins}:{secs:02d}\n\n"
                           f"<b>Words to find:</b>\n{self.get_hint_text()}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
                    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                               InlineKeyboardButton("📊 Score", callback_data="game_score"))
                    safe_edit_message(cap, self.chat_id, self.message_id, reply_markup=markup)
                time.sleep(8)
        except Exception:
            logger.exception("Timer worker failed")
        finally:
            self.active = False


# -------------------------
# GAME START WRAPPERS (handlers)
# -------------------------
@bot.message_handler(commands=["new", "new_hard", "new_physics", "new_chemistry", "new_math", "new_jee", "new_anagram", "new_speedrun", "new_definehunt", "new_survival", "new_team", "new_daily", "new_phrase"])
def handle_start_commands(m):
    cmd = m.text.split()[0].lstrip("/").lower()
    chat_id = m.chat.id
    user_id = m.from_user.id
    ensure_user_registered(user_id, m.from_user.first_name or m.from_user.username or "Player")

    if cmd == "new":
        start_game_session(chat_id, user_id, mode="default", is_hard=False)
        bot.reply_to(m, "Started normal game.")
    elif cmd == "new_hard":
        start_game_session(chat_id, user_id, mode="default", is_hard=True)
        bot.reply_to(m, "Started hard game.")
    elif cmd == "new_physics":
        start_game_session(chat_id, user_id, mode="physics", is_hard=False, word_pool=PHYSICS_WORDS)
        bot.reply_to(m, "Started physics pool game.")
    elif cmd == "new_chemistry":
        start_game_session(chat_id, user_id, mode="chemistry", is_hard=False, word_pool=CHEMISTRY_WORDS)
        bot.reply_to(m, "Started chemistry pool game.")
    elif cmd == "new_math":
        start_game_session(chat_id, user_id, mode="math", is_hard=False, word_pool=MATH_WORDS)
        bot.reply_to(m, "Started math pool game.")
    elif cmd == "new_jee":
        start_game_session(chat_id, user_id, mode="jee", is_hard=False, word_pool=JEE_WORDS)
        bot.reply_to(m, "Started JEE pool game.")
    elif cmd == "new_anagram":
        start_game_session(chat_id, user_id, mode="anagram")
        bot.reply_to(m, "Started Anagram Sprint (text-based).")
    elif cmd == "new_speedrun":
        start_game_session(chat_id, user_id, mode="speedrun", is_hard=False)
        bot.reply_to(m, "Started Speedrun mode.")
    elif cmd == "new_definehunt":
        start_game_session(chat_id, user_id, mode="definehunt")
        bot.reply_to(m, "Started Definition Hunt.")
    elif cmd == "new_survival":
        start_game_session(chat_id, user_id, mode="survival")
        bot.reply_to(m, "Started Survival mode.")
    elif cmd == "new_team":
        # initialize a team session object stored in games with special mode flag
        # team flow requires further commands: /join_team and /start_team
        if chat_id in games:
            bot.reply_to(m, "A game is already active here. Finish it first.")
            return
        session = GameSession(chat_id, mode="team", is_hard=False)
        games[chat_id] = session
        # store team data structure on session object (teams, joins)
        session.teams = {"A": set(), "B": set()}
        session.join_phase = True
        session.max_joins = 20
        bot.reply_to(m, "Team Battle initialized. Players: use /join_team to join. Owner/admin use /start_team to begin.")
    elif cmd == "new_daily":
        # daily challenge: if exists for today, show it; otherwise create and store
        today = date.today().isoformat()
        puzzle_json = db.get_daily(today)
        if puzzle_json:
            # already exists, show summary
            bot.reply_to(m, "Today's Daily Challenge already exists. Use /daily_status or /new_daily to view.")
        else:
            # create seeded puzzle (use deterministic seed by day)
            random.seed(today)
            pool = ALL_WORDS[:]
            words = random.sample(pool, 6)
            # prepare a grid and placements for daily
            temp_session = GameSession(chat_id, mode="daily", is_hard=False, word_pool=words)
            puzzle = {"words": words, "grid": temp_session.grid, "placements": temp_session.placements}
            db.set_daily(today, json.dumps(puzzle))
            bot.reply_to(m, "Daily challenge created for today. Players can start it via /new_daily_play (or I will show it when someone asks).")
    elif cmd == "new_phrase":
        start_game_session(chat_id, user_id, mode="phrase")
        bot.reply_to(m, "Started Hidden Phrase mode.")
    else:
        bot.reply_to(m, "Unknown mode.")


# -------------------------
# Team join/start handlers
# -------------------------
@bot.message_handler(commands=["join_team"])
def cmd_join_team(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    name = m.from_user.first_name or m.from_user.username or "Player"
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session initialized. Use /new_team to initialize.")
        return
    session = games[chat_id]
    if not getattr(session, "join_phase", False):
        bot.reply_to(m, "Join phase is closed. Wait for admin to start the team battle.")
        return
    # simple auto-balance: put into smaller team
    a = session.teams["A"]
    b = session.teams["B"]
    if uid in a or uid in b:
        bot.reply_to(m, "You already joined a team.")
        return
    if len(a) <= len(b):
        a.add(uid)
        bot.reply_to(m, f"{name} joined Team A.")
    else:
        b.add(uid)
        bot.reply_to(m, f"{name} joined Team B.")


@bot.message_handler(commands=["start_team"])
def cmd_start_team(m):
    chat_id = m.chat.id
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session initialized.")
        return
    # only admin or owner
    if not db.is_admin(m.from_user.id) and not (OWNER_ID and m.from_user.id == OWNER_ID):
        bot.reply_to(m, "Only owner/admin can start the team battle.")
        return
    session = games[chat_id]
    session.join_phase = False
    # build a normal grid for team battle
    pool = ALL_WORDS[:]
    session._prepare_grid(pool)
    # send grid
    img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=False)
    caption = f"🏁 Team Battle started!\nTeam A: {len(session.teams['A'])} players\nTeam B: {len(session.teams['B'])} players\nFind words and score for your team!"
    sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
        InlineKeyboardButton("📊 Score", callback_data="game_score"),
    ))
    session.message_id = sent.message_id


# -------------------------
# Review & Issue handlers
# -------------------------
@bot.message_handler(commands=["review"])
def cmd_review(m):
    text = m.text.replace("/review", "").strip()
    if not text:
        bot.reply_to(m, "Usage: /review <your feedback>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player", text)
    bot.reply_to(m, "✅ Thank you for your review. Owner will see it.")
    # notify owner
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"📝 New review from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
        except Exception:
            logger.exception("Failed to notify owner of review")


# Owner review moderation
@bot.message_handler(commands=["list_reviews", "approve_review"])
def cmd_review_moderation(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    cmd = m.text.split()[0].lstrip("/")
    if cmd == "list_reviews":
        parts = m.text.split()
        mode = parts[1] if len(parts) > 1 else "pending"
        if mode == "all":
            rows = db.list_reviews(None)
        elif mode == "pending":
            rows = db.list_reviews(0)
        else:
            rows = db.list_reviews(None)
        if not rows:
            bot.reply_to(m, "No reviews found.")
            return
        txt = ""
        for r in rows:
            txt += f"ID:{r[0]} User:{r[2]} ({r[1]}) At:{r[4]} Approved:{r[5]}\n{textwrap_shorten(r[3], 120)}\n\n"
        # send as PM to owner (he's calling from owner account)
        bot.reply_to(m, txt[:4000])
    elif cmd == "approve_review":
        parts = m.text.split()
        if len(parts) < 2:
            bot.reply_to(m, "Usage: /approve_review <id>")
            return
        try:
            rid = int(parts[1])
            db.approve_review(rid)
            bot.reply_to(m, f"Review {rid} approved.")
        except Exception:
            bot.reply_to(m, "Operation failed.")


def textwrap_shorten(s: str, n: int):
    return (s[: n - 1] + "…") if len(s) > n else s


# -------------------------
# Addpoints & admin utilities
# -------------------------
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
    # find target id
    target_id = None
    try:
        if target.lstrip("-").isdigit():
            target_id = int(target)
        else:
            if not target.startswith("@"):
                target = "@" + target
            chat = bot.get_chat(target)
            target_id = chat.id
    except Exception:
        bot.reply_to(m, "Could not find user. They must have started the bot or have a public username.")
        return
    # ensure user
    db.register_user(target_id, "Player")
    if mode == "score":
        db.update_stats(target_id, score_delta=amount)
        bot.reply_to(m, f"Added {amount} to total_score of {target_id}")
    else:
        db.update_stats(target_id, hint_delta=amount)
        bot.reply_to(m, f"Added {amount} to hint balance of {target_id}")
    try:
        bot.send_message(target_id, f"💸 You received {amount} pts ({mode}) from the owner.")
    except Exception:
        pass


# -------------------------
# Broadcast
# -------------------------
@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return
    msg = parts[1]
    users = db.get_all_users()
    success = 0
    fail = 0
    for uid in users:
        try:
            bot.send_message(uid, msg)
            success += 1
        except:
            fail += 1
    bot.reply_to(m, f"Broadcast complete. Success: {success}, Fail: {fail}")


# -------------------------
# DEFINE command
# -------------------------
@bot.message_handler(commands=["define"])
def cmd_define(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /define <word>")
        return
    w = parts[1].strip()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=6)
        data = r.json()
        if isinstance(data, list) and data:
            meanings = data[0].get("meanings", [])
            if meanings:
                defs = meanings[0].get("definitions", [])
                if defs:
                    definition = defs[0].get("definition", "No definition")
                    example = defs[0].get("example", "")
                    txt = f"📚 <b>{html.escape(w)}</b>\n{html.escape(definition)}"
                    if example:
                        txt += f"\n\n<i>Example:</i> {html.escape(example)}"
                    bot.reply_to(m, txt)
                    return
        bot.reply_to(m, f"No definition found for {w}")
    except Exception:
        logger.exception("define error")
        bot.reply_to(m, "Error fetching definition.")


# -------------------------
# Guess processing (common)
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback_text_handler(m):
    """
    This handler will capture user natural text entries (like answering when ForceReply).
    We register next-step handlers for ForceReply flows in other places (registered via register_next_step_handler).
    If not in such flow, this is fallback; ignore or respond politely.
    """
    # do nothing unless it's a registered next_step in telebot — telebot handles registered steps automatically.
    # Provide helpful hint for users who typed something unexpected:
    txt = m.text.strip()
    if txt.startswith("/"):
        # unknown command
        if txt.split()[0].lower() == "/cmd":
            # handled by /cmd earlier
            return
        # else unknown command
        try:
            bot.reply_to(m, "Unknown command. Use the menu or /cmd to see available commands.")
        except:
            pass
    else:
        # ignore casual messages
        pass


# Telebot next step handler is used in callback flow (registered in callbacks). But we also create helpers:
def process_word_guess(msg):
    # This is used as a next-step handler when user pressed 'Found It' and a ForceReply was sent.
    # telebot will pass a Message object here.
    m = msg  # alias
    cid = m.chat.id
    if cid not in games:
        try:
            bot.reply_to(m, "❌ No active game in this chat.")
        except:
            pass
        return
    word = (m.text or "").strip().upper()
    if not word:
        return
    session = games[cid]
    uid = m.from_user.id
    user_name = m.from_user.first_name or m.from_user.username or "Player"
    last = session.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        try:
            bot.reply_to(m, f"⏳ Slow down! Wait {COOLDOWN} seconds between guesses.")
        except:
            pass
        return
    session.players_last_guess[uid] = now
    # try delete the user's message (tidy)
    try:
        bot.delete_message(cid, m.message_id)
    except:
        pass
    # handle modes
    if session.mode == "anagram":
        # check against anagrams
        found_word = None
        for item in session.anagrams:
            if item["word"].upper() == word:
                found_word = item["word"].upper()
                break
        if found_word:
            if found_word in session.found:
                bot.send_message(cid, f"⚠️ {found_word} already solved.")
                return
            session.found.add(found_word)
            pts = NORMAL_POINTS
            session.players_scores[uid] = session.players_scores.get(uid, 0) + pts
            db.update_stats(uid, score_delta=pts)
            bot.send_message(cid, f"✨ {user_name} solved {found_word} (+{pts} pts)")
            # check finish
            if len(session.found) == len(session.anagrams):
                end_game_session(cid, "win", uid)
        else:
            bot.send_message(cid, f"❌ {user_name} — {word} is not a valid anagram answer.")
        return

    # for grid-based modes
    if word in session.words:
        if word in session.found:
            bot.send_message(cid, f"⚠️ <b>{word}</b> is already found!")
            return
        session.found.add(word)
        session.last_activity = time.time()
        # scoring
        if len(session.found) == 1:
            points = FIRST_BLOOD_POINTS
        elif len(session.found) == len(session.words):
            points = FINISHER_POINTS
        else:
            points = NORMAL_POINTS
        prev = session.players_scores.get(uid, 0)
        session.players_scores[uid] = prev + points
        db.update_stats(uid, score_delta=points)
        try:
            reply = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(user_name)} found <code>{word}</code> (+{points} pts) 🎯")
            threading.Timer(4, lambda: safe_delete_message(cid, reply.message_id)).start()
        except:
            pass
        # regenerate image and replace old one
        try:
            img_bio = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
            sent_msg = None
            try:
                sent_msg = bot.send_photo(cid, img_bio, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {session.mode}\n"
                                                                f"⏱ Time Left: {(max(0, int(session.duration - (time.time() - session.start_time)))//60)}:{(max(0, int(session.duration - (time.time() - session.start_time)))%60):02d}\n\n"
                                                                f"<b>Words:</b>\n{session.get_hint_text()}"),
                                          reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                                                                                  InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                                                                                  InlineKeyboardButton("📊 Score", callback_data="game_score")))
            except Exception:
                # fallback via temp file
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                        tf.write(img_bio.getvalue())
                        temp_path = tf.name
                    with open(temp_path, "rb") as f:
                        sent_msg = bot.send_photo(cid, f, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {session.mode}\n"
                                                                  f"⏱ Time Left: {(max(0, int(session.duration - (time.time() - session.start_time)))//60)}:{(max(0, int(session.duration - (time.time() - session.start_time)))%60):02d}\n\n"
                                                                  f"<b>Words:</b>\n{session.get_hint_text()}"),
                                                  reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"),
                                                                                          InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                                                                                          InlineKeyboardButton("📊 Score", callback_data="game_score")))
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Failed to send updated grid image")
            # try delete previous image
            try:
                old = session.message_id
                if old:
                    safe_delete_message(cid, old)
            except Exception:
                pass
            try:
                if sent_msg:
                    session.message_id = sent_msg.message_id
            except Exception:
                logger.exception("Could not set new session.message_id")
        except Exception:
            logger.exception("Error regenerating grid image after found word")
        # if done
        if len(session.found) == len(session.words):
            end_game_session(cid, "win", uid)
    else:
        try:
            msg = bot.send_message(cid, f"❌ {html.escape(user_name)} — '{html.escape(word)}' is not in the list.")
            threading.Timer(3, lambda: safe_delete_message(cid, msg.message_id)).start()
        except Exception:
            pass


def safe_delete_message(chat_id: int, message_id: int):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# -------------------------
# End game wrapper
# -------------------------
def end_game_session(cid: int, reason: str, winner_id: Optional[int] = None):
    if cid not in games:
        return
    game = games[cid]
    game.active = False
    if reason == "win" and winner_id:
        try:
            winner_row = db.get_user(winner_id, "Player")
            db.update_stats(winner_id, win=True)
            db.record_game(cid, winner_id, game.mode)
            standings = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
            summary = ""
            for idx, (uid_score, pts) in enumerate(standings, 1):
                user = db.get_user(uid_score, "Player")
                summary += f"{idx}. {html.escape(user[1])} - {pts} pts\n"
            bot.send_message(cid, f"🏆 GAME OVER! MVP: {html.escape(winner_row[1])}\n\nSession Standings:\n{summary}\nType /new to play again.")
        except Exception:
            logger.exception("end_game win flow failed")
    elif reason == "timeout":
        try:
            found_count = len(game.found)
            remaining = [w for w in game.words if w not in game.found]
            standings = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
            summary = ""
            for idx, (uid_score, pts) in enumerate(standings, 1):
                user = db.get_user(uid_score, "Player")
                summary += f"{idx}. {html.escape(user[1])} - {pts} pts\n"
            bot.send_message(cid, f"⏰ TIME'S UP!\nFound: {found_count}/{len(game.words)}\nRemaining: {', '.join(remaining) if remaining else 'None'}\n\nStandings:\n{summary}")
        except Exception:
            logger.exception("end_game timeout flow failed")
    elif reason == "stopped":
        try:
            bot.send_message(cid, "🛑 Game stopped manually.")
        except Exception:
            pass
    # cleanup
    try:
        del games[cid]
    except Exception:
        pass


# -------------------------
# Health & run
# -------------------------
@app.route("/")
def index():
    return "Word Vortex Bot (v6.0) running"


if __name__ == "__main__":
    # start flask thread for health check
    def run_flask():
        port = int(os.environ.get("PORT", "5000"))
        app.run(host="0.0.0.0", port=port)

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    print("✅ Word Vortex Bot v6.0 starting...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            logger.exception("Polling error; restarting in 5s")
            time.sleep(5)
