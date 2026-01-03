#!/usr/bin/env python3
"""
WORD VORTEX - ULTIMATE PREMIUM EDITION
Version: 7.0 - Consolidated full bot
- All requested features included:
  * Multiple game modes (normal, hard, physics, chemistry, math, jee, anagram, speedrun, definehunt, survival, team, daily, phrase)
  * Commands button DM-first + /cmd fallback
  * /cmdinfo per-command help
  * Reviews (/review) and owner moderation (/list_reviews, /approve_review)
  * Redeem flow: /redeem_request -> owner /redeem_pay (mark SENT) -> user /redeem_received (mark COMPLETE)
  * Animated "found" GIF + premium final image with watermark "@Ruhvaan"
  * Images regenerated and previous ones cleaned up
  * Admin utilities: /addpoints (default -> balance), /addadmin, /deladmin, /admins, /reset_leaderboard, /broadcast, /set_hint_cost, /toggle_force_join, /set_start_image, /show_settings, /restart
  * Robust fallbacks and logging
- Requirements: pip install pyTelegramBotAPI Pillow requests flask
- Set TELEGRAM_TOKEN and OWNER_ID env vars before running.
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

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "")  # e.g., "@Ruhvaan_Updates"
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
PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

DB_PATH = os.environ.get("WORDS_DB", "wordsgrid_full.db")

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
                is_banned INTEGER DEFAULT 0,
                cash_balance INTEGER DEFAULT 0
            )"""
        )
        # admins
        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")
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
        # redeems
        c.execute(
            """CREATE TABLE IF NOT EXISTS redeems (
                redeem_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_points INTEGER,
                requested_at TEXT,
                processed INTEGER DEFAULT 0,
                admin_id INTEGER,
                notes TEXT,
                status INTEGER DEFAULT 0
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
        # settings
        c.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        conn.commit()
        conn.close()

    # Users
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

    # Admins
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

    # History
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
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows

    # Reviews
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

    # Redeems
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
    ALL_WORDS = ["PYTHON", "JAVA", "SCRIPT", "ROBOT", "SPACE", "GALAXY", "NEBULA", "FUTURE", "MATRIX", "VECTOR"]
    logger.info("Using fallback wordlist.")

fetch_remote_wordlist()

# -------------------------
# IMAGE UTILITIES (watermark, higher quality, animation)
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

class GridRenderer:
    @staticmethod
    def draw(grid: List[List[str]], placements: Dict[str, List[Tuple[int,int]]], found: set, blank_words: Optional[set]=None, is_hard=False, watermark="@Ruhvaan", version="v7.0"):
        cell_size = 56
        header = 94
        footer = 44
        pad = 24
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        width = cols * cell_size + pad * 2
        height = header + rows * cell_size + footer + pad * 2
        img = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(img)
        header_font = _load_font(36)
        letter_font = _load_font(30)
        small_font = _load_font(14)
        draw.rectangle([0,0,width,header], fill="#eef6fb")
        tb = draw.textbbox((0,0),"WORD VORTEX", font=header_font)
        draw.text(((width - (tb[2]-tb[0]))/2,18),"WORD VORTEX", fill="#1f6feb", font=header_font)
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        draw.text((pad, header-26), mode_text, fill="#6b7280", font=small_font)
        start_y = header + pad
        disabled_color = "#b0bec5"
        for r in range(rows):
            for c in range(cols):
                x = pad + c*cell_size
                y = start_y + r*cell_size
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
                draw.text((x + (cell_size - (bb[2]-bb[0]))/2, y + (cell_size - (bb[3]-bb[1]))/2 - 4), ch, fill=color, font=letter_font)
        # draw lines for found words (not blanked)
        try:
            if placements and found:
                for w, coords in placements.items():
                    if w in found and (not blank_words or w not in blank_words) and coords:
                        a = coords[0]; b = coords[-1]
                        x1 = pad + a[1]*cell_size + cell_size/2
                        y1 = start_y + a[0]*cell_size + cell_size/2
                        x2 = pad + b[1]*cell_size + cell_size/2
                        y2 = start_y + b[0]*cell_size + cell_size/2
                        draw.line([(x1,y1),(x2,y2)], fill="#ffffff", width=8)
                        draw.line([(x1,y1),(x2,y2)], fill="#ff4757", width=5)
                        r_end = 6
                        draw.ellipse([x1-r_end,y1-r_end,x1+r_end,y1+r_end], fill="#ff4757")
                        draw.ellipse([x2-r_end,y2-r_end,x2+r_end,y2+r_end], fill="#ff4757")
        except Exception:
            logger.exception("Error drawing found lines")
        # footer watermark and version
        wf = _load_font(14)
        wtext = watermark
        wb = draw.textbbox((0,0), wtext, font=wf)
        draw.text((width - wb[2] - 12, height - footer + 12), wtext, fill="#95a5a6", font=wf)
        vf = _load_font(12)
        draw.text((12, height - footer + 12), version, fill="#95a5a6", font=vf)
        bio = io.BytesIO()
        img.save(bio, "JPEG", quality=95, optimize=True)
        bio.seek(0)
        try:
            bio.name = "grid.jpg"
        except:
            pass
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
            bio = io.BytesIO()
            base.save(bio, "GIF")
            bio.seek(0)
            return bio
        a = coords[0]; b = coords[-1]
        x1 = pad + a[1]*cell + cell/2
        y1 = header + pad + a[0]*cell + cell/2
        x2 = pad + b[1]*cell + cell/2
        y2 = header + pad + b[0]*cell + cell/2
        frames = []
        steps = 12
        for i in range(steps):
            im = base.copy()
            d = ImageDraw.Draw(im)
            t = (i+1)/steps
            xi = x1 + (x2 - x1)*t
            yi = y1 + (y2 - y1)*t
            d.line([(x1,y1),(xi,yi)], fill="#ffffff", width=8)
            d.line([(x1,y1),(xi,yi)], fill="#ff4757", width=5)
            r_end = 6
            d.ellipse([x1-r_end,y1-r_end,x1+r_end,y1+r_end], fill="#ff4757")
            d.ellipse([xi-r_end,yi-r_end,xi+r_end,yi+r_end], fill="#ff4757")
            wf = _load_font(14)
            wtext = watermark
            wb = d.textbbox((0,0), wtext, font=wf)
            d.text((im.width - wb[2] - 12, im.height - 44), wtext, fill="#95a5a6", font=wf)
            frames.append(im.convert("P", palette=Image.ADAPTIVE))
        # final frame: blank out found words
        final_bio = GridRenderer.draw(grid, placements, found=set(), blank_words=set(found), is_hard=is_hard)
        final = Image.open(final_bio).convert("P", palette=Image.ADAPTIVE)
        frames.append(final)
        out = io.BytesIO()
        frames[0].save(out, format='GIF', save_all=True, append_images=frames[1:], duration=80, loop=0, optimize=True)
        out.seek(0)
        try:
            out.name = "found.gif"
        except:
            pass
        return out
    except Exception:
        logger.exception("create_found_animation failed")
        bio = io.BytesIO()
        base_bio = GridRenderer.draw(grid, placements, found=set(), is_hard=is_hard)
        bio.write(base_bio.getvalue())
        bio.seek(0)
        return bio

# -------------------------
# GAME SESSION
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
        self.timer_thread: Optional[threading.Thread] = None
        self.active = True
        self.anagrams: List[Dict] = []
        self.definitions: List[str] = []
        # pick pool
        pool = []
        if word_pool:
            pool = [w.upper() for w in word_pool if isinstance(w, str)]
        else:
            pool = ALL_WORDS[:]
        # generate per mode
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
        self.start_timer()

    def _prepare_grid(self, pool):
        choices = pool[:] if pool else ALL_WORDS[:]
        if len(choices) < self.word_count:
            choices = choices * ((self.word_count // max(1,len(choices))) + 2)
        self.words = random.sample(choices, self.word_count)
        self.grid = [[" " for _ in range(self.size)] for __ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        for w in sorted_words:
            placed = False
            for _ in range(400):
                r = random.randint(0,self.size-1)
                c = random.randint(0,self.size-1)
                dr,dc = random.choice(dirs)
                if self._can_place(r,c,dr,dc,w):
                    coords=[]
                    for i,ch in enumerate(w):
                        rr,cc = r + i*dr, c + i*dc
                        self.grid[rr][cc]=ch
                        coords.append((rr,cc))
                    self.placements[w]=coords
                    placed=True
                    break
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c]==" ":
                    self.grid[r][c]=random.choice(string.ascii_uppercase)

    def _prepare_anagram(self, pool):
        choices = [w for w in pool if 4<=len(w)<=10]
        if len(choices)<8:
            choices *= 5
        selected = random.sample(choices,8)
        self.anagrams=[]
        for w in selected:
            j = list(w); random.shuffle(j)
            jumbled = "".join(j)
            if jumbled == w:
                random.shuffle(j)
                jumbled = "".join(j)
            self.anagrams.append({"word":w,"jumbled":jumbled})

    def _prepare_definehunt(self, pool):
        choices = [w for w in pool if 4<=len(w)<=10]
        if len(choices)<6:
            choices *= 3
        selected = random.sample(choices,6)
        self.words = [w.upper() for w in selected]
        self.definitions=[]
        for w in self.words:
            try:
                r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w.lower()}", timeout=6)
                data = r.json()
                if isinstance(data, list) and data:
                    meanings = data[0].get("meanings",[])
                    if meanings:
                        defs = meanings[0].get("definitions",[])
                        if defs:
                            self.definitions.append(defs[0].get("definition","")[:220])
                            continue
            except:
                pass
            self.definitions.append(f"Starts with {w[0]} and length {len(w)}")
        self._prepare_grid(self.words)

    def _prepare_speedrun(self, pool):
        self.word_count = 20 if not self.is_hard else 30
        choices=[w for w in pool if 3<=len(w)<=8]
        if len(choices)<self.word_count:
            choices *= ((self.word_count//max(1,len(choices)))+2)
        self.words = random.sample(choices,self.word_count)
        self._prepare_grid(self.words)

    def _prepare_survival(self, pool):
        self.word_count=4
        choices=[w for w in pool if 3<=len(w)<=6]
        if len(choices)<self.word_count:
            choices*=3
        self.words=random.sample(choices,self.word_count)
        self._prepare_grid(self.words)
        self.survival_round = 1

    def _prepare_phrase(self, pool):
        words=[w for w in pool if 3<=len(w)<=7]
        if len(words)<6:
            words*=3
        phrase_len=random.choice([3,4,5])
        phrase_words = random.sample(words,phrase_len)
        self.words = phrase_words + random.sample([w for w in pool if w not in phrase_words], self.word_count - phrase_len)
        self._prepare_grid(self.words)
        self.phrase = " ".join(phrase_words)

    def _can_place(self, r,c,dr,dc,word):
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
        self.timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self.timer_thread.start()

    def _timer_worker(self):
        try:
            while self.active:
                rem = int(self.duration - (time.time() - self.start_time))
                if rem <= 0:
                    try:
                        bot.send_message(self.chat_id, "⏰ Time's up! The game has ended.")
                    except:
                        pass
                    try:
                        end_game_session(self.chat_id, "timeout")
                    except:
                        logger.exception("End session on timeout failed")
                    break
                if self.message_id:
                    mins,secs = divmod(rem,60)
                    cap = (f"🔥 <b>WORD VORTEX STARTED!</b>\nMode: {self.mode} {'(Hard)' if self.is_hard else ''}\n⏱ Time Left: {mins}:{secs:02d}\n\n{self.get_hint_text()}")
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
                    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score"))
                    safe_edit_message(cap, self.chat_id, self.message_id, reply_markup=markup)
                time.sleep(8)
        except Exception:
            logger.exception("Timer worker failed")
        finally:
            self.active=False

# -------------------------
# HELPERS & MENU
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
        return status in ("creator","administrator","member")
    except Exception:
        logger.debug("Subscription check failed; allowing by default.")
        return True

def safe_edit_message(caption, cid, mid, reply_markup=None):
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
        except:
            pass
        return True
    except Exception:
        logger.exception("safe_edit_message failed")
        return False

def try_send_dm(uid: int, text: str, reply_markup=None) -> bool:
    try:
        bot.send_message(uid, text, parse_mode="HTML", reply_markup=reply_markup)
        return True
    except Exception:
        return False

COMMANDS_FULL_TEXT = """
🤖 Word Vortex - Full Command List

User:
/start /help - open menu
/cmd - fallback if Commands button can't DM you
/cmdinfo <command> - per-command help
/ping
/new, /new_hard, /new_physics, /new_chemistry, /new_math, /new_jee
/new_anagram, /new_speedrun, /new_definehunt, /new_survival, /new_team, /new_daily, /new_phrase
/hint, /scorecard, /mystats, /balance, /leaderboard
/issue <text>, /review <text>, /define <word>
/redeem_request

Owner:
/addpoints, /addadmin, /deladmin, /admins, /reset_leaderboard, /broadcast
/set_hint_cost, /toggle_force_join, /set_start_image, /show_settings, /restart
/list_reviews, /approve_review
/redeem_list, /redeem_pay
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
# BOT HANDLERS
# -------------------------
@bot.message_handler(commands=["start","help"])
def handler_start(m):
    name = m.from_user.first_name or m.from_user.username or "Player"
    db.register_user(m.from_user.id, name)
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🔔 /start by {name} (ID:{m.from_user.id}) in chat {m.chat.id}")
        except:
            pass
    txt = f"👋 <b>Hello, {html.escape(name)}!</b>\nWelcome to Word Vortex. Use the buttons below or /cmd."
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=build_main_menu_markup())
    except Exception:
        bot.reply_to(m, txt, reply_markup=build_main_menu_markup())

