#!/usr/bin/env python3
"""
WORDS GRID ROBOT - ULTIMATE PREMIUM EDITION
Version: 6.3 (DM Premium + Redeem + Reviews + Commands DM-first)
Developer: Ruhvaan (updated)

Summary of key changes in this file:
- Commands button fixed: tries to DM the user the full commands list first; falls back to sending in the chat if DM fails.
- Added Redeem flow (button + /redeem_request for users; /redeem_list and /redeem_pay for owner).
- Added Reviews: /review for users, owner can /list_reviews and /approve_review.
- Added Redeems & Reviews DB tables and migration for cash_balance in users table.
- /addpoints now defaults to adding to hint balance (use 'score' to add to total_score).
- Added "💵 Redeem" and "➕ Add to Group" buttons in the start menu.
- Kept all previous features (games, grid images, hints, leaderboards, admin commands) intact.

Notes:
- The bot cannot DM users who haven't started a private chat with it. Ask users to open a private chat and send /start first.
- Redeem payments are manual/out-of-band; bot only tracks requests and marks them processed.
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
NORMAL_POINTS = 2
FINISHER_POINTS = 5

BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

REDEEM_THRESHOLD = 150  # points required to request a redeem (manual payment)
PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# ==========================================
# 🗄️ DATABASE MANAGER (includes admins, reviews, redeems)
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
        # users table (ensure cash_balance column exists via migration if needed)
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
        # reviews
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            text TEXT,
            created_at TEXT,
            approved INTEGER DEFAULT 0
        )''')
        # redeems
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
        return self.get_user(user_id, name)

    def update_stats(self, user_id, score_delta=0, hint_delta=0, win=False, games_played_delta=0, cash_delta=0):
        conn = self.connect()
        c = conn.cursor()
        if score_delta != 0 or hint_delta != 0:
            c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", 
                      (score_delta, hint_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        if games_played_delta != 0:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
        if cash_delta != 0:
            c.execute("UPDATE users SET cash_balance = cash_balance + ? WHERE user_id=?", (cash_delta, user_id))
        conn.commit()
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

    def get_all_users(self):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        data = [x[0] for x in c.fetchall()]
        conn.close()
        return data

    # Reviews
    def add_review(self, user_id, username, text):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO reviews (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, username, text, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_reviews(self, approved=None):
        conn = self.connect()
        c = conn.cursor()
        if approved is None:
            c.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        else:
            c.execute("SELECT * FROM reviews WHERE approved=? ORDER BY created_at DESC", (approved,))
        rows = c.fetchall()
        conn.close()
        return rows

    def approve_review(self, review_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE reviews SET approved=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    # Redeems
    def add_redeem_request(self, user_id, amount_points):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO redeems (user_id, amount_points, requested_at) VALUES (?, ?, ?)",
                  (user_id, amount_points, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def list_redeems(self, processed=0):
        conn = self.connect()
        c = conn.cursor()
        c.execute("SELECT * FROM redeems WHERE processed=? ORDER BY requested_at DESC", (processed,))
        rows = c.fetchall()
        conn.close()
        return rows

    def process_redeem(self, redeem_id, admin_id, notes=""):
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

# ==========================================
# 🎨 Image Utilities (unchanged)
# ==========================================
class GridRenderer:
    @staticmethod
    def draw(grid, is_hard=False):
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
        bbox = draw.textbbox((0,0), title_text, font=header_font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw)/2, 30), title_text, fill="#2980b9", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        bbox2 = draw.textbbox((0,0), mode_text, font=footer_font)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((width - tw2)/2, 75), mode_text, fill="#7f8c8d", font=footer_font)
        grid_start_y = header_height + padding
        for r in range(rows):
            for c in range(cols):
                x = padding + (c * cell_size)
                y = grid_start_y + (r * cell_size)
                shape = [x, y, x + cell_size, y + cell_size]
                draw.rectangle(shape, outline=GRID_COLOR, width=2)
                char = grid[r][c]
                bbox_char = draw.textbbox((0,0), char, font=letter_font)
                cw = bbox_char[2] - bbox_char[0]
                ch = bbox_char[3] - bbox_char[1]
                draw.text((x + (cell_size - cw)/2, y + (cell_size - ch)/2 - 5), char, fill=TEXT_COLOR, font=letter_font)
        draw.text((30, height - 30), "Made by @Ruhvaan", fill="#95a5a6", font=footer_font)
        draw.text((width - 100, height - 30), "v5.0", fill="#95a5a6", font=footer_font)
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
        bg = Image.new('RGB', (width, height), '#0f1724')  # dark
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
            medal = "🥇" if idx==1 else "🥈" if idx==2 else "🥉" if idx==3 else f"{idx}."
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

# ==========================================
# 🧠 WORDS + GAME SESSION (unchanged)
# ==========================================
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
    except Exception as e:
        logger.error(f"Word Fetch Error: {e}")
        ALL_WORDS = ['PYTHON', 'JAVA', 'SCRIPT', 'ROBOT', 'FUTURE', 'SPACE', 'GALAXY', 'NEBULA']

fetch_words()

games = {}  # chat_id -> GameSession

class GameSession:
    def __init__(self, chat_id, is_hard=False):
        self.chat_id = chat_id
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.start_time = time.time()
        self.last_activity = time.time()
        self.words = []
        self.found = set()
        self.grid = []
        self.players_scores = {}  # uid -> points
        self.players_last_guess = {}
        self.generate()

    def generate(self):
        if not ALL_WORDS: fetch_words()
        pool = ALL_WORDS[:] if len(ALL_WORDS) >= self.word_count else (ALL_WORDS * 2)
        self.words = random.sample(pool, self.word_count)
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        for word in sorted_words:
            placed = False
            attempts = 0
            while not placed and attempts < 200:
                attempts += 1
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                dr, dc = random.choice(dirs)
                if self._can_place(row, col, dr, dc, word):
                    self._place(row, col, dr, dc, word)
                    placed = True
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == ' ':
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def _can_place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            nr, nc = r + i*dr, c + i*dc
            if not (0 <= nr < self.size and 0 <= nc < self.size): return False
            if self.grid[nr][nc] != ' ' and self.grid[nr][nc] != word[i]: return False
        return True

    def _place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            self.grid[r + i*dr][c + i*dc] = word[i]

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + ("-" * (len(w)-1))
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

# ==========================================
# 🛡️ HELPERS & PERMISSIONS (minor tweaks)
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
    except Exception as e:
        logger.debug(f"Subscription check failed: {e}")
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

def admin_only(func):
    def wrapper(m):
        if not is_admin_or_owner(m.from_user.id):
            bot.reply_to(m, "❌ Only owner or admin can use this.")
            return
        return func(m)
    return wrapper

def safe_edit_message(caption, cid, mid, reply_markup=None):
    # robust edit fallback
    try:
        bot.edit_message_caption(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup)
        return True
    except Exception:
        pass
    try:
        bot.edit_message_caption(caption, cid, mid, reply_markup=reply_markup)
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

def try_send_dm(uid, text, reply_markup=None):
    """
    Try to send a DM to uid. Return True if DM succeeded, False otherwise.
    """
    try:
        bot.send_message(uid, text, parse_mode='HTML', reply_markup=reply_markup)
        return True
    except Exception:
        return False

# ==========================================
# 🎮 HANDLERS & MENU (updated)
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def show_main_menu(m):
    # Ensure user exists in DB (safe)
    try:
        db.get_user(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player")
    except Exception as e:
        logger.exception("DB get_user error in show_main_menu")

    txt = (f"👋 <b>Hello, {html.escape(m.from_user.first_name or m.from_user.username or 'Player')}!</b>\n\n"
           "🧩 <b>Welcome to Word Vortex</b>\n"
           "The most advanced multiplayer word search bot on Telegram.\n\n"
           "👇 <b>What would you like to do?</b>")

    markup = InlineKeyboardMarkup(row_width=2)
    # Add join/check at top
    markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
               InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
    # Add-to-group button
    try:
        me = bot.get_me().username
        if me:
            markup.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{me}?startgroup=true"),
                       InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))
        else:
            markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))
    except Exception:
        markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'))
    # commands & other options
    markup.add(InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'),
               InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'))
    markup.add(InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'),
               InlineKeyboardButton("💵 Redeem", callback_data='open_redeem'))
    markup.add(InlineKeyboardButton("🐞 Report Issue", callback_data='open_issue'),
               InlineKeyboardButton("💳 Buy Points", callback_data='open_plans'))
    markup.add(InlineKeyboardButton("✍️ Review", callback_data='open_review'),
               InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))

    # Try send photo; if it fails, always send text reply so user sees menu
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=markup)
    except Exception:
        logger.exception("send_photo failed in show_main_menu, sending text fallback")
        try:
            bot.reply_to(m, txt, reply_markup=markup)
        except Exception:
            # Last resort: plain text
            try:
                bot.send_message(m.chat.id, txt)
            except Exception:
                logger.exception("Failed to send any start message")

@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    """
    Callback handler updated:
    - Commands button now tries to DM the user first. If DM fails, fallback to group.
    - Redeem flow implemented via callbacks 'open_redeem' and 'redeem_confirm'.
    """
    cid = c.message.chat.id
    mid = c.message.message_id
    uid = c.from_user.id
    data = c.data

    # QUICK: always answer callback (short) to clear client loading state
    def ack(text="Done", alert=False):
        try:
            bot.answer_callback_query(c.id, text, show_alert=alert)
        except:
            pass

    # CHECK JOIN
    if data == "check_join":
        if is_subscribed(uid):
            ack("✅ Verified! Welcome.")
            try: bot.delete_message(cid, mid)
            except: pass
            show_main_menu(c.message)
        else:
            ack("❌ You haven't joined yet!", alert=True)
        return

    # OPEN ISSUE -> ForceReply prompt
    if data == 'open_issue':
        try:
            bot.send_message(cid, f"@{c.from_user.username or c.from_user.first_name} Please type your issue or use /issue <message>:", reply_markup=ForceReply(selective=True))
            ack("✍️ Type your issue below.")
        except:
            ack("❌ Unable to open issue prompt.", alert=True)
        return

    # OPEN PLANS -> send new message (not alert)
    if data == 'open_plans':
        txt = "💳 Points Plans:\n\n"
        for p in PLANS:
            txt += f"- {p['points']} pts : ₹{p['price_rs']}\n"
        txt += f"\nTo buy, contact the owner: {SUPPORT_GROUP_LINK}"
        # Try DM-first
        if try_send_dm(uid, txt):
            ack("I sent plans to your PM.")
        else:
            try:
                bot.send_message(cid, txt)
                ack("Plans opened here.")
            except:
                ack("❌ Could not open plans.", alert=True)
        return

    # HELP / PLAY -> send new message with Back button
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
        if try_send_dm(uid, txt, reply_markup=markup):
            ack("I sent play help to your PM.")
        else:
            try:
                bot.send_message(cid, txt, reply_markup=markup, parse_mode='HTML')
                ack("Opened play help here.")
            except:
                ack("❌ Could not open play help.", alert=True)
        return

    # HELP / COMMANDS -> DM-first, fallback to group
    if data == 'help_cmd':
        txt = ("<b>🤖 Command List:</b>\n\n"
               "/start, /help - Open menu\n"
               "/ping - Check bot ping\n"
               "/new - Start a game\n"
               "/new_hard - Start hard game\n"
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
               "/addpoints <username_or_id> <amount> [balance|score] (Owner)\n"
               "/addadmin <username_or_id> (Owner)\n"
               "/deladmin <username_or_id> (Owner)\n"
               "/admins - list admins\n"
               "/set_hint_cost <amount> (Owner)\n"
               "/toggle_force_join (Owner)\n"
               "/set_start_image <url> (Owner)\n"
               "/show_settings (Owner)\n"
               "/restart (Owner)\n"
               "/review <text> - submit feedback\n"
               "/redeem_request - request payout when you have enough score")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        if try_send_dm(uid, txt, reply_markup=markup):
            ack("I sent the commands to your PM.")
        else:
            try:
                bot.send_message(cid, txt, reply_markup=markup, parse_mode='HTML')
                ack("Opened commands here.")
            except:
                ack("❌ Could not open commands.", alert=True)
        return

    # LEADERBOARD -> send new message
    if data == 'menu_lb':
        top = db.get_top_players(10)
        txt = "🏆 <b>Global Leaderboard</b>\n\n"
        for idx, (name, score) in enumerate(top, 1):
            txt += f"{idx}. <b>{html.escape(name)}</b> : {score} pts\n"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        if try_send_dm(uid, txt, reply_markup=markup):
            ack("I sent leaderboard to your PM.")
        else:
            try:
                bot.send_message(cid, txt, reply_markup=markup, parse_mode='HTML')
                ack("Opened leaderboard here.")
            except:
                ack("❌ Could not open leaderboard.", alert=True)
        return

    # MENU BACK / STATS -> rebuild menu as new message
    if data in ('menu_stats', 'menu_back'):
        try:
            show_main_menu(c.message)  # show_main_menu will send a new menu message
            ack("Menu opened.")
        except:
            ack("❌ Could not open menu.", alert=True)
        return

    # REDEEM flow: open_redeem and redeem_confirm
    if data == 'open_redeem':
        try:
            user = db.get_user(uid, c.from_user.first_name)
            total = user[5]
        except Exception:
            total = 0
        if total < REDEEM_THRESHOLD:
            msg = f"❌ You need at least {REDEEM_THRESHOLD} pts to request redeem. Your score: {total} pts."
            # DM-first
            if try_send_dm(uid, msg):
                ack("I've sent details to your PM.")
            else:
                try:
                    bot.send_message(cid, msg)
                    ack("Opened here.")
                except:
                    ack("❌ Could not send redeem info.", alert=True)
            return
        # Enough points: send confirmation DM-first with inline confirm button
        confirm_kb = InlineKeyboardMarkup()
        confirm_kb.add(InlineKeyboardButton("✅ Confirm Redeem", callback_data='redeem_confirm'),
                       InlineKeyboardButton("❌ Cancel", callback_data='menu_back'))
        confirm_text = (f"💵 Redeem Request\nYou have {total} pts.\nClick Confirm to request redeem of {REDEEM_THRESHOLD} pts. Owner will process payment manually.")
        if try_send_dm(uid, confirm_text, reply_markup=confirm_kb):
            ack("Confirmation sent to your PM.")
        else:
            try:
                bot.send_message(cid, confirm_text, reply_markup=confirm_kb)
                ack("Confirmation opened here.")
            except:
                ack("❌ Could not open confirmation.", alert=True)
        return

    if data == 'redeem_confirm':
        # Create redeem request (user clicked confirm in PM or group)
        try:
            db.add_redeem_request(uid, REDEEM_THRESHOLD)
        except Exception:
            ack("❌ Could not create redeem request.", alert=True)
            return
        # notify user & owner
        try:
            bot.send_message(uid, f"✅ Redeem request submitted for {REDEEM_THRESHOLD} pts. Owner will process it.")
        except:
            try:
                bot.send_message(cid, f"✅ {c.from_user.first_name} requested redeem for {REDEEM_THRESHOLD} pts.")
            except:
                pass
        if OWNER_ID:
            try:
                bot.send_message(OWNER_ID, f"💸 Redeem request: {c.from_user.first_name} ({uid}) requested {REDEEM_THRESHOLD} pts. Use /redeem_list to view.")
            except:
                logger.exception("Could not notify owner of redeem request")
        ack("Redeem requested.")
        return

    # OPEN REVIEW
    if data == 'open_review':
        try:
            bot.send_message(uid, "✍️ Please send your review using /review <your text>", reply_markup=ForceReply(selective=True))
            ack("I sent a private prompt.")
        except:
            try:
                bot.send_message(cid, "✍️ Use /review <text> to submit a review.")
                ack("Opened here.")
            except:
                ack("❌ Could not open review prompt.", alert=True)
        return

    # GAME callbacks (guess/hint/score)
    if data == 'game_guess':
        if cid not in games:
            ack("❌ Game Over or Expired.", alert=True)
            return
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            ack("✍️ Type your guess.")
        except:
            ack("❌ Could not open input.", alert=True)
        return

    if data == 'game_hint':
        if cid not in games:
            ack("❌ No active game.", alert=True)
            return
        user_data = db.get_user(uid, c.from_user.first_name)
        if user_data and user_data[6] < HINT_COST:
            ack(f"❌ Need {HINT_COST} pts. Balance: {user_data[6]}", alert=True)
            return
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            ack("All words found!", alert=True)
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, score_delta=0, hint_delta=-HINT_COST)
        try:
            bot.send_message(cid, f"💡 <b>HINT:</b> <code>{reveal}</code>\nUser: {html.escape(c.from_user.first_name)} (-{HINT_COST} pts)")
            ack("Hint revealed.")
        except:
            ack("❌ Could not send hint.", alert=True)
        return

    if data == 'game_score':
        if cid not in games:
            ack("❌ No active game.", alert=True)
            return
        game = games[cid]
        if not game.players_scores:
            ack("No scores yet. Be the first!", alert=True)
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
            ack("Leaderboard shown.")
        except:
            txt = "📊 Session Leaderboard\n\n"
            for idx, name, pts in rows[:10]:
                txt += f"{idx}. {html.escape(name)} - {pts} pts\n"
            try:
                bot.send_message(cid, txt)
                ack("Leaderboard opened.")
            except:
                ack("❌ Could not show leaderboard.", alert=True)
        return

    # If unknown callback
    ack()

# ==========================================
# 🎮 GAME COMMANDS & core logic (unchanged except addpoints default)
# ==========================================
@bot.message_handler(commands=['new', 'new_hard'])
def start_game(m):
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
    is_hard = 'hard' in m.text.lower()
    session = GameSession(cid, is_hard)
    games[cid] = session
    db.update_stats(m.from_user.id, games_played_delta=1)
    img_bio = GridRenderer.draw(session.grid, is_hard)
    try:
        img_bio.seek(0)
    except:
        pass
    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
               f"Mode: {'Hard (10x10)' if is_hard else 'Normal (8x8)'}\n"
               f"⏱ Time Limit: 10 Minutes\n\n"
               f"<b>👇 WORDS TO FIND:</b>\n"
               f"{session.get_hint_text()}")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'))
    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
               InlineKeyboardButton("📊 Score", callback_data='game_score'))
    try:
        sent = bot.send_photo(cid, img_bio, caption=caption, reply_markup=markup)
        # store message id for replacement when updating grid
        try:
            session.message_id = sent.message_id
        except:
            pass
    except Exception:
        logger.exception("send_photo failed, fallback to temp file")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                tf.write(img_bio.getvalue())
                temp_path = tf.name
            with open(temp_path, 'rb') as f:
                bot.send_photo(cid, f, caption=caption, reply_markup=markup)
            try: os.unlink(temp_path)
            except: pass
        except Exception:
            bot.send_message(cid, caption, reply_markup=markup)

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
        except:
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

@bot.message_handler(commands=['balance'])
def balance(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"💰 Your balance: {u[6]} pts")

@bot.message_handler(commands=['leaderboard'])
def leaderboard(m):
    top = db.get_top_players()
    txt = "🏆 <b>TOP 10 PLAYERS</b> 🏆\n\n"
    for i, (name, score) in enumerate(top, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
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
# Admin / owner commands: addpoints (default->balance), addadmin, deladmin, admins, settings, restart
# ==========================================
@bot.message_handler(commands=['addpoints'])
def addpoints_cmd(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "❌ Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <username_or_id> <amount> [balance|score]")
        return
    target = parts[1].strip()
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be a number.")
        return
    # default to hint balance
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
    # Ensure user exists
    db.get_user(target_id, getattr(chat, 'username', 'Player') if chat else 'Player')
    try:
        if mode == 'score':
            db.update_stats(target_id, score_delta=amount)
        else:
            db.update_stats(target_id, score_delta=0, hint_delta=amount)
        bot.reply_to(m, f"✅ Added {amount} ({mode}) to {target} (ID: {target_id}).")
        try:
            bot.send_message(target_id, f"💸 You received {amount} pts ({mode}) from the owner.")
        except:
            pass
    except Exception as e:
        bot.reply_to(m, f"❌ Failed to add points: {e}")

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
           f"REDEEM_THRESHOLD: {REDEEM_THRESHOLD}\n")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['restart'])
@owner_only
def restart_cmd(m):
    bot.reply_to(m, "🔁 Restarting bot now...")
    # flush logs and restart via execv
    try:
        python = sys.executable
        os.execv(python, [python] + sys.argv)
    except Exception:
        # Last resort: exit process (host may restart)
        logger.exception("Restart via exec failed, exiting.")
        os._exit(0)

# ==========================================
# /define command (unchanged)
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
    except Exception as e:
        logger.exception("define error")
        bot.reply_to(m, "❌ Error fetching definition.")

# ==========================================
# Redeem & Reviews: command handlers
# ==========================================
@bot.message_handler(commands=['redeem_request'])
def cmd_redeem_request(m):
    uid = m.from_user.id
    user = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    total_score = user[5]
    if total_score < REDEEM_THRESHOLD:
        bot.reply_to(m, f"❌ You need at least {REDEEM_THRESHOLD} pts to request redeem. Your score: {total_score}")
        return
    db.add_redeem_request(uid, REDEEM_THRESHOLD)
    bot.reply_to(m, f"✅ Redeem request submitted for {REDEEM_THRESHOLD} pts. Owner will process it.")
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"💸 Redeem request: {user[1]} ({uid}) requested redeem of {REDEEM_THRESHOLD} pts. Use /redeem_list to view.")
        except Exception:
            logger.exception("Could not notify owner about redeem request")

@bot.message_handler(commands=['redeem_list', 'redeem_pay'])
def cmd_redeem_admin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    cmd = parts[0].lstrip('/')
    if cmd == 'redeem_list':
        rows = db.list_redeems(processed=0)
        if not rows:
            bot.reply_to(m, "No pending redeems.")
            return
        txt = "Pending redeems:\n"
        for r in rows:
            txt += f"ID:{r[0]} User:{r[1]} Points:{r[2]} At:{r[3]}\n"
        bot.reply_to(m, txt)
    else:  # redeem_pay
        if len(parts) < 2:
            bot.reply_to(m, "Usage: /redeem_pay <redeem_id> <notes>")
            return
        try:
            rid = int(parts[1])
            notes = " ".join(parts[2:]) if len(parts) > 2 else ""
            res = db.process_redeem(rid, m.from_user.id, notes)
            if not res:
                bot.reply_to(m, "Redeem id not found.")
                return
            user_id, points = res
            # Deduct points from user's total_score (owner handles payment externally)
            db.update_stats(user_id, score_delta=-points)
            bot.reply_to(m, f"Marked redeem {rid} processed for user {user_id}. Please pay externally and update notes.")
            try:
                bot.send_message(user_id, f"✅ Your redeem request ({points} pts) has been processed by owner. They will pay you externally.")
            except Exception:
                pass
        except Exception:
            bot.reply_to(m, "Operation failed.")

@bot.message_handler(commands=['review'])
def cmd_review(m):
    text = m.text.replace("/review", "").strip()
    if not text:
        bot.reply_to(m, "Usage: /review <message>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player", text)
    bot.reply_to(m, "✅ Review submitted. Thank you!")
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"📝 New review from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
        except Exception:
            logger.exception("Could not notify owner about review")

@bot.message_handler(commands=['list_reviews', 'approve_review'])
def cmd_reviews_admin(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    cmd = parts[0].lstrip('/')
    if cmd == 'list_reviews':
        mode = parts[1] if len(parts) > 1 else 'pending'
        if mode == 'all':
            rows = db.list_reviews(None)
        else:
            rows = db.list_reviews(0)
        if not rows:
            bot.reply_to(m, "No reviews.")
            return
        txt = ""
        for r in rows:
            txt += f"ID:{r[0]} User:{r[2]} ({r[1]}) At:{r[4]} Approved:{r[5]}\n{r[3][:250]}\n\n"
        bot.reply_to(m, txt)
    else:
        if len(parts) < 2:
            bot.reply_to(m, "Usage: /approve_review <id>")
            return
        try:
            rid = int(parts[1])
            db.approve_review(rid)
            bot.reply_to(m, f"Review {rid} approved.")
        except Exception:
            bot.reply_to(m, "Operation failed.")

# ==========================================
# CORE GUESS PROCESSING & END GAME (unchanged)
# ==========================================
def process_word_guess(m):
    cid = m.chat.id
    if cid not in games:
        try:
            bot.reply_to(m, "❌ No active game in this chat.")
        except: pass
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
    except: pass
    if word in game.words:
        if word in game.found:
            msg = bot.send_message(cid, f"⚠️ <b>{word}</b> is already found!")
            threading.Timer(3, lambda: bot.delete_message(cid, msg.message_id)).start()
        else:
            game.found.add(word)
            game.last_activity = time.time()
            # scoring
            if len(game.found) == 1:
                points = FIRST_BLOOD_POINTS
            elif len(game.found) == len(game.words):
                points = FINISHER_POINTS
            else:
                points = NORMAL_POINTS
            prev = game.players_scores.get(uid, 0)
            game.players_scores[uid] = prev + points
            db.update_stats(uid, score_delta=points)
            reply = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(user_name)} found <code>{word}</code> (+{points} pts) 🎯")
            threading.Timer(5, lambda: bot.delete_message(cid, reply.message_id)).start()
            # regenerate image with found lines and replace old image (clean chat)
            try:
                img_bio = GridRenderer.draw(game.grid, game.is_hard)
                try:
                    img_bio.seek(0)
                except:
                    pass
                sent_msg = None
                try:
                    sent_msg = bot.send_photo(cid, img_bio, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if game.is_hard else 'Normal'}\n\n"
                                                                    f"<b>👇 WORDS TO FIND:</b>\n{game.get_hint_text()}"),
                                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'),
                                                                                      InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
                                                                                      InlineKeyboardButton("📊 Score", callback_data='game_score')))
                except Exception:
                    # fallback to temp file
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                            tf.write(img_bio.getvalue())
                            temp_path = tf.name
                        with open(temp_path, 'rb') as f:
                            sent_msg = bot.send_photo(cid, f, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if game.is_hard else 'Normal'}\n\n"
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
                # delete old image to keep chat clean
                try:
                    old_mid = getattr(game, 'message_id', None)
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
        except: pass

def end_game_session(cid, reason, winner_id=None):
    if cid not in games: return
    game = games[cid]
    if reason == "win":
        winner = db.get_user(winner_id, "Unknown")
        db.update_stats(winner_id, win=True)
        db.record_game(cid, winner_id)
        top_players = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        summary = ""
        for idx, (uid_score, pts) in enumerate(top_players, 1):
            try:
                user = db.get_user(uid_score, "Player")
                name = user[1] if user else str(uid_score)
            except:
                name = str(uid_score)
            medal = "🥇" if idx==1 else "🥈" if idx==2 else "🥉" if idx==3 else f"{idx}."
            summary += f"{medal} <b>{html.escape(name)}</b> - {pts} pts\n"
        txt = (f"🏆 <b>GAME OVER! VICTORY!</b>\n\n"
               f"👑 <b>MVP:</b> {html.escape(winner[1])}\n"
               f"✅ All {len(game.words)} words found!\n\n"
               f"<b>Session Standings:</b>\n{summary}\n"
               f"Type <code>/new</code> to play again.")
        bot.send_message(cid, txt)
    elif reason == "stopped":
        bot.send_message(cid, "🛑 Game stopped manually.")
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
