#!/usr/bin/env python3
"""
WORD VORTEX BOT - ULTIMATE 3D PREMIUM EDITION v7.0
✨ Dark Theme + Yellow Neon + 3D Depth + Button Animations
Matching screenshot design exactly!
"""

import os
import sys
import time
import html
import io
import random
import logging
import threading
import sqlite3
from typing import List, Tuple, Dict, Optional

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# -------------------------
# CONFIG
# -------------------------
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHZzgByv218uShEzAHBtGjpCJ8_cedldVk")
if not TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set.")
    sys.exit(1)

try:
    OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
except:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")
FORCE_JOIN = os.environ.get("FORCE_JOIN", "False").lower() in ("1", "true", "yes")
SUPPORT_GROUP_LINK = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = os.environ.get("START_IMG_URL", "https://i.imgur.com/8XjQk9p.jpg")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

PHYSICS_WORDS = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "INERTIA", "TORQUE", "POWER", "PHOTON", "QUANTUM", "GRAVITY"]
CHEMISTRY_WORDS = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "ACID", "BASE", "SALT", "OXIDE", "ESTER", "ALKANE"]
MATH_WORDS = ["INTEGRAL", "DERIVATIVE", "MATRIX", "VECTOR", "CALCULUS", "LIMIT", "SERIES", "MODULUS", "ALGORITHM"]
JEE_WORDS = ["KINEMATICS", "ELECTROSTATICS", "THERMODYNAMICS", "ENTROPY", "ENTHALPY", "VECTOR", "MATRIX"]

DB_PATH = "wordsgrid_v7.db"

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
            user_id INTEGER PRIMARY KEY, name TEXT, join_date TEXT,
            games_played INTEGER DEFAULT 0, wins INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0, hint_balance INTEGER DEFAULT 100,
            is_banned INTEGER DEFAULT 0
        )""")
        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            username TEXT, text TEXT, created_at TEXT, approved INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS redeem_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            username TEXT, points INTEGER, upi_id TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, paid_at TEXT
        )""")
        conn.commit()
        conn.close()

    def get_user(self, user_id: int, name: str = "Player"):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)",
                      (user_id, name, time.strftime("%Y-%m-%d")))
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
        c.execute("INSERT INTO users (user_id, name, join_date) VALUES (?, ?, ?)",
                  (user_id, name, time.strftime("%Y-%m-%d")))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row, True

    def update_stats(self, user_id: int, score_delta: int = 0, hint_delta: int = 0,
                     win: bool = False, games_played_delta: int = 0):
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

    def get_top_players(self, limit: int = 10):
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

    def add_review(self, user_id: int, username: str, text: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO reviews (user_id, username, text, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, username, text, time.strftime("%Y-%m-%d %H:%M:%S")))
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

def fetch_wordlist():
    global ALL_WORDS
    try:
        r = requests.get("https://www.mit.edu/~ecprice/wordlist.10000", timeout=8)
        words = [w.strip().upper() for w in r.text.splitlines() if w.strip()]
        words = [w for w in words if w.isalpha() and 4 <= len(w) <= 10 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info(f"Loaded {len(ALL_WORDS)} words")
            return
    except:
        pass
    ALL_WORDS = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "SPACE", "GALAXY", "QUANTUM", "MATRIX", "VECTOR", "ENERGY"]
    logger.info("Using fallback wordlist")

fetch_wordlist()