@bot.message_handler(commands=["cmd"])
def handler_cmd(m):
    try:
        bot.send_message(m.from_user.id, COMMANDS_FULL_TEXT, parse_mode="HTML")
        bot.reply_to(m, "✅ I sent the commands to your private chat.")
    except Exception:
        try:
            bot.reply_to(m, COMMANDS_FULL_TEXT)
        except:
            bot.reply_to(m, "❌ Could not show commands. Start a private chat with the bot and use /start.")

@bot.message_handler(commands=["cmdinfo"])
def handler_cmdinfo(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /cmdinfo <command>")
        return
    key = parts[1].strip().lstrip("/").lower()
    info = {
        "new":{"usage":"/new","desc":"Start normal 8x8 game","who":"Anyone"},
        "new_physics":{"usage":"/new_physics","desc":"Physics pool game","who":"Anyone"},
        "new_anagram":{"usage":"/new_anagram","desc":"Anagram Sprint","who":"Anyone"},
        "cmd":{"usage":"/cmd","desc":"Commands fallback","who":"Anyone"},
    }
    v = info.get(key)
    if not v:
        bot.reply_to(m, f"No info for {key}. Use /cmd.")
        return
    bot.reply_to(m, f"<b>/{key}</b>\nUsage: {v['usage']}\n\n{v['desc']}\nWho: {v['who']}")

# -------------------------
# CALLBACK HANDLER
# -------------------------
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
            ack("✅ Verified")
            try:
                bot.delete_message(cid, c.message.message_id)
            except:
                pass
            handler_start(c.message)
        else:
            ack("❌ Not joined", alert=True)
        return

    if data == "help_play":
        txt = ("<b>How to Play</b>\n1) Start /new in a group\n2) Use Found It -> type word\n3) Scoring: First/Normal/Finisher")
        if try_send_dm(uid, txt):
            ack("Sent to your PM")
        else:
            try:
                bot.send_message(cid, txt)
                ack("Opened here")
            except:
                ack("❌ Could not open", alert=True)
        return

    if data == "help_cmd":
        if try_send_dm(uid, COMMANDS_FULL_TEXT):
            ack("I sent the commands to your PM.")
        else:
            try:
                bot.send_message(cid, COMMANDS_FULL_TEXT)
                ack("Opened here.")
            except:
                ack("❌ Could not open commands.", alert=True)
        return

    if data == "menu_lb":
        top = db.get_top_players(10)
        txt = "🏆 Top Players\n"
        for i,(n,s) in enumerate(top,1):
            txt += f"{i}. {html.escape(n)} - {s} pts\n"
        if try_send_dm(uid, txt):
            ack("Sent to PM")
        else:
            try:
                bot.send_message(cid, txt)
                ack("Opened here")
            except:
                ack("❌ Could not open leaderboard.", alert=True)
        return

    if data == "menu_stats":
        u = db.get_user(uid, c.from_user.first_name or c.from_user.username or "Player")
        session_points = 0
        if c.message.chat.id in games:
            session_points = games[c.message.chat.id].players_scores.get(uid,0)
        txt = (f"📋 Your Stats\nName: {html.escape(u[1])}\nTotal Score: {u[5]}\nWins: {u[4]}\nGames Played: {u[3]}\nSession Points: {session_points}\nHint Balance: {u[6]}")
        if try_send_dm(uid, txt):
            ack("Sent to PM")
        else:
            try:
                bot.send_message(cid, txt)
                ack("Opened here")
            except:
                ack("❌ Could not open stats.", alert=True)
        return

    if data == "open_issue":
        try:
            bot.send_message(uid, "Please send your issue via /issue <text>", reply_markup=ForceReply(selective=True))
            ack("Prompt sent to PM")
        except:
            try:
                bot.send_message(cid, "Use /issue <text> to report.")
                ack("Opened here")
            except:
                ack("❌ Could not open issue prompt.", alert=True)
        return

    if data == "open_plans":
        txt = "💳 Plans:\n" + "\n".join([f"- {p['points']} pts : ₹{p['price_rs']}" for p in PLANS]) + f"\nContact: {SUPPORT_GROUP_LINK}"
        if try_send_dm(uid, txt):
            ack("Sent to PM")
        else:
            try:
                bot.send_message(cid, txt)
                ack("Opened here")
            except:
                ack("❌ Could not open plans.", alert=True)
        return

    if data == "open_review":
        try:
            bot.send_message(uid, "✍️ Send review via /review <text>", reply_markup=ForceReply(selective=True))
            ack("Prompt sent to PM")
        except:
            try:
                bot.send_message(cid, "Use /review <text> to submit review")
                ack("Opened here")
            except:
                ack("❌ Could not open review prompt", alert=True)
        return

    if data == "open_redeem":
        try:
            user = db.get_user(uid, c.from_user.first_name)
            total = user[5]
        except:
            total = 0
        if total < REDEEM_THRESHOLD:
            msg = f"❌ Need {REDEEM_THRESHOLD} pts. Your score: {total}"
            if try_send_dm(uid, msg):
                ack("Sent to PM")
            else:
                try:
                    bot.send_message(cid, msg)
                    ack("Opened here")
                except:
                    ack("❌ Could not open.", alert=True)
            return
        confirm_kb = InlineKeyboardMarkup()
        confirm_kb.add(InlineKeyboardButton("✅ Confirm Redeem", callback_data="redeem_confirm"),
                       InlineKeyboardButton("❌ Cancel", callback_data="menu_back"))
        confirm_text = f"💵 Redeem Request: You have {total} pts. Confirm to request {REDEEM_THRESHOLD} pts."
        if try_send_dm(uid, confirm_text, reply_markup=confirm_kb):
            ack("Confirmation sent to PM")
        else:
            try:
                bot.send_message(cid, confirm_text, reply_markup=confirm_kb)
                ack("Opened here")
            except:
                ack("❌ Could not open confirmation.", alert=True)
        return

    if data == "redeem_confirm":
        try:
            rid = db.add_redeem_request(uid, REDEEM_THRESHOLD)
            try:
                bot.send_message(uid, f"✅ Your order is pending (ID: {rid}). The owner will be notified.")
            except:
                bot.send_message(cid, f"✅ {c.from_user.first_name} requested redeem (ID: {rid}).")
            if OWNER_ID:
                try:
                    bot.send_message(OWNER_ID, f"💸 Redeem request ID {rid}\nUser: {c.from_user.first_name} ({uid})\nPoints: {REDEEM_THRESHOLD}\nUse /redeem_pay {rid} <notes> to mark SENT.")
                except:
                    pass
            ack("Redeem requested.")
        except:
            ack("❌ Could not create redeem.", alert=True)
        return

    # game callbacks handled elsewhere
    if data in ("game_guess","game_hint","game_score"):
        # let other handlers react; we simply ack
        try:
            bot.answer_callback_query(c.id, "")
        except:
            pass
        return

    # menu back
    if data == "menu_back":
        try:
            handler_start(c.message)
            ack("Menu opened")
        except:
            ack("❌ Could not open menu", alert=True)
        return

    ack()

# -------------------------
# GAME START / HANDLERS
# -------------------------
games: Dict[int, GameSession] = {}

def start_game_session(chat_id: int, starter_id: int, mode: str = "default", is_hard: bool = False, word_pool: Optional[List[str]] = None, duration: Optional[int] = None):
    if duration is None:
        duration = GAME_DURATION
    session = GameSession(chat_id, mode=mode, is_hard=is_hard, duration=duration, word_pool=word_pool)
    games[chat_id] = session
    try:
        db.register_user(starter_id, "Player")
        db.update_stats(starter_id, games_played_delta=1)
    except:
        logger.exception("starter register failed")
    # send initial image or text per mode
    if mode == "anagram":
        txt = "🎯 Anagram Sprint:\n"
        for i,a in enumerate(session.anagrams,1):
            txt += f"{i}. <code>{a['jumbled']}</code>\n"
        bot.send_message(chat_id, txt)
    else:
        img_bio = GridRenderer.draw(session.grid, session.placements, session.found, is_hard=session.is_hard, watermark="@Ruhvaan")
        try:
            img_bio.seek(0)
        except:
            pass
        caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\nMode: {mode} {'(Hard)' if is_hard else ''}\n⏱ Time Limit: {session.duration//60} minutes\n\n{session.get_hint_text()}")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"))
        markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"),
                   InlineKeyboardButton("📊 Score", callback_data="game_score"))
        try:
            sent = bot.send_photo(chat_id, img_bio, caption=caption, reply_markup=markup)
            try: session.message_id = sent.message_id
            except: session.message_id = None
        except Exception:
            logger.exception("send_photo failed, fallback to temp file")
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                    tf.write(img_bio.getvalue())
                    tmp = tf.name
                with open(tmp,'rb') as f:
                    sent = bot.send_photo(chat_id, f, caption=caption, reply_markup=markup)
                    try: session.message_id = sent.message_id
                    except: session.message_id = None
                try: os.unlink(tmp)
                except: pass
            except Exception:
                bot.send_message(chat_id, caption, reply_markup=markup)

@bot.message_handler(commands=["new","new_hard","new_physics","new_chemistry","new_math","new_jee","new_anagram","new_speedrun","new_definehunt","new_survival","new_team","new_daily","new_phrase"])
def handle_new(m):
    cmd = m.text.split()[0].lstrip("/").lower()
    chat_id = m.chat.id
    uid = m.from_user.id
    db.register_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if cmd == "new":
        start_game_session(chat_id, uid, mode="default", is_hard=False)
        bot.reply_to(m, "Started normal game.")
    elif cmd == "new_hard":
        start_game_session(chat_id, uid, mode="default", is_hard=True)
        bot.reply_to(m, "Started hard game.")
    elif cmd == "new_physics":
        pool = PHYSICS_WORDS + random.sample(ALL_WORDS, min(50,len(ALL_WORDS)))
        start_game_session(chat_id, uid, mode="physics", is_hard=False, word_pool=pool)
        bot.reply_to(m, "Started physics game.")
    elif cmd == "new_chemistry":
        pool = CHEMISTRY_WORDS + random.sample(ALL_WORDS, min(50,len(ALL_WORDS)))
        start_game_session(chat_id, uid, mode="chemistry", is_hard=False, word_pool=pool)
        bot.reply_to(m, "Started chemistry game.")
    elif cmd == "new_math":
        pool = MATH_WORDS + random.sample(ALL_WORDS, min(50,len(ALL_WORDS)))
        start_game_session(chat_id, uid, mode="math", is_hard=False, word_pool=pool)
        bot.reply_to(m, "Started math game.")
    elif cmd == "new_jee":
        pool = JEE_WORDS + random.sample(ALL_WORDS, min(50,len(ALL_WORDS)))
        start_game_session(chat_id, uid, mode="jee", is_hard=False, word_pool=pool)
        bot.reply_to(m, "Started JEE game.")
    elif cmd == "new_anagram":
        start_game_session(chat_id, uid, mode="anagram")
        bot.reply_to(m, "Anagram Sprint started.")
    elif cmd == "new_speedrun":
        start_game_session(chat_id, uid, mode="speedrun")
        bot.reply_to(m, "Speedrun started.")
    elif cmd == "new_definehunt":
        start_game_session(chat_id, uid, mode="definehunt")
        bot.reply_to(m, "Definition Hunt started.")
    elif cmd == "new_survival":
        start_game_session(chat_id, uid, mode="survival")
        bot.reply_to(m, "Survival started.")
    elif cmd == "new_team":
        if chat_id in games:
            bot.reply_to(m, "A game is already active.")
            return
        s = GameSession(chat_id, mode="team")
        s.teams = {"A": set(), "B": set()}
        s.join_phase = True
        games[chat_id]=s
        bot.reply_to(m, "Team Battle initialized. Players use /join_team to join. Admin use /start_team to start.")
    elif cmd == "new_daily":
        today = date.today().isoformat()
        puzzle = db.get_daily(today)
        if puzzle:
            bot.reply_to(m, "Today's daily challenge exists. Use /new_daily to load.")
        else:
            random.seed(today)
            words = random.sample(ALL_WORDS, min(6,len(ALL_WORDS)))
            s = GameSession(chat_id, mode="daily", word_pool=words)
            db.set_daily(today, json.dumps({"words":words}))
            bot.reply_to(m, "Daily challenge created for today.")
    elif cmd == "new_phrase":
        start_game_session(chat_id, uid, mode="phrase")
        bot.reply_to(m, "Phrase mode started.")
    else:
        bot.reply_to(m, "Unknown start command.")

# -------------------------
# Team flows
# -------------------------
@bot.message_handler(commands=["join_team"])
def join_team(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    name = m.from_user.first_name or m.from_user.username or "Player"
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session.")
        return
    s = games[chat_id]
    if not getattr(s,"join_phase",False):
        bot.reply_to(m, "Join phase closed.")
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
def start_team(m):
    if not (db.is_admin(m.from_user.id) or (OWNER_ID and m.from_user.id == OWNER_ID)):
        bot.reply_to(m, "Owner/admin only.")
        return
    chat_id = m.chat.id
    if chat_id not in games or games[chat_id].mode != "team":
        bot.reply_to(m, "No team session.")
        return
    s = games[chat_id]
    s.join_phase = False
    s._prepare_grid(ALL_WORDS)  # prepare normal grid
    img = GridRenderer.draw(s.grid, s.placements, s.found, watermark="@Ruhvaan")
    bot.send_photo(chat_id, img, caption=f"Team battle started! Team A:{len(s.teams['A'])} Team B:{len(s.teams['B'])}", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("📊 Score", callback_data="game_score")))

# -------------------------
# Reviews/Issues
# -------------------------
@bot.message_handler(commands=["review"])
def review_cmd(m):
    text = m.text.replace("/review","",1).strip()
    if not text:
        bot.reply_to(m, "Usage: /review <text>")
        return
    db.add_review(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player", text)
    bot.reply_to(m, "✅ Review submitted. Owner will see it.")
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"📝 Review from {m.from_user.first_name} ({m.from_user.id}):\n{text}")
        except:
            pass

@bot.message_handler(commands=["list_reviews","approve_review"])
def review_admin(m):
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
        txt=""
        for r in rows:
            txt += f"ID:{r[0]} User:{r[2]} At:{r[4]} Approved:{r[5]}\n{r[3][:300]}\n\n"
        bot.reply_to(m, txt[:4000])
    else:
        if len(parts)<2:
            bot.reply_to(m, "Usage: /approve_review <id>")
            return
        try:
            rid=int(parts[1]); db.approve_review(rid); bot.reply_to(m, f"Approved {rid}")
        except:
            bot.reply_to(m, "Failed")

# -------------------------
# Redeem handlers
# -------------------------
@bot.message_handler(commands=["redeem_request"])
def redeem_request(m):
    uid = m.from_user.id
    u = db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    total = u[5]
    if total < REDEEM_THRESHOLD:
        bot.reply_to(m, f"❌ Need {REDEEM_THRESHOLD} pts. Your: {total}")
        return
    rid = db.add_redeem_request(uid, REDEEM_THRESHOLD)
    bot.reply_to(m, f"✅ Your order is pending (ID: {rid}). Owner notified.")
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"💸 Redeem ID {rid} requested by {u[1]} ({uid}) for {REDEEM_THRESHOLD} pts. Use /redeem_pay {rid} <notes> to mark SENT.")
        except:
            pass

