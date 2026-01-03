#!/usr/bin/env python3
"""
WORD VORTEX - STABLE PREMIUM (Auto-detect guesses, Redeem, Animations, Premium Images)
Version: 7.1

Key changes in this file (fixes you requested):
- Removed "Found It" flow. Bot now automatically watches group messages and checks them against active game words.
- When a correct word is posted in group, bot:
  - Validates it (cooldown per user),
  - Awards points,
  - Sends an animated GIF that draws the found-word line,
  - Sends a final premium image where the found word letters are greyed-out AND the red line remains.
  - Cleans up previous grid image to keep the chat tidy.
- /endgame (admin/owner) implemented to stop active games.
- /status (owner-only) implemented to list active games and basic stats.
- /cmd implemented (DM-first, group fallback).
- Callback/menu button behavior fixed (single callback handler, DM-first).
- Redeem flow and status messages improved (pending -> owner marks SENT -> user confirms -> COMPLETE).
- Many robustness and seek(0) fixes for BytesIO when sending images/animations.

Usage:
- Set TELEGRAM_TOKEN and OWNER_ID environment variables.
- Install dependencies: pip install pyTelegramBotAPI Pillow requests flask
- Run: python bot.py
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
from typing import List, Tuple, Dict, Optional

import requests
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# -------------------------
# CONFIG & LOGGER
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

REDEEM_THRESHOLD = 150
PLANS = [{"points": 50, "price_rs": 10}, {"points": 120, "price_rs": 20}, {"points": 350, "price_rs": 50}, {"points": 800, "price_rs": 100}]

DB_PATH = os.environ.get("WORDS_DB", "wordsgrid_v71.db")

# -------------------------
# DATABASE (SQLite)
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
        # users
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
        # admins
        c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)''')
        # game history
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            mode TEXT,
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
            notes TEXT,
            status INTEGER DEFAULT 0
        )''')
        conn.commit()
        conn.close()

    # users
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
        return self.get_user(user_id, name)

    def update_stats(self, user_id: int, score_delta: int = 0, hint_delta: int = 0, win: bool = False, games_played_delta: int = 0, cash_delta: int = 0):
        conn = self._connect()
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

    # admins
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
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows

    # history
    def record_game(self, chat_id: int, winner_id: int, mode: str):
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, mode, timestamp) VALUES (?, ?, ?, ?)",
                  (chat_id, winner_id, mode, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_top_players(self, limit: int = 10):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

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

    # redeems
    def add_redeem_request(self, user_id: int, amount_points: int) -> int:
        conn = self._connect()
        c = conn.cursor()
        c.execute("INSERT INTO redeems (user_id, amount_points, requested_at, status) VALUES (?, ?, ?, ?)",
                  (user_id, amount_points, time.strftime("%Y-%m-%d %H:%M:%S"), 0))
        conn.commit()
        rid = c.lastrowid
        conn.close()
        return rid

    def list_redeems(self, status: Optional[int] = None):
        conn = self._connect()
        c = conn.cursor()
        if status is None:
            c.execute("SELECT * FROM redeems ORDER BY requested_at DESC")
        else:
            c.execute("SELECT * FROM redeems WHERE status=? ORDER BY requested_at DESC", (status,))
        rows = c.fetchall()
        conn.close()
        return rows

    def mark_redeem_sent(self, redeem_id: int, admin_id: int, notes: str = ""):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT user_id, amount_points FROM redeems WHERE redeem_id=?", (redeem_id,))
        r = c.fetchone()
        if not r:
            conn.close()
            return None
        user_id, points = r
        c.execute("UPDATE redeems SET processed=1, admin_id=?, notes=?, status=1 WHERE redeem_id=?", (admin_id, notes, redeem_id))
        conn.commit()
        conn.close()
        return user_id, points

    def mark_redeem_complete_by_user(self, redeem_id: int, user_id: int):
        conn = self._connect()
        c = conn.cursor()
        c.execute("SELECT user_id, amount_points, status FROM redeems WHERE redeem_id=?", (redeem_id,))
        r = c.fetchone()
        if not r:
            conn.close()
            return None
        row_user_id, points, status = r
        if row_user_id != user_id or status != 1:
            conn.close()
            return None
        c.execute("UPDATE redeems SET status=2 WHERE redeem_id=?", (redeem_id,))
        conn.commit()
        conn.close()
        return points

db = Database()

# -------------------------
# Word source
# -------------------------
ALL_WORDS: List[str] = []

def fetch_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        r = requests.get(url, timeout=8)
        lines = r.text.splitlines()
        words = [w.strip().upper() for w in lines if w.strip()]
        words = [w for w in words if w.isalpha() and 4 <= len(w) <= 12 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info("Loaded remote wordlist")
            return
    except Exception:
        logger.exception("word fetch failed")
    ALL_WORDS = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "GALAXY", "NEBULA", "INTEGRAL", "MATRIX", "VECTOR"]
    logger.info("Using fallback words")

fetch_words()

# -------------------------
# Fonts & image helpers
# -------------------------
def _load_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arial.ttf"
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# Grid renderer + animation (keeps line on final image and blanks letters)
class GridRenderer:
    @staticmethod
    def draw(grid, placements, found, blank_words: Optional[set]=None, is_hard=False, watermark="@Ruhvaan", version="v7.1"):
        cell_size = 56
        header = 94
        footer = 44
        pad = 24
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        width = cols * cell_size + pad*2
        height = header + rows * cell_size + footer + pad*2
        img = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(img)
        header_font = _load_font(36)
        letter_font = _load_font(30)
        small_font = _load_font(14)
        draw.rectangle([0,0,width,header], fill="#eef6fb")
        tb = draw.textbbox((0,0),"WORD VORTEX", font=header_font)
        draw.text(((width-(tb[2]-tb[0]))/2,18),"WORD VORTEX", fill="#1f6feb", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        draw.text((pad, header-26), mode_text, fill="#6b7280", font=small_font)
        grid_start_y = header + pad
        disabled_color = "#b0bec5"
        for r in range(rows):
            for c in range(cols):
                x = pad + c*cell_size
                y = grid_start_y + r*cell_size
                draw.rectangle([x,y,x+cell_size,y+cell_size], outline="#2b90d9", width=2)
                ch = grid[r][c]
                disabled = False
                if blank_words:
                    for bw in blank_words:
                        coords = placements.get(bw, [])
                        if (r,c) in coords:
                            disabled = True
                            break
                color = disabled_color if disabled else "#222"
                bb = draw.textbbox((0,0), ch, font=letter_font)
                draw.text((x+(cell_size-(bb[2]-bb[0]))/2, y+(cell_size-(bb[3]-bb[1]))/2 - 4), ch, fill=color, font=letter_font)
        # draw lines for found words (unless blanked)
        try:
            for w, coords in placements.items():
                if w in found and (not blank_words or w not in blank_words) and coords:
                    a = coords[0]; b = coords[-1]
                    x1 = pad + a[1]*cell_size + cell_size/2
                    y1 = grid_start_y + a[0]*cell_size + cell_size/2
                    x2 = pad + b[1]*cell_size + cell_size/2
                    y2 = grid_start_y + b[0]*cell_size + cell_size/2
                    draw.line([(x1,y1),(x2,y2)], fill="#ffffff", width=8)
                    draw.line([(x1,y1),(x2,y2)], fill="#ff4757", width=5)
                    r_end = 6
                    draw.ellipse([x1-r_end,y1-r_end,x1+r_end,y1+r_end], fill="#ff4757")
                    draw.ellipse([x2-r_end,y2-r_end,x2+r_end,y2+r_end], fill="#ff4757")
        except Exception:
            logger.exception("draw lines failed")
        # watermark & version
        wf = _load_font(14)
        wtext = watermark
        wb = draw.textbbox((0,0), wtext, font=wf)
        draw.text((width - wb[2] - 12, height - footer + 12), wtext, fill="#95a5a6", font=wf)
        vf = _load_font(12)
        draw.text((12, height - footer + 12), version, fill="#95a5a6", font=vf)
        bio = io.BytesIO()
        img.save(bio, "JPEG", quality=95, optimize=True)
        bio.seek(0)
        try: bio.name = "grid.jpg"
        except: pass
        return bio

def create_found_animation(grid, placements, found, target_word, is_hard=False, watermark="@Ruhvaan"):
    try:
        base_bio = GridRenderer.draw(grid, placements, found=set(), is_hard=is_hard)
        base = Image.open(base_bio).convert("RGBA")
        cell = 56
        header = 94
        pad = 24
        coords = placements.get(target_word)
        if not coords:
            out = io.BytesIO(); base.save(out, "GIF"); out.seek(0); return out
        a = coords[0]; b = coords[-1]
        x1 = pad + a[1]*cell + cell/2
        y1 = header + pad + a[0]*cell + cell/2
        x2 = pad + b[1]*cell + cell/2
        y2 = header + pad + b[0]*cell + cell/2
        frames=[]
        steps=10
        for i in range(steps):
            im = base.copy()
            d = ImageDraw.Draw(im)
            t = (i+1)/steps
            xi = x1 + (x2-x1)*t
            yi = y1 + (y2-y1)*t
            d.line([(x1,y1),(xi,yi)], fill="#ffffff", width=8)
            d.line([(x1,y1),(xi,yi)], fill="#ff4757", width=5)
            r_end=6
            d.ellipse([x1-r_end,y1-r_end,x1+r_end,y1+r_end], fill="#ff4757")
            d.ellipse([xi-r_end,yi-r_end,xi+r_end,yi+r_end], fill="#ff4757")
            wf=_load_font(14); wb=d.textbbox((0,0), watermark, font=wf)
            d.text((im.width - wb[2] - 12, im.height - 44), watermark, fill="#95a5a6", font=wf)
            frames.append(im.convert("P", palette=Image.ADAPTIVE))
        # final frame: show final image with blanked letters but keep line drawn
        final_bio = GridRenderer.draw(grid, placements, found=set(), blank_words=set(found), is_hard=is_hard)
        final = Image.open(final_bio).convert("P", palette=Image.ADAPTIVE)
        frames.append(final)
        out = io.BytesIO()
        frames[0].save(out, format='GIF', save_all=True, append_images=frames[1:], duration=80, loop=0, optimize=True)
        out.seek(0)
        try: out.name = "found.gif"
        except: pass
        return out
    except Exception:
        logger.exception("create_found_animation error")
        out = io.BytesIO(); base_bio.seek(0); out.write(base_bio.getvalue()); out.seek(0); return out

# -------------------------
# Game registry & class (same as earlier, trimmed for clarity)
# -------------------------
games: Dict[int, 'GameSession'] = {}

class GameSession:
    def __init__(self, chat_id:int, mode:str="default", is_hard:bool=False, duration:int=GAME_DURATION, word_pool:Optional[List[str]]=None):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.duration = duration
        self.start_time = time.time()
        self.last_activity = time.time()
        self.grid: List[List[str]] = []
        self.placements: Dict[str,List[Tuple[int,int]]] = {}
        self.words: List[str] = []
        self.found: set = set()
        self.players_scores: Dict[int,int] = {}
        self.players_last_guess: Dict[int,float] = {}
        self.message_id: Optional[int] = None
        self.timer_thread: Optional[threading.Thread] = None
        self.active = True
        # build session content
        pool = [w.upper() for w in (word_pool or ALL_WORDS)]
        self._prepare_grid(pool)
        self.start_timer()

    def _prepare_grid(self, pool:List[str]):
        choices = pool[:]
        if len(choices) < self.word_count:
            choices *= ((self.word_count // max(1,len(choices))) + 2)
        self.words = random.sample(choices, self.word_count)
        self.grid = [[" " for _ in range(self.size)] for __ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        for w in sorted_words:
            placed=False
            for _ in range(400):
                r=random.randint(0,self.size-1); c=random.randint(0,self.size-1); dr,dc=random.choice(dirs)
                if self._can_place(r,c,dr,dc,w):
                    coords=[] 
                    for i,ch in enumerate(w):
                        rr,cc = r + i*dr, c + i*dc
                        self.grid[rr][cc]=ch
                        coords.append((rr,cc))
                    self.placements[w]=coords
                    placed=True; break
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c]==" ":
                    self.grid[r][c] = random.choice(string.ascii_uppercase)

    def _can_place(self,r,c,dr,dc,word):
        for i in range(len(word)):
            rr = r + i*dr; cc = c + i*dc
            if not (0<=rr<self.size and 0<=cc<self.size): return False
            if self.grid[rr][cc] != " " and self.grid[rr][cc] != word[i]: return False
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
        self.timer_thread = threading.Thread(target=self._timer, daemon=True)
        self.timer_thread.start()

    def _timer(self):
        try:
            while self.active:
                rem = int(self.duration - (time.time() - self.start_time))
                if rem <= 0:
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! Game ended.")
                    except:
                        pass
                    try:
                        end_game_session(self.chat_id, "timeout")
                    except:
                        pass
                    break
                # update caption each 10s if message present
                if self.message_id:
                    mins,secs = divmod(rem,60)
                    cap = (f"🔥 <b>WORD VORTEX</b>\nMode: {self.mode} {'(Hard)' if self.is_hard else ''}\n⏱ Time Left: {mins}:{secs:02d}\n\n{self.get_hint_text()}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("💵 Redeem", callback_data="open_redeem"),
                               InlineKeyboardButton("📊 Score", callback_data="game_score"))
                    safe_edit_message(cap, self.chat_id, self.message_id, reply_markup=markup)
                time.sleep(10)
        except Exception:
            logger.exception("timer failed")
        finally:
            self.active=False

# -------------------------
# Helpers & menu
# -------------------------
def is_subscribed(user_id:int)->bool:
    if not FORCE_JOIN: return True
    if OWNER_ID and user_id == OWNER_ID: return True
    if not CHANNEL_USERNAME: return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ("creator","administrator","member")
    except Exception:
        logger.debug("sub check failed"); return True

def safe_edit_message(caption,cid,mid,reply_markup=None)->bool:
    try:
        bot.edit_message_caption(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup)
        return True
    except: pass
    try:
        bot.edit_message_text(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup, parse_mode="HTML")
        return True
    except: pass
    try:
        bot.send_message(cid, caption, reply_markup=reply_markup, parse_mode="HTML")
        try: bot.delete_message(cid, mid)
        except: pass
        return True
    except:
        logger.exception("safe_edit failed"); return False

def try_send_dm(uid:int, text:str, reply_markup=None)->bool:
    try:
        bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except:
        return False

COMMANDS_FULL_TEXT = """
🤖 Word Vortex - Commands
Use /cmd to get this list if the Commands button cannot DM you.

