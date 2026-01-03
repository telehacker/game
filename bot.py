#!/usr/bin/env python3
"""
WORDS GRID ROBOT - ULTIMATE PREMIUM EDITION
Version: 5.2 (Enterprise) - Added broadcast, add-to-group button, auto-redeem, cash balance,
changed addpoints default to hint balance, and other fixes.
Developer: Ruhvaan (updated)
"""

import telebot
import random
import string
import requests
import threading
import sqlite3
import time
import os
import sys
import html
import io
import logging
import tempfile
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# ⚙️ CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '8208557623:AAHnIoKHGijL6WN7tYLStJil8ZIMBDsXnpA')
try:
    OWNER_ID = int(os.environ.get('OWNER_ID', '8271254197'))
except Exception:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get('CHANNEL_USERNAME', '@Ruhvaan_Updates')
FORCE_JOIN = os.environ.get('FORCE_JOIN', 'False').lower() in ('1', 'true', 'yes')

SUPPORT_GROUP_LINK = os.environ.get('SUPPORT_GROUP_LINK', 'https://t.me/Ruhvaan')
START_IMG_URL = os.environ.get('START_IMG_URL', 'https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg')

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Scoring constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 4
FINISHER_POINTS = 7

BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600  # seconds (10 minutes)
COOLDOWN = 2
HINT_COST = 50

# Redeem (cash) configuration
REDEEM_THRESHOLD = 150  # points required to redeem
REDEEM_AMOUNT_RS = 10   # rupees per threshold redeemed

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# Sample curated pools
PHYSICS_WORDS = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "ACCEL", "VECTOR", "SCALAR", "WAVE", "PHOTON", "GRAVITY"]
CHEMISTRY_WORDS = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "CATION", "ANION", "ACID", "BASE", "SALT"]
JEE_WORDS = [
    "INTEGRAL", "DIFFERENTIAL", "MATRIX", "VECTOR", "FORCE", "ENERGY", "EQUILIBRIUM", "KINEMATICS",
    "OXIDATION", "REDUCTION"
]