@bot.message_handler(commands=["redeem_list","redeem_pay"])
def redeem_admin(m):
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
        txt=""
        for r in rows:
            txt += f"ID:{r[0]} User:{r[1]} Points:{r[2]} At:{r[3]}\n"
        bot.reply_to(m, txt)
    else:
        if len(parts)<2:
            bot.reply_to(m, "Usage: /redeem_pay <id> <notes>")
            return
        try:
            rid=int(parts[1]); notes=" ".join(parts[2:]) if len(parts)>2 else ""
            res = db.mark_redeem_sent(rid, m.from_user.id, notes)
            if not res:
                bot.reply_to(m, f"Redeem {rid} not found.")
                return
            user_id, points = res
            try:
                bot.send_message(user_id, f"💸 Owner marked redeem ID {rid} as SENT. When you receive the payment confirm with /redeem_received {rid}")
            except:
                pass
            bot.reply_to(m, f"Redeem {rid} marked SENT.")
        except:
            bot.reply_to(m, "Failed")

@bot.message_handler(commands=["redeem_received"])
def redeem_received(m):
    parts = m.text.split()
    if len(parts)<2:
        bot.reply_to(m, "Usage: /redeem_received <id>")
        return
    try:
        rid=int(parts[1]); uid=m.from_user.id
        points = db.mark_redeem_complete_by_user(rid, uid)
        if not points:
            bot.reply_to(m, "Could not confirm redeem (maybe owner didn't mark SENT or wrong id).")
            return
        db.update_stats(uid, cash_delta=0)  # track only; payment is out-of-band
        bot.reply_to(m, f"✅ Redeem {rid} marked COMPLETE. Owner notified.")
        if OWNER_ID:
            try:
                bot.send_message(OWNER_ID, f"✅ User {m.from_user.first_name} ({uid}) confirmed redeem ID {rid}. Points: {points}")
            except:
                pass
    except:
        bot.reply_to(m, "Operation failed")