# -------------------------
# 🔥 PREMIUM 3D DARK THEME IMAGE RENDERER 🔥
# -------------------------
class GridRenderer3D:
    @staticmethod
    def draw_premium_grid(grid: List[List[str]], placements: Dict[str, List[Tuple[int, int]]],
                          found: set, is_hard=False, title="WORD GRID (FIND WORDS)"):
        """
        Creates DARK THEME grid with YELLOW NEON lines matching screenshot
        + 3D depth effect with shadows
        """
        cell_size = 52
        header_h = 80
        footer_h = 60
        pad = 20
        rows = len(grid)
        cols = len(grid[0]) if rows else 0

        # Dark background
        width = cols * cell_size + pad * 2
        height = header_h + footer_h + rows * cell_size + pad * 2
        img = Image.new("RGB", (width, height), "#0a1628")  # Dark blue-black
        draw = ImageDraw.Draw(img)

        # Fonts
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(fp):
                fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            title_font = ImageFont.truetype(fp, 28)
            letter_font = ImageFont.truetype(fp, 26)
        except:
            title_font = letter_font = ImageFont.load_default()

        # Header with dark gradient effect
        draw.rectangle([0, 0, width, header_h], fill="#1a2942")
        draw.text((width//2, header_h//2), title, fill="#e0e0e0", font=title_font, anchor="mm")

        grid_start_y = header_h + pad

        # Grid cells with 3D border effect
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell_size
                y = grid_start_y + r * cell_size

                # 3D shadow effect (bottom-right)
                shadow_offset = 2
                draw.rectangle([x+shadow_offset, y+shadow_offset, x+cell_size+shadow_offset, y+cell_size+shadow_offset],
                              fill="#000000", outline="#000000")

                # Main cell (dark with light border)
                draw.rectangle([x, y, x+cell_size, y+cell_size], fill="#1e3a5f", outline="#3d5a7f", width=1)

                # Letter
                ch = grid[r][c]
                bbox = draw.textbbox((0, 0), ch, font=letter_font)
                text_x = x + (cell_size - (bbox[2] - bbox[0])) / 2
                text_y = y + (cell_size - (bbox[3] - bbox[1])) / 2
                draw.text((text_x, text_y), ch, fill="#d0d0d0", font=letter_font)

        # 🔥 YELLOW NEON 3D LINES (EXACTLY like screenshot) 🔥
        if placements and found:
            for w, coords in placements.items():
                if w in found and coords:
                    a, b = coords[0], coords[-1]
                    x1 = pad + a[1] * cell_size + cell_size / 2
                    y1 = grid_start_y + a[0] * cell_size + cell_size / 2
                    x2 = pad + b[1] * cell_size + cell_size / 2
                    y2 = grid_start_y + b[0] * cell_size + cell_size / 2

                    # Layer 1: Dark shadow (3D depth)
                    shadow_off = 3
                    draw.line([(x1+shadow_off, y1+shadow_off), (x2+shadow_off, y2+shadow_off)],
                             fill="#1a1a00", width=10)

                    # Layer 2: Outer yellow glow
                    draw.line([(x1, y1), (x2, y2)], fill="#ffff00", width=8)

                    # Layer 3: Bright yellow core
                    draw.line([(x1, y1), (x2, y2)], fill="#ffff66", width=4)

                    # Layer 4: White highlight center (3D shine)
                    draw.line([(x1, y1), (x2, y2)], fill="#ffffaa", width=2)

                    # Endpoint circles with 3D effect
                    for px, py in [(x1, y1), (x2, y2)]:
                        # Shadow circle
                        draw.ellipse([px-8+shadow_off, py-8+shadow_off, px+8+shadow_off, py+8+shadow_off],
                                    fill="#1a1a00")
                        # Outer glow
                        draw.ellipse([px-8, py-8, px+8, py+8], fill="#ffff00")
                        # Core
                        draw.ellipse([px-5, py-5, px+5, py+5], fill="#ffff66")
                        # Highlight
                        draw.ellipse([px-2, py-2, px+2, py+2], fill="#ffffff")

        # Footer
        mode_txt = "🔥 HARD MODE CHALLENGE 🔥" if is_hard else "⚡ NORMAL MODE"
        draw.text((width//2, height-30), mode_txt, fill="#ffa500", font=title_font, anchor="mm")

        bio = io.BytesIO()
        img.save(bio, "PNG", quality=95)
        bio.seek(0)
        bio.name = "grid.png"
        return bio

# -------------------------
# HELPERS
# -------------------------
def send_start_card(chat_id: int, caption: str, reply_markup):
    try:
        r = requests.get(START_IMG_URL, timeout=10)
        if r.status_code == 200:
            bio = io.BytesIO(r.content)
            bio.name = "start.jpg"
            bot.send_photo(chat_id, bio, caption=caption, reply_markup=reply_markup)
            return
    except:
        pass
    bot.send_message(chat_id, caption, reply_markup=reply_markup)

def ensure_user_registered(uid: int, name: str):
    try:
        db.register_user(uid, name)
    except:
        pass

# -------------------------
# COMMANDS TEXT
# -------------------------
COMMANDS_TEXT = """
🤖 <b>WORD VORTEX COMMANDS</b>

<b>🎮 Game Modes:</b>
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
/leaderboard - Top 10

<b>📝 Other:</b>
/review - Submit review
/redeem - Cash out points

<b>Admin:</b> /addpoints /reset_leaderboard
"""

# -------------------------
# 🔥 ANIMATED MENU BUTTONS 🔥
# -------------------------
def build_animated_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    if CHANNEL_USERNAME:
        kb.add(
            InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
            InlineKeyboardButton("✅ Check", callback_data="check_join")
        )

    # Main buttons with emojis for "glow" effect
    kb.add(
        InlineKeyboardButton("✨ Features", callback_data="features"),
        InlineKeyboardButton("🎮 Play", callback_data="play")
    )
    kb.add(
        InlineKeyboardButton("📖 Commands", callback_data="commands"),
        InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
    )
    kb.add(
        InlineKeyboardButton("👤 My Stats", callback_data="mystats"),
        InlineKeyboardButton("💰 Redeem", callback_data="redeem")
    )
    kb.add(InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP_LINK))

    return kb

# -------------------------
# GAME SESSION
# -------------------------
games = {}

class GameSession:
    def __init__(self, chat_id: int, mode: str = "default", is_hard: bool = False,
                 word_pool: Optional[List[str]] = None):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.wordcount = 8 if is_hard else 6
        self.start_time = time.time()
        self.grid: List[List[str]] = []
        self.placements: Dict[str, List[Tuple[int, int]]] = {}
        self.words: List[str] = []
        self.found: set = set()
        self.players_scores: Dict[int, int] = {}
        self.players_last_guess: Dict[int, float] = {}
        self.message_id: Optional[int] = None

        pool = word_pool if word_pool else ALL_WORDS
        self._prepare_grid(pool)

    def _prepare_grid(self, pool: List[str]):
        choices = [w for w in pool if 4 <= len(w) <= 10]
        if len(choices) < self.wordcount:
            choices = choices * 3
        self.words = random.sample(choices, min(self.wordcount, len(choices)))

        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]

        for w in sorted(self.words, key=len, reverse=True):
            placed = False
            for _ in range(400):
                r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r, c, dr, dc, w):
                    coords = []
                    for i, ch in enumerate(w):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr, cc))
                    self.placements[w] = coords
                    placed = True
                    break

        for r in range(self.size):
            for c in range(self.size):
                if not self.grid[r][c]:
                    self.grid[r][c] = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

    def _can_place(self, r, c, dr, dc, word):
        for i in range(len(word)):
            rr, cc = r + i*dr, c + i*dc
            if not (0 <= rr < self.size and 0 <= cc < self.size):
                return False
            if self.grid[rr][cc] and self.grid[rr][cc] != word[i]:
                return False
        return True

    def get_hint_text(self):
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ {w}")
            else:
                masked = w[0] + "-"*(len(w)-2) + w[-1] if len(w) > 2 else w
                hints.append(f"❌ {masked}")
        return "\n".join(hints)

