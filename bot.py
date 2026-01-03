#!/usr/bin/env python3
"""
WORD VORTEX - Revised
Version: 5.3 - Clean, stable callbacks, games working, no auto-redeem, addpoints -> hint balance by default,
commands button fixed (sends full list to user's PM), each menu option shows info.
Developer: Updated for you
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
import requests

from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# -------------------------
# CONFIG
# -------------------------
app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '8208557623:AAFNjAao3iZoq2eWR0v7MvPCYqKRl72GN7A')
try:
    OWNER_ID = int(os.environ.get('OWNER_ID', '8271254197'))
except Exception:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get('CHANNEL_USERNAME', '@Ruhvaan_Updates')
FORCE_JOIN = os.environ.get('FORCE_JOIN', 'False').lower() in ('1', 'true', 'yes')
SUPPORT_GROUP_LINK = os.environ.get('SUPPORT_GROUP_LINK', 'https://t.me/Ruhvaan')
START_IMG_URL = os.environ.get('START_IMG_URL', 'https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg')

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Gameplay constants
FIRST_BLOOD_POINTS = 10
NORMAL_POINTS = 2
FINISHER_POINTS = 5
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

# curated pools
PHYSICS_WORDS = ["FORCE", "ENERGY", "MOMENTUM", "VELOCITY", "ACCEL", "VECTOR", "SCALAR", "WAVE", "PHOTON", "GRAVITY"]
CHEMISTRY_WORDS = ["ATOM", "MOLECULE", "REACTION", "BOND", "ION", "CATION", "ANION", "ACID", "BASE", "SALT"]
JEE_WORDS = ["INTEGRAL", "DIFFERENTIAL", "MATRIX", "VECTOR", "FORCE", "ENERGY", "EQUILIBRIUM", "KINEMATICS", "OXIDATION", "REDUCTION"]

# -------------------------
# DATABASE (simple sqlite)
# -------------------------
class DatabaseManager:
    def __init__(self, db_name='wordsgrid.db'):
        self.db_name = db_name
        self.init_db()

    def connect(self):
        return sqlite3.connect(self.db_name, check_same_thread=False)

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
            is_banned INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            timestamp TEXT
        )''')
        conn.commit()
        conn.close()

    def get_user(self, user_id, name="Player"):
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

    def register_user(self, user_id, name="Player"):
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
        conn = self.connect()
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

db = DatabaseManager()

# -------------------------
# IMAGE RENDERING
# -------------------------
class GridRenderer:
    @staticmethod
    def draw(grid, placements=None, found=None, is_hard=False):
        cell = 60
        header = 100
        footer = 40
        pad = 20
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        w = cols * cell + pad*2
        h = rows * cell + header + footer + pad*2
        img = Image.new('RGB', (w, h), '#FFFFFF')
        draw = ImageDraw.Draw(img)
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            header_font = ImageFont.truetype(font_path, 30)
            letter_font = ImageFont.truetype(font_path, 28)
            small = ImageFont.truetype(font_path, 14)
        except Exception:
            header_font = ImageFont.load_default()
            letter_font = ImageFont.load_default()
            small = ImageFont.load_default()

        draw.rectangle([0, 0, w, header], fill='#eef2f6')
        title = "WORD VORTEX"
        bbox = draw.textbbox((0,0), title, font=header_font)
        draw.text(((w-bbox[2])/2, 20), title, fill='#1f6feb', font=header_font)
        draw.text((pad, header-30), "Find the words. Found words will be shown on the grid.", fill='#555', font=small)

        start_y = header + pad
        for r in range(rows):
            for c in range(cols):
                x = pad + c*cell
                y = start_y + r*cell
                draw.rectangle([x, y, x+cell, y+cell], outline='#2b90d9', width=2)
                ch = grid[r][c]
                bb = draw.textbbox((0,0), ch, font=letter_font)
                draw.text((x + (cell - bb[2])/2, y + (cell - bb[3])/2 - 4), ch, fill='#222', font=letter_font)

        # draw found word lines
        if placements and found:
            for wrd, coords in placements.items():
                if wrd in found and coords:
                    a = coords[0]; b = coords[-1]
                    x1 = pad + a[1]*cell + cell/2
                    y1 = start_y + a[0]*cell + cell/2
                    x2 = pad + b[1]*cell + cell/2
                    y2 = start_y + b[0]*cell + cell/2
                    draw.line([(x1,y1),(x2,y2)], fill='#ff4757', width=6)
                    r = 6
                    draw.ellipse([x1-r, y1-r, x1+r, y1+r], fill='#ff4757')
                    draw.ellipse([x2-r, y2-r, x2+r, y2+r], fill='#ff4757')

        draw.text((pad, h-footer+10), "v5.3", fill='#888', font=small)
        bio = io.BytesIO()
        img.save(bio, 'JPEG', quality=90)
        bio.seek(0)
        try:
            bio.name = 'grid.jpg'
        except:
            pass
        return bio

class LeaderboardRenderer:
    @staticmethod
    def draw(rows):
        width = 700
        height = max(120, 60 + 40*len(rows))
        img = Image.new('RGB', (width, height), '#081028')
        draw = ImageDraw.Draw(img)
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            title_font = ImageFont.truetype(font_path, 26)
            row_font = ImageFont.truetype(font_path, 20)
        except:
            title_font = ImageFont.load_default()
            row_font = ImageFont.load_default()
        draw.text((20, 10), "Session Leaderboard", fill='#ffd700', font=title_font)
        y = 50
        for idx, name, pts in rows:
            draw.text((20, y), f"{idx}. {name}", fill='#fff', font=row_font)
            draw.text((520, y), f"{pts} pts", fill='#7be495', font=row_font)
            y += 40
        bio = io.BytesIO()
        img.save(bio, 'PNG', quality=90)
        bio.seek(0)
        try:
            bio.name = 'leaders.png'
        except:
            pass
        return bio

# -------------------------
# WORDS source
# -------------------------
ALL_WORDS = []
def fetch_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        r = requests.get(url, timeout=8)
        lines = r.text.splitlines()
        ALL_WORDS = [w.upper() for w in lines if 4 <= len(w.strip()) <= 9 and w.isalpha() and w.upper() not in BAD_WORDS]
        logger.info("Loaded external wordlist")
    except Exception:
        ALL_WORDS = ['PYTHON','JAVA','SCRIPT','ROBOT','SPACE','GALAXY','NEBULA','FUTURE']
fetch_words()

# -------------------------
# GAME SESSION
# -------------------------
games = {}  # chat_id -> GameSession

class GameSession:
    def __init__(self, chat_id, is_hard=False, duration=GAME_DURATION, word_pool=None):
        self.chat_id = chat_id
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.start_time = time.time()
        self.duration = duration
        self.words = []
        self.found = set()
        self.grid = []
        self.placements = {}  # word -> list[(r,c)]
        self.players_scores = {}
        self.players_last_guess = {}
        self.message_id = None
        self.active = True
        self._make_board(word_pool)

    def _make_board(self, word_pool):
        pool = []
        if word_pool:
            pool = [w.upper() for w in word_pool if w.isalpha()]
        else:
            pool = ALL_WORDS[:] if len(ALL_WORDS) >= self.word_count else (ALL_WORDS*2)
        try:
            self.words = random.sample(pool, self.word_count)
        except Exception:
            self.words = [random.choice(pool) for _ in range(self.word_count)]
        self.grid = [[' ' for _ in range(self.size)] for __ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        for w in sorted_words:
            placed = False
            attempts = 0
            while not placed and attempts < 500:
                attempts += 1
                r = random.randint(0, self.size-1)
                c = random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r,c,dr,dc,w):
                    coords = []
                    for i, ch in enumerate(w):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr,cc))
                    self.placements[w] = coords
                    placed = True
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
                masked = w[0] + '-'*(len(w)-1)
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

    def time_left(self):
        rem = int(self.duration - (time.time()-self.start_time))
        if rem < 0: rem = 0
        return rem

# -------------------------
# HELPERS
# -------------------------
def is_subscribed(user_id):
    if not FORCE_JOIN:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if not CHANNEL_USERNAME:
        return True
    try:
        st = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return st in ['creator','administrator','member']
    except Exception:
        return True

def require_subscription_decorator(fn):
    def wrapper(m):
        if not is_subscribed(m.from_user.id):
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
                   InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
            bot.reply_to(m, "⚠️ Access Denied. Please join the channel to use this bot.", reply_markup=kb)
            return
        return fn(m)
    return wrapper

def safe_send_pm(user_id, text, parse_mode='HTML'):
    try:
        bot.send_message(user_id, text, parse_mode=parse_mode)
        return True
    except Exception:
        try:
            bot.send_message(user_id, text)
            return True
        except Exception:
            return False

# -------------------------
# MAIN MENU
# -------------------------
@bot.message_handler(commands=['start','help'])
def show_menu(m):
    # register user and notify owner
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.register_user(m.from_user.id, name)
    try:
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"🔔 /start by {name} ({m.from_user.id}) in chat {m.chat.id}")
    except Exception:
        pass

    txt = (f"👋 Hello <b>{html.escape(name)}</b>!\n\n"
           "Welcome to Word Vortex — choose an option below. Click any button to view details about it.")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
           InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
    # add-to-group
    try:
        bn = bot.get_me().username
        if bn:
            kb.add(InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{bn}?startgroup=true"))
    except Exception:
        pass
    kb.add(InlineKeyboardButton("🎮 Play Game (info)", callback_data='help_play'),
           InlineKeyboardButton("🤖 Commands (open)", callback_data='help_cmd'))
    kb.add(InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'),
           InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'))
    kb.add(InlineKeyboardButton("🐞 Report Issue", callback_data='open_issue'),
           InlineKeyboardButton("💳 Buy Points", callback_data='open_plans'))
    kb.add(InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=kb)
    except Exception:
        bot.reply_to(m, txt, reply_markup=kb)

# -------------------------
# CALLBACKS (robust, simple)
# -------------------------
@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    data = c.data
    uid = c.from_user.id
    cid = c.message.chat.id

    def reply_pm_or_group(text, chat_id=cid, pm_first=True, reply_markup=None):
        # Primary goal: send full content to user's PM (so commands always open).
        sent_pm = False
        try:
            bot.send_message(uid, text, parse_mode='HTML', reply_markup=reply_markup)
            sent_pm = True
        except Exception:
            try:
                bot.send_message(uid, text)
                sent_pm = True
            except Exception:
                sent_pm = False
        # notify group that PM was sent, else fallback to sending in group
        if sent_pm:
            try:
                bot.answer_callback_query(c.id, "I sent the details to your private chat.")
            except:
                pass
            try:
                bot.send_message(chat_id, f"🔔 {c.from_user.first_name}, I sent the information to your PM.")
            except:
                pass
            return True
        else:
            # try group send
            try:
                bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=reply_markup)
                try:
                    bot.answer_callback_query(c.id, "Opened.")
                except:
                    pass
                return True
            except Exception:
                try:
                    bot.answer_callback_query(c.id, "❌ Could not open. Try starting a private chat with the bot.")
                except:
                    pass
                return False

    # CHECK JOIN
    if data == 'check_join':
        if is_subscribed(uid):
            try:
                bot.answer_callback_query(c.id, "✅ Verified")
                bot.delete_message(cid, c.message.message_id)
            except:
                pass
            show_menu(c.message)
        else:
            try:
                bot.answer_callback_query(c.id, "❌ Not a member", show_alert=True)
            except:
                pass
        return

    # REPORT ISSUE
    if data == 'open_issue':
        prompt = f"@{c.from_user.username or c.from_user.first_name} Please type your issue below or use /issue <message>."
        try:
            bot.send_message(uid, prompt, reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id, "I sent you a prompt in private chat.")
        except Exception:
            try:
                bot.send_message(cid, prompt, reply_markup=ForceReply(selective=True))
                bot.answer_callback_query(c.id, "Please type your issue in the group.")
            except Exception:
                bot.answer_callback_query(c.id, "❌ Could not open issue prompt.", show_alert=True)
        return

    # PLANS
    if data == 'open_plans':
        txt = ("💳 Points Plans (examples):\n\n"
               "- 50 pts : ₹10\n- 120 pts : ₹20\n- 350 pts : ₹50\n\nContact the owner to purchase.")
        reply_pm_or_group(txt)
        return

    # HELP PLAY (info)
    if data == 'help_play':
        txt = ("🎮 Play Game - Info:\n\n"
               "• /new - start normal game (8x8, 6 words)\n"
               "• /new_hard - start hard game (10x10, 8 words)\n"
               "• /new_physics - physics vocabulary pool\n"
               "• /new_chemistry - chemistry vocabulary pool\n"
               "• /new_jee - JEE level mixed pool\n\n"
               "During a game: click 'Found It' and type the word. Hints cost points.")
        reply_pm_or_group(txt)
        return

    # HELP CMD (open commands to PM)
    if data == 'help_cmd':
        cmds = ("🤖 Commands (full list):\n\n"
                "/start, /help - show main menu\n"
                "/ping - check bot latency\n"
                "/new - start normal game\n"
                "/new_hard - start hard game\n"
                "/new_physics - start physics pool game\n"
                "/new_chemistry - start chemistry pool game\n"
                "/new_jee - start JEE-level game\n"
                "/hint - buy a hint (costs points)\n"
                "/endgame - stop game (admin/owner)\n"
                "/mystats or /scorecard - view your stats\n"
                "/balance - check hint balance\n"
                "/leaderboard - global leaderboard\n"
                "/issue - report an issue\n"
                "/plans - see point plans\n"
                "/define <word> - get definition\n"
                "Owner only:\n"
                "/addpoints <id|@username> <amount> [score|balance] - default adds to hint balance\n"
                "/addadmin, /deladmin, /admins, /reset_leaderboard, /broadcast <message>\n")
        # always send to user's PM so "Commands" reliably opens
        reply_pm_or_group(cmds)
        return

    # LEADERBOARD
    if data == 'menu_lb':
        top = db.get_top_players(10)
        txt = "🏆 Global Leaderboard\n\n"
        for i,(name,score) in enumerate(top,1):
            txt += f"{i}. {html.escape(name)} - {score} pts\n"
        reply_pm_or_group(txt)
        return

    # STATS
    if data == 'menu_stats':
        user = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_pts = 0
        if c.message.chat.id in games:
            session_pts = games[c.message.chat.id].players_scores.get(uid,0)
        txt = (f"📋 Your Stats\n\n"
               f"Name: {html.escape(user[1])}\n"
               f"Total Score: {user[5]}\n"
               f"Wins: {user[4]}\n"
               f"Games Played: {user[3]}\n"
               f"Session Points: {session_pts}\n"
               f"Hint Balance: {user[6]}")
        reply_pm_or_group(txt)
        return

    # GAME CALLBACKS: guess/hint/score
    if data == 'game_guess':
        if c.message.chat.id not in games:
            try:
                bot.answer_callback_query(c.id, "❌ No active game", show_alert=True)
            except:
                pass
            return
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            bot.answer_callback_query(c.id, "✍️ Type your guess.")
        except Exception:
            bot.answer_callback_query(c.id, "❌ Could not open input", show_alert=True)
        return

    if data == 'game_hint':
        if c.message.chat.id not in games:
            try:
                bot.answer_callback_query(c.id, "❌ No active game", show_alert=True)
            except:
                pass
            return
        game = games[c.message.chat.id]
        uid = c.from_user.id
        user = db.get_user(uid, c.from_user.first_name)
        if user[6] < HINT_COST:
            try:
                bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user[6]}", show_alert=True)
            except:
                pass
            return
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            try:
                bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            except:
                pass
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, hint_delta=-HINT_COST)
        try:
            bot.send_message(cid, f"💡 Hint: <code>{reveal}</code> (by {html.escape(c.from_user.first_name)})")
            bot.answer_callback_query(c.id, "Hint sent.")
        except:
            bot.answer_callback_query(c.id, "❌ Could not send hint", show_alert=True)
        return

    if data == 'game_score':
        if c.message.chat.id not in games:
            try:
                bot.answer_callback_query(c.id, "❌ No active game", show_alert=True)
            except:
                pass
            return
        game = games[c.message.chat.id]
        if not game.players_scores:
            try:
                bot.answer_callback_query(c.id, "No scores yet", show_alert=True)
            except:
                pass
            return
        leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        rows=[]
        for idx, (u,pts) in enumerate(leaderboard,1):
            user = db.get_user(u, "Player")
            rows.append((idx, user[1], pts))
        img = LeaderboardRenderer.draw(rows[:10])
        try:
            bot.send_photo(cid, img, caption="Session Leaderboard")
            bot.answer_callback_query(c.id, "Leaderboard sent.")
        except:
            txt = "Session Leaderboard\n\n"
            for idx,name,pts in rows[:10]:
                txt += f"{idx}. {html.escape(name)} - {pts} pts\n"
            reply_pm_or_group(txt)
        return

    # default ack
    try:
        bot.answer_callback_query(c.id, "")
    except:
        pass

# -------------------------
# COMMANDS: start game modes, hint, scorecard, addpoints, broadcast, etc.
# -------------------------
def start_game_with_pool(m, pool=None, hard=False):
    cid = m.chat.id
    if cid in games:
        bot.reply_to(m, "⚠️ A game is already active here. Use /endgame to stop it first.")
        return
    user = db.get_user(m.from_user.id, m.from_user.first_name)
    if user and user[7] == 1:
        bot.reply_to(m, "🚫 You are banned from playing.")
        return
    session = GameSession(cid, is_hard=hard, word_pool=pool)
    games[cid] = session
    db.update_stats(m.from_user.id, games_played_delta=1)
    img = GridRenderer.draw(session.grid, placements=session.placements, found=session.found, is_hard=hard)
    caption = (f"🔥 WORD VORTEX STARTED!\nMode: {'Hard' if hard else 'Normal'}\n"
               f"⏱ Time: {session.duration//60} minutes\n\nWords to find:\n{session.get_hint_text()}")
    try:
        sent = bot.send_photo(cid, img, caption=caption, reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'),
            InlineKeyboardButton("💡 Hint", callback_data='game_hint'),
            InlineKeyboardButton("📊 Score", callback_data='game_score')
        ))
        session.message_id = sent.message_id
    except Exception:
        # fallback to sending caption only
        bot.send_message(cid, caption)
    # notify owner about game start
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🎮 Game started in chat {cid} by {m.from_user.first_name} ({m.from_user.id}). Mode: {'Hard' if hard else 'Normal'} Pool: {'custom' if pool else 'default'}")
        except:
            pass

@bot.message_handler(commands=['new'])
def cmd_new(m):
    start_game_with_pool(m, pool=None, hard=False)

@bot.message_handler(commands=['new_hard'])
def cmd_new_hard(m):
    start_game_with_pool(m, pool=None, hard=True)

@bot.message_handler(commands=['new_physics'])
def cmd_new_physics(m):
    start_game_with_pool(m, pool=PHYSICS_WORDS, hard=False)

@bot.message_handler(commands=['new_chemistry'])
def cmd_new_chem(m):
    start_game_with_pool(m, pool=CHEMISTRY_WORDS, hard=False)

@bot.message_handler(commands=['new_jee'])
def cmd_new_jee(m):
    start_game_with_pool(m, pool=JEE_WORDS, hard=False)

@bot.message_handler(commands=['hint'])
def cmd_hint(m):
    cid = m.chat.id
    uid = m.from_user.id
    if cid not in games:
        bot.reply_to(m, "❌ No active game in this chat.")
        return
    user = db.get_user(uid, m.from_user.first_name)
    if user[6] < HINT_COST:
        bot.reply_to(m, f"❌ You need {HINT_COST} pts. Balance: {user[6]}")
        return
    game = games[cid]
    hidden = [w for w in game.words if w not in game.found]
    if not hidden:
        bot.reply_to(m, "All words already found!")
        return
    reveal = random.choice(hidden)
    db.update_stats(uid, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")

@bot.message_handler(commands=['scorecard','mystats'])
def cmd_scorecard(m):
    uid = m.from_user.id
    user = db.get_user(uid, m.from_user.first_name)
    session_pts = 0
    gid = m.chat.id
    if gid in games:
        session_pts = games[gid].players_scores.get(uid, 0)
    txt = (f"📋 Your Scorecard\n\nName: {html.escape(user[1])}\n"
           f"Total Score: {user[5]}\nWins: {user[4]}\nGames Played: {user[3]}\n"
           f"Session Points (this chat): {session_pts}\nHint Balance: {user[6]}")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['balance'])
def cmd_balance(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"💰 Hint Balance: {u[6]} pts")

@bot.message_handler(commands=['leaderboard'])
def cmd_leaderboard(m):
    top = db.get_top_players()
    txt = "🏆 TOP PLAYERS\n\n"
    for i,(n,s) in enumerate(top,1):
        txt += f"{i}. {html.escape(n)} - {s} pts\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['endgame'])
def cmd_endgame(m):
    cid = m.chat.id
    if cid not in games:
        bot.reply_to(m, "No active game to stop.")
        return
    if not (db.is_admin(m.from_user.id) or (OWNER_ID and m.from_user.id == OWNER_ID)):
        bot.reply_to(m, "Only admin/owner can stop the game.")
        return
    end_game_session(cid, "stopped")
    bot.reply_to(m, "Game stopped.")

# -------------------------
# Addpoints: default adds to hint balance; 'score' explicitly adds to score
# -------------------------
@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Only owner can use this.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]\nDefault: balance (hint balance).")
        return
    target = parts[1]
    try:
        amount = int(parts[2])
    except:
        bot.reply_to(m, "Amount must be integer.")
        return
    mode = parts[3].lower() if len(parts) >=4 else 'balance'
    target_id = None
    if target.lstrip('-').isdigit():
        target_id = int(target)
    else:
        if not target.startswith('@'):
            target = '@' + target
        try:
            ch = bot.get_chat(target)
            target_id = ch.id
        except Exception:
            bot.reply_to(m, "Could not find user. They must have started the bot or have a public username.")
            return
    db.get_user(target_id, getattr(ch, 'username', 'Player') if 'ch' in locals() else 'Player')
    if mode == 'score':
        db.update_stats(target_id, score_delta=amount)
        bot.reply_to(m, f"Added {amount} to score of {target_id}")
    else:
        db.update_stats(target_id, hint_delta=amount)
        bot.reply_to(m, f"Added {amount} to hint balance of {target_id}")
    try:
        bot.send_message(target_id, f"💸 You received {amount} pts ({mode}) from the owner.")
    except:
        pass

# -------------------------
# Broadcast (owner only)
# -------------------------
@bot.message_handler(commands=['broadcast'])
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
    for u in users:
        try:
            bot.send_message(u, msg)
            success += 1
        except:
            fail += 1
    bot.reply_to(m, f"Broadcast done. Success: {success}, Fail: {fail}")

# -------------------------
# DEFINE (dictionaryapi)
# -------------------------
@bot.message_handler(commands=['define'])
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
            meanings = data[0].get('meanings',[])
            if meanings:
                defs = meanings[0].get('definitions',[])
                if defs:
                    d = defs[0].get('definition','No definition')
                    ex = defs[0].get('example','')
                    txt = f"📚 <b>{html.escape(word)}</b>\n{html.escape(d)}"
                    if ex:
                        txt += f"\n\n<i>Example:</i> {html.escape(ex)}"
                    bot.reply_to(m, txt)
                    return
        bot.reply_to(m, f"No definition found for {word}")
    except Exception:
        bot.reply_to(m, "Error fetching definition.")

# -------------------------
# GUESS PROCESSING: main logic, update image when found
# -------------------------
def process_word_guess(m):
    cid = m.chat.id
    if cid not in games:
        try:
            bot.reply_to(m, "No active game here.")
        except:
            pass
        return
    word = (m.text or "").strip().upper()
    if not word:
        return
    session = games[cid]
    uid = m.from_user.id
    name = m.from_user.first_name or m.from_user.username or "Player"
    last = session.players_last_guess.get(uid, 0)
    now = time.time()
    if now - last < COOLDOWN:
        bot.reply_to(m, f"⏳ Wait {COOLDOWN}s between guesses.")
        return
    session.players_last_guess[uid] = now
    # delete user's reply for cleanliness
    try:
        bot.delete_message(cid, m.message_id)
    except:
        pass
    if word in session.words:
        if word in session.found:
            msg = bot.send_message(cid, f"⚠️ {word} already found.")
            threading.Timer(3, lambda: safe_delete(cid, msg.message_id)).start()
            return
        session.found.add(word)
        session.last_activity = time.time()
        if len(session.found) == 1:
            pts = FIRST_BLOOD_POINTS
        elif len(session.found) == len(session.words):
            pts = FINISHER_POINTS
        else:
            pts = NORMAL_POINTS
        prev = session.players_scores.get(uid, 0)
        session.players_scores[uid] = prev + pts
        db.update_stats(uid, score_delta=pts)
        # notify
        notify = bot.send_message(cid, f"✨ {html.escape(name)} found <code>{word}</code> (+{pts} pts)")
        threading.Timer(4, lambda: safe_delete(cid, notify.message_id)).start()
        # regenerate image and replace previous
        try:
            img = GridRenderer.draw(session.grid, placements=session.placements, found=session.found, is_hard=session.is_hard)
            sent = bot.send_photo(cid, img, caption=(f"🔥 WORD VORTEX — Updated\nWords:\n{session.get_hint_text()}"),
                                  reply_markup=InlineKeyboardMarkup().add(
                                      InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'),
                                      InlineKeyboardButton("💡 Hint", callback_data='game_hint'),
                                      InlineKeyboardButton("📊 Score", callback_data='game_score')
                                  ))
            # try delete previous main image if present
            try:
                if session.message_id:
                    safe_delete(cid, session.message_id)
            except:
                pass
            session.message_id = sent.message_id if sent else session.message_id
        except Exception:
            logger.exception("Could not send updated grid image")
        # if all found end game
        if len(session.found) == len(session.words):
            end_game_session(cid, 'win', uid)
    else:
        try:
            msg = bot.send_message(cid, f"❌ {html.escape(name)} — '{html.escape(word)}' is not in the list.")
            threading.Timer(3, lambda: safe_delete(cid, msg.message_id)).start()
        except:
            pass

def safe_delete(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

def end_game_session(chat_id, reason, winner_id=None):
    if chat_id not in games:
        return
    session = games[chat_id]
    session.active = False
    if reason == 'win' and winner_id:
        winner = db.get_user(winner_id, "Player")
        db.update_stats(winner_id, win=True)
        db.record_game(chat_id, winner_id)
        # build standings
        standings = sorted(session.players_scores.items(), key=lambda x: x[1], reverse=True)
        txt = f"🏆 GAME OVER — All words found!\nMVP: {html.escape(winner[1])}\n\nStandings:\n"
        for i,(u,pts) in enumerate(standings,1):
            usr = db.get_user(u,"Player")
            txt += f"{i}. {html.escape(usr[1])} - {pts} pts\n"
        bot.send_message(chat_id, txt)
    elif reason == 'stopped':
        bot.send_message(chat_id, "🛑 Game stopped by admin.")
    elif reason == 'timeout':
        found = len(session.found)
        rem = [w for w in session.words if w not in session.found]
        txt = f"⏰ Time's up! Found {found}/{len(session.words)}\nRemaining: {', '.join(rem) if rem else 'None'}"
        bot.send_message(chat_id, txt)
    try:
        del games[chat_id]
    except:
        pass

# -------------------------
# ADMIN: reset leaderboard
# -------------------------
@bot.message_handler(commands=['reset_leaderboard'])
def cmd_reset_lb(m):
    if not (m.from_user.id == OWNER_ID):
        bot.reply_to(m, "Owner only.")
        return
    db.reset_leaderboard()
    bot.reply_to(m, "Leaderboard reset.")

# -------------------------
# RUN
# -------------------------
@app.route('/')
def index():
    return "Word Vortex Bot Running"

if __name__ == '__main__':
    # start flask thread for health check
    def run_flask():
        port = int(os.environ.get('PORT', '5000'))
        app.run(host='0.0.0.0', port=port)
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    print("Bot starting...")
    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=5)
        except Exception as e:
            logger.exception("Polling error")
            time.sleep(5)