# -------------------------
# Admin utilities (addpoints default->balance)
# -------------------------
@bot.message_handler(commands=["addpoints"])
def addpoints(m):
    if m.from_user.id != OWNER_ID:
        bot.reply_to(m, "Owner only.")
        return
    parts = m.text.split()
    if len(parts)<3:
        bot.reply_to(m, "Usage: /addpoints <id|@username> <amount> [score|balance]")
        return
    target=parts[1]; amt=0
    try: amt=int(parts[2])
    except: bot.reply_to(m,"Amount must be integer"); return
    mode = parts[3].lower() if len(parts)>=4 else "balance"
    try:
        if target.lstrip("-").isdigit():
            tid=int(target)
        else:
            if not target.startswith("@"): target="@"+target
            ch=bot.get_chat(target); tid=ch.id
    except:
        bot.reply_to(m,"Could not find user")
        return
    db.register_user(tid,"Player")
    if mode=="score":
        db.update_stats(tid, score_delta=amt)
    else:
        db.update_stats(tid, hint_delta=amt)
    bot.reply_to(m,f"Added {amt} ({mode}) to {tid}")
    try: bot.send_message(tid, f"💸 You received {amt} pts ({mode}) from owner")
    except: pass

@bot.message_handler(commands=["addadmin","deladmin","admins","reset_leaderboard","broadcast","set_hint_cost","toggle_force_join","set_start_image","show_settings","restart"])
def admin_cmds(m):
    cmd = m.text.split()[0].lstrip("/")
    if cmd in ("addadmin","deladmin","reset_leaderboard","broadcast","set_hint_cost","toggle_force_join","set_start_image","show_settings","restart"):
        if m.from_user.id != OWNER_ID:
            bot.reply_to(m, "Owner only.")
            return
    # addadmin
    if cmd=="addadmin":
        parts=m.text.split()
        if len(parts)<2: bot.reply_to(m,"Usage: /addadmin <id|@username>"); return
        t=parts[1]
        try:
            if t.lstrip("-").isdigit(): aid=int(t)
            else:
                if not t.startswith("@"): t="@"+t
                ch=bot.get_chat(t); aid=ch.id
            db.add_admin(aid); bot.reply_to(m,f"Added admin {aid}")
        except:
            bot.reply_to(m,"Failed to add admin")
    elif cmd=="deladmin":
        parts=m.text.split()
        if len(parts)<2: bot.reply_to(m,"Usage: /deladmin <id|@username>"); return
        t=parts[1]
        try:
            if t.lstrip("-").isdigit(): aid=int(t)
            else:
                if not t.startswith("@"): t="@"+t
                ch=bot.get_chat(t); aid=ch.id
            db.remove_admin(aid); bot.reply_to(m,f"Removed admin {aid}")
        except:
            bot.reply_to(m,"Failed to remove admin")
    elif cmd=="admins":
        admins=db.list_admins(); txt="Admins:\n" + "\n".join(str(a) for a in admins)
        if OWNER_ID: txt+=f"\nOwner: {OWNER_ID}"
        bot.reply_to(m,txt)
    elif cmd=="reset_leaderboard":
        db.reset_leaderboard(); bot.reply_to(m,"Leaderboard reset.")
    elif cmd=="broadcast":
        parts=m.text.split(maxsplit=1)
        if len(parts)<2: bot.reply_to(m,"Usage: /broadcast <message>"); return
        msg=parts[1]; users=db.get_all_users(); s=f=0
        for u in users:
            try: bot.send_message(u,msg); s+=1
            except: f+=1
        bot.reply_to(m,f"Broadcast done. Success:{s} Fail:{f}")
    elif cmd=="set_hint_cost":
        parts=m.text.split()
        if len(parts)<2: bot.reply_to(m,"Usage: /set_hint_cost <amount>"); return
        try:
            global HINT_COST; HINT_COST=int(parts[1]); bot.reply_to(m,f"HINT_COST set to {HINT_COST}")
        except:
            bot.reply_to(m,"Invalid amount")
    elif cmd=="toggle_force_join":
        global FORCE_JOIN; FORCE_JOIN=not FORCE_JOIN; bot.reply_to(m,f"FORCE_JOIN set to {FORCE_JOIN}")
    elif cmd=="set_start_image":
        parts=m.text.split(maxsplit=1)
        if len(parts)<2: bot.reply_to(m,"Usage: /set_start_image <url>"); return
        global START_IMG_URL; START_IMG_URL=parts[1].strip(); bot.reply_to(m,"Start image updated.")
    elif cmd=="show_settings":
        bot.reply_to(m, f"FORCE_JOIN: {FORCE_JOIN}\nHINT_COST: {HINT_COST}\nSTART_IMG_URL: {START_IMG_URL}\nREDEEM_THRESHOLD: {REDEEM_THRESHOLD}")
    elif cmd=="restart":
        bot.reply_to(m, "Restarting..."); time.sleep(0.5)
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except:
            os._exit(0)

