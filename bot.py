#!/usr/bin/env python3
"""
WORD VORTEX BOT - COMPLETE PREMIUM EDITION v6.5
✨ All Features + Premium Glow + Fixed Commands + Redeem System
Created: January 2026
"""

import os
import sys
import time
import html
import io
import random
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

TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHZzgByv218uShEzAHBtGjpCJ8_cedldVk")
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN environment variable not set.")
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

# Gameplay constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

PHYSICS_WORDS = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "ACCEL", "VECTOR", "SCALAR", "WAVE", "PHOTON", "GRAVITY", "INERTIA", "TORQUE", "POWER"]
CHEMISTRY_WORDS = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "CATION", "ANION", "ACID", "BASE", "SALT", "OXIDE", "ESTER"]
MATH_WORDS = ["INTEGRAL", "DERIVATIVE", "MATRIX", "VECTOR", "CALCULUS", "LIMIT", "PROB", "MODULUS", "ALGORITHM", "LEMMA", "SERIES"]
JEE_WORDS = ["KINEMATICS", "ELECTROSTATICS", "THERMODYNAMICS", "INTEGRAL", "DIFFERENTIAL", "MATRIX", "VECTOR", "ENTROPY"]

DB_PATH = os.environ.get("WORDS_DB", "wordsgrid_v6.db")

