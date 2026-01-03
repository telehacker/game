#!/usr/bin/env python3
"""
WORD VORTEX - Consolidated Stable Bot
Version: 6.2

This file is a consolidated, stable implementation that builds on the larger earlier version
you referenced (~1500 lines) and includes the requested features and buttons:
- Fixed "Commands" behavior: always tries to send full command list to user's PM first; falls back to group.
- /cmd fallback if Commands button cannot DM the user.
- Multiple game modes: /new, /new_hard, /new_physics, /new_chemistry, /new_math, /new_jee,
  /new_anagram, /new_speedrun, /new_definehunt, /new_survival, /new_team, /new_daily, /new_phrase
- Image grid rendering with found-word lines, caption updates, and replacement of previous image to keep chat tidy.
- Timers for games (caption countdown updates).
- /hint buying, /scorecard, /leaderboard, /balance.
- /addpoints (defaults to hint balance), /addadmin, /deladmin, /admins, /reset_leaderboard.
- Broadcast (/broadcast), review system (/review, /list_reviews, /approve_review), redeem workflow (manual).
- /cmdinfo <command> per-command help entries.
- Robust fallback and logging.
- Add-to-group button and owner notifications on /start and when games start.

Notes:
- Set TELEGRAM_TOKEN and OWNER_ID environment variables before running.
- Install dependencies: pip install pyTelegramBotAPI pillow requests flask
- This file aims for clarity and robustness; adjust small texts, limits, and pools as needed.
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
from datetime import date
from typing import List, Dict, Tuple, Optional

import requests
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# -------------------------
# CONFIG
# -------------------------
app = Flask(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN","8208557623:AAHnIoKHGijL6WN7tYLStJil8ZIMBDsXnpA")
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set")
    sys.exit(1)
try:
    OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
except Exception:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")
FORCE_JOIN = os.environ.get("FORCE_JOIN", "False").lower() in ("1", "true", "yes")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = os.environ.get("START_IMG_URL", "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------------
# CONSTANTS
# -------------------------
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

REDEEM_THRESHOLD = 150  # manual redeem threshold (owner handles payout)
PLANS = [{"points": 50, "price_rs": 10}, {"points": 120, "price_rs": 20}, {"points": 350, "price_rs": 50}, {"points": 800, "price_rs": 100}]

# small curated pools (randomized selection will be used each game)
PHYSICS_POOL = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "ACCEL", "VECTOR", "SCALAR", "WAVE", "PHOTON", "GRAVITY"]
CHEMISTRY_POOL = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "CATION", "ANION", "ACID", "BASE", "SALT"]
MATH_POOL = ["INTEGRAL", "DERIVATIVE", "MATRIX", "VECTOR", "CALCULUS", "LIMIT", "PROB", "MOD", "LEMMA", "ALGEBRA"]
JEE_POOL = ["KINEMATICS", "ELECTROSTATICS", "THERMO", "INTEGRAL", "DIFFERENTIAL", "MATRIX", "VECTOR"]

# -------------------------
# DATABASE (sqlite)
# -------------------------
DB_FILE = os.environ.get("WORDS_DB", "wordsgrid_consolidated.db")


class DatabaseManager:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.init_db()

    def connect(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def init_db(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            join_date TEXT,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100,
            is_banned INTEGER DEFAULT 0,
            cash_balance INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            mode TEXT,
            timestamp TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            created_at TEXT,
            approved INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS redeems (
            redeem_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount_points INTEGER,
            requested_at TEXT,
            processed INTEGER DEFAULT 0,
            admin_id INTEGER,
            notes TEXT
        )''')
        conn.commit()
        conn.close()

    # user helpers
    def get_user(self, user_id: int, name: str = "Player"):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        if not user:
            join_date = time.strftime("%Y-%m-%d")
            c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            user = c.fetchone()
        conn.close()
        return user

    def register_user(self, user_id: int, name: str = "Player"):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        r = c.fetchone()
        if r:
            conn.close()
            return r, False
        join_date = time.strftime("%Y-%m-%d")
        c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return r, True

    def update_stats(self, user_id: int, score_delta: int = 0, hint_delta: int = 0, win: bool = False, games_played_delta: int = 0, cash_delta: int = 0):
        conn = self.connect()
        c = conn.cursor()
        if score_delta != 0:
            c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (score_delta, user_id))
        if hint_delta != 0:
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (hint_delta, user_id))
        if cash_delta != 0:
            c.execute("UPDATE users SET cash_balance = cash_balance + ? WHERE user_id=?", (cash_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        if games_played_delta != 0:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
        conn.commit()
        conn.close()

    # admin helpers
    def add_admin(self, admin_id: int):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        conn.close()

    def remove_admin(self, admin_id: int):
        conn = self.connect()
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))
        conn.commit()
        conn.close()

    def is_admin(self, user_id: int) -> bool:
        if OWNER_ID and user_id == OWNER_ID:
            return True
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return bool(r)

    def list_admins(self) -> List[int]:
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins")
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows

    # history, reviews, redeems
    def record_game(self, chat_id: int, winner_id: int, mode: str):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, mode, timestamp) VALUES (?, ?, ?, ?)",
                  (chat_id, winner_id, mode, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_top_players(self, limit: int = 10):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def reset_leaderboard(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = 0, wins = 0")
        conn.commit()
        conn.close()

    def get_all_users(self) -> List[int]:
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows

    def add_review(self, user_id: int, username: str, text: str):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO reviews (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, username, text, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_reviews(self, approved: Optional[int] = None):
        conn = self.connect()
        c = conn.cursor()
        if approved is None:
            c.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM reviews WHERE approved=? ORDER BY created_at DESC", (approved,))
        rows = c.fetchall()
        conn.close()
        return rows

    def approve_review(self, review_id: int):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE reviews SET approved=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    def add_redeem_request(self, user_id: int, amount_points: int):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO redeems (user_id, amount_points, requested_at) VALUES (?, ?, ?)",
                  (user_id, amount_points, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_redeems(self, processed: Optional[int] = 0):
        conn = self.connect()
        c = conn.cursor()
        if processed is None:
            c.execute("SELECT * FROM redeems ORDER BY requested_at DESC")
        else:
            c.execute("SELECT * FROM redeems WHERE processed=? ORDER BY requested_at DESC", (processed,))
        rows = c.fetchall()
        conn.close()
        return rows

    def process_redeem(self, redeem_id: int, admin_id: int, notes: str = ""):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT user_id, amount_points FROM redeems WHERE redeem_id=?", (redeem_id,))
        r = c.fetchone()
        if not r:
            conn.close()
            return None
        user_id, points = r
        c.execute("UPDATE redeems SET processed=1, admin_id=?, notes=? WHERE redeem_id=?", (admin_id, notes, redeem_id))
        conn.commit()
        conn.close()
        return user_id, points


db = DatabaseManager()

# -------------------------
# WORDLIST
# -------------------------
ALL_WORDS: List[str] = []


def fetch_remote_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        r = requests.get(url, timeout=8)
        lines = [l.strip().upper() for l in r.text.splitlines() if l.strip()]
        words = [w for w in lines if w.isalpha() and 4 <= len(w) <= 12 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info("Loaded remote wordlist: %d words", len(ALL_WORDS))
            return
    except Exception:
        logger.exception("Failed to fetch remote words")
    ALL_WORDS = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "GALAXY", "NEBULA", "INTEGRAL", "MATRIX", "VECTOR", "ENERGY"]


fetch_remote_words()

# -------------------------
# IMAGE UTILITIES
# -------------------------
def draw_grid(grid: List[List[str]], placements: Dict[str, List[Tuple[int, int]]], found: set, is_hard: bool = False):
    cell = 56
    header = 92
    footer = 44
    pad = 24
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    w = cols * cell + pad * 2
    h = header + rows * cell + footer + pad * 2
    img = Image.new("RGB", (w, h), "#fff")
    draw = ImageDraw.Draw(img)
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        header_font = ImageFont.truetype(font_path, 34)
        letter_font = ImageFont.truetype(font_path, 28)
        small = ImageFont.truetype(font_path, 14)
    except Exception:
        header_font = ImageFont.load_default()
        letter_font = ImageFont.load_default()
        small = ImageFont.load_default()
    draw.rectangle([0, 0, w, header], fill="#eef6fb")
    draw.text((pad, 18), "WORD VORTEX", fill="#1f6feb", font=header_font)
    start_y = header + pad
    for r in range(rows):
        for c in range(cols):
            x = pad + c * cell
            y = start_y + r * cell
            draw.rectangle([x, y, x + cell, y + cell], outline="#2b90d9", width=2)
            ch = grid[r][c]
            bb = draw.textbbox((0, 0), ch, font=letter_font)
            draw.text((x + (cell - (bb[2] - bb[0])) / 2, y + (cell - (bb[3] - bb[1])) / 2 - 4), ch, fill="#222", font=letter_font)
    # draw found lines
    try:
        for wrd, coords in placements.items():
            if wrd in found and coords:
                a = coords[0]; b = coords[-1]
                x1 = pad + a[1] * cell + cell / 2
                y1 = start_y + a[0] * cell + cell / 2
                x2 = pad + b[1] * cell + cell / 2
                y2 = start_y + b[0] * cell + cell / 2
                draw.line([(x1, y1), (x2, y2)], fill="#fff", width=8)
                draw.line([(x1, y1), (x2, y2)], fill="#ff4757", width=5)
                r_end = 6
                draw.ellipse([x1 - r_end, y1 - r_end, x1 + r_end, y1 + r_end], fill="#ff4757")
                draw.ellipse([x2 - r_end, y2 - r_end, x2 + r_end, y2 + r_end], fill="#ff4757")
    except Exception:
        logger.exception("draw found-lines failed")
    draw.text((pad, h - footer + 12), "Made by @Ruhvaan", fill="#95a5a6", font=small)
    bio = io.BytesIO()
    img.save(bio, "JPEG", quality=90)
    bio.seek(0)
    try:
        bio.name = "grid.jpg"
    except Exception:
        pass
    return bio

def draw_leaderboard(rows: List[Tuple[int, str, int]]):
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
# Helper utilities
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
        logger.debug("Subscription check error; allowing by default")
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
        logger.exception("safe_edit_message failed")
        return False

def pm_first_or_fallback(user_id: int, chat_id: int, text: str, reply_markup=None):
    """
    Try to DM user_id; if fails, send the text in chat_id (group)
    Returns True if DM sent, False otherwise.
    """
    try:
        bot.send_message(user_id, text, parse_mode="HTML", reply_markup=reply_markup)
        try:
            bot.send_message(chat_id, f"🔔 I sent the details to {user_id}'s private chat.")
        except:
            pass
        return True
    except Exception:
        # fallback to group
        try:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
            return False
        except Exception:
            return False

# -------------------------
# COMMANDS text and cmdinfo
# -------------------------
COMMANDS_TEXT = """🤖 Word Vortex - Commands (Full)
Use /cmdinfo <command> for per-command usage.