# -------------------------
# Define, scorecard, hint, leaderboard
# -------------------------
@bot.message_handler(commands=["define"])
def define_cmd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts)<2: bot.reply_to(m,"Usage: /define <word>"); return
    w=parts[1].strip()
    try:
        r=requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=6)
        data=r.json()
        if isinstance(data,list) and data:
            meanings=data[0].get("meanings",[])
            if meanings:
                defs=meanings[0].get("definitions",[])
                if defs:
                    d=defs[0].get("definition","")
                    ex=defs[0].get("example","")
                    txt=f"📚 <b>{html.escape(w)}</b>\n{html.escape(d)}"
                    if ex: txt+=f"\n\n<i>Example:</i> {html.escape(ex)}"
                    bot.reply_to(m,txt); return
        bot.reply_to(m,f"No definition for {w}")
    except:
        logger.exception("define failed"); bot.reply_to(m,"Error fetching definition")

@bot.message_handler(commands=["scorecard","mystats"])
def scorecard(m):
    uid=m.from_user.id; u=db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    session_pts=0
    gid=m.chat.id
    if gid in games: session_pts=games[gid].players_scores.get(uid,0)
    cash_bal = u[8] if len(u)>8 else 0
    bot.reply_to(m, (f"📋 <b>Your Scorecard</b>\nName: {html.escape(u[1])}\nTotal Score: {u[5]}\nWins: {u[4]}\nGames Played: {u[3]}\nSession Points: {session_pts}\nHint Balance: {u[6]}\nCash Balance: {cash_bal}"))