User:
/start /help
/cmd - fallback commands
/new, /new_hard, /new_physics, /new_chemistry, /new_math, /new_jee
/new_anagram, /new_speedrun, /new_definehunt, /new_survival, /new_team, /new_daily, /new_phrase
/hint, /scorecard, /mystats, /balance, /leaderboard
/issue <text>, /review <text>, /define <word>
/redeem_request

Owner:
/addpoints /addadmin /deladmin /admins /reset_leaderboard /broadcast
/set_hint_cost /toggle_force_join /set_start_image /show_settings /restart
/list_reviews /approve_review
/redeem_list /redeem_pay
"""

def build_main_menu_markup():
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
    except:
        pass
    kb.add(InlineKeyboardButton("🎮 Play Game", callback_data="help_play"),
           InlineKeyboardButton("🤖 Commands", callback_data="help_cmd"))
    kb.add(InlineKeyboardButton("🏆 Leaderboard", callback_data="menu_lb"),
           InlineKeyboardButton("👤 My Stats", callback_data="menu_stats"))
    kb.add(InlineKeyboardButton("🐞 Report Issue", callback_data="open_issue"),
           InlineKeyboardButton("💳 Buy Points", callback_data="open_plans"))
    kb.add(InlineKeyboardButton("✍️ Review", callback_data="open_review"),
           InlineKeyboardButton("💵 Redeem", callback_data="open_redeem"))
    kb.add(InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))
    return kb

# -------------------------
# Bot handlers
# -------------------------
@bot.message_handler(commands=["start","help"])
def handle_start(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.register_user(m.from_user.id, name)
    if OWNER_ID:
        try: bot.send_message(OWNER_ID, f"🔔 /start by {name} (id:{m.from_user.id}) in chat {m.chat.id}") 
        except: pass
    txt = f"👋 <b>Hello, {html.escape(name)}</b>!\nWelcome to Word Vortex.\nClick buttons below. Commands try to DM you."
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=build_main_menu_markup())
    except:
        bot.reply_to(m, txt, reply_markup=build_main_menu_markup())

@bot.message_handler(commands=["cmd"])
def handler_cmd(m):
    try:
        bot.send_message(m.from_user.id, COMMANDS_FULL_TEXT, parse_mode="HTML")
        bot.reply_to(m, "✅ I sent commands to your private chat.")
    except:
        try:
            bot.reply_to(m, COMMANDS_FULL_TEXT)
        except:
            bot.reply_to(m, "❌ Could not show commands. Start a private chat with the bot and try /start.")

@bot.message_handler(commands=["status"])
def handler_status(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    txt = "Active games:\n"
    for cid, s in games.items():
        txt += f"- chat_id: {cid}, mode: {s.mode}, words: {len(s.words)}, found: {len(s.found)}\n"
    bot.reply_to(m, txt or "No active games.")

@bot.message_handler(commands=["endgame"])
def handler_endgame(m):
    cid = m.chat.id
    if cid not in games:
        bot.reply_to(m, "No active game here.")
        return
    if not (db.is_admin(m.from_user.id) or (OWNER_ID and m.from_user.id == OWNER_ID)):
        bot.reply_to(m, "Owner/admin only.")
        return
    end_game_session(cid, "stopped")
    bot.reply_to(m, "Game stopped.")

# Callback handler (menu)
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data
    def ack(text="", alert=False):
        try:
            bot.answer_callback_query(c.id, text, show_alert=alert)
        except:
            pass

    if data == "check_join":
        if is_subscribed(uid):
            try: bot.delete_message(cid, c.message.message_id)
            except: pass
            handle_start(c.message)
            ack("✅ Verified")
        else:
            ack("❌ Not joined", alert=True)
        return

    if data == "help_cmd":
        if try_send_dm(uid, COMMANDS_FULL_TEXT):
            ack("I sent commands to your PM.")
        else:
            try: bot.send_message(cid, COMMANDS_FULL_TEXT); ack("Opened here.")
            except: ack("❌ Could not open.", alert=True)
        return

    if data == "open_redeem":
        user = db.get_user(uid, c.from_user.first_name)
        total = user[5]
        if total < REDEEM_THRESHOLD:
            msg = f"❌ Need {REDEEM_THRESHOLD} pts. Your: {total}"
            if try_send_dm(uid, msg): ack("Sent to PM")
            else:
                try: bot.send_message(cid, msg); ack("Opened here")
                except: ack("❌ Could not open.", alert=True)
            return
        confirm_kb = InlineKeyboardMarkup()
        confirm_kb.add(InlineKeyboardButton("✅ Confirm Redeem", callback_data="redeem_confirm"),
                       InlineKeyboardButton("❌ Cancel", callback_data="menu_back"))
        confirm_text = f"💵 Redeem Request\nYou have {total} pts. Confirm to request {REDEEM_THRESHOLD} pts."
        if try_send_dm(uid, confirm_text, reply_markup=confirm_kb): ack("Confirmation sent to PM")
        else:
            try: bot.send_message(cid, confirm_text, reply_markup=confirm_kb); ack("Opened here")
            except: ack("❌ Could not open confirmation", alert=True)
        return

    if data == "redeem_confirm":
        rid = db.add_redeem_request(uid, REDEEM_THRESHOLD)
        try: bot.send_message(uid, f"✅ Your order is pending (ID: {rid}). Owner notified.")
        except: bot.send_message(cid, f"✅ {c.from_user.first_name} requested redeem (ID:{rid}).")
        if OWNER_ID:
            try: bot.send_message(OWNER_ID, f"💸 Redeem ID {rid} by {c.from_user.first_name} ({uid}) for {REDEEM_THRESHOLD} pts. Use /redeem_pay {rid} <notes> to mark SENT.")
            except: pass
        ack("Redeem requested.")
        return

    if data == "menu_back":
        try: handle_start(c.message); ack("Menu opened")
        except: ack("❌ Could not open", alert=True)
        return

    # other callbacks handled elsewhere
    ack()

# -------------------------
# Start game handler
# -------------------------
@bot.message_handler(commands=["new","new_hard","new_physics","new_chemistry","new_math","new_jee","new_anagram","new_speedrun","new_definehunt","new_survival","new_team","new_daily","new_phrase"])
def handle_new(m):
    cmd = m.text.split()[0].lstrip("/").lower()
    chat_id = m.chat.id
    uid = m.from_user.id
    db.register_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if cmd == "new":
        s = GameSession(chat_id, mode="default", is_hard=False)
        games[chat_id] = s
        _send_session_start(s)
    elif cmd == "new_hard":
        s = GameSession(chat_id, mode="default", is_hard=True)
        games[chat_id] = s
        _send_session_start(s)
    elif cmd == "new_physics":
        pool = ["FORCE","ENERGY","MOMENTUM","VELOCITY","VECTOR","PHOTON","GRAVITY"]
        pool += random.sample(ALL_WORDS, min(50,len(ALL_WORDS)))
        s = GameSession(chat_id, mode="physics", is_hard=False, word_pool=pool)
        games[chat_id]=s; _send_session_start(s)
    elif cmd == "new_anagram":
        s = GameSession(chat_id, mode="anagram")
        games[chat_id]=s
        txt = "🎯 Anagram Sprint\nSolve these:\n"
        for i,a in enumerate(s.anagrams,1):
            txt += f"{i}. <code>{a['jumbled']}</code>\n"
        bot.send_message(chat_id, txt)
    else:
        # simplified: other modes create a basic session (you can expand)
        s = GameSession(chat_id, mode=cmd)
        games[chat_id]=s
        _send_session_start(s)
    db.update_stats(uid, games_played_delta=1)
    try:
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"🎮 Game started in {chat_id} by {m.from_user.first_name} ({cmd})")
    except:
        pass

def _send_session_start(session: GameSession):
    img = GridRenderer.draw(session.grid, session.placements, session.found, is_hard=session.is_hard, watermark="@Ruhvaan")
    try:
        img.seek(0)
    except: pass
    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\nMode: {session.mode} {'(Hard)' if session.is_hard else ''}\n"
               f"⏱ Time Limit: {session.duration//60} minutes\n\n{session.get_hint_text()}")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💵 Redeem", callback_data="open_redeem"),
               InlineKeyboardButton("📊 Score", callback_data="game_score"))
    try:
        sent = bot.send_photo(session.chat_id, img, caption=caption, reply_markup=markup)
        session.message_id = getattr(sent, "message_id", None)
    except Exception:
        logger.exception("send start image failed")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                tf.write(img.getvalue())
                tmp = tf.name
            with open(tmp,'rb') as f:
                sent = bot.send_photo(session.chat_id, f, caption=caption, reply_markup=markup)
                session.message_id = getattr(sent, "message_id", None)
            try: os.unlink(tmp)
            except: pass
        except Exception:
            bot.send_message(session.chat_id, caption, reply_markup=markup)

# -------------------------
# Automatic guess detection: watch group messages and validate words
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def auto_guess_handler(m):
    # Ignore private chats for auto-guessing
    if m.chat.type not in ("group","supergroup"):
        # still handle other commands in private chat above
        return
    chat_id = m.chat.id
    if chat_id not in games:
        # no active game
        return
    session = games[chat_id]
    if not session.active:
        return
    text = (m.text or "").strip().upper()
    if not text:
        return
    # normalize: only letters, remove punctuation around single word
    token = "".join([ch for ch in text if ch.isalpha()])
    if not token:
        return
    # If message contains multiple words, check each token separately
    tokens = text.split()
    candidates = []
    for t in tokens:
        cleaned = "".join([ch for ch in t if ch.isalpha()]).upper()
        if cleaned:
            candidates.append(cleaned)
    # check each candidate; prioritize exact match
    for cand in candidates:
        if cand in session.words and cand not in session.found:
            uid = m.from_user.id
            now = time.time()
            last = session.players_last_guess.get(uid, 0)
            if now - last < COOLDOWN:
                try:
                    # optionally notify user privately about cooldown - skip to avoid spam
                    pass
                except:
                    pass
                return
            # process as correct guess
            session.players_last_guess[uid] = now
            process_correct_guess(session, cand, m.from_user)
            # optionally delete the user's guess message for cleanliness
            try:
                bot.delete_message(chat_id, m.message_id)
            except:
                pass
            return
    # if no candidate matched, ignore

def process_correct_guess(session: GameSession, word: str, user):
    chat_id = session.chat_id
    uid = user.id
    name = user.first_name or user.username or "Player"
    session.found.add(word)
    session.last_activity = time.time()
    # scoring
    if len(session.found) == 1:
        pts = FIRST_BLOOD_POINTS
    elif len(session.found) == len(session.words):
        pts = FINISHER_POINTS
    else:
        pts = NORMAL_POINTS
    session.players_scores[uid] = session.players_scores.get(uid,0) + pts
    db.update_stats(uid, score_delta=pts)
    # animation
    try:
        anim = create_found_animation(session.grid, session.placements, session.found, word, is_hard=session.is_hard, watermark="@Ruhvaan")
        anim.seek(0)
        bot.send_animation(chat_id, anim, caption=f"✨ {html.escape(name)} found <code>{word}</code> (+{pts} pts) 🎯")
    except Exception:
        logger.exception("send animation failed")
        bot.send_message(chat_id, f"✨ {html.escape(name)} found <code>{word}</code> (+{pts} pts) 🎯")
    # final premium image with blanked letters AND keep line visible
    try:
        final = GridRenderer.draw(session.grid, session.placements, session.found, blank_words=set(session.found), is_hard=session.is_hard, watermark="@Ruhvaan", version="v7.1")
        final.seek(0)
        sent = bot.send_photo(chat_id, final, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if session.is_hard else 'Normal'}\n\n{session.get_hint_text()}"),
                              reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💵 Redeem", callback_data="open_redeem"),
                                                                      InlineKeyboardButton("📊 Score", callback_data="game_score")))
        try:
            if getattr(session,"message_id",None):
                bot.delete_message(chat_id, session.message_id)
        except:
            pass
        try:
            session.message_id = getattr(sent,"message_id", None)
        except:
            session.message_id = None
    except Exception:
        logger.exception("send final image failed")
    # check end
    if len(session.found) == len(session.words):
        end_game_session(chat_id, "win", uid)

# -------------------------
# Redeem handlers (owner workflow + user confirmation)
# -------------------------
@bot.message_handler(commands=["redeem_request"])
def redeem_request_cmd(m):
    uid = m.from_user.id
    u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if u[5] < REDEEM_THRESHOLD:
        bot.reply_to(m, f"❌ Need {REDEEM_THRESHOLD} pts. You have {u[5]}")
        return
    rid = db.add_redeem_request(uid, REDEEM_THRESHOLD)
    bot.reply_to(m, f"✅ Your order is pending (ID: {rid}). Owner will be notified.")
    if OWNER_ID:
        try: bot.send_message(OWNER_ID, f"💸 Redeem request ID {rid} by {u[1]} ({uid}) for {REDEEM_THRESHOLD} pts. Use /redeem_pay {rid} <notes> to mark SENT.")
        except: pass

@bot.message_handler(commands=["redeem_list","redeem_pay"])
def redeem_admin_cmd(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    cmd = parts[0].lstrip("/")
    if cmd == "redeem_list":
        rows = db.list_redeems(status=0)
        if not rows:
            bot.reply_to(m, "No pending redeems.")
            return
        txt = "Pending redeems:\n"
        for r in rows:
            txt += f"ID:{r[0]} User:{r[1]} Points:{r[2]} At:{r[3]}\n"
        bot.reply_to(m, txt)
    else:
        if len(parts) < 2:
            bot.reply_to(m, "Usage: /redeem_pay <id> <notes>")
            return
        try:
            rid = int(parts[1]); notes = " ".join(parts[2:]) if len(parts)>2 else ""
            res = db.mark_redeem_sent(rid, m.from_user.id, notes)
            if not res:
                bot.reply_to(m, f"Redeem {rid} not found.")
                return
            user_id, points = res
            try: bot.send_message(user_id, f"💸 Owner marked redeem ID {rid} as SENT. After you receive payment, confirm with /redeem_received {rid}")
            except: pass
            bot.reply_to(m, f"Redeem {rid} marked SENT.")
        except:
            bot.reply_to(m, "Operation failed.")

@bot.message_handler(commands=["redeem_received"])
def redeem_received_cmd(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /redeem_received <id>")
        return
    try:
        rid = int(parts[1]); uid = m.from_user.id
        points = db.mark_redeem_complete_by_user(rid, uid)
        if not points:
            bot.reply_to(m, "Cannot confirm redeem. Either invalid id or owner did not mark as SENT.")
            return
        db.update_stats(uid, cash_delta=0)
        bot.reply_to(m, f"✅ Redeem ID {rid} marked COMPLETE. Owner notified.")
        if OWNER_ID:
            try: bot.send_message(OWNER_ID, f"✅ User {m.from_user.first_name} ({uid}) confirmed redeem ID {rid}. Points: {points}")
            except: pass
    except:
        bot.reply_to(m, "Operation failed.")

# -------------------------
# Admin addpoints, reviews, define, scorecard, hint, leaderboard
# -------------------------
@bot.message_handler(commands=["addpoints"])
def addpoints_cmd(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]")
        return
    target = parts[1]; amt = 0
    try: amt = int(parts[2])
    except: bot.reply_to(m,"Amount must be integer"); return
    mode = parts[3].lower() if len(parts) >=4 else "balance"
    try:
        if target.lstrip("-").isdigit(): tid=int(target)
        else:
            if not target.startswith("@"): target = "@"+target
            ch = bot.get_chat(target); tid = ch.id
    except:
        bot.reply_to(m, "Could not find user")
        return
    db.register_user(tid, "Player")
    if mode == "score":
        db.update_stats(tid, score_delta=amt)
    else:
        db.update_stats(tid, hint_delta=amt)
    bot.reply_to(m, f"Added {amt} ({mode}) to {tid}")
    try: bot.send_message(tid, f"💸 You received {amt} pts ({mode}) from owner")
    except: pass

@bot.message_handler(commands=["review"])
def review_cmd(m):
    text = m.text.replace("/review","",1).strip()
    if not text:
        bot.reply_to(m, "Usage: /review <text>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player", text)
    bot.reply_to(m, "✅ Review submitted. Thank you!")
    if OWNER_ID:
        try: bot.send_message(OWNER_ID, f"📝 Review from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
        except: pass

@bot.message_handler(commands=["define"])
def define_cmd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts)<2:
        bot.reply_to(m,"Usage: /define <word>"); return
    w = parts[1].strip()
    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=6)
        data = r.json()
        if isinstance(data, list) and data:
            meanings = data[0].get("meanings",[])
            if meanings:
                defs = meanings[0].get("definitions",[])
                if defs:
                    d = defs[0].get("definition","")
                    ex = defs[0].get("example","")
                    txt = f"📚 <b>{html.escape(w)}</b>\n{html.escape(d)}"
                    if ex: txt += f"\n\n<i>Example:</i> {html.escape(ex)}"
                    bot.reply_to(m, txt); return
        bot.reply_to(m, f"No definition found for {w}")
    except:
        logger.exception("define failed"); bot.reply_to(m,"Error fetching definition")

@bot.message_handler(commands=["scorecard","mystats"])
def scorecard_cmd(m):
    uid = m.from_user.id; u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    session_pts = 0
    gid = m.chat.id
    if gid in games: session_pts = games[gid].players_scores.get(uid,0)
    cash = u[8] if len(u)>8 else 0
    bot.reply_to(m, (f"📋 <b>Your Scorecard</b>\nName: {html.escape(u[1])}\nTotal Score: {u[5]}\nWins: {u[4]}\nGames Played: {u[3]}\nSession Points: {session_pts}\nHint Balance: {u[6]}\nCash Balance: {cash}"))

@bot.message_handler(commands=["hint"])
def hint_cmd(m):
    gid=m.chat.id; uid=m.from_user.id
    if gid not in games: bot.reply_to(m, "No active game"); return
    u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if u[6] < HINT_COST: bot.reply_to(m, f"❌ Need {HINT_COST} pts. Your: {u[6]}"); return
    g = games[gid]
    hidden = [w for w in g.words if w not in g.found]
    if not hidden: bot.reply_to(m,"All words found"); return
    reveal = random.choice(hidden)
    db.update_stats(uid, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")

@bot.message_handler(commands=["leaderboard"])
def leaderboard_cmd(m):
    top = db.get_top_players()
    txt = "🏆 Top Players\n"
    for i,(n,s) in enumerate(top,1): txt+=f"{i}. {html.escape(n)} - {s} pts\n"
    bot.reply_to(m,txt)

# -------------------------
# End & run
# -------------------------
@app.route("/")
def index():
    return "Word Vortex Bot v7.1 running"

if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", "5000"))
        app.run(host="0.0.0.0", port=port)
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Starting Word Vortex Bot v7.1...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            logger.exception("Polling error; restarting in 5s")
            time.sleep(5)