# ==========================================
# 🗄️ DATABASE MANAGER (includes admins + migrations)
# ==========================================
class DatabaseManager:
    def __init__(self, db_name='wordsgrid_premium.db'):
        self.db_name = db_name
        self.init_db()

    def connect(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)

    def init_db(self):
        conn = self.connect()
        c = conn.cursor()
        # Create users table with cash_balance column. If table existed from older version, we ALTER it.
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
        # admins table
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )''')
        # game_history
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            timestamp TEXT
        )''')
        conn.commit()

        # Migration: ensure cash_balance column exists (for very old DBs)
        try:
            c.execute("PRAGMA table_info(users)")
            cols = [r[1] for r in c.fetchall()]
            if 'cash_balance' not in cols:
                logger.info("Migrating DB: adding cash_balance column")
                c.execute("ALTER TABLE users ADD COLUMN cash_balance INTEGER DEFAULT 0")
                conn.commit()
        except Exception:
            logger.exception("DB migration check failed")
        conn.close()

    # User helpers
    def get_user(self, user_id, name):
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

    def register_user(self, user_id, name):
        """
        Ensure user exists. Return (user_row, created_bool).
        """
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        if user:
            conn.close()
            return user, False
        join_date = time.strftime("%Y-%m-%d")
        c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)", (user_id, name, join_date))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        conn.close()
        return user, True

    def update_stats(self, user_id, score_delta=0, hint_delta=0, win=False, games_played_delta=0):
        """
        Update stats. score_delta adds to total_score, hint_delta to hint_balance.
        After updating score, automatically process redeeming cash if threshold reached.
        """
        conn = self.connect()
        c = conn.cursor()
        # Update total_score
        if score_delta != 0:
            c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (score_delta, user_id))
        # Update hint_balance
        if hint_delta != 0:
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (hint_delta, user_id))
        # Wins
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        # Games played
        if games_played_delta != 0:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
        conn.commit()

        # Auto-redeem: check total_score and convert every REDEEM_THRESHOLD points to REDEEM_AMOUNT_RS rupees
        try:
            c.execute("SELECT total_score, cash_balance, name FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
            if row:
                total_score_now, cash_bal_now, name = row[0], row[1], row[2] if len(row) > 2 else ""
                if REDEEM_THRESHOLD > 0:
                    redeem_count = total_score_now // REDEEM_THRESHOLD
                    if redeem_count > 0:
                        # deduct points and increase cash_balance
                        deduct = redeem_count * REDEEM_THRESHOLD
                        add_cash = redeem_count * REDEEM_AMOUNT_RS
                        c.execute("UPDATE users SET total_score = total_score - ?, cash_balance = cash_balance + ? WHERE user_id=?",
                                  (deduct, add_cash, user_id))
                        conn.commit()
                        # notify user and owner
                        try:
                            bot.send_message(user_id, f"🎉 Congrats! You redeemed {add_cash} ₹ (for {deduct} pts). Your cash balance: {cash_bal_now + add_cash} ₹")
                        except Exception:
                            logger.debug("Could not notify user about auto-redeem")
                        if OWNER_ID:
                            try:
                                bot.send_message(OWNER_ID, f"💸 Auto-redeem: {name} ({user_id}) redeemed ₹{add_cash} (used {deduct} pts).")
                            except Exception:
                                logger.debug("Could not notify owner about auto-redeem")
        except Exception:
            logger.exception("Auto-redeem failed")
        finally:
            conn.close()

    # Admin helpers
    def add_admin(self, admin_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        conn.close()

    def remove_admin(self, admin_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))
        conn.commit()
        conn.close()

    def is_admin(self, user_id):
        if OWNER_ID and user_id == OWNER_ID:
            return True
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins WHERE admin_id=?", (user_id,))
        res = c.fetchone()
        conn.close()
        return bool(res)

    def list_admins(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT admin_id FROM admins")
        data = [r[0] for r in c.fetchall()]
        conn.close()
        return data

    def record_game(self, chat_id, winner_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, timestamp) VALUES (?, ?, ?)",
                  (chat_id, winner_id, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_top_players(self, limit=10):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        data = c.fetchall()
        conn.close()
        return data

    def reset_leaderboard(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = 0, wins = 0")
        conn.commit()
        conn.close()

    def get_all_users(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        data = [x[0] for x in c.fetchall()]
        conn.close()
        return data

db = DatabaseManager()

# ==========================================
# (GridRenderer, LeaderboardRenderer, GameSession) ...
# For brevity: reuse the same implementations from previous version (visual lines, placements, timers)
# I'll include the updated GridRenderer and GameSession which support placements and found-lines.
# ==========================================

class GridRenderer:
    @staticmethod
    def draw(grid, placements=None, found=None, is_hard=False):
        cell_size = 60
        header_height = 100
        footer_height = 50
        padding = 30
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        width = (cols * cell_size) + (padding * 2)
        height = (rows * cell_size) + header_height + footer_height + (padding * 2)
        BG_COLOR = "#FFFFFF"
        GRID_COLOR = "#3498db"
        TEXT_COLOR = "#2c3e50"
        HEADER_BG = "#ecf0f1"
        img = Image.new('RGB', (width, height), BG_COLOR)
        draw = ImageDraw.Draw(img)
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path): font_path = "arial.ttf"
            letter_font = ImageFont.truetype(font_path, 32)
            header_font = ImageFont.truetype(font_path, 40)
            footer_font = ImageFont.truetype(font_path, 15)
        except:
            letter_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            footer_font = ImageFont.load_default()

        draw.rectangle([0, 0, width, header_height], fill=HEADER_BG)
        title_text = "WORD VORTEX"
        bbox = draw.textbbox((0, 0), title_text, font=header_font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) / 2, 30), title_text, fill="#2980b9", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        bbox2 = draw.textbbox((0, 0), mode_text, font=footer_font)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((width - tw2) / 2, 75), mode_text, fill="#7f8c8d", font=footer_font)

        grid_start_y = header_height + padding
        for r in range(rows):
            for c in range(cols):
                x = padding + (c * cell_size)
                y = grid_start_y + (r * cell_size)
                shape = [x, y, x + cell_size, y + cell_size]
                draw.rectangle(shape, outline=GRID_COLOR, width=2)
                char = grid[r][c]
                bbox_char = draw.textbbox((0, 0), char, font=letter_font)
                cw = bbox_char[2] - bbox_char[0]
                ch = bbox_char[3] - bbox_char[1]
                draw.text((x + (cell_size - cw) / 2, y + (cell_size - ch) / 2 - 5), char, fill=TEXT_COLOR, font=letter_font)

        if placements and found:
            try:
                for word, coords in placements.items():
                    if word in found and coords:
                        first = coords[0]; last = coords[-1]
                        x1 = padding + (first[1] * cell_size) + cell_size / 2
                        y1 = grid_start_y + (first[0] * cell_size) + cell_size / 2
                        x2 = padding + (last[1] * cell_size) + cell_size / 2
                        y2 = grid_start_y + (last[0] * cell_size) + cell_size / 2
                        draw.line([(x1, y1), (x2, y2)], fill="#ffffff", width=8)
                        draw.line([(x1, y1), (x2, y2)], fill="#ff4757", width=5)
                        r_end = 6
                        draw.ellipse([x1 - r_end, y1 - r_end, x1 + r_end, y1 + r_end], fill="#ff4757")
                        draw.ellipse([x2 - r_end, y2 - r_end, x2 + r_end, y2 + r_end], fill="#ff4757")
            except Exception:
                logger.exception("Error drawing found-word lines")

        draw.text((30, height - 30), "Made by @Ruhvaan", fill="#95a5a6", font=footer_font)
        draw.text((width - 100, height - 30), "v5.2", fill="#95a5a6", font=footer_font)
        bio = io.BytesIO()
        img.save(bio, 'JPEG', quality=95)
        bio.seek(0)
        try:
            bio.name = 'grid.jpg'
        except:
            pass
        return bio

class LeaderboardRenderer:
    @staticmethod
    def draw_session_leaderboard(rows):
        width = 700
        height = max(120, 60 + 50 * len(rows))
        bg = Image.new('RGB', (width, height), '#0f1724')
        draw = ImageDraw.Draw(bg)
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path): font_path = "arial.ttf"
            title_font = ImageFont.truetype(font_path, 28)
            row_font = ImageFont.truetype(font_path, 22)
        except:
            title_font = ImageFont.load_default()
            row_font = ImageFont.load_default()
        draw.text((20, 10), "Session Leaderboard", fill="#FFD700", font=title_font)
        y = 50
        for idx, name, pts in rows:
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            draw.text((20, y), f"{medal}", fill="#FFFFFF", font=row_font)
            draw.text((80, y), f"{name}", fill="#FFFFFF", font=row_font)
            draw.text((width - 120, y), f"{pts} pts", fill="#7be495", font=row_font)
            y += 40
        bio = io.BytesIO()
        bg.save(bio, 'PNG', quality=90)
        bio.seek(0)
        try:
            bio.name = 'leaders.png'
        except:
            pass
        return bio

ALL_WORDS = []
def fetch_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        resp = requests.get(url, timeout=10)
        content = resp.content.decode("utf-8")
        raw_words = [w.upper() for w in content.splitlines()]
        ALL_WORDS = [w for w in raw_words if 4 <= len(w) <= 9 and w.isalpha() and w not in BAD_WORDS]
        logger.info(f"Loaded {len(ALL_WORDS)} words.")
    except Exception:
        logger.exception("Word Fetch Error")
        ALL_WORDS = ['PYTHON', 'JAVA', 'SCRIPT', 'ROBOT', 'FUTURE', 'SPACE', 'GALAXY', 'NEBULA']

fetch_words()

games = {}  # chat_id -> GameSession

class GameSession:
    def __init__(self, chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None):
        self.chat_id = chat_id
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.start_time = time.time()
        self.last_activity = time.time()
        self.words = []
        self.found = set()
        self.grid = []
        self.players_scores = {}
        self.players_last_guess = {}
        self.duration = duration
        self.message_id = None
        self.active = True
        self.timer_thread = None
        self.placements = {}
        self.word_pool = word_pool
        self.generate()

    def generate(self):
        if self.word_pool:
            pool = [w.upper() for w in self.word_pool if 4 <= len(w) <= 12]
        else:
            if not ALL_WORDS:
                fetch_words()
            pool = ALL_WORDS[:] if len(ALL_WORDS) >= self.word_count else (ALL_WORDS * 2)
        try:
            self.words = random.sample(pool, min(self.word_count, len(pool)))
        except Exception:
            self.words = [random.choice(pool) for _ in range(self.word_count)]
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        self.placements = {}
        for word in sorted_words:
            placed = False
            attempts = 0
            while not placed and attempts < 400:
                attempts += 1
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                dr, dc = random.choice(dirs)
                if self._can_place(row, col, dr, dc, word):
                    coords = []
                    for i in range(len(word)):
                        nr, nc = row + i*dr, col + i*dc
                        self.grid[nr][nc] = word[i]
                        coords.append((nr, nc))
                    self.placements[word] = coords
                    placed = True
            if not placed:
                for r in range(self.size):
                    for c in range(self.size):
                        for dr, dc in dirs:
                            if self._can_place(r, c, dr, dc, word):
                                coords = []
                                for i in range(len(word)):
                                    nr, nc = r + i*dr, c + i*dc
                                    self.grid[nr][nc] = word[i]
                                    coords.append((nr, nc))
                                self.placements[word] = coords
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
                        break
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == ' ':
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def _can_place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            nr, nc = r + i*dr, c + i*dc
            if not (0 <= nr < self.size and 0 <= nc < self.size):
                return False
            if self.grid[nr][nc] != ' ' and self.grid[nr][nc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + ("-" * (len(w)-1))
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

    def start_timer(self):
        if self.timer_thread and self.timer_thread.is_alive():
            return
        self.timer_thread = threading.Thread(target=self._run_timer, daemon=True)
        self.timer_thread.start()

    def _run_timer(self):
        try:
            while self.active:
                elapsed = time.time() - self.start_time
                remaining = int(self.duration - elapsed)
                if remaining <= 0:
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! The game has ended.")
                    except Exception:
                        logger.exception("Failed to notify chat on timeout")
                    try:
                        end_game_session(self.chat_id, "timeout")
                    except Exception:
                        logger.exception("end_game_session on timeout failed")
                    break
                if self.message_id:
                    mins = remaining // 60
                    secs = remaining % 60
                    time_str = f"{mins}:{secs:02d}"
                    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
                               f"Mode: {'Hard (10x10)' if self.is_hard else 'Normal (8x8)'}\n"
                               f"⏱ Time Left: {time_str}\n\n"
                               f"<b>👇 WORDS TO FIND:</b>\n"
                               f"{self.get_hint_text()}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'))
                    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
                               InlineKeyboardButton("📊 Score", callback_data='game_score'))
                    try:
                        safe_edit_message(caption, self.chat_id, self.message_id, reply_markup=markup)
                    except Exception:
                        logger.exception("Timer safe_edit_message failed")
                time.sleep(10)
        except Exception:
            logger.exception("GameSession._run_timer error")
        finally:
            self.active = False

# ==========================================
# Helpers, Menu, Callbacks (includes Add-to-Group button)
# ==========================================
def is_subscribed(user_id):
    if not FORCE_JOIN:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if not CHANNEL_USERNAME:
        return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['creator', 'administrator', 'member']
    except Exception:
        return True

def require_subscription(func):
    def wrapper(message):
        if not is_subscribed(message.from_user.id):
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
            markup.add(InlineKeyboardButton("🔄 Check Join", callback_data="check_join"))
            bot.reply_to(message, "⚠️ <b>Access Denied!</b>\nYou must join our channel to play.", reply_markup=markup)
            return
        return func(message)
    return wrapper

def is_admin_or_owner(user_id):
    return (OWNER_ID and user_id == OWNER_ID) or db.is_admin(user_id)

def owner_only(func):
    def wrapper(m):
        if m.from_user.id != OWNER_ID:
            bot.reply_to(m, "❌ Only owner can use this.")
            return
        return func(m)
    return wrapper

def safe_edit_message(caption, cid, mid, reply_markup=None):
    try:
        bot.edit_message_caption(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        bot.edit_message_text(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup, parse_mode='HTML')
        return True
    except Exception:
        pass
    try:
        bot.send_message(cid, caption, reply_markup=reply_markup, parse_mode='HTML')
        try:
            bot.delete_message(cid, mid)
        except:
            pass
        return True
    except Exception:
        logger.exception("safe_edit_message: all edit/send attempts failed")
        return False

@bot.message_handler(commands=['start', 'help'])
def show_main_menu(m):
    try:
        name = m.from_user.first_name or m.from_user.username or "Player"
        user_row, created = db.register_user(m.from_user.id, name)
        if OWNER_ID:
            try:
                bot.send_message(OWNER_ID, f"🔔 /start used:\nName: {html.escape(name)}\nID: {m.from_user.id}\nChat: {m.chat.id}")
            except Exception:
                logger.exception("Failed to notify owner about /start")
    except Exception:
        logger.exception("DB register_user error in show_main_menu")

    txt = (f"👋 <b>Hello, {html.escape(m.from_user.first_name or m.from_user.username or 'Player')}!</b>\n\n"
           "🧩 <b>Welcome to Word Vortex</b>\n"
           "The most advanced multiplayer word search bot on Telegram.\n\n"
           "👇 <b>What would you like to do?</b>")

    # Build keyboard. Put Join & Check Join at the top and Add to Group button.
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
               InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
    # Add "Add to group" button (dynamic bot username)
    try:
        bot_username = bot.get_me().username
        if bot_username:
            markup.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{bot_username}?startgroup=true"),
                       InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))
        else:
            markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))
    except Exception:
        markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))

    markup.add(InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'),
               InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'))
    markup.add(InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'),
               InlineKeyboardButton("🐞 Report Issue", callback_data='open_issue'))
    markup.add(InlineKeyboardButton("💳 Buy Points", callback_data='open_plans'),
               InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))

    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=markup)
    except Exception:
        logger.exception("send_photo failed in show_main_menu, sending text fallback")
        try:
            bot.reply_to(m, txt, reply_markup=markup)
        except Exception:
            try:
                bot.send_message(m.chat.id, txt)
            except Exception:
                logger.exception("Failed to send any start message")