def start_game(chat_id: int, starter_id: int, mode: str = "default",
               is_hard: bool = False, word_pool: Optional[List[str]] = None):
    if chat_id in games:
        return None

    session = GameSession(chat_id, mode=mode, is_hard=is_hard, word_pool=word_pool)
    games[chat_id] = session

    db.update_stats(starter_id, games_played_delta=1)

    try:
        img = GridRenderer3D.draw_premium_grid(session.grid, session.placements,
                                               session.found, is_hard=session.is_hard)
        caption = (f"🔥 <b>WORD GRID STARTED!</b>\n"
                   f"Mode: {mode.upper()}\n\n"
                   f"<b>Find these words:</b>\n{session.get_hint_text()}")

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        kb.add(
            InlineKeyboardButton("💡 Hint", callback_data="game_hint"),
            InlineKeyboardButton("📊 Score", callback_data="game_score")
        )

        sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
        session.message_id = sent.message_id
    except Exception as e:
        logger.exception("Game start failed")
        return None

    return session

def update_game_image(chat_id: int):
    if chat_id not in games:
        return
    session = games[chat_id]
    try:
        img = GridRenderer3D.draw_premium_grid(session.grid, session.placements,
                                               session.found, is_hard=session.is_hard)
        caption = f"🔥 <b>WORD GRID</b>\n\n<b>Words:</b>\n{session.get_hint_text()}"

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        kb.add(
            InlineKeyboardButton("💡 Hint", callback_data="game_hint"),
            InlineKeyboardButton("📊 Score", callback_data="game_score")
        )

        try:
            bot.edit_message_media(
                media=telebot.types.InputMediaPhoto(img),
                chat_id=chat_id,
                message_id=session.message_id
            )
            bot.edit_message_caption(caption, chat_id=chat_id,
                                    message_id=session.message_id, reply_markup=kb)
        except:
            sent = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
            session.message_id = sent.message_id
    except Exception as e:
        logger.exception("Update failed")