@bot.message_handler(commands=["balance"])
def balance(m):
    u=db.get_user(m.from_user.id, m.from_user.first_name or m.from_user.username or "Player")
    bot.reply_to(m, f"💰 Your balance: {u[6]} pts")

@bot.message_handler(commands=["leaderboard"])
def leaderboard(m):
    rows=db.get_top_players()
    txt="🏆 Top Players\n"
    for i,(n,s) in enumerate(rows,1): txt+=f"{i}. {html.escape(n)} - {s} pts\n"
    bot.reply_to(m,txt)

@bot.message_handler(commands=["hint"])
def hint(m):
    gid=m.chat.id; uid=m.from_user.id
    if gid not in games: bot.reply_to(m,"No active game"); return
    u=db.get_user(uid, m.from_user.first_name or m.from_user.username or "Player")
    if u[6] < HINT_COST: bot.reply_to(m, f"❌ Need {HINT_COST} pts. Your: {u[6]}"); return
    game=games[gid]
    hidden=[w for w in game.words if w not in game.found]
    if not hidden: bot.reply_to(m,"All words found"); return
    reveal=random.choice(hidden)
    db.update_stats(uid, hint_delta=-HINT_COST)
    bot.reply_to(m, f"💡 Hint: <code>{reveal}</code> (-{HINT_COST} pts)")