# callback handler (keeps robust fallback)
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    cid = c.message.chat.id
    mid = c.message.message_id
    uid = c.from_user.id
    data = c.data
    try:
        bot.answer_callback_query(c.id, "", show_alert=False)
    except:
        pass

    def send_text_with_fallback(chat_id, text, reply_markup=None, parse_mode='HTML'):
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except Exception:
            pass
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except Exception:
            pass
        try:
            bot.send_message(uid, text, parse_mode=parse_mode)
            try:
                bot.send_message(chat_id, "🔔 I have sent you the information in a private message. Please check your PMs.")
            except:
                pass
            return True
        except Exception:
            return False

    if data == "check_join":
        if is_subscribed(uid):
            try: bot.delete_message(cid, mid)
            except: pass
            show_main_menu(c.message)
            try: bot.answer_callback_query(c.id, "✅ Verified! Welcome.")
            except: pass
        else:
            try: bot.answer_callback_query(c.id, "❌ You haven't joined yet!", show_alert=True)
            except: pass
        return

    if data == 'open_issue':
        prompt = f"@{c.from_user.username or c.from_user.first_name} Please type your issue or use /issue <message>:"
        try:
            bot.send_message(cid, prompt, reply_markup=ForceReply(selective=True))
            try: bot.answer_callback_query(c.id, "✍️ Type your issue below.")
            except: pass
            return
        except Exception:
            pass
        try:
            bot.send_message(uid, prompt, reply_markup=ForceReply(selective=True))
            try: bot.answer_callback_query(c.id, "✍️ Sent a private prompt. Check your PMs.")
            except: pass
            try: bot.send_message(cid, f"🔔 {c.from_user.first_name}, I sent you a private prompt to report your issue.")
            except: pass
            return
        except Exception:
            try: bot.answer_callback_query(c.id, "❌ Unable to open issue prompt.", show_alert=True)
            except: pass
        return

    if data == 'open_plans':
        txt = "💳 Points Plans:\n\n"
        for p in PLANS:
            txt += f"- {p['points']} pts : ₹{p['price_rs']}\n"
        txt += f"\nTo buy, contact the owner: {SUPPORT_GROUP_LINK}"
        ok = send_text_with_fallback(cid, txt)
        try:
            if ok: bot.answer_callback_query(c.id, "Plans opened.")
            else: bot.answer_callback_query(c.id, "❌ Could not open plans.", show_alert=True)
        except: pass
        return

    if data == 'help_play':
        txt = ("<b>📖 How to Play:</b>\n\n"
               "1️⃣ <b>Start:</b> Type <code>/new</code> in a group.\n"
               "2️⃣ <b>Search:</b> Look at the image grid carefully.\n"
               "3️⃣ <b>Solve:</b> Click 'Found It' & type the word.\n\n"
               "<b>🏆 Scoring Rules:</b>\n"
               f"• First Word: +{FIRST_BLOOD_POINTS} Pts\n"
               f"• Normal Word: +{NORMAL_POINTS} Pts\n"
               f"• Last Word: +{FINISHER_POINTS} Pts")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        ok = send_text_with_fallback(cid, txt, reply_markup=markup)
        try:
            if ok: bot.answer_callback_query(c.id, "Opened play help.")
            else: bot.answer_callback_query(c.id, "❌ Could not open play help.", show_alert=True)
        except: pass
        return

    if data == 'help_cmd':
        txt = ("<b>🤖 Command List:</b>\n\n"
               "/start, /help - Open menu\n"
               "/ping - Check bot ping\n"
               "/new - Start a normal game\n"
               "/new_hard - Start hard game\n"
               "/new_physics - Start physics vocab game\n"
               "/new_chemistry - Start chemistry vocab game\n"
               "/new_jee - Start JEE-level mixed game\n"
               "/hint - Buy hint (-50)\n"
               "/endgame - Stop the game\n"
               "/mystats - View profile\n"
               "/balance - Check hint balance\n"
               "/leaderboard - Top players\n"
               "/scorecard - Personal session score\n"
               "/issue - Report issue\n"
               "/plans - Buy points info\n"
               "/define <word> - Get definition\n"
               "/achievements - Your achievements\n"
               "/status - Bot stats (Owner)\n"
               "/settings - Bot settings (Owner)\n"
               "/addpoints <username_or_id> <amount> [balance|score] (Owner)  <-- now defaults to balance\n"
               "/addadmin <username_or_id> (Owner)\n"
               "/deladmin <username_or_id> (Owner)\n"
               "/admins - list admins\n"
               "/set_hint_cost <amount> (Owner)\n"
               "/toggle_force_join (Owner)\n"
               "/set_start_image <url> (Owner)\n"
               "/show_settings (Owner)\n"
               "/restart (Owner)\n"
               "/reset_leaderboard (Owner)\n"
               "/broadcast <message> (Owner)")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        ok = send_text_with_fallback(cid, txt, reply_markup=markup)
        try:
            if ok: bot.answer_callback_query(c.id, "Opened commands.")
            else: bot.answer_callback_query(c.id, "❌ Could not open commands.", show_alert=True)
        except: pass
        return

    if data == 'menu_lb':
        top = db.get_top_players(10)
        txt = "🏆 <b>Global Leaderboard</b>\n\n"
        for idx, (name, score) in enumerate(top, 1):
            txt += f"{idx}. <b>{html.escape(name)}</b> : {score} pts\n"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        ok = send_text_with_fallback(cid, txt, reply_markup=markup)
        try:
            if ok: bot.answer_callback_query(c.id, "Opened leaderboard.")
            else: bot.answer_callback_query(c.id, "❌ Could not open leaderboard.", show_alert=True)
        except: pass
        return

    if data == 'menu_back':
        try:
            show_main_menu(c.message)
            try: bot.answer_callback_query(c.id, "Menu opened.")
            except: pass
        except:
            try: bot.answer_callback_query(c.id, "❌ Could not open menu.", show_alert=True)
            except: pass
        return

    if data == 'menu_stats':
        try:
            user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
            session_points = 0
            gid = c.message.chat.id
            if gid in games:
                session_points = games[gid].players_scores.get(uid, 0)
            # user tuple indices: 0:id,1:name,2:join_date,3:games_played,4:wins,5:total_score,6:hint_balance,7:is_banned,8:cash_balance
            cash_bal = user[8] if len(user) > 8 else 0
            txt = (f"📋 <b>Your Stats</b>\n"
                   f"Name: {html.escape(user[1])}\n"
                   f"Total Score: {user[5]}\n"
                   f"Wins: {user[4]}\n"
                   f"Games Played: {user[3]}\n"
                   f"Session Points (this chat): {session_points}\n"
                   f"Hint Balance: {user[6]}\n"
                   f"Cash Balance (₹): {cash_bal}")
            ok = send_text_with_fallback(c.message.chat.id, txt)
            try:
                if ok: bot.answer_callback_query(c.id, "Stats opened.")
                else: bot.answer_callback_query(c.id, "❌ Could not open stats.", show_alert=True)
            except: pass
        except Exception:
            logger.exception("menu_stats handler error")
            try: bot.answer_callback_query(c.id, "❌ Could not open stats.", show_alert=True)
            except: pass
        return

    # Game callbacks (unchanged logic; kept robust)
    if data == 'game_guess':
        if cid not in games:
            try: bot.answer_callback_query(c.id, "❌ Game Over or Expired.", show_alert=True)
            except: pass
            return
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            try: bot.answer_callback_query(c.id, "✍️ Type your guess.")
            except: pass
        except Exception:
            logger.exception("game_guess handler error")
            try: bot.answer_callback_query(c.id, "❌ Could not open input.", show_alert=True)
            except: pass
        return

    if data == 'game_hint':
        if cid not in games:
            try: bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            except: pass
            return
        user_data = db.get_user(uid, c.from_user.first_name)
        if user_data and user_data[6] < HINT_COST:
            try: bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user_data[6]}", show_alert=True)
            except: pass
            return
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            try: bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            except: pass
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, score_delta=0, hint_delta=-HINT_COST)
        try:
            bot.send_message(cid, f"💡 <b>HINT:</b> <code>{reveal}</code>\nUser: {html.escape(c.from_user.first_name)} (-{HINT_COST} pts)")
            try: bot.answer_callback_query(c.id, "Hint revealed.")
            except: pass
        except Exception:
            logger.exception("game_hint send failed")
            try: bot.answer_callback_query(c.id, "❌ Could not send hint.", show_alert=True)
            except: pass
        return

    if data == 'game_score':
        if cid not in games:
            try: bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            except: pass
            return
        game = games[cid]
        if not game.players_scores:
            try: bot.answer_callback_query(c.id, "No scores yet. Be the first!", show_alert=True)
            except: pass
            return
        leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        rows = []
        for i, (uid_score, pts) in enumerate(leaderboard, 1):
            try:
                user = db.get_user(uid_score, "Player")
                name = user[1] if user else str(uid_score)
            except:
                name = str(uid_score)
            rows.append((i, name, pts))
        img_bio = LeaderboardRenderer.draw_session_leaderboard(rows[:10])
        try:
            bot.send_photo(cid, img_bio, caption="📊 Session Leaderboard")
            try: bot.answer_callback_query(c.id, "Leaderboard shown.")
            except: pass
        except:
            txt = "📊 Session Leaderboard\n\n"
            for idx, name, pts in rows[:10]:
                txt += f"{idx}. {html.escape(name)} - {pts} pts\n"
            ok = send_text_with_fallback(cid, txt)
            try:
                if ok: bot.answer_callback_query(c.id, "Leaderboard opened.")
                else: bot.answer_callback_query(c.id, "❌ Could not show leaderboard.", show_alert=True)
            except: pass
        return

    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