# -------------------------
# DATABASE
# -------------------------
class Database:
    def __init__(self, path=DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path, check_same_thread=False)

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            join_date TEXT,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100,
            is_banned INTEGER DEFAULT 0
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")
        c.execute("""CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            mode TEXT,
            timestamp TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            created_at TEXT,
            approved INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS redeem_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            points INTEGER,
            upi_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            paid_at TEXT
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()

    def get_user(self, user_id: int, name: str = "Player"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            join_date = time.strftime("%Y-%m-%d")
            c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
        conn.close()
        return row

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

    def is_admin(self, user_id: int) -> bool:
        if OWNER_ID and user_id == OWNER_ID:
            return True
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return bool(r)

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

    def list_admins(self) -> List[int]:
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins")
        data = [r[0] for r in c.fetchall()]
        conn.close()
        return data

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

    def add_redeem_request(self, user_id: int, username: str, points: int, upi_id: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO redeem_requests (user_id, username, points, upi_id, created_at) VALUES (?, ?, ?, ?, ?)",
                  (user_id, username, points, upi_id, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_redeem_requests(self, status: str = "pending"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM redeem_requests WHERE status=? ORDER BY created_at DESC", (status,))
        rows = c.fetchall()
        conn.close()
        return rows

    def mark_redeem_paid(self, request_id: int):
        conn = self._connect()
        c = conn.cursor()
        c.execute("UPDATE redeem_requests SET status='paid', paid_at=? WHERE request_id=?",
                  (time.strftime("%Y-%m-%d %H:%M:%S"), request_id))
        conn.commit()
        conn.close()

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
    fallback = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "SPACE", "GALAXY", "NEBULA", "FUTURE", "MATRIX", "VECTOR", 
                "ENERGY", "QUANTUM", "PHOTON", "PROTON", "NEUTRON"]
    ALL_WORDS = fallback
    logger.info("Using fallback wordlist.")

fetch_remote_wordlist()

# -------------------------
# ✨ PREMIUM IMAGE RENDERER WITH GLOW EFFECT ✨
# -------------------------
class GridRendererUtil:
    @staticmethod
    def draw_grid_image(grid: List[List[str]], placements: Dict[str, List[Tuple[int, int]]], found: set, is_hard=False, title="WORD VORTEX", version="v6.5 ✨"):
        cell_size = 56
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
            header_font = letter_font = small_font = ImageFont.load_default()

        # Header
        draw.rectangle([0, 0, width, header_h], fill="#eef6fb")
        tbox = draw.textbbox((0, 0), title, font=header_font)
        draw.text(((width - (tbox[2] - tbox[0])) / 2, 18), title, fill="#1f6feb", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        draw.text((pad, header_h - 26), mode_text, fill="#6b7280", font=small_font)

        grid_start_y = header_h + pad

        # Draw grid
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell_size
                y = grid_start_y + r * cell_size
                draw.rectangle([x, y, x + cell_size, y + cell_size], outline="#2b90d9", width=2)
                ch = grid[r][c]
                bb = draw.textbbox((0, 0), ch, font=letter_font)
                draw.text((x + (cell_size - (bb[2] - bb[0])) / 2, y + (cell_size - (bb[3] - bb[1])) / 2 - 4), ch, fill="#222", font=letter_font)

        # ✨✨✨ PREMIUM 3-LAYER GLOW EFFECT ✨✨✨
        try:
            if placements and found:
                for w, coords in placements.items():
                    if w in found and coords:
                        a = coords[0]
                        b = coords[-1]
                        x1 = pad + a[1] * cell_size + cell_size / 2
                        y1 = grid_start_y + a[0] * cell_size + cell_size / 2
                        x2 = pad + b[1] * cell_size + cell_size / 2
                        y2 = grid_start_y + b[0] * cell_size + cell_size / 2

                        # Layer 1: Outer Glow/Shadow (Semi-transparent effect)
                        draw.line([(x1, y1), (x2, y2)], fill="#ff475750", width=14)

                        # Layer 2: Middle bright line
                        draw.line([(x1, y1), (x2, y2)], fill="#ff4757", width=8)

                        # Layer 3: Core white bright line (animated feel)
                        draw.line([(x1, y1), (x2, y2)], fill="#ffffff", width=3)

                        # Premium rounded endpoints (circles)
                        r_glow = 8
                        draw.ellipse([x1 - r_glow, y1 - r_glow, x1 + r_glow, y1 + r_glow], fill="#ff475770")
                        draw.ellipse([x2 - r_glow, y2 - r_glow, x2 + r_glow, y2 + r_glow], fill="#ff475770")

                        r_core = 5
                        draw.ellipse([x1 - r_core, y1 - r_core, x1 + r_core, y1 + r_core], fill="#ff4757")
                        draw.ellipse([x2 - r_core, y2 - r_core, x2 + r_core, y2 + r_core], fill="#ff4757")
        except Exception:
            logger.exception("Error drawing premium glow lines")

        # Footer
        draw.text((pad, height - footer_h + 12), "Made by @Ruhvaan", fill="#95a5a6", font=small_font)
        draw.text((width - 140, height - footer_h + 12), version, fill="#95a5a6", font=small_font)

        bio = io.BytesIO()
        img.save(bio, "JPEG", quality=92)
        bio.seek(0)
        bio.name = "grid.jpg"
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
            title_f = row_f = ImageFont.load_default()
        draw.text((20, 8), "🏆 Session Leaderboard", fill="#ffd700", font=title_f)
        y = 48
        for idx, name, pts in rows:
            draw.text((20, y), f"{idx}. {name}", fill="#fff", font=row_f)
            draw.text((520, y), f"{pts} pts", fill="#7be495", font=row_f)
            y += 36
        bio = io.BytesIO()
        img.save(bio, "PNG", quality=90)
        bio.seek(0)
        bio.name = "leaders.png"
        return bio

# -------------------------
# HELPERS
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
        return True


def send_start_card(chat_id: int, caption: str, reply_markup):
    """✨ Premium 3-tier image loading system"""
    # Try 1: Download + Upload (most reliable)
    try:
        r = requests.get(START_IMG_URL, timeout=12)
        if r.status_code == 200 and "image" in (r.headers.get("content-type") or "").lower():
            bio = io.BytesIO(r.content)
            bio.name = "start.jpg"
            bot.send_photo(chat_id, bio, caption=caption, reply_markup=reply_markup)
            return True
    except:
        pass

    # Try 2: URL-based
    try:
        bot.send_photo(chat_id, START_IMG_URL, caption=caption, reply_markup=reply_markup)
        return True
    except:
        pass

    # Try 3: Text fallback
    bot.send_message(chat_id, caption, reply_markup=reply_markup)
    return False


def ensure_user_registered(uid: int, name: str):
    try:
        db.register_user(uid, name)
    except:
        pass

# -------------------------
# COMMANDS TEXT
# -------------------------
COMMANDS_FULL_TEXT = """
🤖 <b>Word Vortex - Command List</b>

<b>🎮 Game:</b>
/new - Normal (8x8)
/new_hard - Hard (10x10)
/new_physics - Physics words
/new_chemistry - Chemistry
/new_math - Math mode
/new_jee - JEE mixed

<b>💡 Actions:</b>
/hint - Get hint (-50 pts)
/mystats - Your stats
/balance - Hint balance
/leaderboard - Top players

<b>📝 Support:</b>
/review <text> - Submit review
/define <word> - Dictionary
/redeem_request - Cash out

<b>👨‍💼 Admin:</b>
/addpoints <user> <amt>
/reset_leaderboard
/redeem_list
/redeem_pay <id>
"""

# -------------------------
# MENU
# -------------------------
def build_main_menu_markup():
    kb = InlineKeyboardMarkup(row_width=2)
    if CHANNEL_USERNAME:
        kb.add(
            InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
            InlineKeyboardButton("🔄 Check", callback_data="check_join"),
        )
    try:
        me = bot.get_me().username
        if me:
            kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{me}?startgroup=true"))
    except:
        pass
    kb.add(
        InlineKeyboardButton("✨ Features", callback_data="open_features"),
        InlineKeyboardButton("📖 How to Play", callback_data="help_play"),
    )
    kb.add(
        InlineKeyboardButton("🤖 Commands", callback_data="help_cmd"),
        InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
    )
    kb.add(
        InlineKeyboardButton("👤 My Stats", callback_data="menu_stats"),
        InlineKeyboardButton("💳 Buy Points", callback_data="open_plans"),
    )
    kb.add(InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP_LINK))
    return kb

# -------------------------
# GAME SESSION CLASS
# -------------------------
games = {}

class GameSession:
    def __init__(self, chat_id: int, mode: str = "default", is_hard: bool = False, duration: int = GAME_DURATION, word_pool: Optional[List[str]] = None):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.wordcount = 8 if is_hard else 6
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
        self.active = True

        pool = word_pool if word_pool else ALL_WORDS
        self._prepare_grid(pool)

    def _prepare_grid(self, pool: List[str]):
        # Select words
        choices = [w for w in pool if 4 <= len(w) <= 10]
        if len(choices) < self.wordcount:
            choices = choices * 3
        self.words = random.sample(choices, min(self.wordcount, len(choices)))

        # Initialize grid
        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]

        # Directions
        dirs = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]

        # Place words
        for w in sorted(self.words, key=len, reverse=True):
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
                logger.warning(f"Could not place word: {w}")

        # Fill empty cells
        for r in range(self.size):
            for c in range(self.size):
                if not self.grid[r][c]:
                    self.grid[r][c] = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def _can_place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            rr, cc = r + i * dr, c + i * dc
            if not (0 <= rr < self.size and 0 <= cc < self.size):
                return False
            if self.grid[rr][cc] and self.grid[rr][cc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + "-" * (len(w) - 2) + w[-1]
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)


def start_game_session(chat_id: int, starter_id: int, mode: str = "default", is_hard: bool = False, word_pool: Optional[List[str]] = None):
    if chat_id in games:
        return None

    session = GameSession(chat_id, mode=mode, is_hard=is_hard, word_pool=word_pool)
    games[chat_id] = session

    try:
        db.register_user(starter_id, "Player")
        db.update_stats(starter_id, games_played_delta=1)
    except:
        pass

    try:
        img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
        caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
                   f"Mode: {mode.upper()} {'(HARD)' if is_hard else ''}\n"
                   f"⏱ Time: {session.duration//60} min\n\n"
                   f"<b>Words to find:</b>\n{session.get_hint_text()}")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                   InlineKeyboardButton("📊 Score", callback_data="game_score"))
        sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=markup)
        session.message_id = sent.message_id
    except Exception as e:
        logger.exception("Failed to start game")
        return None

    return session


def update_game_image(chat_id: int):
    if chat_id not in games:
        return
    session = games[chat_id]
    try:
        img = GridRendererUtil.draw_grid_image(session.grid, session.placements, session.found, is_hard=session.is_hard)
        caption = (f"🔥 <b>WORD VORTEX</b>\n"
                   f"Mode: {session.mode.upper()}\n\n"
                   f"<b>Words:</b>\n{session.get_hint_text()}")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                   InlineKeyboardButton("📊 Score", callback_data="game_score"))

        # Try edit first
        try:
            bot.edit_message_media(
                media=telebot.types.InputMediaPhoto(img),
                chat_id=chat_id,
                message_id=session.message_id
            )
            bot.edit_message_caption(caption, chat_id=chat_id, message_id=session.message_id, reply_markup=markup, parse_mode="HTML")
        except:
            # Send new if edit fails
            sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=markup)
            session.message_id = sent.message_id
    except Exception as e:
        logger.exception("Failed to update game image")


def process_word_guess(msg):
    cid = msg.chat.id
    if cid not in games:
        bot.reply_to(msg, "❌ No active game.")
        return

    session = games[cid]
    uid = msg.from_user.id
    username = msg.from_user.first_name or msg.from_user.username or "Player"
    word = (msg.text or "").strip().upper()

    if not word:
        return

    # Cooldown check
    last = session.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        bot.reply_to(msg, f"⏳ Wait {COOLDOWN}s between guesses.")
        return
    session.players_last_guess[uid] = now

    # Check word
    if word not in session.words:
        bot.reply_to(msg, f"❌ '{word}' is not in the list!")
        return

    if word in session.found:
        bot.reply_to(msg, f"✅ '{word}' already found!")
        return

    # Correct guess!
    session.found.add(word)
    session.last_activity = time.time()

    # Points
    if len(session.found) == 1:
        points = FIRST_BLOOD_POINTS
    elif len(session.found) == len(session.words):
        points = FINISHER_POINTS
    else:
        points = NORMAL_POINTS

    prev = session.players_scores.get(uid, 0)
    session.players_scores[uid] = prev + points
    db.update_stats(uid, score_delta=points)

    bot.send_message(cid, f"🎉 <b>Excellent!</b>\n{html.escape(username)} found <code>{word}</code>! +{points} pts")

    # Update image with premium glow line
    update_game_image(cid)

    # Check if game over
    if len(session.found) == len(session.words):
        bot.send_message(cid, "🏆 <b>Game Complete!</b> All words found!")
        del games[cid]


# -------------------------
# COMMAND HANDLERS
# -------------------------
@bot.message_handler(commands=["start", "help"])
def cmd_start(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    ensure_user_registered(m.from_user.id, name)
    txt = f"👋 <b>Hello, {html.escape(name)}!</b>\n\nWelcome to Word Vortex ✨\nTap a button below:"
    send_start_card(m.chat.id, txt, build_main_menu_markup())


@bot.message_handler(commands=["cmd"])
def cmd_cmd(m):
    try:
        sent_pm = False
        try:
            bot.send_message(m.from_user.id, COMMANDS_FULL_TEXT, parse_mode="HTML")
            sent_pm = True
        except:
            pass
        if sent_pm:
            bot.reply_to(m, "✅ Commands sent to PM!")
        else:
            bot.reply_to(m, COMMANDS_FULL_TEXT)
    except:
        bot.reply_to(m, "❌ Error showing commands.")


@bot.message_handler(commands=["new"])
def cmd_new(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use /new in a group chat!")
        return
    session = start_game_session(m.chat.id, m.from_user.id, mode="default", is_hard=False)
    if not session:
        bot.reply_to(m, "❌ A game is already active or failed to start.")


@bot.message_handler(commands=["new_hard"])
def cmd_new_hard(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in a group!")
        return
    start_game_session(m.chat.id, m.from_user.id, mode="hard", is_hard=True)


@bot.message_handler(commands=["new_physics"])
def cmd_new_physics(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in a group!")
        return
    start_game_session(m.chat.id, m.from_user.id, mode="physics", word_pool=PHYSICS_WORDS)


@bot.message_handler(commands=["new_chemistry"])
def cmd_new_chemistry(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in a group!")
        return
    start_game_session(m.chat.id, m.from_user.id, mode="chemistry", word_pool=CHEMISTRY_WORDS)


@bot.message_handler(commands=["new_math"])
def cmd_new_math(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in a group!")
        return
    start_game_session(m.chat.id, m.from_user.id, mode="math", word_pool=MATH_WORDS)


@bot.message_handler(commands=["new_jee"])
def cmd_new_jee(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in a group!")
        return
    start_game_session(m.chat.id, m.from_user.id, mode="jee", word_pool=JEE_WORDS)


@bot.message_handler(commands=["leaderboard"])
def cmd_leaderboard(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>Global Leaderboard</b>\n\n"
    for i, (name, score) in enumerate(top, 1):
        txt += f"{i}. {html.escape(name)} - {score} pts\n"
    bot.reply_to(m, txt if top else "No players yet.")


@bot.message_handler(commands=["mystats"])
def cmd_mystats(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
    txt = (f"📋 <b>Your Stats</b>\n"
           f"Name: {html.escape(user[1])}\n"
           f"Total Score: {user[5]}\n"
           f"Wins: {user[4]}\n"
           f"Games: {user[3]}\n"
           f"Hint Balance: {user[6]}")
    bot.reply_to(m, txt)


@bot.message_handler(commands=["balance"])
def cmd_balance(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
    bot.reply_to(m, f"💰 Your hint balance: <b>{user[6]}</b> pts")


@bot.message_handler(commands=["review"])
def cmd_review(m):
    text = m.text.replace("/review", "").strip()
    if not text:
        bot.reply_to(m, "Usage: /review <your feedback>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or "Player", text)
    bot.reply_to(m, "✅ Thank you! Review submitted.")


@bot.message_handler(commands=["redeem_request"])
def cmd_redeem_request(m):
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /redeem_request <points> <UPI_ID>\nExample: /redeem_request 500 name@paytm")
        return
    try:
        points = int(parts[1])
        upi = parts[2]
        user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
        if user[5] < points:
            bot.reply_to(m, f"❌ Insufficient balance. You have {user[5]} pts.")
            return
        db.add_redeem_request(m.from_user.id, m.from_user.first_name or "Player", points, upi)
        bot.reply_to(m, f"✅ Redeem request submitted for {points} pts to {upi}")
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")


@bot.message_handler(commands=["addpoints"])
def cmd_addpoints(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <user_id> <amount>")
        return
    try:
        target_id = int(parts[1])
        amount = int(parts[2])
        db.update_stats(target_id, hint_delta=amount)
        bot.reply_to(m, f"✅ Added {amount} pts to user {target_id}")
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")


@bot.message_handler(commands=["reset_leaderboard"])
def cmd_reset_lb(m):
    if not db.is_admin(m.from_user.id):
        return
    db.reset_leaderboard()
    bot.reply_to(m, "✅ Leaderboard reset!")


@bot.message_handler(commands=["redeem_list"])
def cmd_redeem_list(m):
    if not db.is_admin(m.from_user.id):
        return
    reqs = db.list_redeem_requests("pending")
    if not reqs:
        bot.reply_to(m, "No pending requests.")
        return
    txt = "💸 <b>Pending Redeem Requests:</b>\n\n"
    for req in reqs:
        txt += f"ID: {req[0]} | User: {req[2]} | Points: {req[3]} | UPI: {req[4]}\n"
    bot.reply_to(m, txt)


@bot.message_handler(commands=["redeem_pay"])
def cmd_redeem_pay(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /redeem_pay <request_id>")
        return
    try:
        req_id = int(parts[1])
        db.mark_redeem_paid(req_id)
        bot.reply_to(m, f"✅ Request {req_id} marked as paid!")
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {e}")


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
                    txt = f"<b>{html.escape(w)}</b>\n{html.escape(definition)}"
                    if example:
                        txt += f"\n\n<i>Example:</i> {html.escape(example)}"
                    bot.reply_to(m, txt)
                    return
        bot.reply_to(m, f"No definition found for '{w}'")
    except:
        bot.reply_to(m, "Error fetching definition.")


# -------------------------
# CALLBACK HANDLER
# -------------------------
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data

    def pm_first_send(text: str, reply_markup=None):
        try:
            bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
            bot.answer_callback_query(c.id, "Sent to PM!")
            return True
        except:
            pass
        try:
            bot.send_message(cid, text, parse_mode="HTML", reply_markup=reply_markup)
            bot.answer_callback_query(c.id, "Opened here.")
            return True
        except:
            bot.answer_callback_query(c.id, "❌ Could not open. Try /cmd", show_alert=True)
            return False

    if data == "check_join":
        if is_subscribed(uid):
            bot.answer_callback_query(c.id, "✅ Verified!")
            cmd_start(c.message)
        else:
            bot.answer_callback_query(c.id, "❌ You haven't joined!", show_alert=True)
        return

    if data == "open_features":
        txt = (
            "✨ <b>Word Vortex Premium Features</b>\n\n"
            "🎮 <b>Game Modes:</b>\n"
            "Normal, Hard, Physics, Chemistry, Math, JEE\n\n"
            "⚡ <b>Premium Features:</b>\n"
            "• 3-Layer Glow Effect on found words\n"
            "• Real-time image updates\n"
            "• Leaderboards & Stats\n"
            "• Hints System\n"
            "• Points & Redeem\n\n"
            "Commands: /cmd"
        )
        pm_first_send(txt)
        return

    if data == "help_play":
        txt = (
            "<b>📖 How to Play</b>\n\n"
            "1️⃣ Start: /new or /new_physics\n"
            "2️⃣ Grid sent with masked words\n"
            "3️⃣ Click 'Found It' and type word\n"
            "4️⃣ Correct = Points + Premium Glow!\n\n"
            "<b>Scoring:</b>\n"
            "First: +10 | Normal: +2 | Last: +5"
        )
        pm_first_send(txt)
        return

    if data == "help_cmd":
        pm_first_send(COMMANDS_FULL_TEXT)
        return

    if data == "menu_lb":
        top = db.get_top_players(10)
        txt = "🏆 <b>Global Leaderboard</b>\n\n"
        for i, (name, score) in enumerate(top, 1):
            txt += f"{i}. {html.escape(name)} - {score} pts\n"
        pm_first_send(txt if top else "No players yet.")
        return

    if data == "menu_stats":
        user = db.get_user(uid, c.from_user.first_name or "Player")
        txt = (f"📋 <b>Your Stats</b>\n"
               f"Name: {html.escape(user[1])}\n"
               f"Score: {user[5]} | Wins: {user[4]}\n"
               f"Games: {user[3]} | Balance: {user[6]}")
        pm_first_send(txt)
        return

    if data == "open_plans":
        txt = "💳 <b>Points Plans:</b>\n\n"
        for p in PLANS:
            txt += f"• {p['points']} pts : ₹{p['price_rs']}\n"
        txt += f"\nContact: {SUPPORT_GROUP_LINK}"
        pm_first_send(txt)
        return

    if data == "game_guess":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            bot.answer_callback_query(c.id, "Type your guess")
        except:
            bot.answer_callback_query(c.id, "❌ Could not open input.", show_alert=True)
        return

    if data == "game_hint":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        game = games[cid]
        user_row = db.get_user(uid, c.from_user.first_name)
        if user_row[6] < HINT_COST:
            bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user_row[6]}", show_alert=True)
            return
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, hint_delta=-HINT_COST)
        bot.send_message(cid, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")
        bot.answer_callback_query(c.id, "Hint revealed")
        return

    if data == "game_score":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        game = games[cid]
        if not game.players_scores:
            bot.answer_callback_query(c.id, "No scores yet.", show_alert=True)
            return
        leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        rows = []
        for i, (uid_score, pts) in enumerate(leaderboard, 1):
            user = db.get_user(uid_score, "Player")
            rows.append((i, user[1], pts))
        img = LeaderboardImage.draw_rows(rows[:10])
        try:
            bot.send_photo(cid, img, caption="📊 Session Leaderboard")
            bot.answer_callback_query(c.id, "Leaderboard shown")
        except:
            txt = "📊 Session Leaderboard\n\n"
            for idx, name, pts in rows[:10]:
                txt += f"{idx}. {html.escape(name)} - {pts} pts\n"
            pm_first_send(txt)
        return

    bot.answer_callback_query(c.id, "")


# -------------------------
# ✅ FALLBACK HANDLER (FIXED - NO COMMAND SWALLOWING)
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def fallback_text_handler(m):
    # ✅ CRITICAL FIX: Let other handlers process commands
    if m.text and m.text.strip().startswith('/'):
        return
    # For other text, just ignore (or handle ForceReply flows)


# -------------------------
# RUN BOT
# -------------------------
if __name__ == "__main__":
    logger.info("🚀 Word Vortex v6.5 Premium Bot Started!")
    logger.info("✨ Features: Premium Glow Lines | Fixed Commands | Redeem System")
    bot.infinity_polling()