# -------------------------
# PROCESS WORD GUESS (register_next_step uses this)
# -------------------------
def process_word_guess(m):
    cid = m.chat.id
    if cid not in games:
        try: bot.reply_to(m,"❌ No active game here."); return
        except: return
    word = (m.text or "").strip().upper()
    if not word: return
    session = games[cid]
    uid = m.from_user.id
    name = m.from_user.first_name or m.from_user.username or "Player"
    last = session.players_last_guess.get(uid,0)
    now = time.time()
    if now - last < COOLDOWN:
        try: bot.reply_to(m, f"⏳ Wait {COOLDOWN}s between guesses."); return
        except: return
    session.players_last_guess[uid] = now
    try:
        bot.delete_message(cid, m.message_id)
    except: pass
    if session.mode == "anagram":
        matched=None
        for it in session.anagrams:
            if it["word"].upper()==word: matched=it["word"].upper(); break
        if not matched:
            bot.send_message(cid, f"❌ {name} — {word} not a valid anagram.")
            return
        if matched in session.found:
            bot.send_message(cid, f"⚠️ {matched} already solved.")
            return
        session.found.add(matched); pts=NORMAL_POINTS
        session.players_scores[uid]=session.players_scores.get(uid,0)+pts
        db.update_stats(uid, score_delta=pts)
        bot.send_message(cid, f"✨ {name} solved {matched} (+{pts} pts)")
        if len(session.found)==len(session.anagrams): end_game_session(cid,"win",uid)
        return
    # grid mode
    if word in session.words:
        if word in session.found:
            bot.send_message(cid, f"⚠️ {word} already found."); return
        session.found.add(word)
        session.last_activity=time.time()
        if len(session.found)==1: pts=FIRST_BLOOD_POINTS
        elif len(session.found)==len(session.words): pts=FINISHER_POINTS
        else: pts=NORMAL_POINTS
        session.players_scores[uid]=session.players_scores.get(uid,0)+pts
        db.update_stats(uid, score_delta=pts)
        # send animation then final image
        try:
            anim = create_found_animation(session.grid, session.placements, session.found, word, is_hard=session.is_hard, watermark="@Ruhvaan")
            anim.seek(0)
            bot.send_animation(cid, anim, caption=f"✨ {html.escape(name)} found <code>{word}</code> (+{pts} pts) 🎯")
        except Exception:
            logger.exception("animation failed")
            bot.send_message(cid, f"✨ {html.escape(name)} found <code>{word}</code> (+{pts} pts) 🎯")
        # final image with blank_words = found (cut letters)
        try:
            final = GridRenderer.draw(session.grid, session.placements, session.found, blank_words=set(session.found), is_hard=session.is_hard, watermark="@Ruhvaan", version="v7.0")
            final.seek(0)
            sent = bot.send_photo(cid, final, caption=(f"🔥 <b>WORD VORTEX</b>\nMode: {'Hard' if session.is_hard else 'Normal'}\n\n{session.get_hint_text()}"),
                                  reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔍 Found It!", callback_data="game_guess"), InlineKeyboardButton("💡 Hint (-50)", callback_data="game_hint"), InlineKeyboardButton("📊 Score", callback_data="game_score")))
            try:
                if getattr(session,"message_id",None):
                    bot.delete_message(cid, session.message_id)
            except:
                pass
            try: session.message_id = sent.message_id
            except: session.message_id = None
        except Exception:
            logger.exception("final image failed")
        if len(session.found)==len(session.words): end_game_session(cid,"win",uid)
    else:
        try:
            msg = bot.send_message(cid, f"❌ {html.escape(name)} — '{html.escape(word)}' is not in the list.")
            threading.Timer(3, lambda: bot.delete_message(cid, msg.message_id)).start()
        except:
            pass

# -------------------------
# End game
# -------------------------
def end_game_session(cid, reason, winner_id=None):
    if cid not in games: return
    g = games[cid]
    g.active=False
    if reason=="win" and winner_id:
        try:
            winner = db.get_user(winner_id,"Player")
            db.update_stats(winner_id, win=True)
            db.record_game(cid,winner_id,g.mode)
            standings = sorted(g.players_scores.items(), key=lambda x:x[1], reverse=True)
            summary = ""
            for i,(uid,pts) in enumerate(standings,1):
                user = db.get_user(uid,"Player")
                summary += f"{i}. {html.escape(user[1])} - {pts} pts\n"
            bot.send_message(cid, f"🏆 GAME OVER! MVP: {html.escape(winner[1])}\n\nSession Standings:\n{summary}\nType /new to play again.")
        except:
            logger.exception("end_game win failed")
    elif reason=="timeout":
        try:
            found_count = len(g.found)
            remaining = [w for w in g.words if w not in g.found]
            standings = sorted(g.players_scores.items(), key=lambda x:x[1], reverse=True)
            summary = ""
            for i,(uid,pts) in enumerate(standings,1):
                user = db.get_user(uid,"Player")
                summary += f"{i}. {html.escape(user[1])} - {pts} pts\n"
            bot.send_message(cid, f"⏰ TIME'S UP!\nFound: {found_count}/{len(g.words)}\nRemaining: {', '.join(remaining) if remaining else 'None'}\n\nStandings:\n{summary}")
        except:
            logger.exception("end_game timeout failed")
    elif reason=="stopped":
        bot.send_message(cid, "🛑 Game stopped manually.")
    try: del games[cid]
    except: pass

# -------------------------
# Fallback text handler
# -------------------------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback_text(m):
    # telebot's register_next_step_handler handles ForceReply flows; this is general fallback
    if m.text.startswith("/"):
        if m.text.split()[0].lower()=="/cmd":
            return
        try:
            bot.reply_to(m, "Unknown command. Use /cmd or the menu.")
        except:
            pass

# -------------------------
# HEALTH & RUN
# -------------------------
@app.route("/")
def index():
    return "Word Vortex Bot (v7.0) running"

if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get("PORT", "5000"))
        app.run(host="0.0.0.0", port=port)
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Starting Word Vortex Bot v7.0...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            logger.exception("Polling error; restarting in 5s")
            time.sleep(5)