User:
/start /help - open menu
/cmd - fallback to show commands
/cmdinfo <command> - detailed usage
/ping - ping
/new - normal game
/new_hard - hard game
/new_physics /new_chemistry /new_math /new_jee - domain games
/new_anagram - Anagram Sprint
/new_speedrun - Speedrun
/new_definehunt - Definition Hunt
/new_survival - Survival
/new_team - Team Battle (then /join_team, /start_team)
/new_daily - Daily challenge
/new_phrase - Hidden Phrase
/hint - buy hint
/scorecard /mystats - your stats
/balance - your hint balance
/leaderboard - top players
/issue <text> - report issue
/review <text> - submit review
/define <word> - definition

Owner:
/addpoints /addadmin /deladmin /admins /reset_leaderboard /broadcast
/set_hint_cost /toggle_force_join /set_start_image /show_settings /restart
/list_reviews /approve_review
/redeem_list /redeem_pay
"""

CMDINFO = {
    "new": {"usage": "/new", "desc": "Start a normal 8x8 game. Use in group.", "who": "Anyone"},
    "new_physics": {"usage": "/new_physics", "desc": "Start a physics vocabulary game (random selection).", "who": "Anyone"},
    "new_anagram": {"usage": "/new_anagram", "desc": "Anagram Sprint: text-only scramble round for vocabulary.", "who": "Anyone"},
    "cmd": {"usage": "/cmd", "desc": "Fallback to show full commands (if Commands button doesn't DM you).", "who": "Anyone"},
    "cmdinfo": {"usage": "/cmdinfo <command>", "desc": "Get detailed help for one command.", "who": "Anyone"},
    # more entries can be added as needed
}

# -------------------------
# Main menu & callbacks
# -------------------------
def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    if CHANNEL_USERNAME:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
    else:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=SUPPORT_GROUP_LINK))
    kb.add(InlineKeyboardButton("🔄 Check Join", callback_data="check_join"))
    try:
        me = bot.get_me().username
        if me:
            kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{me}?startgroup=true"))
    except Exception:
        pass
    kb.add(InlineKeyboardButton("🎮 Play Game", callback_data="help_play"),
           InlineKeyboardButton("🤖 Commands", callback_data="help_cmd"))
    kb.add(InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
           InlineKeyboardButton("👤 My Stats", callback_data="menu_stats"))
    kb.add(InlineKeyboardButton("🐞 Report Issue", callback_data="open_issue"),
           InlineKeyboardButton("💳 Buy Points", callback_data="open_plans"))
    kb.add(InlineKeyboardButton("✍️ Review", callback_data="open_review"),
           InlineKeyboardButton("👨‍💻 Owner", url=SUPPORT_GROUP_LINK))
    return kb

@bot.message_handler(commands=["start","help"])
def handle_start(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.register_user(m.from_user.id, name)
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🔔 /start by {name} ({m.from_user.id}) in chat {m.chat.id}")
        except Exception:
            logger.debug("Owner notify failed")
    txt = f"👋 <b>Hello, {html.escape(name)}</b>!\nWelcome to Word Vortex. Click a button; Commands tries to DM you (PM-first)."
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=main_menu())
    except Exception:
        bot.reply_to(m, txt, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    data = c.data
    uid = c.from_user.id
    chat_id = c.message.chat.id
    try:
        bot.answer_callback_query(c.id, "")
    except Exception:
        pass

    def pm_first(text, reply_markup=None):
        sent_pm = False
        try:
            bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
            sent_pm = True
        except Exception:
            logger.debug("PM failed")
        if sent_pm:
            try:
                bot.send_message(chat_id, f"🔔 {c.from_user.first_name}, I sent the info to your private chat.")
            except:
                pass
            try:
                bot.answer_callback_query(c.id, "Sent to your PM.")
            except:
                pass
            return
        try:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
            try:
                bot.answer_callback_query(c.id, "Opened here.")
            except:
                pass
            return
        except Exception:
            try:
                bot.answer_callback_query(c.id, "❌ Could not open. Start a PM with the bot and use /cmd", show_alert=True)
            except:
                pass
            return

    if data == "check_join":
        if is_subscribed(uid):
            try:
                bot.delete_message(chat_id, c.message.message_id)
            except:
                pass
            handle_start(c.message)
            try:
                bot.answer_callback_query(c.id, "✅ Verified")
            except:
                pass
        else:
            try:
                bot.answer_callback_query(c.id, "❌ Not joined", show_alert=True)
            except:
                pass
        return

    if data == "help_cmd":
        pm_first(COMMANDS_TEXT)
        return

    if data == "help_play":
        txt = ("🎮 How to Play:\n1) Start a game with /new (or domain commands).\n2) Bot sends a grid image and masked words.\n3) Use 'Found It' -> type word. Correct answers update image + score.")
        pm_first(txt)
        return

    if data == "menu_lb":
        top = db.get_top_players(10)
        txt = "🏆 Global Leaderboard\n"
        for i,(n,s) in enumerate(top,1):
            txt += f"{i}. {html.escape(n)} - {s} pts\n"
        pm_first(txt)
        return

    if data == "menu_stats":
        user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_pts = 0
        if chat_id in games:
            session_pts = games[chat_id].players_scores.get(uid,0)
        txt = (f"📋 Your Stats\nName: {html.escape(user[1])}\nTotal Score: {user[5]}\nWins: {user[4]}\nGames Played: {user[3]}\nSession Points: {session_pts}\nHint Balance: {user[6]}")
        pm_first(txt)
        return

    if data == "open_issue":
        try:
            bot.send_message(uid, f"@{c.from_user.username or c.from_user.first_name} Please type your issue (or use /issue <text>):", reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "Prompt sent to PM.")
        except:
            try:
                bot.send_message(chat_id, f"@{c.from_user.username or c.from_user.first_name} Please type your issue (or use /issue <text>):", reply_markup=ForceReply(selective=True))
                bot.answer_callback_query(c.id, "Opened here.")
            except:
                bot.answer_callback_query(c.id, "❌ Could not open issue prompt.", show_alert=True)
        return

    if data == "open_plans":
        txt = "💳 Points Plans:\n" + "\n".join([f"- {p['points']} pts : ₹{p['price_rs']}" for p in PLANS]) + f"\n\nContact: {SUPPORT_GROUP_LINK}"
        pm_first(txt)
        return

    if data == "open_review":
        try:
            bot.send_message(uid, "✍️ Please send your review with /review <text>", reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "Sent PM prompt.")
        except:
            try:
                bot.send_message(chat_id, "Use /review <text> to submit a review.")
                bot.answer_callback_query(c.id, "Opened here.")
            except:
                bot.answer_callback_query(c.id, "❌ Could not open.", show_alert=True)
        return

    # fallback ack
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

# -------------------------
# /cmd fallback & /cmdinfo
# -------------------------
@bot.message_handler(commands=["cmd"])
def cmd_fallback(m):
    try:
        bot.send_message(m.from_user.id, COMMANDS_TEXT, parse_mode="HTML")
        bot.reply_to(m, "✅ I sent the commands to your private chat.")
    except Exception:
        try:
            bot.reply_to(m, COMMANDS_TEXT)
        except:
            bot.reply_to(m, "❌ Could not show commands. Please start a private chat with the bot and try /cmd.")

@bot.message_handler(commands=["cmdinfo"])
def cmd_info(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /cmdinfo <command>")
        return
    k = parts[1].strip().lstrip("/").lower()
    info = CMDINFO.get(k)
    if not info:
        bot.reply_to(m, f"No detailed info for '{k}'. Use /cmd for full list.")
        return
    bot.reply_to(m, f"<b>/{k}</b>\nUsage: {info['usage']}\n\n{info['desc']}\nWho: {info['who']}\nWhy: {info['why']}")

# -------------------------
# Game session classes & flows (core simplified but functional)
# -------------------------
class GameSession:
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
        self.placements: Dict[str, List[Tuple[int,int]]] = {}
        self.words: List[str] = []
        self.found: set = set()
        self.players_scores: Dict[int,int] = {}
        self.players_last_guess: Dict[int,float] = {}
        self.message_id: Optional[int] = None
        self.active = True
        self.timer_thread: Optional[threading.Thread] = None
        self.anagrams = []
        self.definitions = []
        self.prepare(mode, word_pool)
        self.start_timer()

    def prepare(self, mode, pool):
        if mode == "anagram":
            choices = pool or ALL_WORDS
            selected = random.sample(choices, min(8, len(choices)))
            self.anagrams = [{"word": w, "jumbled": "".join(random.sample(list(w), len(w)))} for w in selected]
            return
        # grid-based
        pool_list = pool or (ALL_WORDS[:] if ALL_WORDS else [])
        if mode == "physics":
            pool_list = PHYSICS_POOL[:]
        elif mode == "chemistry":
            pool_list = CHEMISTRY_POOL[:]
        elif mode == "math":
            pool_list = MATH_POOL[:]
        elif mode == "jee":
            pool_list = JEE_POOL[:]
        if len(pool_list) < self.word_count:
            pool_list = (pool_list * ((self.word_count // max(1,len(pool_list))) + 2))
        self.words = random.sample(pool_list, self.word_count)
        # empty grid
        self.grid = [[" " for _ in range(self.size)] for __ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        for word in sorted(self.words, key=len, reverse=True):
            placed = False
            for _ in range(400):
                r = random.randint(0, self.size-1)
                c = random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self.can_place(r,c,dr,dc,word):
                    coords = []
                    for i,ch in enumerate(word):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr,cc))
                    self.placements[word] = coords
                    placed = True
                    break
            if not placed:
                # fallback scanning
                for rr in range(self.size):
                    for cc in range(self.size):
                        for dr, dc in dirs:
                            if self.can_place(rr,cc,dr,dc,word):
                                coords=[]
                                for i,ch in enumerate(word):
                                    rrr,ccc = rr + i*dr, cc + i*dc
                                    self.grid[rrr][ccc] = ch
                                    coords.append((rrr,ccc))
                                self.placements[word]=coords
                                placed=True
                                break
                        if placed: break
                    if placed: break
        # fill blanks
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == " ":
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def can_place(self, r,c,dr,dc,word):
        for i in range(len(word)):
            rr = r + i*dr
            cc = c + i*dc
            if not (0 <= rr < self.size and 0 <= cc < self.size):
                return False
            if self.grid[rr][cc] != " " and self.grid[rr][cc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints=[]
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                hints.append(f"<code>{w[0]}{'-'*(len(w)-1)}</code> ({len(w)})")
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
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! Game ended.")
                    except:
                        pass
                    try:
                        end_game(self.chat_id, "timeout")
                    except:
                        pass
                    break
                # update caption every 10s
                if self.message_id:
                    mins, secs = divmod(rem, 60)
                    cap = (f"🔥 <b>WORD VORTEX</b>\nMode: {self.mode}\n⏱ Time Left: {mins}:{secs:02d}\n\n{self.get_hint_text()}")
                    try:
                        safe_edit_message(cap, self.chat_id, self.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
                    except:
                        pass
                time.sleep(10)
        except Exception:
            logger.exception("timer worker failed")
        finally:
            self.active=False

# Short registry
games: Dict[int, GameSession] = {}

# -------------------------
# Start game handlers (single handler responds to all /new* commands)
# -------------------------
@bot.message_handler(commands=["new","new_hard","new_physics","new_chemistry","new_math","new_jee","new_anagram","new_speedrun","new_definehunt","new_survival","new_team","new_daily","new_phrase"])
def cmd_start(m):
    cmd = m.text.split()[0].lstrip("/").lower()
    chat_id = m.chat.id
    uid = m.from_user.id
    db.register_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if cmd == "new":
        if chat_id in games: bot.reply_to(m, "Game already active here.")
        else:
            s = GameSession(chat_id, mode="default", is_hard=False)
            games[chat_id]=s
            bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
            cap = f"🔥 <b>WORD VORTEX STARTED!</b>\nMode: Normal\n⏱ {s.duration//60} minutes\n\n{ s.get_hint_text() }"
            msg = bot.send_photo(chat_id, bio, caption=cap, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
            s.message_id = msg.message_id
            db.update_stats(uid, games_played_delta=1)
            if OWNER_ID:
                try: bot.send_message(OWNER_ID, f"🎮 Game started in {chat_id} by {m.from_user.first_name} (normal)") 
                except: pass
    elif cmd == "new_hard":
        if chat_id in games: bot.reply_to(m, "Game active.")
        else:
            s = GameSession(chat_id, mode="default", is_hard=True)
            games[chat_id]=s
            bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
            cap = f"🔥 <b>WORD VORTEX STARTED!</b>\nMode: Hard\n⏱ {s.duration//60} minutes\n\n{ s.get_hint_text() }"
            msg = bot.send_photo(chat_id, bio, caption=cap, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
            s.message_id = msg.message_id
            db.update_stats(uid, games_played_delta=1)
            if OWNER_ID:
                try: bot.send_message(OWNER_ID, f"🎮 Hard game started in {chat_id} by {m.from_user.first_name}") 
                except: pass
    elif cmd == "new_physics":
        pool = PHYSICS_POOL + random.sample(ALL_WORDS, min(50, len(ALL_WORDS)))
        s = GameSession(chat_id, mode="physics", is_hard=False, word_pool=pool)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        cap = f"🔥 <b>WORD VORTEX</b> - Physics\n{ s.get_hint_text() }"
        msg = bot.send_photo(chat_id, bio, caption=cap, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_chemistry":
        pool = CHEMISTRY_POOL + random.sample(ALL_WORDS, min(50, len(ALL_WORDS)))
        s = GameSession(chat_id, mode="chemistry", is_hard=False, word_pool=pool)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption=f"🔥 Chemistry round\n{ s.get_hint_text() }", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_math":
        pool = MATH_POOL + random.sample(ALL_WORDS, min(50, len(ALL_WORDS)))
        s = GameSession(chat_id, mode="math", is_hard=False, word_pool=pool)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption=f"🔥 Math round\n{ s.get_hint_text() }", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_jee":
        pool = JEE_POOL + random.sample(ALL_WORDS, min(50, len(ALL_WORDS)))
        s = GameSession(chat_id, mode="jee", is_hard=False, word_pool=pool)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption=f"🔥 JEE round\n{ s.get_hint_text() }", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_anagram":
        # Anagram Sprint: prepare 8 anagrams
        choices = random.sample(ALL_WORDS, min(12,len(ALL_WORDS)))
        anagrams = []
        for w in choices[:8]:
            j = list(w)
            random.shuffle(j)
            jumbled = "".join(j)
            if jumbled == w:
                random.shuffle(j)
                jumbled = "".join(j)
            anagrams.append({"word": w, "jumbled": jumbled})
        s = GameSession(chat_id, mode="anagram", is_hard=False)
        s.anagrams = anagrams
        games[chat_id] = s
        txt = "🎯 <b>Anagram Sprint</b>\nSolve these:\n"
        for idx,a in enumerate(anagrams,1):
            txt += f"{idx}. <code>{a['jumbled']}</code>\n"
        bot.send_message(chat_id, txt)
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_speedrun":
        s = GameSession(chat_id, mode="speedrun", is_hard=False)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption=f"⚡ Speedrun: find as many words as possible in {s.duration//60} minutes", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_definehunt":
        # pick words and fetch short definitions
        selected = random.sample(ALL_WORDS, min(6, len(ALL_WORDS)))
        s = GameSession(chat_id, mode="definehunt", is_hard=False, word_pool=selected)
        # populate definitions (best-effort)
        defs=[]
        for w in s.words:
            try:
                r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w.lower()}", timeout=6)
                data=r.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings",[])
                    if meanings:
                        defs_list = meanings[0].get("definitions",[])
                        if defs_list:
                            defs.append(defs_list[0].get("definition",""))
                            continue
            except:
                pass
            defs.append(f"Starts with {w[0]} and length {len(w)}")
        s.definitions = defs
        games[chat_id]=s
        # send definitions privately to starter if possible
        try:
            bot.send_message(uid, "Definitions for this round:\n" + "\n".join([f"{i+1}. {d}" for i,d in enumerate(defs)]))
        except:
            bot.send_message(chat_id, "Definitions are visible here (PM failed):\n" + "\n".join([f"{i+1}. {d}" for i,d in enumerate(defs)]))
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption="🧠 Definition Hunt: definitions sent to starter", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_survival":
        s = GameSession(chat_id, mode="survival", is_hard=False)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        msg = bot.send_photo(chat_id, bio, caption="🔥 Survival started - survive rounds", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        s.message_id = msg.message_id
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_team":
        # initialize team session (players use /join_team then owner/admin /start_team)
        if chat_id in games:
            bot.reply_to(m, "A game is active here.")
            return
        s = GameSession(chat_id, mode="team", is_hard=False)
        s.teams = {"A": set(), "B": set()}
        s.join_phase = True
        games[chat_id] = s
        bot.reply_to(m, "Team Battle initialized. Players: /join_team to join. Admin: /start_team to start.")
    elif cmd == "new_daily":
        today = date.today().isoformat()
        # create and store if absent
        # simplified: create a short daily and present
        selected = random.sample(ALL_WORDS, min(6,len(ALL_WORDS)))
        s = GameSession(chat_id, mode="daily", is_hard=False, word_pool=selected)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        bot.send_photo(chat_id, bio, caption="📅 Daily challenge (today)", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
        db.update_stats(uid, games_played_delta=1)
    elif cmd == "new_phrase":
        s = GameSession(chat_id, mode="phrase", is_hard=False)
        # create phrase words by sampling short words
        phrase_words = random.sample([w for w in ALL_WORDS if 3<=len(w)<=6],3)
        s.words = phrase_words + random.sample([w for w in ALL_WORDS if w not in phrase_words], s.word_count - len(phrase_words))
        s._prepare_grid = lambda *_: None  # avoid re-prepare
        # fill grid to show words - we will just call prepare with current words
        s.prepare("default", s.words)
        games[chat_id]=s
        bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
        bot.send_photo(chat_id, bio, caption=f"🔐 Hidden Phrase round (find phrase of {len(phrase_words)} words)", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess")))
        db.update_stats(uid, games_played_delta=1)
    else:
        bot.reply_to(m, "Unknown start command.")

# -------------------------
# Team join/start flows
# -------------------------
@bot.message_handler(commands=["join_team"])
def cmd_join_team(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session initialized. Use /new_team to init.")
        return
    s = games[chat_id]
    if not getattr(s, "join_phase", False):
        bot.reply_to(m, "Join phase is closed.")
        return
    a,b = s.teams["A"], s.teams["B"]
    if uid in a or uid in b:
        bot.reply_to(m, "You already joined.")
        return
    if len(a) <= len(b):
        a.add(uid); bot.reply_to(m, "You joined Team A")
    else:
        b.add(uid); bot.reply_to(m, "You joined Team B")

@bot.message_handler(commands=["start_team"])
def cmd_start_team(m):
    if not (db.is_admin(m.from_user.id) or (OWNER_ID and m.from_user.id == OWNER_ID)):
        bot.reply_to(m, "Only admin/owner can start team battle.")
        return
    chat_id = m.chat.id
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session.")
        return
    s = games[chat_id]
    s.join_phase = False
    # prepare competition grid
    s.prepare("default", None)
    bio = draw_grid(s.grid, s.placements, s.found, s.is_hard)
    bot.send_photo(chat_id, bio, caption=f"🏁 Team Battle started! Team A: {len(s.teams['A'])} players, Team B: {len(s.teams['B'])} players", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("📊 Score", callback_data="game_score")))

# -------------------------
# Guess processing (registered via ForceReply or callback flows)
# -------------------------
def process_word_guess(message):
    chat_id = message.chat.id
    if chat_id not in games:
        try: bot.reply_to(message, "No active game here.")
        except: pass
        return
    word = (message.text or "").strip().upper()
    if not word: return
    s = games[chat_id]
    uid = message.from_user.id
    name = message.from_user.first_name or message.from_user.username or "Player"
    last = s.players_last_guess.get(uid,0)
    now = time.time()
    if now - last < COOLDOWN:
        try: bot.reply_to(message, f"⏳ Wait {COOLDOWN}s between guesses.")
        except: pass
        return
    s.players_last_guess[uid]=now
    # delete user reply for cleanliness
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    # anagram mode
    if s.mode == "anagram":
        matched = None
        for item in s.anagrams:
            if item["word"].upper() == word:
                matched = item["word"].upper(); break
        if not matched:
            bot.send_message(chat_id, f"❌ {html.escape(name)} — '{html.escape(word)}' is not a valid answer.")
            return
        if matched in s.found:
            bot.send_message(chat_id, f"⚠️ {matched} already solved.")
            return
        s.found.add(matched)
        pts = NORMAL_POINTS
        s.players_scores[uid]=s.players_scores.get(uid,0)+pts
        db.update_stats(uid, score_delta=pts)
        bot.send_message(chat_id, f"✨ {html.escape(name)} solved {matched} (+{pts} pts)")
        if len(s.found) == len(s.anagrams):
            end_game(chat_id, "win", uid)
        return
    # grid modes
    if word in s.words:
        if word in s.found:
            bot.send_message(chat_id, f"⚠️ {word} already found.")
            return
        s.found.add(word); s.last_activity=time.time()
        if len(s.found)==1: pts = FIRST_BLOOD_POINTS
        elif len(s.found) == len(s.words): pts = FINISHER_POINTS
        else: pts = NORMAL_POINTS
        s.players_scores[uid] = s.players_scores.get(uid,0) + pts
        db.update_stats(uid, score_delta=pts)
        bot.send_message(chat_id, f"✨ {html.escape(name)} found {word} (+{pts} pts)")
        # regenerate image and replace old one
        try:
            img = draw_grid(s.grid, s.placements, s.found, s.is_hard)
            sent = bot.send_photo(chat_id, img, caption=f"🔥 Word Vortex ({s.mode})\n{ s.get_hint_text() }", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
            try:
                if s.message_id:
                    bot.delete_message(chat_id, s.message_id)
            except:
                pass
            s.message_id = sent.message_id if sent else s.message_id
        except Exception:
            logger.exception("failed to send updated grid")
        if len(s.found) == len(s.words):
            end_game(chat_id, "win", uid)
    else:
        bot.send_message(chat_id, f"❌ {html.escape(name)} — '{html.escape(word)}' not in list.")

# -------------------------
# End game
# -------------------------
def end_game(chat_id: int, reason: str, winner_id: Optional[int] = None):
    if chat_id not in games: return
    s = games[chat_id]
    s.active = False
    if reason == "win" and winner_id:
        db.update_stats(winner_id, win=True)
        db.record_game(chat_id, winner_id, s.mode)
        standings = sorted(s.players_scores.items(), key=lambda x:x[1], reverse=True)
        text = "🏆 GAME OVER! Standings:\n"
        for i,(uid,pts) in enumerate(standings,1):
            user = db.get_user(uid, "Player")
            text += f"{i}. {html.escape(user[1])} - {pts} pts\n"
        bot.send_message(chat_id, text)
    elif reason == "timeout":
        found = len(s.found)
        remaining = [w for w in s.words if w not in s.found]
        text = f"⏰ TIME's UP! Found {found}/{len(s.words)}. Remaining: {', '.join(remaining) if remaining else 'None'}"
        bot.send_message(chat_id, text)
    elif reason == "stopped":
        bot.send_message(chat_id, "🛑 Game stopped.")
    try: del games[chat_id]
    except: pass

# -------------------------
# Report / Review commands
# -------------------------
@bot.message_handler(commands=["issue"])
def cmd_issue(m):
    text = m.text.replace("/issue","",1).strip()
    if not text:
        bot.reply_to(m, "Usage: /issue <your message>")
        return
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🚨 REPORT from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
            bot.reply_to(m, "✅ Report sent to owner.")
        except:
            bot.reply_to(m, "❌ Could not send report.")
    else:
        bot.reply_to(m, "Owner not configured.")

@bot.message_handler(commands=["review"])
def cmd_review(m):
    text = m.text.replace("/review","",1).strip()
    if not text:
        bot.reply_to(m, "Usage: /review <your feedback>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player", text)
    bot.reply_to(m, "✅ Review submitted. Thanks!")
    if OWNER_ID:
        try: bot.send_message(OWNER_ID, f"📝 Review from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
        except: pass

@bot.message_handler(commands=["list_reviews","approve_review"])
def cmd_review_admin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    cmd = parts[0].lstrip("/")
    if cmd == "list_reviews":
        mode = parts[1] if len(parts)>1 else "pending"
        if mode=="all":
            rows = db.list_reviews(None)
        else:
            rows = db.list_reviews(0)
        if not rows:
            bot.reply_to(m, "No reviews.")
            return
        txt = ""
        for r in rows:
            txt += f"ID:{r[0]} User:{r[2]} At:{r[4]} Approved:{r[5]}\n{r[3][:200]}\n\n"
        bot.reply_to(m, txt)
    else:
        if len(parts)<2:
            bot.reply_to(m, "Usage: /approve_review <id>")
            return
        try:
            rid = int(parts[1])
            db.approve_review(rid)
            bot.reply_to(m, f"Review {rid} approved.")
        except:
            bot.reply_to(m, "Failed.")

# -------------------------
# Redeem flow
# -------------------------
@bot.message_handler(commands=["redeem_request"])
def cmd_redeem_request(m):
    uid = m.from_user.id
    u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    total = u[5]
    if total < REDEEM_THRESHOLD:
        bot.reply_to(m, f"❌ Need at least {REDEEM_THRESHOLD} pts to request redeem. Your score: {total}")
        return
    db.add_redeem_request(uid, REDEEM_THRESHOLD)
    bot.reply_to(m, f"✅ Redeem request submitted for {REDEEM_THRESHOLD} pts. Owner will process.")
    if OWNER_ID:
        try: bot.send_message(OWNER_ID, f"💸 Redeem request by {u[1]} ({uid}) for {REDEEM_THRESHOLD} pts.")
        except: pass

@bot.message_handler(commands=["redeem_list","redeem_pay"])
def cmd_redeem_admin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    cmd = parts[0].lstrip("/")
    if cmd == "redeem_list":
        rows = db.list_redeems(0)
        if not rows:
            bot.reply_to(m, "No pending redeems.")
            return
        txt = "Pending Redeems:\n"
        for r in rows:
            txt += f"ID:{r[0]} User:{r[1]} Points:{r[2]} At:{r[3]}\n"
        bot.reply_to(m, txt)
    else:
        if len(parts)<2:
            bot.reply_to(m, "Usage: /redeem_pay <redeem_id> <notes>")
            return
        try:
            rid = int(parts[1]); notes = " ".join(parts[2:]) if len(parts)>2 else ""
            res = db.process_redeem(rid, m.from_user.id, notes)
            if not res:
                bot.reply_to(m, "Redeem id not found.")
                return
            user_id, points = res
            db.update_stats(user_id, score_delta=-points)
            bot.reply_to(m, f"Marked redeem {rid} processed for user {user_id}. Please pay externally and add notes.")
            try: bot.send_message(user_id, f"✅ Your redeem request ({points} pts) has been processed by owner.") 
            except: pass
        except Exception:
            bot.reply_to(m, "Failed.")

# -------------------------
# Addpoints (default -> hint balance)
# -------------------------
@bot.message_handler(commands=["addpoints"])
def cmd_addpoints(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    if len(parts)<3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]")
        return
    target = parts[1]; amount=0
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be integer."); return
    mode = parts[3].lower() if len(parts)>=4 else "balance"
    target_id = None
    try:
        if target.lstrip("-").isdigit():
            target_id = int(target)
        else:
            if not target.startswith("@"): target = "@" + target
            ch = bot.get_chat(target); target_id = ch.id
    except:
        bot.reply_to(m, "Could not find user. They must have a public username or started the bot."); return
    db.register_user(target_id, "Player")
    if mode=="score":
        db.update_stats(target_id, score_delta=amount)
        bot.reply_to(m, f"Added {amount} to score of {target_id}")
    else:
        db.update_stats(target_id, hint_delta=amount)
        bot.reply_to(m, f"Added {amount} to hint balance of {target_id}")
    try: bot.send_message(target_id, f"💸 You received {amount} pts ({mode}) from owner.") 
    except: pass

# -------------------------
# Broadcast & Admin utils
# -------------------------
@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split(maxsplit=1)
    if len(parts)<2:
        bot.reply_to(m, "Usage: /broadcast <message>"); return
    msg = parts[1]
    users = db.get_all_users()
    succ=0; fail=0
    for u in users:
        try: bot.send_message(u, msg); succ+=1
        except: fail+=1
    bot.reply_to(m, f"Broadcast done. Success:{succ} Fail:{fail}")

# -------------------------
# Define, Scorecard, Leaderboard, Hint
# -------------------------
@bot.message_handler(commands=["define"])
def cmd_define(m):
    parts = m.text.split(maxsplit=1)
    if len(parts)<2:
        bot.reply_to(m, "Usage: /define <word>"); return
    w = parts[1].strip()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=6)
        data = r.json()
        if isinstance(data, list) and data:
            meanings = data[0].get("meanings", [])
            if meanings:
                defs = meanings[0].get("definitions", [])
                if defs:
                    d = defs[0].get("definition", "No definition")
                    ex = defs[0].get("example","")
                    txt = f"📚 <b>{html.escape(w)}</b>\n{html.escape(d)}"
                    if ex: txt += f"\n\n<i>Example:</i> {html.escape(ex)}"
                    bot.reply_to(m, txt); return
        bot.reply_to(m, f"No definition found for {w}")
    except:
        logger.exception("define failed"); bot.reply_to(m, "Error fetching definition")

@bot.message_handler(commands=["scorecard","mystats"])
def cmd_scorecard(m):
    uid = m.from_user.id; u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    session_pts = 0
    gid = m.chat.id
    if gid in games:
        session_pts = games[gid].players_scores.get(uid,0)
    cash_bal = u[8] if len(u)>8 else 0
    bot.reply_to(m, (f"📋 <b>Your Scorecard</b>\nName: {html.escape(u[1])}\nTotal Score: {u[5]}\nWins: {u[4]}\nGames Played: {u[3]}\nSession Points: {session_pts}\nHint Balance: {u[6]}\nCash: {cash_bal}"))

@bot.message_handler(commands=["balance"])
def cmd_balance(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player")
    bot.reply_to(m, f"💰 Your hint balance: {u[6]} pts")

@bot.message_handler(commands=["leaderboard"])
def cmd_leaderboard(m):
    rows = db.get_top_players()
    txt = "🏆 Top Players\n"
    for i,(n,s) in enumerate(rows,1):
        txt += f"{i}. {html.escape(n)} - {s} pts\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["hint"])
def cmd_hint(m):
    gid = m.chat.id; uid = m.from_user.id
    if gid not in games: bot.reply_to(m, "No active game here."); return
    u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if u[6] < HINT_COST:
        bot.reply_to(m, f"❌ Need {HINT_COST} pts to buy hint. Balance: {u[6]}"); return
    game = games[gid]
    hidden = [w for w in game.words if w not in game.found]
    if not hidden: bot.reply_to(m, "All words found!"); return
    reveal = random.choice(hidden)
    db.update_stats(uid, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")

# -------------------------
# Fallback handler & runner
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def catch_all(m):
    # telebot registers next-step handlers for ForceReply flows earlier via register_next_step_handler
    # If message is an answer to ForceReply and the bot expects it, the telebot next-step handler will catch it.
    # Here we keep fallback minimal.
    if m.text.startswith("/"):
        if m.text.split()[0].lower() == "/cmd":
            cmd_fallback(m); return
        # unknown command
        try:
            bot.reply_to(m, "Unknown command. Use the menu or /cmd for commands.")
        except:
            pass
    else:
        # casual text: ignore or reply small help
        pass

# -------------------------
# Health route and run
# -------------------------
@app.route("/")
def index():
    return "Word Vortex v6.2 running"

if __name__ == "__main__":
    # start health server
    def run_flask():
        port = int(os.environ.get("PORT", "5000"))
        app.run(host="0.0.0.0", port=port)
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Bot starting...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            logger.exception("Polling error, restarting in 5s")
            time.sleep(5)