# ==========================================
# Game start functions (support modes), hint, issue, scorecard, etc.
# (Reused from previous version)
# ==========================================

def start_game_with_mode(m, mode='default'):
    cid = m.chat.id
    if cid in games:
        if time.time() - games[cid].last_activity < GAME_DURATION:
            bot.reply_to(m, "⚠️ A game is already active here! Finish it or use /endgame.")
            return
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    if u and u[7] == 1:
        bot.reply_to(m, "🚫 You are banned from playing.")
        return
    bot.send_chat_action(cid, 'upload_photo')
    is_hard = (mode == 'hard')
    pool = None
    if mode == 'physics':
        pool = PHYSICS_WORDS
    elif mode == 'chemistry':
        pool = CHEMISTRY_WORDS
    elif mode == 'jee':
        pool = JEE_WORDS
    session = GameSession(cid, is_hard, duration=GAME_DURATION, word_pool=pool)
    games[cid] = session
    db.update_stats(m.from_user.id, games_played_delta=1)
    img_bio = GridRenderer.draw(session.grid, placements=session.placements, found=session.found, is_hard=is_hard)
    try:
        img_bio.seek(0)
    except:
        pass
    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
               f"Mode: {'Hard (10x10)' if is_hard else 'Normal (8x8)'}\n"
               f"⏱ Time Limit: {session.duration//60} minutes\n\n"
               f"<b>👇 WORDS TO FIND:</b>\n"
               f"{session.get_hint_text()}")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'))
    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
               InlineKeyboardButton("📊 Score", callback_data='game_score'))
    sent_msg = None
    try:
        sent_msg = bot.send_photo(cid, img_bio, caption=caption, reply_markup=markup)
    except Exception:
        logger.exception("send_photo failed, fallback to temp file")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                tf.write(img_bio.getvalue())
                temp_path = tf.name
            with open(temp_path, 'rb') as f:
                sent_msg = bot.send_photo(cid, f, caption=caption, reply_markup=markup)
            try: os.unlink(temp_path)
            except: pass
        except Exception:
            try:
                bot.send_message(cid, caption, reply_markup=markup)
            except Exception:
                logger.exception("Failed to send game start message")
    try:
        if sent_msg:
            session.message_id = sent_msg.message_id
    except Exception:
        logger.exception("Could not set session.message_id")
    try:
        session.start_timer()
    except Exception:
        logger.exception("Failed to start session timer")
    if OWNER_ID:
        try:
            starter_name = m.from_user.first_name or m.from_user.username or str(m.from_user.id)
            bot.send_message(OWNER_ID, f"🎮 Game started in chat {cid} by {starter_name} (ID: {m.from_user.id}). Mode: {mode}")
        except Exception:
            logger.exception("Failed to notify owner about new game")