def process_word_guess(msg):
    cid = msg.chat.id
    if cid not in games:
        return

    session = games[cid]
    uid = msg.from_user.id
    username = msg.from_user.first_name or "Player"
    word = (msg.text or "").strip().upper()

    if not word:
        return

    # Cooldown
    last = session.players_last_guess.get(uid, 0)
    if time.time() - last < COOLDOWN:
        bot.reply_to(msg, f"⏳ Wait {COOLDOWN}s")
        return
    session.players_last_guess[uid] = time.time()

    # Check
    if word not in session.words:
        bot.reply_to(msg, f"❌ '{word}' not in list!")
        return

    if word in session.found:
        bot.reply_to(msg, f"✅ Already found!")
        return

    # Correct!
    session.found.add(word)

    if len(session.found) == 1:
        points = FIRST_BLOOD_POINTS
    elif len(session.found) == len(session.words):
        points = FINISHER_POINTS
    else:
        points = NORMAL_POINTS

    prev = session.players_scores.get(uid, 0)
    session.players_scores[uid] = prev + points
    db.update_stats(uid, score_delta=points)

    bot.send_message(cid, f"🎉 {html.escape(username)} found <b>{word}</b>! +{points} pts")

    update_game_image(cid)

    if len(session.found) == len(session.words):
        bot.send_message(cid, "🏆 <b>GAME COMPLETE!</b>")
        del games[cid]

# -------------------------
# COMMANDS
# -------------------------
@bot.message_handler(commands=["start", "help"])
def cmd_start(m):
    name = m.from_user.first_name or "Player"
    ensure_user_registered(m.from_user.id, name)
    txt = f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n🔥 WORD VORTEX 3D PREMIUM\n\nTap a button:"
    send_start_card(m.chat.id, txt, build_animated_menu())

@bot.message_handler(commands=["cmd"])
def cmd_cmd(m):
    try:
        bot.send_message(m.from_user.id, COMMANDS_TEXT)
        bot.reply_to(m, "✅ Commands sent to PM!")
    except:
        bot.reply_to(m, COMMANDS_TEXT)

@bot.message_handler(commands=["new"])
def cmd_new(m):
    if m.chat.type == "private":
        bot.reply_to(m, "❌ Use in group!")
        return
    start_game(m.chat.id, m.from_user.id)

@bot.message_handler(commands=["new_hard"])
def cmd_new_hard(m):
    if m.chat.type == "private":
        return
    start_game(m.chat.id, m.from_user.id, is_hard=True)

@bot.message_handler(commands=["new_physics"])
def cmd_new_physics(m):
    if m.chat.type == "private":
        return
    start_game(m.chat.id, m.from_user.id, mode="physics", word_pool=PHYSICS_WORDS)

@bot.message_handler(commands=["new_chemistry"])
def cmd_new_chemistry(m):
    if m.chat.type == "private":
        return
    start_game(m.chat.id, m.from_user.id, mode="chemistry", word_pool=CHEMISTRY_WORDS)

@bot.message_handler(commands=["new_math"])
def cmd_new_math(m):
    if m.chat.type == "private":
        return
    start_game(m.chat.id, m.from_user.id, mode="math", word_pool=MATH_WORDS)

@bot.message_handler(commands=["new_jee"])
def cmd_new_jee(m):
    if m.chat.type == "private":
        return
    start_game(m.chat.id, m.from_user.id, mode="jee", word_pool=JEE_WORDS)

@bot.message_handler(commands=["leaderboard"])
def cmd_lb(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>TOP 10</b>\n\n"
    for i, (name, score) in enumerate(top, 1):
        txt += f"{i}. {html.escape(name)} - {score}\n"
    bot.reply_to(m, txt if top else "No players yet.")

@bot.message_handler(commands=["mystats"])
def cmd_stats(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
    txt = (f"📋 <b>Stats</b>\n"
           f"Score: {user[5]}\nWins: {user[4]}\n"
           f"Games: {user[3]}\nBalance: {user[6]}")
    bot.reply_to(m, txt)

@bot.message_handler(commands=["balance"])
def cmd_bal(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
    bot.reply_to(m, f"💰 Balance: <b>{user[6]}</b> pts")

@bot.message_handler(commands=["review"])
def cmd_review(m):
    text = m.text.replace("/review", "").strip()
    if not text:
        bot.reply_to(m, "Usage: /review <text>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or "Player", text)
    bot.reply_to(m, "✅ Review submitted!")

@bot.message_handler(commands=["redeem"])
def cmd_redeem(m):
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /redeem <points> <UPI_ID>\nExample: /redeem 500 name@paytm")
        return
    try:
        points = int(parts[1])
        upi = parts[2]
        user = db.get_user(m.from_user.id, m.from_user.first_name or "Player")
        if user[5] < points:
            bot.reply_to(m, f"❌ Need {points} pts. You have {user[5]}")
            return
        db.add_redeem_request(m.from_user.id, m.from_user.first_name or "Player", points, upi)
        bot.reply_to(m, f"✅ Redeem request: {points} pts → {upi}")
    except:
        bot.reply_to(m, "❌ Error")

@bot.message_handler(commands=["addpoints"])
def cmd_addpts(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 3:
        return
    try:
        target = int(parts[1])
        amt = int(parts[2])
        db.update_stats(target, hint_delta=amt)
        bot.reply_to(m, f"✅ Added {amt} to {target}")
    except:
        pass

@bot.message_handler(commands=["reset_leaderboard"])
def cmd_reset(m):
    if not db.is_admin(m.from_user.id):
        return
    db.reset_leaderboard()
    bot.reply_to(m, "✅ Reset!")

@bot.message_handler(commands=["redeem_list"])
def cmd_redeem_list(m):
    if not db.is_admin(m.from_user.id):
        return
    reqs = db.list_redeem_requests()
    if not reqs:
        bot.reply_to(m, "No requests")
        return
    txt = "💸 Pending:\n\n"
    for r in reqs:
        txt += f"ID:{r[0]} {r[2]} {r[3]}pts {r[4]}\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["redeem_pay"])
def cmd_pay(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2:
        return
    try:
        db.mark_redeem_paid(int(parts[1]))
        bot.reply_to(m, "✅ Paid!")
    except:
        pass

# -------------------------
# CALLBACKS
# -------------------------
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data

    def pm_send(text: str):
        try:
            bot.send_message(uid, text, parse_mode="HTML")
            bot.answer_callback_query(c.id, "Sent to PM!")
        except:
            try:
                bot.send_message(cid, text, parse_mode="HTML")
                bot.answer_callback_query(c.id, "Opened")
            except:
                bot.answer_callback_query(c.id, "Error")

    if data == "check_join":
        bot.answer_callback_query(c.id, "✅ Verified!")
        return

    if data == "features":
        pm_send("✨ <b>PREMIUM FEATURES</b>\n\n• Dark 3D Theme\n• Yellow Neon Lines\n• 6 Game Modes\n• Redeem System")
        return

    if data == "play":
        pm_send("🎮 <b>HOW TO PLAY</b>\n\n1. Start: /new\n2. Find words in grid\n3. Click 'Found It'\n4. Type word")
        return

    if data == "commands":
        pm_send(COMMANDS_TEXT)
        return

    if data == "leaderboard":
        top = db.get_top_players(10)
        txt = "🏆 <b>TOP 10</b>\n\n"
        for i, (name, score) in enumerate(top, 1):
            txt += f"{i}. {html.escape(name)} - {score}\n"
        pm_send(txt if top else "No players")
        return

    if data == "mystats":
        user = db.get_user(uid, c.from_user.first_name or "Player")
        txt = f"📋 <b>Stats</b>\nScore: {user[5]}\nWins: {user[4]}\nGames: {user[3]}\nBalance: {user[6]}"
        pm_send(txt)
        return

    if data == "redeem":
        pm_send("💰 <b>REDEEM</b>\n\nUse: /redeem <points> <UPI>\n\nMin 500 pts")
        return

    if data == "game_guess":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No game")
            return
        try:
            msg = bot.send_message(cid, f"@{c.from_user.username or c.from_user.first_name} Type word:",
                                  reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            bot.answer_callback_query(c.id, "Type")
        except:
            bot.answer_callback_query(c.id, "Error")
        return

    if data == "game_hint":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No game")
            return
        game = games[cid]
        user = db.get_user(uid, c.from_user.first_name)
        if user[6] < HINT_COST:
            bot.answer_callback_query(c.id, f"Need {HINT_COST} pts", show_alert=True)
            return
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All found!")
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, hint_delta=-HINT_COST)
        bot.send_message(cid, f"💡 Hint: <code>{reveal}</code>")
        bot.answer_callback_query(c.id, "Revealed")
        return

    if data == "game_score":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No game")
            return
        game = games[cid]
        if not game.players_scores:
            bot.answer_callback_query(c.id, "No scores")
            return
        leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        txt = "📊 <b>SCORES</b>\n\n"
        for i, (u, pts) in enumerate(leaderboard, 1):
            user = db.get_user(u, "Player")
            txt += f"{i}. {html.escape(user[1])} - {pts}\n"
        bot.send_message(cid, txt)
        bot.answer_callback_query(c.id, "")
        return

    bot.answer_callback_query(c.id, "")

# -------------------------
# FALLBACK (FIXED)
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=['text'])
def fallback(m):
    if m.text and m.text.strip().startswith('/'):
        return

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    logger.info("🔥 Word Vortex 3D Premium v7.0 Started!")
    bot.infinity_polling()