@bot.message_handler(commands=['new'])
def start_game(m):
    start_game_with_mode(m, mode='default')

@bot.message_handler(commands=['new_hard'])
def start_game_hard(m):
    start_game_with_mode(m, mode='hard')

@bot.message_handler(commands=['new_physics'])
def start_game_physics(m):
    start_game_with_mode(m, mode='physics')

@bot.message_handler(commands=['new_chemistry'])
def start_game_chem(m):
    start_game_with_mode(m, mode='chemistry')

@bot.message_handler(commands=['new_jee'])
def start_game_jee(m):
    start_game_with_mode(m, mode='jee')

@bot.message_handler(commands=['hint'])
def hint_cmd(m):
    cid = m.chat.id
    uid = m.from_user.id
    if cid not in games:
        bot.reply_to(m, "❌ No active game in this chat.")
        return
    user_data = db.get_user(uid, m.from_user.first_name)
    if user_data and user_data[6] < HINT_COST:
        bot.reply_to(m, f"❌ You need {HINT_COST} pts to buy a hint. Balance: {user_data[6]}")
        return
    game = games[cid]
    hidden = [w for w in game.words if w not in game.found]
    if not hidden:
        bot.reply_to(m, "All words already found!")
        return
    reveal = random.choice(hidden)
    db.update_stats(uid, score_delta=0, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 HINT: <code>{reveal}</code> (-{HINT_COST} pts)")

@bot.message_handler(commands=['issue'])
def report_issue(m):
    issue = m.text.replace("/issue", "").strip()
    if not issue:
        bot.reply_to(m, "Usage: /issue <message>\nOr use the 'Report Issue' button from the menu.")
        return
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🚨 <b>REPORT</b>\nFROM: {m.from_user.first_name} ({m.from_user.id})\nMSG: {issue}")
            bot.reply_to(m, "✅ Report sent to Developer.")
        except Exception:
            logger.exception("Failed sending issue to owner")
            bot.reply_to(m, "❌ Could not send. Owner might not be reachable.")
    else:
        bot.reply_to(m, "⚠️ Owner not configured.")

@bot.message_handler(commands=['ping'])
def ping(m):
    t0 = time.time()
    try:
        bot.send_chat_action(m.chat.id, 'typing')
    except:
        pass
    t1 = time.time()
    ms = int((t1 - t0) * 1000)
    bot.reply_to(m, f"Pong! 🏓 {ms} ms")

@bot.message_handler(commands=['scorecard'])
def scorecard(m):
    uid = m.from_user.id
    u = db.get_user(uid, m.from_user.first_name)
    session_points = 0
    gid = m.chat.id
    if gid in games:
        session_points = games[gid].players_scores.get(uid, 0)
    cash_bal = u[8] if len(u) > 8 else 0
    txt = (f"📋 <b>Your Scorecard</b>\n"
           f"Name: {html.escape(u[1])}\n"
           f"Total Score: {u[5]}\n"
           f"Wins: {u[4]}\n"
           f"Session Points (this chat): {session_points}\n"
           f"Hint Balance: {u[6]}\n"
           f"Cash Balance (₹): {cash_bal}")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['mystats'])
def mystats(m):
    scorecard(m)

@bot.message_handler(commands=['balance'])
def balance(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"💰 Your balance: {u[6]} pts")

@bot.message_handler(commands=['leaderboard'])
def leaderboard(m):
    top = db.get_top_players()
    txt = "🏆 <b>TOP 10 PLAYERS</b> 🏆\n\n"
    for i, (name, score) in enumerate(top, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        txt += f"{medal} <b>{html.escape(name)}</b> - {score} pts\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['endgame'])
def force_end(m):
    cid = m.chat.id
    if cid in games:
        if not is_admin_or_owner(m.from_user.id):
            bot.reply_to(m, "Only an admin or owner can force-stop the game.")
            return
        end_game_session(cid, "stopped")
    else:
        bot.reply_to(m, "No active game to stop.")

# ==========================================
# Admin commands: addpoints (default -> hint balance), addadmin, deladmin, admins, settings, restart, reset_leaderboard, broadcast
# ==========================================

@bot.message_handler(commands=['addpoints'])
def addpoints_cmd(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "❌ Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <username_or_id> <amount> [balance|score]\nNote: default is balance (hint balance). Use 'score' to add to score.")
        return
    target = parts[1].strip()
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be a number.")
        return
    mode = parts[3].strip().lower() if len(parts) >= 4 else 'balance'
    target_id = None
    chat = None
    if target.lstrip('-').isdigit():
        target_id = int(target)
    else:
        if not target.startswith('@'):
            target = '@' + target
        try:
            chat = bot.get_chat(target)
            target_id = chat.id
        except Exception as e:
            bot.reply_to(m, f"❌ Could not find user {target}. They must have a public username or have started the bot.")
            return
    db.get_user(target_id, getattr(chat, 'username', 'Player') if chat else 'Player')
    try:
        if mode == 'score':
            # add to total_score (this will auto-redeem if threshold reached)
            db.update_stats(target_id, score_delta=amount)
            bot.reply_to(m, f"✅ Added {amount} points to score of {target} (ID: {target_id}).")
        else:
            # default: add to hint balance
            db.update_stats(target_id, score_delta=0, hint_delta=amount)
            bot.reply_to(m, f"✅ Added {amount} to hint balance of {target} (ID: {target_id}).")
        try:
            bot.send_message(target_id, f"💸 You received {amount} pts ({mode}) from the owner.")
        except:
            pass
    except Exception as e:
        bot.reply_to(m, f"❌ Failed to add points: {e}")

@bot.message_handler(commands=['broadcast'])
@owner_only
def broadcast_cmd(m):
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
        except Exception:
            fail += 1
    bot.reply_to(m, f"Broadcast complete. Success: {success}, Failed: {fail}")

@bot.message_handler(commands=['addadmin'])
@owner_only
def addadmin_cmd(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /addadmin <username_or_id>")
        return
    target = parts[1].strip()
    admin_id = None
    chat = None
    if target.lstrip('-').isdigit():
        admin_id = int(target)
    else:
        if not target.startswith('@'):
            target = '@' + target
        try:
            chat = bot.get_chat(target)
            admin_id = chat.id
        except Exception:
            bot.reply_to(m, f"❌ Could not find user {target}. They must have a public username or have started the bot.")
            return
    db.add_admin(admin_id)
    bot.reply_to(m, f"✅ Added admin: {admin_id}")
    try:
        bot.send_message(admin_id, "✅ You have been made an admin for Word Vortex Bot.")
    except:
        pass

@bot.message_handler(commands=['deladmin'])
@owner_only
def deladmin_cmd(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /deladmin <username_or_id>")
        return
    target = parts[1].strip()
    admin_id = None
    if target.lstrip('-').isdigit():
        admin_id = int(target)
    else:
        if not target.startswith('@'):
            target = '@' + target
        try:
            chat = bot.get_chat(target)
            admin_id = chat.id
        except Exception:
            bot.reply_to(m, f"❌ Could not find user {target}.")
            return
    db.remove_admin(admin_id)
    bot.reply_to(m, f"✅ Removed admin: {admin_id}")

@bot.message_handler(commands=['admins'])
def admins_cmd(m):
    admins = db.list_admins()
    txt = "🔧 Current Admins:\n"
    for a in admins:
        txt += f"- {a}\n"
    if OWNER_ID:
        txt += f"\nOwner: {OWNER_ID}"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['set_hint_cost'])
@owner_only
def set_hint_cost(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /set_hint_cost <amount>")
        return
    global HINT_COST
    try:
        HINT_COST = int(parts[1])
        bot.reply_to(m, f"✅ HINT_COST set to {HINT_COST}")
    except:
        bot.reply_to(m, "Amount must be an integer.")

@bot.message_handler(commands=['toggle_force_join'])
@owner_only
def toggle_force_join(m):
    global FORCE_JOIN
    FORCE_JOIN = not FORCE_JOIN
    bot.reply_to(m, f"✅ FORCE_JOIN is now {FORCE_JOIN}")

@bot.message_handler(commands=['set_start_image'])
@owner_only
def set_start_image(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /set_start_image <image_url>")
        return
    global START_IMG_URL
    START_IMG_URL = parts[1].strip()
    bot.reply_to(m, "✅ START image updated.")

@bot.message_handler(commands=['show_settings'])
@owner_only
def show_settings(m):
    txt = (f"🔧 Settings:\n\n"
           f"FORCE_JOIN: {FORCE_JOIN}\n"
           f"HINT_COST: {HINT_COST}\n"
           f"START_IMG_URL: {START_IMG_URL}\n"
           f"CHANNEL_USERNAME: {CHANNEL_USERNAME}\n"
           f"SUPPORT_GROUP_LINK: {SUPPORT_GROUP_LINK}\n"
           f"REDEEM_THRESHOLD: {REDEEM_THRESHOLD}\n"
           f"REDEEM_AMOUNT_RS: {REDEEM_AMOUNT_RS}\n")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['restart'])
@owner_only
def restart_cmd(m):
    bot.reply_to(m, "🔁 Restarting bot now...")
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception:
        logger.exception("Restart via exec failed, exiting.")
        os._exit(0)

@bot.message_handler(commands=['reset_leaderboard'])
@owner_only
def reset_leaderboard_cmd(m):
    try:
        db.reset_leaderboard()
        bot.reply_to(m, "✅ Leaderboard reset. All players' scores and wins set to 0.")
    except Exception:
        logger.exception("reset_leaderboard failed")
        bot.reply_to(m, "❌ Failed to reset leaderboard.")

# ==========================================
# /define and other handlers
# ==========================================
@bot.message_handler(commands=['define'])
def define_cmd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /define <word>")
        return
    word = parts[1].strip()
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        resp = requests.get(url, timeout=8)
        data = resp.json()
        if isinstance(data, list) and data:
            meanings = data[0].get('meanings', [])
            if meanings:
                defs = meanings[0].get('definitions', [])
                if defs:
                    definition = defs[0].get('definition', 'No definition found.')
                    example = defs[0].get('example', '')
                    txt = f"📚 <b>{word}</b>\n{definition}"
                    if example:
                        txt += f"\n\n<i>Example:</i> {example}"
                    bot.reply_to(m, txt)
                    return
        bot.reply_to(m, f"❌ No definition found for '{word}'.")
    except Exception:
        logger.exception("define error")
        bot.reply_to(m, "❌ Error fetching definition.")

# ==========================================
# Guess processing (updates image with line) - same as previous version but kept here
# ==========================================
def process_word_guess(m):
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
    game = games[cid]
    uid = m.from_user.id
    user_name = m.from_user.first_name or (m.from_user.username or "Player")
    last = game.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        try:
            bot.reply_to(m, f"⏳ Slow down! Wait {COOLDOWN} seconds between guesses.")
        except:
            pass
        return
    game.players_last_guess[uid] = now
    try:
        bot.delete_message(cid, m.message_id)
    except:
        pass
    if word in game.words:
        if word in game.found:
            try:
                msg = bot.send_message(cid, f"⚠️ <b>{word}</b> is already found!")
                threading.Timer(3, lambda: bot.delete_message(cid, msg.message_id)).start()
            except:
                pass
        else:
            game.found.add(word)
            game.last_activity = time.time()
            if len(game.found) == 1:
                points = FIRST_BLOOD_POINTS
            elif len(game.found) == len(game.words):
                points = FINISHER_POINTS
            else:
                points = NORMAL_POINTS
            prev = game.players_scores.get(uid, 0)
            game.players_scores[uid] = prev + points
            # Add points to user's total_score (this will trigger auto-redeem if threshold crossed)
            db.update_stats(uid, score_delta=points)
            try:
                reply = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(user_name)} found <code>{word}</code> (+{points} pts) 🎯")
                threading.Timer(5, lambda: bot.delete_message(cid, reply.message_id)).start()
            except:
                pass
            # regenerate image with lines and replace previous photo
            try:
                img_bio = GridRenderer.draw(game.grid, placements=game.placements, found=game.found, is_hard=game.is_hard)
                try:
                    img_bio.seek(0)
                except:
                    pass
                sent_msg = None
                try:
                    sent_msg = bot.send_photo(cid, img_bio, caption=(f"🔥 <b>WORD VORTEX</b>\n"
                                                                    f"Mode: {'Hard' if game.is_hard else 'Normal'}\n"
                                                                    f"⏱ Time Left: {(max(0, int(game.duration - (time.time() - game.start_time)))//60)}:{(max(0, int(game.duration - (time.time() - game.start_time)))%60):02d}\n\n"
                                                                    f"<b>👇 WORDS TO FIND:</b>\n{game.get_hint_text()}"),
                                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'),
                                                                                      InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
                                                                                      InlineKeyboardButton("📊 Score", callback_data='game_score')))
                except Exception:
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                            tf.write(img_bio.getvalue())
                            temp_path = tf.name
                        with open(temp_path, 'rb') as f:
                            sent_msg = bot.send_photo(cid, f, caption=(f"🔥 <b>WORD VORTEX</b>\n"
                                                                      f"Mode: {'Hard' if game.is_hard else 'Normal'}\n"
                                                                      f"⏱ Time Left: {(max(0, int(game.duration - (time.time() - game.start_time)))//60)}:{(max(0, int(game.duration - (time.time() - game.start_time)))%60):02d}\n\n"
                                                                      f"<b>👇 WORDS TO FIND:</b>\n{game.get_hint_text()}"),
                                                  reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'),
                                                                                          InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
                                                                                          InlineKeyboardButton("📊 Score", callback_data='game_score')))
                        try:
                            os.unlink(temp_path)
                        except:
                            pass
                    except Exception:
                        logger.exception("Failed to send updated grid image")
                try:
                    old_mid = game.message_id
                    if old_mid:
                        try:
                            bot.delete_message(cid, old_mid)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    if sent_msg:
                        game.message_id = sent_msg.message_id
                except Exception:
                    logger.exception("Could not set new session.message_id")
            except Exception:
                logger.exception("Error regenerating grid image after found word")
            if len(game.found) == len(game.words):
                end_game_session(cid, "win", uid)
    else:
        try:
            msg = bot.send_message(cid, f"❌ {html.escape(user_name)} — '{html.escape(word)}' is not in the list.")
            threading.Timer(3, lambda: bot.delete_message(cid, msg.message_id)).start()
        except:
            pass

def end_game_session(cid, reason, winner_id=None):
    if cid not in games:
        return
    game = games[cid]
    try:
        game.active = False
    except:
        pass

    if reason == "win":
        winner = db.get_user(winner_id, "Unknown")
        db.update_stats(winner_id, score_delta=0, win=True)
        db.record_game(cid, winner_id)
        top_players = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        summary = ""
        for idx, (uid_score, pts) in enumerate(top_players, 1):
            try:
                user = db.get_user(uid_score, "Player")
                name = user[1] if user else str(uid_score)
            except:
                name = str(uid_score)
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            summary += f"{medal} <b>{html.escape(name)}</b> - {pts} pts\n"
        txt = (f"🏆 <b>GAME OVER! VICTORY!</b>\n\n"
               f"👑 <b>MVP:</b> {html.escape(winner[1])}\n"
               f"✅ All {len(game.words)} words found!\n\n"
               f"<b>Session Standings:</b>\n{summary}\n"
               f"Type <code>/new</code> to play again.")
        try:
            bot.send_message(cid, txt)
        except Exception:
            logger.exception("Failed to send win summary")
    elif reason == "stopped":
        try:
            bot.send_message(cid, "🛑 Game stopped manually.")
        except Exception:
            logger.exception("Failed to send stopped message")
    elif reason == "timeout":
        found_count = len(game.found)
        remaining = [w for w in game.words if w not in game.found]
        top_players = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        summary = ""
        for idx, (uid_score, pts) in enumerate(top_players, 1):
            try:
                user = db.get_user(uid_score, "Player")
                name = user[1] if user else str(uid_score)
            except:
                name = str(uid_score)
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            summary += f"{medal} <b>{html.escape(name)}</b> - {pts} pts\n"
        rem_txt = ", ".join(remaining) if remaining else "None"
        txt = (f"⏰ <b>TIME'S UP!</b>\n\n"
               f"✅ Found: {found_count}/{len(game.words)} words\n"
               f"❌ Remaining: {rem_txt}\n\n"
               f"<b>Session Standings:</b>\n{summary}\n"
               f"Type <code>/new</code> to play again.")
        try:
            bot.send_message(cid, txt)
        except Exception:
            logger.exception("Failed to send timeout summary")
    try:
        del games[cid]
    except KeyError:
        pass

# ==========================================
# SERVER STARTUP
# ==========================================
@app.route('/')
def index():
    return "Word Vortex Bot is Running! 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("✅ System Online. Connected to Telegram.")
    print("✅ Database Loaded.")
    print("✅ Image Engine Ready.")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"⚠️ Polling Error: {e}")
            time.sleep(5)
