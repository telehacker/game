#!/usr/bin/env python3
"""
WORD VORTEX ULTIMATE v10.5 - FIXED & ENHANCED (syntax + runtime robustness fixes)
Enhanced: fixes for shoplist, ai_add, upload_patch, review visibility and other enhancements:
- Safer AI response parsing, better error messages
- Robust patch upload acknowledgement
- shoplist text building fixed (no stray sequences), chunked output
- Added /cmd message command listing all commands
- Improved ImageRenderer visuals
- Added owner/admin env list and hardened owner-only commands
- /runlang to run python/nodejs with lightweight sandboxing (owner-only)
- /npm_install and enhancements to pip_install for frontend packages
- Extra logging and DB error logs for failures
"""

import os
import sys
import time
import html
import io
import random
import logging
import sqlite3
import json
import threading
import traceback
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Any
import subprocess
import tempfile

# optional resource limits for sandboxed runs (POSIX)
try:
    import resource
except Exception:
    resource = None

import requests
from PIL import Image, ImageDraw, ImageFont
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ---------------------------
# CONFIG
# ---------------------------
TOKEN = os.environ.get("TELEGRAM_TOKEN", "7606978190:AAFcxLx5UxboOVdY5kJP9d2D-E9-9G7NK3U")
if not TOKEN:
    print("❌ TELEGRAM_TOKEN not set")
    sys.exit(1)

OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) if os.environ.get("OWNER_ID") else 8271254197

# Additional admin ids (comma separated) to allow multiple admins via env
ADMIN_IDS = []
_admin_env = os.environ.get("ADMIN_IDS", "")
if _admin_env:
    try:
        ADMIN_IDS = [int(x.strip()) for x in _admin_env.split(",") if x.strip()]
    except Exception:
        ADMIN_IDS = []

# Notification target: prefer explicit NOTIFICATION_GROUP env var (group/channel id or @username).
# If NOTIFICATION_GROUP is not set we fallback to OWNER_ID. This avoids silently using owner id as group.
NOTIFICATION_GROUP = os.environ.get("NOTIFICATION_GROUP")  # can be "-100..." or "@channelname"
if NOTIFICATION_GROUP:
    # if it's digits, convert to int for send_message
    try:
        NOTIFICATION_GROUP = int(NOTIFICATION_GROUP)
    except Exception:
        pass
else:
    NOTIFICATION_GROUP = None

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = True
SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg"

# GitHub / OpenAI config (optional)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT")
REPO_OWNER = os.environ.get("REPO_OWNER") or os.environ.get("GITHUB_REPO_OWNER") or "telehacker"
REPO_NAME = os.environ.get("REPO_NAME") or os.environ.get("GITHUB_REPO_NAME") or "game"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# GAME CONSTANTS & RULES
# ---------------------------
FIRST_BLOOD = 15
NORMAL_PTS = 3
FINISHER = 10
HINT_COST = 50
COOLDOWN = 1  # seconds
DAILY_REWARD = 100
STREAK_BONUS = 20
REFERRAL_BONUS = 200
COMBO_BONUS = 5
SPEED_BONUS = 5

# Timer settings
GAME_DURATION_SECONDS = 10 * 60  # 10 minutes = 600 seconds

# Redeem rules
REDEEM_MIN_NON_PREMIUM = 1000
REDEEM_MIN_PREMIUM = 500
REDEEM_CONVERSION_DIV = 100  # points // 100 => INR

# Referral activity thresholds
REFERRAL_MIN_GAMES = 2
REFERRAL_MIN_WORDS = 3

# Bad words set for review moderation
BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}

# ACHIEVEMENTS
ACHIEVEMENTS = {
    "streak_master": {"icon": "🏆", "name": "Streak Master", "desc": "Claim daily 7 days in a row", "reward": 500},
    "first_blood": {"icon": "⚡", "name": "First Blood", "desc": "Get first find in a game", "reward": 50},
    "word_hunter": {"icon": "🔎", "name": "Word Hunter", "desc": "Find 100 words total", "reward": 300},
    "collector": {"icon": "📚", "name": "Collector", "desc": "Collect 1000 points", "reward": 500},
    "combo_killer": {"icon": "🔥", "name": "Combo King", "desc": "Get 5 combos in a single game", "reward": 250},
    "speedster": {"icon": "⚡", "name": "Speedster", "desc": "Find a word within 3 seconds after image", "reward": 150},
    "perfectionist": {"icon": "🎯", "name": "Perfectionist", "desc": "Find all words in a game", "reward": 400},
    "social_butterfly": {"icon": "👥", "name": "Influencer", "desc": "Refer 10 verified users", "reward": 600},
    "shopper": {"icon": "🛒", "name": "Shopper", "desc": "Make 1 paid purchase", "reward": 50},
    "tester": {"icon": "🔧", "name": "Beta Tester", "desc": "Use /selftest and report results", "reward": 20},
}

# Creative messages
CORRECT_EMOJIS = ['🎯', '💥', '⚡', '🔥', '✨', '💫', '🌟', '⭐', '🎊', '🎉']
WRONG_EMOJIS = ['😅', '🤔', '😬', '💭', '🎭', '🤷', '😕']

CORRECT_MESSAGES = [
    "BOOM! 💥 {name} crushed it!",
    "ON FIRE! 🔥 {name} is unstoppable!",
    "LEGENDARY! ⚡ {name} found {word}!",
]

WRONG_MESSAGES = [
    "Oops! 😅 {word} nahi hai list mein!",
    "Nope! 🤔 {word} galat hai bro!",
]

ALREADY_FOUND_MESSAGES = [
    "Déjà vu! 👀 {word} already found!",
]

FIRST_BLOOD_MESSAGES = [
    "⚡ FIRST BLOOD! {name} draws first!",
]

COMBO_MESSAGES = [
    "DOUBLE KILL! 🔥",
]

# Shop items
SHOP_ITEMS = {
    "xp_booster": {"name": "🚀 XP Booster 2x (30 days)", "price": 199, "type": "xp_boost", "value": 30},
    "premium_1d": {"name": "👑 Premium 1 Day", "price": 49, "type": "premium", "value": 1},
    "premium_7d": {"name": "👑 Premium 7 Days", "price": 249, "type": "premium", "value": 7},
    "premium_30d": {"name": "👑 Premium 30 Days", "price": 999, "type": "premium", "value": 30},
    "hints_10": {"name": "💡 10 Hints Pack", "price": 30, "type": "hints", "value": 10},
}

# Additional runtime containers
user_states: Dict[int, Dict[str, Any]] = {}
feature_pack: Dict[str, Any] = {}  # loaded from owner-uploaded JSON to add themes/messages/shop items

# ---------------------------
# WORD SOURCE
# ---------------------------
ALL_WORDS: List[str] = []

def load_words():
    global ALL_WORDS
    try:
        r = requests.get("https://www.mit.edu/~ecprice/wordlist.10000", timeout=10)
        words = [w.strip().upper() for w in r.text.splitlines() if w.strip()]
        words = [w for w in words if w.isalpha() and 4 <= len(w) <= 10 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info(f"✅ Loaded {len(ALL_WORDS)} words")
            return
    except Exception as e:
        logger.debug("Wordlist fetch failed: %s", e)
    # fallback
    ALL_WORDS = ["PYTHON","JAVA","ROBOT","SPACE","GALAXY","QUANTUM","ENERGY","MATRIX","VECTOR","DIGITAL","ALGORITHM","NETWORK","SERVER","CLIENT","SOCKET"]
    logger.info("⚠️ Using fallback wordlist")

load_words()

# ---------------------------
# DATABASE
# ---------------------------
class Database:
    def __init__(self):
        # Use DB_PATH if provided to allow custom DB location
        self.db = os.environ.get("DB_PATH", "word_vortex_v105_final.db")
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        conn = self._conn()
        c = conn.cursor()

        # users table (preserve existing schema)
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, name TEXT, username TEXT,
            join_date TEXT, games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0, total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100, gems INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0, last_daily TEXT,
            referrer_id INTEGER, is_premium INTEGER DEFAULT 0, premium_expiry TEXT,
            is_banned INTEGER DEFAULT 0, achievements TEXT DEFAULT '[]',
            words_found INTEGER DEFAULT 0, verified INTEGER DEFAULT 0
        )""")

        # admins
        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")

        # shop purchases
        c.execute("""CREATE TABLE IF NOT EXISTS shop_purchases (
            purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, item_type TEXT, price REAL,
            status TEXT DEFAULT 'pending', date TEXT
        )""")

        # reviews
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, text TEXT,
            rating INTEGER, created_at TEXT, approved INTEGER DEFAULT 0
        )""")

        # redeem requests
        c.execute("""CREATE TABLE IF NOT EXISTS redeem_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, points INTEGER,
            amount_inr INTEGER, upi_id TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, paid_at TEXT
        )""")

        # referrals
        c.execute("""CREATE TABLE IF NOT EXISTS referrals (
            referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER, referred_id INTEGER,
            created_at TEXT, UNIQUE(referrer_id, referred_id)
        )""")

        # referral_awards to mark if reward given (additive schema)
        c.execute("""CREATE TABLE IF NOT EXISTS referral_awards (
            award_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER, referred_id INTEGER, awarded INTEGER DEFAULT 0,
            awarded_at TEXT
        )""")

        # NEW: games history
        c.execute("""CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, mode TEXT, size INTEGER,
            start_time TEXT, end_time TEXT, winner_id INTEGER, winner_score INTEGER
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS game_finds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER, word TEXT, finder_id INTEGER, found_at TEXT
        )""")

        # known chats
        c.execute("""CREATE TABLE IF NOT EXISTS known_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            first_seen TEXT
        )""")

        # feature packs storage (JSON)
        c.execute("""CREATE TABLE IF NOT EXISTS feature_packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, contents TEXT, uploaded_at TEXT
        )""")

        # Additional tables required by the Technical paragraph
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS errors (
            error_id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT,
            message TEXT,
            tb TEXT,
            context TEXT,
            created_at TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS patches (
            patch_id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            contents TEXT,
            uploaded_at TEXT,
            created_issue_url TEXT
        )""")

        # Ensure games table has full_state column (additive)
        try:
            c.execute("ALTER TABLE games ADD COLUMN full_state TEXT")
        except Exception:
            # Column probably exists already; ignore
            pass

        conn.commit()
        conn.close()

    # basic user retrieval and creation
    def get_user(self, user_id: int, name: str = "Player", username: str = ""):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("""INSERT INTO users (user_id, name, username, join_date)
                        VALUES (?, ?, ?, ?)""",
                     (user_id, name, username, datetime.now().strftime("%Y-%m-%d")))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
        conn.close()
        return row

    def is_premium(self, user_id: int) -> bool:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT is_premium, premium_expiry FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        if not row[1]:
            return False
        try:
            expiry = datetime.fromisoformat(row[1])
            return datetime.now() < expiry
        except Exception:
            return False

    def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        conn = self._conn()
        c = conn.cursor()
        for key, val in kwargs.items():
            c.execute(f"UPDATE users SET {key} = ? WHERE user_id=?", (val, user_id))
        conn.commit()
        conn.close()

    def add_score(self, user_id: int, points: int):
        """Legacy: increase both total_score and hint_balance (keeps older behavior)."""
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", 
                 (points, points, user_id))
        conn.commit()
        conn.close()

    def add_score_only(self, user_id: int, points: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (points, user_id))
        conn.commit()
        conn.close()

    def add_hint_balance(self, user_id: int, amount: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()
        conn.close()

    def add_xp(self, user_id: int, xp: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT xp, level FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        curr_xp, level = row

        multiplier = 2 if self.is_premium(user_id) else 1
        new_xp = curr_xp + (xp * multiplier)
        new_level = level

        if new_xp >= level * 1000:
            new_level = level + 1
            try:
                bot.send_message(user_id, f"🎉 <b>LEVEL UP!</b> You're now level {new_level}!")
            except Exception:
                pass

        c.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (new_xp, new_level, user_id))
        conn.commit()
        conn.close()

    def add_achievement(self, user_id: int, ach_id: str) -> bool:
        user = self.get_user(user_id)
        achievements_json = user['achievements'] if user and 'achievements' in user.keys() else "[]"
        achievements = json.loads(achievements_json)
        if ach_id in achievements:
            return False
        achievements.append(ach_id)
        self.update_user(user_id, achievements=json.dumps(achievements))
        return True

    def buy_premium(self, user_id: int, days: int):
        conn = self._conn()
        c = conn.cursor()
        expiry = datetime.now() + timedelta(days=days)
        c.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE user_id=?", 
                 (expiry.isoformat(), user_id))
        conn.commit()
        conn.close()

    def add_purchase(self, user_id: int, item_type: str, price: float):
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO shop_purchases (user_id, item_type, price, date) 
                    VALUES (?, ?, ?, ?)""",
                 (user_id, item_type, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        pid = c.lastrowid
        conn.close()
        return pid

    def is_admin(self, user_id: int) -> bool:
        try:
            if OWNER_ID and user_id == OWNER_ID:
                return True
        except Exception:
            pass
        if user_id in ADMIN_IDS:
            return True
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM admins WHERE admin_id=?", (user_id,))
        r = c.fetchone()
        conn.close()
        return bool(r)

    def add_admin(self, admin_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
        conn.commit()
        conn.close()

    def get_top_players(self, limit=10):
        """
        Return rows with user_id, name, total_score, level, is_premium
        so callers can reliably show names (or lookup when missing).
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT user_id, name, total_score, level, is_premium FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def add_review(self, user_id: int, username: str, text: str, rating: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO reviews (user_id, username, text, rating, created_at)
                    VALUES (?, ?, ?, ?, ?)""",
                 (user_id, username, text, rating, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_reviews(self, approved_only=True):
        conn = self._conn()
        c = conn.cursor()
        if approved_only:
            c.execute("SELECT * FROM reviews WHERE approved=1 ORDER BY created_at DESC LIMIT 10")
        else:
            c.execute("SELECT * FROM reviews ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        return rows

    def get_review(self, review_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT review_id, user_id, username, text, rating, created_at, approved FROM reviews WHERE review_id=?", (review_id,))
        r = c.fetchone()
        conn.close()
        return r

    def approve_review(self, review_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE reviews SET approved=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    def delete_review(self, review_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("DELETE FROM reviews WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    def add_redeem(self, user_id: int, username: str, points: int, upi: str):
        conn = self._conn()
        c = conn.cursor()
        amount = points // REDEEM_CONVERSION_DIV
        c.execute("""INSERT INTO redeem_requests 
                    (user_id, username, points, amount_inr, upi_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                 (user_id, username, points, amount, upi, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_redeem_requests(self, status='pending'):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM redeem_requests WHERE status=? ORDER BY created_at DESC", (status,))
        rows = c.fetchall()
        conn.close()
        return rows

    def mark_redeem_paid(self, request_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE redeem_requests SET status='paid', paid_at=? WHERE request_id=?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), request_id))
        conn.commit()
        conn.close()

    def mark_shop_paid(self, purchase_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE shop_purchases SET status='paid' WHERE purchase_id=?", (purchase_id,))
        conn.commit()
        c.execute("SELECT user_id, item_type, price FROM shop_purchases WHERE purchase_id=?", (purchase_id,))
        r = c.fetchone()
        conn.close()
        return r

    def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        conn = self._conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO referrals (referrer_id, referred_id, created_at)
                        VALUES (?, ?, ?)""",
                     (referrer_id, referred_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            # create award tracking row (not awarded yet)
            c.execute("""INSERT OR IGNORE INTO referral_awards (referrer_id, referred_id, awarded) VALUES (?, ?, 0)""",
                      (referrer_id, referred_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def award_referral_if_eligible(self, referred_id: int):
        """
        Check if referred user has met activity thresholds and if referral award pending,
        then award REFERRAL_BONUS to referrer and mark awarded.
        Called after games_played or words_found increments.
        """
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT referrer_id FROM referrals WHERE referred_id=?", (referred_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False
        referrer_id = row[0]

        # check if already awarded
        c.execute("SELECT awarded FROM referral_awards WHERE referrer_id=? AND referred_id=?", (referrer_id, referred_id))
        award_row = c.fetchone()
        if award_row and award_row[0]:
            conn.close()
            return False  # already awarded

        # check activity thresholds from users table
        c.execute("SELECT games_played, words_found, verified FROM users WHERE user_id=?", (referred_id,))
        urow = c.fetchone()
        if not urow:
            conn.close()
            return False

        games_played = urow['games_played'] if 'games_played' in urow.keys() else (urow[4] if len(urow) > 4 else 0)
        words_found = urow['words_found'] if 'words_found' in urow.keys() else (urow[18] if len(urow) > 18 else 0)
        verified = urow['verified'] if 'verified' in urow.keys() else (urow[19] if len(urow) > 19 else 0)

        # require verification + (games OR words threshold)
        if not verified:
            conn.close()
            return False

        if games_played >= REFERRAL_MIN_GAMES or words_found >= REFERRAL_MIN_WORDS:
            # award referrer
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?", (REFERRAL_BONUS, referrer_id))
            c.execute("UPDATE referral_awards SET awarded=1, awarded_at=? WHERE referrer_id=? AND referred_id=?",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), referrer_id, referred_id))
            conn.commit()
            conn.close()
            try:
                bot.send_message(referrer_id, f"🎉 You earned +{REFERRAL_BONUS} pts for referring a verified active user!")
            except Exception:
                pass
            return True

        conn.close()
        return False

    def claim_daily(self, user_id: int) -> Tuple[bool, int]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT last_daily, streak FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, 0
        last_daily = row['last_daily'] if 'last_daily' in row.keys() else None
        streak = row['streak'] if 'streak' in row.keys() else 0

        today = datetime.now().strftime("%Y-%m-%d")
        if last_daily == today:
            conn.close()
            return False, 0

        if last_daily:
            try:
                last_date = datetime.strptime(last_daily, "%Y-%m-%d")
                days_diff = (datetime.now() - last_date).days
            except Exception:
                days_diff = 2
            if days_diff == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        base_reward = DAILY_REWARD + (streak * STREAK_BONUS)
        reward = base_reward * 2 if self.is_premium(user_id) else base_reward

        c.execute("""UPDATE users SET hint_balance = hint_balance + ?,
                    last_daily = ?, streak = ? WHERE user_id=?""",
                 (reward, today, streak, user_id))
        conn.commit()
        conn.close()
        return True, reward

    def get_all_users(self):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        rows = [r[0] for r in c.fetchall()]
        conn.close()
        return rows

    # NEW helper to get known chats (for broadcast to groups)
    def get_known_chats(self):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT chat_id, title FROM known_chats")
        rows = c.fetchall()
        conn.close()
        return rows

    # Game logging
    def log_game_start(self, chat_id: int, mode: str, size: int, full_state: Optional[str] = None) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT INTO games (chat_id, mode, size, start_time, full_state) VALUES (?, ?, ?, ?, ?)",
                  (chat_id, mode, size, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), full_state))
        conn.commit()
        game_id = c.lastrowid
        conn.close()
        return game_id

    def log_word_found(self, game_id: int, word: str, finder_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT INTO game_finds (game_id, word, finder_id, found_at) VALUES (?, ?, ?, ?)",
                  (game_id, word, finder_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def log_game_end(self, game_id: int, winner_id: int, winner_score: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE games SET end_time=?, winner_id=?, winner_score=? WHERE game_id=?",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), winner_id, winner_score, game_id))
        conn.commit()
        conn.close()

    def get_game_history(self, user_id: Optional[int] = None, limit=20):
        conn = self._conn()
        c = conn.cursor()
        if user_id:
            c.execute("""SELECT g.game_id, g.chat_id, g.mode, g.size, g.start_time, g.end_time, g.winner_id, g.winner_score
                         FROM games g
                         JOIN game_finds f ON g.game_id = f.game_id
                         WHERE f.finder_id=? GROUP BY g.game_id ORDER BY g.start_time DESC LIMIT ?""", (user_id, limit))
        else:
            c.execute("SELECT game_id, chat_id, mode, size, start_time, end_time, winner_id, winner_score FROM games ORDER BY start_time DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_game_finds(self, game_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT word, finder_id, found_at FROM game_finds WHERE game_id=? ORDER BY found_at", (game_id,))
        rows = c.fetchall()
        conn.close()
        return rows

    def add_known_chat(self, chat_id: int, title: str = ""):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO known_chats (chat_id, title, first_seen) VALUES (?, ?, ?)",
                  (chat_id, title, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def save_feature_pack(self, name: str, contents: str):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT INTO feature_packs (name, contents, uploaded_at) VALUES (?, ?, ?)",
                  (name, contents, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def save_patch(self, filename: str, contents: str):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT INTO patches (filename, contents, uploaded_at) VALUES (?, ?, ?)",
                  (filename, contents, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        pid = c.lastrowid
        conn.close()
        return pid

    def log_error(self, error_type: str, message: str, tb: str = "", context: str = ""):
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO errors (error_type, message, tb, context, created_at)
                     VALUES (?, ?, ?, ?, ?)""",
                  (error_type, message, tb, context, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        eid = c.lastrowid
        conn.close()
        return eid

    # settings helpers
    def set_setting(self, key: str, value: str):
        conn = self._conn()
        c = conn.cursor()
        # Use upsert supported syntax
        c.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                  (key, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_setting(self, key: str) -> Optional[str]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = c.fetchone()
        conn.close()
        return r['value'] if r else None

db = Database()

# ---------------------------
# Helper: display name resolution (DB preferred, else Telegram lookup)
# ---------------------------
def get_display_name(user_id: int) -> str:
    """
    Return a human-friendly display name for a Telegram user id.
    Preference order:
      1) DB stored name if meaningful (not "Player" and not empty)
      2) Telegram API (first_name + last_name) or @username if available — also update DB for future
      3) fallback to numeric id as string
    """
    try:
        row = db.get_user(user_id)
        if row:
            name = row['name'] if 'name' in row.keys() else None
            if name and name.strip() and name.strip().lower() != "player":
                return name
        # Try Telegram API
        try:
            tg = bot.get_chat(user_id)
            # prefer full name
            name_parts = []
            if getattr(tg, "first_name", None):
                name_parts.append(tg.first_name)
            if getattr(tg, "last_name", None):
                name_parts.append(tg.last_name)
            if name_parts:
                real_name = " ".join(name_parts).strip()
                try:
                    db.update_user(user_id, name=real_name)
                except Exception:
                    pass
                return real_name
            if getattr(tg, "username", None):
                uname = "@" + tg.username
                try:
                    db.update_user(user_id, name=uname)
                except Exception:
                    pass
                return uname
        except Exception:
            # Telegram lookup may fail if bot hasn't seen the user
            pass
    except Exception:
        pass
    return str(user_id)

# Global uncaught exception handler: log to DB and logger
def handle_uncaught(exc_type, exc, exc_tb):
    tb = "".join(traceback.format_exception(exc_type, exc, exc_tb))
    try:
        db.log_error(str(exc_type), str(exc), tb, context="uncaught")
    except Exception:
        pass
    logger.error("Uncaught exception: %s", tb)

sys.excepthook = handle_uncaught

# Helper: owner or admin (improved)
def is_owner_or_admin(user_id: int) -> bool:
    try:
        if OWNER_ID and user_id == OWNER_ID:
            return True
    except Exception:
        pass
    if user_id in ADMIN_IDS:
        return True
    return db.is_admin(user_id)

# ---------------------------
# IMAGE RENDERER (improved visuals)
# ---------------------------
class ImageRenderer:
    @staticmethod
    def _rounded_rectangle(draw, xy, radius, fill):
        x0, y0, x1, y1 = xy
        try:
            draw.rounded_rectangle(xy, radius=radius, fill=fill)
        except Exception:
            # Fallback if older Pillow doesn't have rounded_rectangle
            draw.rectangle(xy, fill=fill)

    @staticmethod
    def draw_grid(grid: List[List[str]], placements: Dict, found: Dict[str,int],
                  mode="NORMAL", words_left=0, theme: str = "default", countdown_seconds: Optional[int] = None):
        """
        Draws the grid image with enhanced visuals.
        If countdown_seconds provided, displays a static countdown at time of image generation.
        theme can be used to select visual styles (e.g., 'gold', 'default').
        """
        cell = 50
        header = 110
        footer = 70
        pad = 20
        rows = len(grid)
        cols = len(grid[0]) if rows else 0

        w = cols * cell + pad * 2
        h = header + footer + rows * cell + pad * 2

        # Header color different for 'gold' theme
        any_premium_found = False
        try:
            for word, finder in (found or {}).items():
                if finder and db.is_premium(finder):
                    any_premium_found = True
                    break
        except Exception:
            any_premium_found = False

        if theme == "gold" or any_premium_found:
            bg = "#0b0a05"
            header_fill = "#3b2b00"
            accent = "#ffd700"
        else:
            bg = "#071025"
            header_fill = "#112233"
            accent = "#4dd0e1"

        img = Image.new("RGB", (w, h), bg)
        draw = ImageDraw.Draw(img)

        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            if not os.path.exists(font_path):
                raise Exception("Font not found")
            title_font = ImageFont.truetype(font_path, 28)
            letter_font = ImageFont.truetype(font_path, 28)
            small_font = ImageFont.truetype(font_path, 16)
        except Exception:
            title_font = ImageFont.load_default()
            letter_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        # Header with subtle gradient (approx)
        ImageRenderer._rounded_rectangle(draw, (0, 0, w, header), radius=8, fill=header_fill)
        title = "WORD GRID (FIND WORDS)"
        try:
            bbox = draw.textbbox((0, 0), title, font=title_font)
            draw.text(((w - (bbox[2]-bbox[0]))//2, 22), title, fill=accent, font=title_font)
        except Exception:
            draw.text((w//2 - 100, 22), title, fill=accent, font=title_font)

        mode_text = f"⚡ {mode.upper()}"
        draw.text((pad, header-36), mode_text, fill="#ffa500" if not any_premium_found else "#ffd700", font=small_font)
        draw.text((w-240, header-36), f"Left: {words_left}", fill="#4CAF50", font=small_font)

        if countdown_seconds is not None:
            try:
                draw.text((w-120, 10), f"⏱ {countdown_seconds}s", fill="#ffdd57", font=small_font)
            except Exception:
                pass

        grid_y = header + pad

        # Grid letters with subtle cell shading
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell
                y = grid_y + r * cell
                shadow = 2
                # shadow
                draw.rectangle([x+shadow, y+shadow, x+cell+shadow, y+cell+shadow], fill="#000000")
                draw.rectangle([x, y, x+cell, y+cell], fill="#102b44", outline="#254a6b", width=1)

                ch = grid[r][c]
                try:
                    bbox = draw.textbbox((0, 0), ch, font=letter_font)
                    tx = x + (cell - (bbox[2]-bbox[0]))//2
                    ty = y + (cell - (bbox[3]-bbox[1]))//2
                except Exception:
                    tx = x + cell//2 - 8
                    ty = y + cell//2 - 10
                draw.text((tx, ty), ch, fill="#ffffff", font=letter_font)

        # Thin lines for found words
        if placements and found:
            for word, coords in placements.items():
                try:
                    if word in found and coords:
                        finder = found.get(word)
                        is_prem = db.is_premium(finder) if finder else False

                        a, b = coords[0], coords[-1]
                        x1 = pad + a[1]*cell + cell//2
                        y1 = grid_y + a[0]*cell + cell//2
                        x2 = pad + b[1]*cell + cell//2
                        y2 = grid_y + b[0]*cell + cell//2

                        line_col_outer = "#ffd700" if (is_prem or theme == "gold") else "#88ff88"
                        line_col_inner = "#fff2a6" if (is_prem or theme == "gold") else "#b2ffb2"

                        draw.line([(x1,y1),(x2,y2)], fill=line_col_outer, width=4)
                        draw.line([(x1,y1),(x2,y2)], fill=line_col_inner, width=1)

                        for px, py in [(x1,y1),(x2,y2)]:
                            draw.ellipse([px-6, py-6, px+6, py+6], fill=line_col_outer)
                except Exception:
                    continue

        # Footer
        draw.rectangle([0, h-footer, w, h], fill="#081822")
        footer_text = "Made by @Ruhvaan • Word Vortex v10.5"
        if theme == "gold":
            footer_text = "VIP • " + footer_text
        try:
            bboxf = draw.textbbox((0,0), footer_text, font=small_font)
            draw.text((w - bboxf[2] - 20, h-footer+25), footer_text, fill="#9aa9b0", font=small_font)
        except Exception:
            draw.text((w//2 - 120, h-footer+25), footer_text, fill="#7f8c8d", font=small_font)

        bio = io.BytesIO()
        img.save(bio, "PNG", quality=95)
        bio.seek(0)
        bio.name = "grid.png"
        return bio

# ---------------------------
# GAME SESSION & MANAGEMENT
# ---------------------------
games: Dict[int, "GameSession"] = {}

class GameSession:
    def __init__(self, chat_id: int, mode="normal", is_hard=False, custom_words=None, theme: str = "default"):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        # enforce desired word counts: 8x8 -> 6 words, 10x10 -> 8 words
        self.word_count = 8 if self.size == 10 else 6
        self.start_time = time.time()
        self.expiry_time = self.start_time + GAME_DURATION_SECONDS
        self.image_sent_time: Optional[float] = None
        self.grid: List[List[str]] = []
        self.placements: Dict[str, List[Tuple[int,int]]] = {}
        self.found: Dict[str, int] = {}
        self.players: Dict[int, int] = {}
        self.last_guess: Dict[int, float] = {}
        self.last_find_time: Dict[int, float] = {}
        self.combo_count: Dict[int, int] = {}
        self.message_id: Optional[int] = None
        self.game_id: Optional[int] = None
        self.theme = theme  # theme name: 'default' or 'gold' etc.

        # Build pool
        if custom_words:
            word_pool = list(dict.fromkeys([w.upper() for w in custom_words if isinstance(w, str)]))
            extra_needed = max(0, self.word_count * 2 - len(word_pool))
            if extra_needed > 0 and ALL_WORDS:
                sampled = random.sample(ALL_WORDS, min(extra_needed, len(ALL_WORDS)))
                word_pool.extend(sampled)
        else:
            word_pool = ALL_WORDS

        self._generate(word_pool)

    def _generate(self, pool):
        valid = [w for w in pool if isinstance(w, str) and 4 <= len(w) <= 8]
        if len(valid) < self.word_count:
            valid = (valid * ((self.word_count // max(1, len(valid))) + 2))[:max(self.word_count, len(valid))]
        self.words = random.sample(valid, min(self.word_count, len(valid)))

        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]

        for word in sorted(self.words, key=len, reverse=True):
            placed = False
            for _ in range(1000):
                r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)
                if self._can_place(r, c, dr, dc, word):
                    coords = []
                    for i, ch in enumerate(word):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr, cc))
                    self.placements[word] = coords
                    placed = True
                    break
            if not placed:
                # fallback: scan board to place
                for r0 in range(self.size):
                    for c0 in range(self.size):
                        for dr, dc in dirs:
                            if self._can_place(r0, c0, dr, dc, word):
                                coords = []
                                for i, ch in enumerate(word):
                                    rr, cc = r0 + i*dr, c0 + i*dc
                                    self.grid[rr][cc] = ch
                                    coords.append((rr, cc))
                                self.placements[word] = coords
                                placed = True
                                break
                        if placed:
                            break
                    if placed:
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

    def get_word_list(self):
        lines = []
        for w in self.words:
            if w in self.found:
                lines.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + "•"*(len(w)-2) + w[-1] if len(w) > 2 else w[0] + "•"
                lines.append(f"❌ {masked} ({len(w)})")
        return "\n".join(lines)

    def remaining_time(self) -> int:
        return max(0, int(self.expiry_time - time.time()))

    def is_expired(self) -> bool:
        return time.time() >= self.expiry_time

# Helper to auto-end a game when expiry hits
def schedule_game_expiry(session: GameSession):
    def worker():
        try:
            now = time.time()
            to_sleep = max(0, session.expiry_time - now)
            time.sleep(to_sleep)
            # If session still exists and expired, end it
            if session.chat_id in games and games[session.chat_id] is session and session.is_expired():
                try:
                    end_game(session.chat_id, reason="time")
                except Exception:
                    tb = traceback.format_exc()
                    logger.exception("Error ending expired game")
                    try:
                        db.log_error("end_game_error", "Error ending expired game", tb, context=f"chat:{session.chat_id}")
                    except Exception:
                        pass
        except Exception:
            tb = traceback.format_exc()
            logger.exception("Expiry worker error")
            try:
                db.log_error("expiry_worker_error", "Expiry worker error", tb)
            except Exception:
                pass
    t = threading.Thread(target=worker, daemon=True)
    t.start()

def start_game(chat_id, starter_id, mode="normal", is_hard=False, custom_words=None, theme: str = "default"):
    if chat_id in games:
        try:
            bot.send_message(chat_id, "⚠️ Game already active! Use /stop to end it.")
        except Exception:
            pass
        return None

    session = GameSession(chat_id, mode, is_hard, custom_words, theme)
    games[chat_id] = session
    try:
        # Save a small JSON snapshot of initial game state into DB
        try:
            full_state = json.dumps({
                "size": session.size,
                "words": session.words,
                "placements": {w: coords for w, coords in session.placements.items()},
                "mode": session.mode,
                "theme": session.theme
            }, default=str)
        except Exception:
            full_state = None

        session.game_id = db.log_game_start(chat_id, mode, session.size, full_state=full_state)
    except Exception:
        tb = traceback.format_exc()
        logger.exception("Failed to log game start")
        try:
            db.log_error("log_game_start", "Failed to log game start", tb, context=f"chat:{chat_id}")
        except Exception:
            pass

    user = db.get_user(starter_id)
    try:
        # increment games_played safely
        prev_games = user['games_played'] if user and 'games_played' in user.keys() else (user[4] if user and len(user) > 4 else 0)
        db.update_user(starter_id, games_played=prev_games + 1)
        # Check referral eligibility in case this was first activity
        db.award_referral_if_eligible(starter_id)
    except Exception:
        logger.exception("Failed to update games_played")

    try:
        # Draw image with countdown seconds (static snapshot)
        img = ImageRenderer.draw_grid(
            session.grid, session.placements, session.found,
            mode, len(session.words), theme=session.theme, countdown_seconds=session.remaining_time()
        )

        caption = (f"🎮 <b>GAME STARTED!</b>\n"
                  f"Mode: <b>{mode.upper()}</b>\n"
                  f"Words: {len(session.words)}\n"
                  f"Time: <b>{session.remaining_time()}s</b>\n\n"
                  f"<b>Find these:</b>\n{session.get_word_list()}")

        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🔍 Found It!", callback_data="g_guess"))
        kb.row(
            InlineKeyboardButton("💡 Hint", callback_data="g_hint"),
            InlineKeyboardButton("📊 Score", callback_data="g_score")
        )
        kb.row(InlineKeyboardButton("🛑 Stop Game", callback_data="g_stop"))

        msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
        session.message_id = msg.message_id
        session.image_sent_time = time.time()

        # Remember known chat (so owner can broadcast to groups later)
        try:
            title = ""
            try:
                title = msg.chat.title or ""
            except Exception:
                pass
            db.add_known_chat(chat_id, title)
        except Exception:
            pass

        # schedule expiry worker
        schedule_game_expiry(session)

        return session
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception("Start game failed: %s", e)
        try:
            db.log_error("start_game_error", str(e), tb, context=f"chat:{chat_id}")
        except Exception:
            pass
        if chat_id in games:
            del games[chat_id]
        try:
            bot.send_message(chat_id, f"❌ Failed to start game: {str(e)}")
        except Exception:
            pass
        return None

def update_game(chat_id):
    if chat_id not in games:
        return
    session = games[chat_id]

    try:
        img = ImageRenderer.draw_grid(
            session.grid, session.placements, session.found,
            session.mode, len(session.words) - len(session.found), theme=session.theme, countdown_seconds=session.remaining_time()
        )

        caption = (f"🎮 <b>WORD GRID</b>\n"
                  f"Found: {len(session.found)}/{len(session.words)}\n"
                  f"Time left: <b>{session.remaining_time()}s</b>\n\n"
                  f"{session.get_word_list()}")

        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🔍 Found It!", callback_data="g_guess"))
        kb.row(
            InlineKeyboardButton("💡 Hint", callback_data="g_hint"),
            InlineKeyboardButton("📊 Score", callback_data="g_score")
        )
        kb.row(InlineKeyboardButton("🛑 Stop Game", callback_data="g_stop"))

        if session.message_id:
            try:
                bot.edit_message_media(
                    telebot.types.InputMediaPhoto(img, caption=caption),
                    chat_id=chat_id,
                    message_id=session.message_id,
                    reply_markup=kb
                )
            except Exception:
                msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
                session.message_id = msg.message_id
        else:
            msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
            session.message_id = msg.message_id

    except Exception:
        tb = traceback.format_exc()
        logger.exception("Update failed")
        try:
            db.log_error("update_game_error", "Update failed", tb, context=f"chat:{chat_id}")
        except Exception:
            pass

def end_game(chat_id, reason: str = "finished"):
    """
    End a game: announce winner (if any), log, delete the grid message and cleanup.
    reason: 'finished' or 'time' or 'stopped'
    """
    if chat_id not in games:
        return
    session = games[chat_id]
    try:
        # If some words found, compute winner
        if session.players:
            try:
                winner = max(session.players.items(), key=lambda x: x[1])
                winner_user = db.get_user(winner[0])
                prev_wins = winner_user['wins'] if winner_user and 'wins' in winner_user.keys() else (winner_user[5] if winner_user and len(winner_user) > 5 else 0)
                db.update_user(winner[0], wins=prev_wins + 1)
                # use display name helper
                winner_name = get_display_name(winner[0])
                bot.send_message(chat_id, f"🏆 <b>GAME COMPLETE!</b>\n\nWinner: {html.escape(winner_name)}\nScore: {winner[1]} pts\nReason: {reason}")
                if session.game_id:
                    try:
                        db.log_game_end(session.game_id, winner[0], winner[1])
                    except Exception:
                        logger.exception("Failed to log game end")
            except Exception:
                logger.exception("Error computing winner")
        else:
            bot.send_message(chat_id, f"🛑 Game ended. Reason: {reason}")

        # attempt to delete the game's image message to reduce clutter
        if session.message_id:
            try:
                bot.delete_message(chat_id, session.message_id)
            except Exception:
                pass

    except Exception:
        tb = traceback.format_exc()
        logger.exception("Error while ending game")
        try:
            db.log_error("end_game_error", "Error while ending game", tb, context=f"chat:{chat_id}")
        except Exception:
            pass
    finally:
        try:
            del games[chat_id]
        except Exception:
            pass

def handle_guess(msg):
    cid = msg.chat.id
    if cid not in games:
        return

    # ignore commands
    if msg.text and msg.text.strip().startswith('/'):
        return

    session = games[cid]
    uid = msg.from_user.id
    name = msg.from_user.first_name or "Player"
    word = (msg.text or "").strip().upper()

    if not word:
        return

    # PREMIUM: No cooldown!
    cooldown = 0 if db.is_premium(uid) else COOLDOWN
    last = session.last_guess.get(uid, 0)
    if time.time() - last < cooldown:
        try:
            bot.reply_to(msg, f"⏳ Wait {cooldown}s")
        except Exception:
            pass
        return
    session.last_guess[uid] = time.time()

    if word not in session.words:
        try:
            bot.reply_to(msg, f"❌ '{word}' not in list!")
        except Exception:
            pass
        session.combo_count[uid] = 0
        return

    if word in session.found:
        try:
            bot.reply_to(msg, f"✅ Already found!")
        except Exception:
            pass
        return

    # mark who found which word
    session.found[word] = uid
    if session.game_id:
        try:
            db.log_word_found(session.game_id, word, uid)
        except Exception:
            logger.exception("Failed to log word find")

    pts = 0
    bonuses = []

    if len(session.found) == 1:
        pts += FIRST_BLOOD
        bonuses.append("🥇FIRST BLOOD")
    elif len(session.found) == len(session.words):
        pts += FINISHER
        bonuses.append("🏆FINISHER")
    else:
        pts += NORMAL_PTS

    # Speed bonus based on time since image sent (if available) for fair speed measurement
    elapsed_since_image = time.time() - (session.image_sent_time or session.start_time)
    if elapsed_since_image < 10:
        pts += SPEED_BONUS
        bonuses.append("⚡SPEED +5")

    # consecutive combo bonus
    session.combo_count[uid] = session.combo_count.get(uid, 0) + 1
    if session.combo_count[uid] >= 2:
        pts += COMBO_BONUS
        bonuses.append(f"🔥COMBO x{session.combo_count[uid]}")

    session.players[uid] = session.players.get(uid, 0) + pts
    # award to DB
    try:
        db.add_score(uid, pts)
        db.add_xp(uid, pts * 10)
    except Exception:
        logger.exception("Failed to award points/xp")

    # increment words_found in DB
    user = db.get_user(uid)
    try:
        current_words_found = user['words_found'] if user and 'words_found' in user.keys() else (user[18] if user and len(user) > 18 and user[18] is not None else 0)
    except Exception:
        current_words_found = 0
    try:
        db.update_user(uid, words_found=current_words_found + 1)
        # referral check (maybe eligible after finding words)
        db.award_referral_if_eligible(uid)
    except Exception:
        logger.exception("Failed to update words_found")

    bonus_text = " • " + " • ".join(bonuses) if bonuses else ""
    try:
        bot.send_message(cid, f"🎉 <b>{html.escape(name)}</b> found <code>{word}</code>!\n+{pts} pts{bonus_text}")
    except Exception:
        pass

    update_game(cid)

    # if all words found -> end game
    if len(session.found) == len(session.words):
        # end_game will announce winner & delete message
        end_game(cid, reason="all_found")

# ---------------------------
# SUBSCRIPTION CHECK & MENUS
# ---------------------------
def is_subscribed(user_id: int) -> bool:
    if not CHANNEL_USERNAME:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ("creator", "administrator", "member")
    except Exception:
        return False

def must_join_menu():
    kb = InlineKeyboardMarkup()
    if CHANNEL_USERNAME:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
    kb.add(InlineKeyboardButton("✅ Verify Membership", callback_data="verify"))
    return kb

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    if CHANNEL_USERNAME:
        kb.row(
            InlineKeyboardButton("📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
            InlineKeyboardButton("✅ Verify", callback_data="verify")
        )

    kb.row(
        InlineKeyboardButton("🎮 Play", callback_data="play"),
        InlineKeyboardButton("📖 How to Play", callback_data="howtoplay")
    )
    kb.row(
        InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard"),
        InlineKeyboardButton("👤 Profile", callback_data="profile")
    )
    kb.row(
        InlineKeyboardButton("🏅 Achievements", callback_data="achievements"),
        InlineKeyboardButton("🎁 Daily", callback_data="daily")
    )
    kb.row(
        InlineKeyboardButton("🛒 Shop", callback_data="shop"),
        InlineKeyboardButton("💰 Redeem", callback_data="redeem_menu")
    )
    kb.row(
        InlineKeyboardButton("⭐ Review", callback_data="review_menu"),
        InlineKeyboardButton("👥 Invite", callback_data="referral")
    )
    kb.row(
        InlineKeyboardButton("📋 Commands", callback_data="commands"),
        InlineKeyboardButton("📚 JEE Mains PYQ", callback_data="jee_pyq")
    )
    kb.row(InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP))

    return kb

def game_modes_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("⚡ Normal (8x8)", callback_data="play_normal"),
        InlineKeyboardButton("🔥 Hard (10x10)", callback_data="play_hard")
    )
    # Subject modes use random words from ALL_WORDS (no fixed lists)
    kb.row(
        InlineKeyboardButton("🧪 Chemistry", callback_data="play_chemistry"),
        InlineKeyboardButton("⚛️ Physics", callback_data="play_physics")
    )
    kb.row(
        InlineKeyboardButton("📐 Math", callback_data="play_math"),
        InlineKeyboardButton("🎓 JEE", callback_data="play_jee")
    )
    kb.row(InlineKeyboardButton("« Back", callback_data="back_main"))
    return kb

def shop_menu():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🚀 XP Booster 2x (30d) - ₹199", callback_data="shop_xp_booster"))
    kb.add(InlineKeyboardButton("👑 Premium 1 Day - ₹49", callback_data="shop_premium_1d"))
    kb.add(InlineKeyboardButton("👑 Premium 7 Days - ₹249", callback_data="shop_premium_7d"))
    kb.add(InlineKeyboardButton("👑 Premium 30 Days - ₹999", callback_data="shop_premium_30d"))
    kb.add(InlineKeyboardButton("💡 10 Hints Pack - ₹30", callback_data="shop_hints_10"))
    kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
    return kb

# ---------------------------
# COMMAND HANDLERS
# ---------------------------
@bot.message_handler(commands=['start','help'])
def cmd_start(m):
    name = m.from_user.first_name or "Player"
    username = m.from_user.username or ""
    uid = m.from_user.id

    # referral handling: /start ref<id>
    parts = m.text.split() if m.text else []
    if len(parts) > 1:
        ref_code = parts[1]
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                if referrer_id != uid:
                    success = db.add_referral(referrer_id, uid)
                    if success:
                        # record referrer_id on referred user row
                        db.update_user(uid, referrer_id=referrer_id)
                        try:
                            bot.send_message(referrer_id, f"🔔 Someone used your referral link! They must verify & play to activate your reward.")
                        except Exception:
                            pass
                        notify_owner(f"👥 Referral created: {name} (ID: {uid}) referred by {referrer_id}")
            except Exception:
                logger.debug("Invalid referral code")

    if not is_subscribed(uid):
        txt = (f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n"
               f"⚠️ <b>You must join our channel to use this bot!</b>\n\n"
               f"1️⃣ Click 'Join Channel' button\n"
               f"2️⃣ Join the channel\n"
               f"3️⃣ Click 'Verify Membership'")
        try:
            bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=must_join_menu())
        except Exception:
            bot.send_message(m.chat.id, txt, reply_markup=must_join_menu())
        return

    db.get_user(uid, name, username)

    chat_type = "Group" if m.chat.type in ["group", "supergroup"] else "Private"
    if chat_type == "Group":
        chat_info = f"Chat: {m.chat.title} (ID: {m.chat.id})"
    else:
        chat_info = "Private Chat"

    notify_owner(
        f"🔔 <b>NEW START</b>\n\n"
        f"👤 User: {html.escape(name)}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Username: @{username if username else 'None'}\n"
        f"💬 {chat_info}\n"
        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    txt = (f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n"
           f"🎮 <b>WORD VORTEX ULTIMATE v10.5</b>\n"
           f"Complete feature-packed word game!\n\n"
           f"🌟 <b>Features:</b>\n"
           f"• 6 game modes with neon graphics\n"
           f"• Enhanced scoring with bonuses\n"
           f"• Achievements & Level system\n"
           f"• Shop with real money (₹)\n"
           f"• Real money rewards\n\n"
           f"Tap a button to start!")

    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=main_menu())
    except Exception:
        bot.send_message(m.chat.id, txt, reply_markup=main_menu())

@bot.message_handler(commands=['define'])
def cmd_define(m):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, "Usage: /define <word>\nExample: /define quantum")
        return

    word = args[1].strip().lower()

    try:
        r = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=10)
        if r.status_code == 200:
            data = r.json()[0]
            meanings = data.get('meanings', [])

            txt = f"📖 <b>{word.upper()}</b>\n\n"
            for i, meaning in enumerate(meanings[:2], 1):
                pos = meaning.get('partOfSpeech', 'unknown')
                definitions = meaning.get('definitions', [])
                if definitions:
                    defn = definitions[0].get('definition', '')
                    txt += f"<b>{i}. {pos}</b>\n{defn}\n\n"

            bot.reply_to(m, txt)
        else:
            bot.reply_to(m, f"❌ Definition not found for '{word}'")
    except Exception as e:
        bot.reply_to(m, f"❌ Error fetching definition: {str(e)}")

@bot.message_handler(commands=['new'])
def cmd_new(m):
    if not is_subscribed(m.from_user.id):
        bot.reply_to(m, "⚠️ You must join channel first! Use /start")
        return
    # start a normal game in this chat
    start_game(m.chat.id, m.from_user.id)

@bot.message_handler(commands=['stop','end'])
def cmd_stop(m):
    if m.chat.id in games:
        end_game(m.chat.id, reason="stopped")
        bot.reply_to(m, "🛑 Game stopped!")
    else:
        bot.reply_to(m, "❌ No active game!")

@bot.message_handler(commands=['stats','profile'])
def cmd_stats(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name)
    level = user['level'] if user and 'level' in user.keys() else (user[9] if user and len(user) > 9 else 1)
    xp = user['xp'] if user and 'xp' in user.keys() else (user[10] if user and len(user) > 10 else 0)
    xp_needed = level * 1000
    xp_progress = (xp / xp_needed * 100) if xp_needed > 0 else 0

    premium_badge = " 👑 PREMIUM" if db.is_premium(m.from_user.id) else " 🔓 FREE"

    # safe field extraction
    name = user['name'] if user and 'name' in user.keys() else (user[1] if user else m.from_user.first_name or "Player")
    total_score = user['total_score'] if user and 'total_score' in user.keys() else (user[6] if user and len(user) > 6 else 0)
    hint_balance = user['hint_balance'] if user and 'hint_balance' in user.keys() else (user[7] if user and len(user) > 7 else 0)
    games_played = user['games_played'] if user and 'games_played' in user.keys() else (user[4] if user and len(user) > 4 else 0)
    wins = user['wins'] if user and 'wins' in user.keys() else (user[5] if user and len(user) > 5 else 0)
    words_found = user['words_found'] if user and 'words_found' in user.keys() else (user[18] if user and len(user) > 18 else 0)
    streak = user['streak'] if user and 'streak' in user.keys() else (user[11] if user and len(user) > 11 else 0)

    txt = (f"👤 <b>PROFILE</b>\n\n"
           f"Name: {html.escape(str(name))}{premium_badge}\n"
           f"Level: {level} 🏅\n"
           f"XP: {xp}/{xp_needed} ({xp_progress:.1f}%)\n\n"
           f"Score: {total_score} pts\n"
           f"Balance: {hint_balance} pts\n"
           f"Games: {games_played} • Wins: {wins}\n"
           f"Words Found: {words_found}\n"
           f"Streak: {streak} days 🔥")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['leaderboard','lb'])
def cmd_leaderboard(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>TOP 10 PLAYERS</b>\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, row in enumerate(top, 1):
        # row is sqlite3.Row with (user_id, name, total_score, level, is_premium)
        try:
            uid = row[0]
            name = get_display_name(uid)
            score = row[2]
            level = row[3]
            is_prem = bool(row[4])
        except Exception:
            # fallback
            name = str(row)
            score = 0
            level = 1
            is_prem = False
        medal = medals[i-1] if i <= 3 else f"{i}."
        badge = " 👑" if is_prem else ""
        txt += f"{medal} {html.escape(str(name))}{badge} • Lvl {level} • {score} pts\n"
    bot.reply_to(m, txt if top else "No players yet!")

@bot.message_handler(commands=['daily'])
def cmd_daily(m):
    success, reward = db.claim_daily(m.from_user.id)
    if not success:
        bot.reply_to(m, "❌ Already claimed today!\nCome back tomorrow!")
        return
    user = db.get_user(m.from_user.id)

    # award streak achievement if applicable
    streak_val = user['streak'] if user and 'streak' in user.keys() else (user[11] if user and len(user) > 11 else 0)
    if user and streak_val >= 7:
        if db.add_achievement(m.from_user.id, "streak_master"):
            bot.send_message(m.chat.id, f"🏆 <b>Achievement Unlocked!</b>\n{ACHIEVEMENTS['streak_master']['icon']} {ACHIEVEMENTS['streak_master']['name']}")

    premium_msg = " (2x Premium)" if db.is_premium(m.from_user.id) else ""
    txt = f"🎁 <b>DAILY REWARD!</b>\n\n+{reward} pts{premium_msg}\nStreak: {streak_val} days 🔥"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['referral','invite'])
def cmd_referral(m):
    uid = m.from_user.id
    botinfo = bot.get_me()
    username_me = botinfo.username if botinfo and hasattr(botinfo, 'username') else ''
    ref_link = f"https://t.me/{username_me}?start=ref{uid}"
    txt = (f"👥 <b>INVITE & EARN</b>\n\n"
           f"Earn {REFERRAL_BONUS} pts per friend after they verify & play!\n\n"
           f"Your link:\n<code>{ref_link}</code>")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}"))
    bot.reply_to(m, txt, reply_markup=kb)

# ---------------------------
# ADMIN COMMANDS
# ---------------------------
@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(m):
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /addadmin <user_id>")
        return
    try:
        admin_id = int(args[1])
        db.add_admin(admin_id)
        bot.reply_to(m, f"✅ Added {admin_id} as admin!")
    except Exception:
        bot.reply_to(m, "Invalid user ID")

@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Usage: /addpoints <user_id> <points>  (adds to hint balance)")
        return
    try:
        user_id = int(args[1])
        points = int(args[2])
        db.add_hint_balance(user_id, points)
        bot.reply_to(m, f"✅ Added {points} points to hint balance of user {user_id}")
        try:
            bot.send_message(user_id, f"🎁 Admin added +{points} pts to your hint balance!")
        except Exception:
            pass
    except Exception as e:
        bot.reply_to(m, f"Invalid input: {e}")

@bot.message_handler(commands=['addscore'])
def cmd_addscore(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Usage: /addscore <user_id> <points>  (adds to total_score)")
        return
    try:
        user_id = int(args[1])
        points = int(args[2])
        db.add_score_only(user_id, points)
        bot.reply_to(m, f"✅ Added {points} points to total_score of user {user_id}")
        try:
            bot.send_message(user_id, f"🎁 Admin added +{points} pts to your score!")
        except Exception:
            pass
    except Exception as e:
        bot.reply_to(m, f"Invalid input: {e}")

@bot.message_handler(commands=['givehints'])
def cmd_givehints(m):
    if not db.is_admin(m.from_user.id) and not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Usage: /givehints <user_id> <amount>\nExample: /givehints 123456789 50")
        return
    try:
        user_id = int(args[1])
        amount = int(args[2])
        if amount <= 0:
            bot.reply_to(m, "Amount must be positive.")
            return
        db.add_hint_balance(user_id, amount)
        bot.reply_to(m, f"✅ Added {amount} pts to hint balance of user {user_id}")
        try:
            bot.send_message(user_id, f"🎁 Admin added +{amount} pts to your hint balance!")
        except Exception:
            pass
    except Exception as e:
        bot.reply_to(m, f"Invalid input: {e}")

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(m):
    """
    OWNER_ONLY broadcast:
    - sends to all known group chats where bot is currently admin (and to users if you want)
    - pins the broadcast (if bot has rights)
    Usage:
      /broadcast Your message here...
    NOTE: This will attempt to send to known group chats (known_chats table). It will not spam inactive unknown chats.
    """
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    text = m.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return

    # Send to known group chats (where the bot was seen before)
    chats = db.get_known_chats()
    sent = 0
    failed = 0
    for row in chats:
        try:
            chat_id = int(row['chat_id'] if 'chat_id' in row.keys() else row[0])
            # check bot privileges first - skip if bot is not an admin or cannot send messages
            try:
                member = bot.get_chat_member(chat_id, bot.get_me().id)
                if member.status not in ("administrator", "creator"):
                    # skip groups where bot is not admin (pin requires admin)
                    continue
            except Exception:
                # skip chats we cannot query
                continue

            msg = bot.send_message(chat_id, text)
            sent += 1
            # try pinning (if admin)
            try:
                bot.pin_chat_message(chat_id, msg.message_id, disable_notification=False)
            except Exception:
                # ignore pin failure, maybe bot lacks pin permissions on that chat
                pass
        except Exception as e:
            failed += 1
            logger.debug("Broadcast send failed for chat %s: %s", row, e)
            continue

    # Also send to all users (optional): keep the legacy behaviour for user broadcast
    users = db.get_all_users()
    user_success = 0
    user_fail = 0
    for uid in users:
        try:
            bot.send_message(uid, text)
            user_success += 1
        except Exception:
            user_fail += 1

    bot.reply_to(m, f"📢 Broadcast finished. Groups sent: {sent}, group failures: {failed}\nUsers sent: {user_success}, user failures: {user_fail}")

@bot.message_handler(commands=['markshoppaid'])
def cmd_markshoppaid(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /markshoppaid <purchase_id>")
        return
    try:
        pid = int(args[1])
        purchase = db.mark_shop_paid(pid)
        if not purchase:
            bot.reply_to(m, "Purchase not found.")
            return
        user_id, item_type, price = purchase
        bot.reply_to(m, f"✅ Marked purchase {pid} as paid. Notifying user.")
        try:
            bot.send_message(user_id, f"✅ Your purchase #{pid} ({item_type}) has been marked PAID. Thank you!")
        except Exception:
            logger.debug("Could not notify purchaser")
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

# PREMIUM ADMIN COMMANDS
@bot.message_handler(commands=['givepremium'])
def cmd_givepremium(m):
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Usage: /givepremium <user_id> <days>\nExample: /givepremium 123456789 7")
        return
    try:
        user_id = int(args[1])
        days = int(args[2])
        db.buy_premium(user_id, days)
        user = db.get_user(user_id)
        user_name = user['name'] if user and 'name' in user.keys() else (user[1] if user else str(user_id))
        bot.reply_to(m, f"✅ <b>Premium activated!</b>\n\nUser: {user_name} (ID: {user_id})\nDays: {days}\nExpiry: {days} days from now")
        try:
            bot.send_message(user_id, 
                f"🎉 <b>PREMIUM ACTIVATED!</b>\n\n"
                f"👑 You now have {days} days of premium!\n\n"
                f"<b>Premium Benefits:</b>\n"
                f"✅ No cooldown (instant guessing)\n"
                f"✅ Hints 50% cheaper (25 pts)\n"
                f"✅ Double XP (2x)\n"
                f"✅ Double Daily Reward (2x)\n"
                f"✅ Premium badge 👑\n\nEnjoy! 🚀")
        except Exception:
            pass
    except Exception as e:
        bot.reply_to(m, f"❌ Error: {str(e)}")

@bot.message_handler(commands=['checkpremium'])
def cmd_checkpremium(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /checkpremium <user_id>")
        return
    try:
        user_id = int(args[1])
        user = db.get_user(user_id)
        is_prem = db.is_premium(user_id)
        if is_prem:
            expiry = user['premium_expiry'] if user and 'premium_expiry' in user.keys() else (user[15] if user and len(user) > 15 else "unknown")
            txt = f"👑 <b>PREMIUM USER</b>\n\nName: {user['name'] if user and 'name' in user.keys() else (user[1] if user else str(user_id))}\nID: {user_id}\nExpiry: {expiry}"
        else:
            txt = f"❌ <b>NOT PREMIUM</b>\n\nName: {user['name'] if user and 'name' in user.keys() else (user[1] if user else str(user_id))}\nID: {user_id}"
        bot.reply_to(m, txt)
    except Exception:
        bot.reply_to(m, "Invalid user ID")

@bot.message_handler(commands=['shoplist'])
def cmd_shoplist(m):
    """
    Admin-only: list recent shop purchases.
    Fixes:
      - safe field extraction
      - remove stray characters and chunk message to avoid length issues
    """
    if not db.is_admin(m.from_user.id):
        return
    conn = db._conn()
    c = conn.cursor()
    c.execute("SELECT * FROM shop_purchases ORDER BY date DESC LIMIT 20")
    purchases = c.fetchall()
    conn.close()

    if not purchases:
        bot.reply_to(m, "No shop purchases yet!")
        return

    lines = ["🛒 <b>SHOP PURCHASES</b>\n"]
    for p in purchases:
        try:
            purchase_id = p['purchase_id'] if 'purchase_id' in p.keys() else p[0]
            user_id = p['user_id'] if 'user_id' in p.keys() else p[1]
            item_type = p['item_type'] if 'item_type' in p.keys() else p[2]
            price = p['price'] if 'price' in p.keys() else p[3]
            status = p['status'] if 'status' in p.keys() else (p[4] if len(p) > 4 else 'pending')
            date = p['date'] if 'date' in p.keys() else (p[5] if len(p) > 5 else '')
            user = db.get_user(user_id)
            user_name = user['name'] if user and 'name' in user.keys() else str(user_id)
            lines.append(f"<b>ID:</b> {purchase_id}\n<b>User:</b> {html.escape(str(user_name))} ({user_id})\n<b>Item:</b> {item_type}\n<b>Price:</b> ₹{price}\n<b>Status:</b> {status}\n<b>Date:</b> {date}\n\n")
        except Exception:
            continue

    # send in chunks (avoid telegram limits)
    chunk = ""
    for part in lines:
        if len(chunk) + len(part) > 3800:
            bot.reply_to(m, chunk)
            chunk = ""
        chunk += part
    if chunk:
        bot.reply_to(m, chunk)

@bot.message_handler(commands=['listreviews'])
def cmd_listreviews(m):
    if not db.is_admin(m.from_user.id):
        return
    reviews = db.get_reviews(approved_only=False)
    if not reviews:
        bot.reply_to(m, "No reviews yet!")
        return

    # Build messages in chunks to avoid hitting Telegram message length limits
    lines = ["📝 <b>ALL REVIEWS</b>\n"]
    for r in reviews:
        status = "✅" if r['approved'] else "⏳"
        text = (r['text'] or '')
        snippet = text if len(text) <= 240 else text[:240] + "..."
        lines.append(f"{status} ID:{r['review_id']} | {r['username']} | ⭐{r['rating']}\n{snippet}\n")

    chunk = ""
    for part in lines:
        if len(chunk) + len(part) > 3800:
            bot.reply_to(m, chunk)
            chunk = ""
        chunk += part + "\n"
    if chunk:
        bot.reply_to(m, chunk)

@bot.message_handler(commands=['approvereview'])
def cmd_approvereview(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /approvereview <review_id>")
        return
    try:
        review_id = int(args[1])
        db.approve_review(review_id)
        bot.reply_to(m, f"✅ Approved review {review_id}")
        rv = db.get_review(review_id)
        if rv:
            reviewer_id = rv[1]
            try:
                bot.send_message(reviewer_id, "✅ Your review was approved and is now visible to others. Thank you!")
            except Exception:
                logger.debug("Could not notify reviewer")
            # For immediate visibility: also post approved review to notification group if available
            try:
                if NOTIFICATION_GROUP:
                    bot.send_message(NOTIFICATION_GROUP, f"⭐ New approved review:\n{rv['username']} • ⭐{rv['rating']}\n{rv['text']}")
            except Exception:
                pass
    except Exception as e:
        bot.reply_to(m, f"Invalid ID: {e}")

@bot.message_handler(commands=['delreview'])
def cmd_delreview(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /delreview <review_id>")
        return
    try:
        review_id = int(args[1])
        db.delete_review(review_id)
        bot.reply_to(m, f"✅ Deleted review {review_id}")
    except Exception:
        bot.reply_to(m, "Invalid ID")

@bot.message_handler(commands=['redeemlist'])
def cmd_redeemlist(m):
    if not db.is_admin(m.from_user.id):
        return
    requests_list = db.get_redeem_requests('pending')
    if not requests_list:
        bot.reply_to(m, "No pending redeem requests!")
        return
    txt = "💰 <b>PENDING REDEEMS</b>\n\n"
    for r in requests_list[:10]:
        try:
            request_id = r['request_id'] if 'request_id' in r.keys() else r[0]
            username = r['username'] if 'username' in r.keys() else r[2]
            user_id = r['user_id'] if 'user_id' in r.keys() else r[1]
            points = r['points'] if 'points' in r.keys() else r[3]
            amount_inr = r['amount_inr'] if 'amount_inr' in r.keys() else r[4]
            upi_id = r['upi_id'] if 'upi_id' in r.keys() else r[5]
            txt += f"ID: {request_id} \nUser: {username} ({user_id})\nPoints: {points} → ₹{amount_inr}\nUPI: {upi_id}\n\n"
        except Exception:
            continue
    txt += "Use /redeempay <id> to mark as paid"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['redeempay'])
def cmd_redeempay(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /redeempay <request_id>")
        return
    try:
        request_id = int(args[1])
        db.mark_redeem_paid(request_id)
        bot.reply_to(m, f"✅ Marked request {request_id} as paid")
    except Exception:
        bot.reply_to(m, "Invalid ID")

@bot.message_handler(commands=['gamehistory'])
def cmd_gamehistory(m):
    args = m.text.split()
    if len(args) > 1 and args[1].lower() == "all":
        rows = db.get_game_history(None, limit=20)
    else:
        rows = db.get_game_history(m.from_user.id, limit=20)
    if not rows:
        bot.reply_to(m, "No games found.")
        return
    txt = "📜 <b>GAME HISTORY</b>\n\n"
    for r in rows:
        gid = r['game_id'] if 'game_id' in r.keys() else r[0]
        chat_id = r['chat_id'] if 'chat_id' in r.keys() else r[1]
        mode = r['mode'] if 'mode' in r.keys() else r[2]
        size = r['size'] if 'size' in r.keys() else r[3]
        start_time = r['start_time'] if 'start_time' in r.keys() else r[4]
        end_time = r['end_time'] if 'end_time' in r.keys() else r[5]
        winner_id = r['winner_id'] if 'winner_id' in r.keys() else r[6]
        winner_score = r['winner_score'] if 'winner_score' in r.keys() else r[7]
        txt += f"Game #{gid} • {mode} • {size}x{size}\nStart: {start_time}\nEnd: {end_time or 'ongoing'}\nWinner: {winner_id or 'N/A'} • {winner_score or 0}\n\n"
    bot.reply_to(m, txt)

# Error listing/inspection/issue creation commands (admin)
@bot.message_handler(commands=['list_errors'])
def cmd_list_errors(m):
    if not db.is_admin(m.from_user.id):
        return
    conn = db._conn()
    c = conn.cursor()
    c.execute("SELECT error_id, error_type, message, created_at FROM errors ORDER BY created_at DESC LIMIT 30")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(m, "No errors logged.")
        return
    txt = "❗️ Recent Errors\n\n"
    for r in rows:
        txt += f"ID:{r['error_id']} | {r['error_type']} | {r['created_at']}\n{(r['message'] or '')[:300]}\n\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['view_error'])
def cmd_view_error(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /view_error <id>")
        return
    try:
        eid = int(args[1])
        conn = db._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM errors WHERE error_id=?", (eid,))
        row = c.fetchone()
        conn.close()
        if not row:
            bot.reply_to(m, "Error not found")
            return
        tb = row['tb'] or ""
        txt = f"ID: {row['error_id']}\nType: {row['error_type']}\nTime: {row['created_at']}\nMessage:\n{row['message']}\n\nTraceback:\n{tb[:3500]}"
        bot.reply_to(m, txt if len(txt) < 4000 else txt[:3900] + "\n\n[truncated]")
    except Exception as e:
        bot.reply_to(m, f"Invalid id: {e}")

@bot.message_handler(commands=['issue_error'])
def cmd_issue_error(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /issue_error <error_id>")
        return
    try:
        eid = int(args[1])
        conn = db._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM errors WHERE error_id=?", (eid,))
        row = c.fetchone()
        conn.close()
        if not row:
            bot.reply_to(m, "Error not found")
            return

        if not (GITHUB_TOKEN and REPO_OWNER and REPO_NAME):
            bot.reply_to(m, "GitHub not configured (GITHUB_TOKEN/REPO_OWNER/REPO_NAME).")
            return

        title = f"Auto-logged Error #{eid}: {row['error_type']}"
        body = f"Time: {row['created_at']}\n\nMessage:\n{row['message']}\n\nTraceback:\n```\n{row['tb']}\n```\n\nContext: {row['context']}"
        try:
            gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
            payload = {"title": title, "body": body, "labels": ["bug", "auto-logged"]}
            r = requests.post(gh_url, headers=headers, json=payload, timeout=15)
            if r.status_code in (200,201):
                issue_url = r.json().get("html_url")
                conn = db._conn()
                c = conn.cursor()
                c.execute("UPDATE errors SET context = COALESCE(context, '') || ? WHERE error_id=?", (f"\nIssue: {issue_url}", eid))
                conn.commit()
                conn.close()
                bot.reply_to(m, f"Issue created: {issue_url}")
            else:
                bot.reply_to(m, f"Failed to create issue: {r.status_code} {r.text}")
        except Exception as e:
            bot.reply_to(m, f"Error creating issue: {e}")
    except Exception as e:
        bot.reply_to(m, f"Invalid id: {e}")

@bot.message_handler(commands=['ai_add'])
def ai_add(message):
    if not db.is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Only admins can add features.")
        return

    idea = message.text.replace("/ai_add", "").strip()
    if not idea:
        bot.reply_to(message, "⚠️ Please provide a feature description.")
        return

    if not OPENAI_API_KEY:
        bot.reply_to(message, "❌ OpenAI API key not configured (OPENAI_API_KEY).")
        return

    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a Python bot developer."},
                {"role": "user", "content": f"Generate a Python function to {idea}. Keep it self-contained."}
            ]
        }
        r = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=30)

        if r.status_code != 200:
            bot.reply_to(message, f"❌ OpenAI API returned {r.status_code}: {r.text[:1000]}")
            return

        data = r.json()

        # Robust extraction of generated content
        code = ""
        try:
            # Chat completion (preferred)
            choices = data.get("choices") or []
            if choices:
                first = choices[0]
                if isinstance(first.get("message"), dict):
                    code = first["message"].get("content", "") or first["message"].get("content", "")
                elif "text" in first:
                    code = first.get("text", "")
                else:
                    # fallback: try message.content path
                    code = first.get("message", {}).get("content", "") if isinstance(first.get("message"), dict) else ""
        except Exception as e:
            logger.exception("AI parsing error: %s", e)

        code = (code or "").strip()

        if not code:
            bot.reply_to(message, "❌ AI returned empty content. Raw response saved to logs.")
            # save raw response for debugging
            try:
                db.log_error("ai_add_empty", "OpenAI returned no code", tb=json.dumps(data)[:2000])
            except Exception:
                pass
            return

        pid = db.save_patch(f"ai_patch_{int(time.time())}.py", code)
        # show first part of code safely
        display = html.escape(code[:3000])
        bot.reply_to(message, f"✅ AI-generated feature saved as patch #{pid}\n\n<pre>{display}</pre>", parse_mode="HTML")

    except Exception as e:
        bot.reply_to(message, f"❌ AI error: {e}")
        tb = traceback.format_exc()
        try:
            db.log_error("ai_add_error", str(e), tb)
        except Exception:
            pass

# ---------------------------
# FEATURE PACK UPLOAD (owner/admin, safe JSON)
# ---------------------------
@bot.message_handler(commands=['upload_feature_pack'])
def cmd_upload_feature_pack(m):
    """
    Owner or admin can upload a JSON file (as document) with theme/messages/shop entries.
    This is safe: only JSON content is accepted, no code executed.
    """
    if not is_owner_or_admin(m.from_user.id):
        bot.reply_to(m, "Unauthorized")
        return
    bot.reply_to(m, "✅ Send JSON file as document now (only JSON, <= 200 KB).")
    user_states[m.from_user.id] = {'type': 'feature_pack_upload'}

@bot.message_handler(func=lambda m: m.from_user.id in user_states and user_states[m.from_user.id].get('type') == 'feature_pack_upload', content_types=['document'])
def handle_feature_pack_upload(m):
    uid = m.from_user.id
    doc = m.document
    if not doc:
        bot.reply_to(m, "No document found.")
        if uid in user_states:
            del user_states[uid]
        return
    if doc.file_size > 200000:
        bot.reply_to(m, "File too large. Max 200 KB.")
        if uid in user_states:
            del user_states[uid]
        return
    try:
        file_info = bot.get_file(doc.file_id)
        f = bot.download_file(file_info.file_path)
        content = f.decode('utf-8', errors='replace')
        parsed = json.loads(content)
        # basic validation: must be dict
        if not isinstance(parsed, dict):
            bot.reply_to(m, "Invalid JSON structure.")
            if uid in user_states:
                del user_states[uid]
            return
        # save to DB and in-memory
        db.save_feature_pack(doc.file_name, content)
        global feature_pack
        feature_pack = parsed
        bot.reply_to(m, "✅ Feature pack uploaded and applied (non-code features).")
    except Exception as e:
        bot.reply_to(m, f"❌ Failed to load: {e}")
        tb = traceback.format_exc()
        try:
            db.log_error("feature_pack_upload_error", str(e), tb, context=f"file:{doc.file_name if doc else 'unknown'}")
        except Exception:
            pass
    finally:
        if uid in user_states:
            del user_states[uid]

# ---------------------------
# PATCH UPLOAD (owner/admin) - more robust acknowledgement
# ---------------------------
@bot.message_handler(commands=['upload_patch'])
def cmd_upload_patch(m):
    if not is_owner_or_admin(m.from_user.id):
        bot.reply_to(m, "Unauthorized")
        return
    bot.reply_to(m, "✅ Send patch file as document now (only text/patch, <= 500 KB). It will be saved to DB. No code will be executed.")
    user_states[m.from_user.id] = {'type': 'patch_upload'}

@bot.message_handler(func=lambda m: m.from_user.id in user_states and user_states[m.from_user.id].get('type') == 'patch_upload', content_types=['document'])
def handle_patch_upload(m):
    uid = m.from_user.id
    doc = m.document
    if not doc:
        bot.reply_to(m, "No document found.")
        if uid in user_states:
            del user_states[uid]
        return
    if doc.file_size > 500000:
        bot.reply_to(m, "File too large. Max 500 KB.")
        if uid in user_states:
            del user_states[uid]
        return
    try:
        # Acknowledge early so user sees bot is processing
        bot.reply_to(m, f"📥 Received {doc.file_name}, processing...")
        file_info = bot.get_file(doc.file_id)
        raw = bot.download_file(file_info.file_path)
        content = raw.decode('utf-8', errors='replace')
        pid = db.save_patch(doc.file_name, content)
        bot.reply_to(m, f"✅ Patch uploaded and saved as #{pid}. To create a GitHub issue for this patch use /create_patch_issue {pid} (requires GITHUB_TOKEN and REPO settings).")
    except Exception as e:
        bot.reply_to(m, f"❌ Failed to upload: {e}")
        tb = traceback.format_exc()
        try:
            db.log_error("patch_upload_error", str(e), tb, context=f"file:{doc.file_name if doc else 'unknown'}")
        except Exception:
            pass
    finally:
        if uid in user_states:
            del user_states[uid]

@bot.message_handler(commands=['create_patch_issue'])
def cmd_create_patch_issue(m):
    if not db.is_admin(m.from_user.id) and not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /create_patch_issue <patch_id>")
        return
    try:
        patch_id = int(args[1])
        conn = db._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM patches WHERE patch_id=?", (patch_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            bot.reply_to(m, "Patch not found.")
            return
        if not (GITHUB_TOKEN and REPO_OWNER and REPO_NAME):
            bot.reply_to(m, "GitHub not configured (GITHUB_TOKEN/REPO_OWNER/REPO_NAME).")
            return
        title = f"Patch upload #{patch_id}: {row['filename']}"
        body = f"Uploaded patch:\n\nFilename: {row['filename']}\nUploaded at: {row['uploaded_at']}\n\nContents:\n```\n{row['contents'][:6000]}\n```\n"
        try:
            gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues"
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
            payload = {"title": title, "body": body, "labels": ["patch", "uploaded"]}
            r = requests.post(gh_url, headers=headers, json=payload, timeout=15)
            if r.status_code in (200,201):
                issue_url = r.json().get("html_url")
                conn = db._conn()
                c = conn.cursor()
                c.execute("UPDATE patches SET created_issue_url=? WHERE patch_id=?", (issue_url, patch_id))
                conn.commit()
                conn.close()
                bot.reply_to(m, f"Issue created: {issue_url}")
            else:
                bot.reply_to(m, f"Failed to create issue: {r.status_code} {r.text}")
        except Exception as e:
            bot.reply_to(m, f"Error creating issue: {e}")
    except Exception as e:
        bot.reply_to(m, f"Invalid id: {e}")

@bot.message_handler(commands=['show_patch','view_patch'])
def cmd_show_patch(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /show_patch <patch_id>")
        return
    try:
        pid = int(args[1])
        conn = db._conn()
        c = conn.cursor()
        c.execute("SELECT filename, contents, uploaded_at, created_issue_url FROM patches WHERE patch_id=?", (pid,))
        row = c.fetchone()
        conn.close()
        if not row:
            bot.reply_to(m, "Patch not found.")
            return
        contents = row['contents'] if 'contents' in row.keys() else row[1]
        header = f"Patch #{pid}: {row['filename']} (uploaded: {row['uploaded_at']})\nIssue: {row['created_issue_url'] or 'None'}\n\n"
        bot.reply_to(m, header + (contents[:3900] + ("\n\n[truncated]" if len(contents) > 3900 else "")))
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")

# ---------------------------
# TEXT STATE HANDLERS (reviews, redeem flows)
# ---------------------------
@bot.message_handler(func=lambda m: m.from_user.id in user_states and m.text and not m.text.startswith('/'))
def handle_state(m):
    uid = m.from_user.id
    state = user_states.get(uid)
    if not state:
        return

    if state['type'] == 'review_rating':
        try:
            rating = int(m.text)
            if not (1 <= rating <= 5):
                raise ValueError
            user_states[uid] = {'type': 'review_text', 'rating': rating}
            bot.reply_to(m, "✍️ Now send your review text:")
        except Exception:
            bot.reply_to(m, "❌ Please send rating 1-5")

    elif state['type'] == 'review_text':
        text = m.text or ""
        rating = state['rating']
        flagged = any(bad in text.upper() for bad in BAD_WORDS)

        db.add_review(uid, m.from_user.first_name or "User", text, rating)
        del user_states[uid]

        notify_owner(
            f"⭐ <b>NEW REVIEW</b>\n\n"
            f"User: {html.escape(m.from_user.first_name or 'User')}\n"
            f"Rating: {'⭐' * rating}\n"
            f"Review: {html.escape(text)}\n\n"
            f"Use /approvereview or /delreview to manage"
        )

        if flagged:
            bot.reply_to(m, "⚠️ Your review contains words that may violate rules and is under moderation. Owner will review it.")
        else:
            bot.reply_to(m, "⭐ Thank you for your review! It will be shown after approval.")

    elif state['type'] == 'redeem_points':
        try:
            points = int(m.text)
            min_required = REDEEM_MIN_PREMIUM if db.is_premium(uid) else REDEEM_MIN_NON_PREMIUM
            if points < min_required:
                bot.reply_to(m, f"❌ Minimum {min_required} points required to redeem (you are {'premium' if db.is_premium(uid) else 'non-premium'}).")
                del user_states[uid]
                return
            user = db.get_user(uid)
            balance = user['total_score'] if user and 'total_score' in user.keys() else (user[6] if user and len(user) > 6 else 0)
            if balance < points:
                bot.reply_to(m, f"❌ You only have {balance} points!")
                del user_states[uid]
                return
            user_states[uid] = {'type': 'redeem_upi', 'points': points}
            bot.reply_to(m, "💳 Now send your UPI ID:\nExample: yourname@paytm")
        except Exception:
            bot.reply_to(m, "❌ Invalid number!")
            del user_states[uid]

    elif state['type'] == 'redeem_upi':
        upi = m.text
        points = state['points']
        user = db.get_user(uid)
        db.add_redeem(uid, m.from_user.first_name or "User", points, upi)
        current_score = user['total_score'] if user and 'total_score' in user.keys() else (user[6] if user and len(user) > 6 else 0)
        db.update_user(uid, total_score=max(0, current_score - points))
        del user_states[uid]

        notify_owner(
            f"💰 <b>NEW REDEEM REQUEST</b>\n\n"
            f"User: {html.escape(m.from_user.first_name or 'User')}\n"
            f"ID: <code>{uid}</code>\n"
            f"Points: {points}\n"
            f"Amount: ₹{points // REDEEM_CONVERSION_DIV}\n"
            f"UPI: <code>{upi}</code>\n\n"
            f"Use /redeemlist to see all"
        )

        bot.reply_to(m, f"✅ Redeem request submitted!\n\nPoints: {points}\nAmount: ₹{points // REDEEM_CONVERSION_DIV}\nUPI: {upi}\n\nOwner will process within 24-48 hours.")

# ---------------------------
# ForceReply handler for legacy "Found It!" flow (still supported)
# ---------------------------

@bot.message_handler(
    func=lambda m: (
        getattr(m, "reply_to_message", None) is not None
        and isinstance(getattr(m.reply_to_message, "text", None), str)
        and "Type the word you found" in m.reply_to_message.text
        and m.text
        and not m.text.startswith("/")
    ),
    content_types=['text']
)
def guess_reply_handler(m):
    try:
        handle_guess(m)
    except Exception:
        tb = traceback.format_exc()
        logger.exception("Error handling guess reply")
        try:
            db.log_error("guess_reply_error", "Error handling guess reply", tb, context=f"chat:{getattr(m, 'chat', {}).id if getattr(m, 'chat', None) else 'unknown'}")
        except Exception:
            pass

# ---------------------------
# CALLBACKS (menus & game actions)
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data

    # VERIFY
    if data == "verify":
        if is_subscribed(uid):
            db.update_user(uid, verified=1)
            notify_owner(
                f"✅ <b>USER VERIFIED</b>\n\n"
                f"User: {html.escape(c.from_user.first_name or 'User')}\n"
                f"ID: <code>{uid}</code>\n"
                f"Username: @{c.from_user.username if c.from_user.username else 'None'}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            bot.answer_callback_query(c.id, "✅ Verified! Welcome!", show_alert=True)
            try:
                bot.delete_message(cid, c.message.message_id)
            except Exception:
                pass
            name = c.from_user.first_name or "Player"
            txt = (f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n"
                   f"🎮 <b>WORD VORTEX ULTIMATE v10.5</b>\n\n"
                   f"✅ <b>Verified Successfully!</b>\n\n"
                   f"Select an option below to continue:")
            try:
                bot.send_photo(cid, START_IMG_URL, caption=txt, reply_markup=main_menu())
            except Exception:
                bot.send_message(cid, txt, reply_markup=main_menu())
            # maybe check referral eligibility now
            db.award_referral_if_eligible(uid)
            return
        else:
            bot.answer_callback_query(c.id, "❌ Please join channel first!", show_alert=True)
            return

    # subscription check for other actions
    if not is_subscribed(uid) and data not in ["verify"]:
        bot.answer_callback_query(c.id, "⚠️ Join channel first!", show_alert=True)
        return

    if data == "play":
        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=c.message.message_id, reply_markup=game_modes_menu())
            bot.answer_callback_query(c.id)
        except Exception:
            try:
                bot.send_message(uid, "🎮 Select mode:", reply_markup=game_modes_menu())
                bot.answer_callback_query(c.id, "Sent to PM!")
            except Exception:
                bot.answer_callback_query(c.id, "Error!", show_alert=True)
        return

    if data == "howtoplay":
        help_text = """🎮 <b>HOW TO PLAY</b>

1️⃣ Click "🎮 Play" button
2️⃣ Select game mode
3️⃣ Find words in grid
4️⃣ Simply type the word you found in chat (no need to click buttons)
5️⃣ Earn points!

<b>🏆 SCORING:</b>
🥇 First Blood: +15 pts
⚡ Normal: +3 pts
🎯 Finisher: +10 pts
⚡ Speed Bonus: +5 pts (10 sec)
🔥 Combo: +5 pts (consecutive)"""
        try:
            bot.send_message(uid, help_text)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except Exception:
            bot.send_message(cid, help_text)
            bot.answer_callback_query(c.id)
        return

    if data == "back_main":
        try:
            bot.edit_message_reply_markup(chat_id=cid, message_id=c.message.message_id, reply_markup=main_menu())
            bot.answer_callback_query(c.id)
        except Exception:
            pass
        return

    if data == "leaderboard":
        top = db.get_top_players(10)
        txt = "🏆 <b>TOP 10</b>\n\n"
        for i, row in enumerate(top, 1):
            try:
                uid_row = row[0]
                name = get_display_name(uid_row)
                score = row[2]
            except Exception:
                name = str(row)
                score = 0
            badge = " 👑" if (row[4] if len(row) > 4 else False) else ""
            txt += f"{i}. {html.escape(str(name))}{badge} • {score} pts\n"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "profile":
        user = db.get_user(uid)
        premium_badge = " 👑 PREMIUM" if db.is_premium(uid) else " 🔓 FREE"
        # safe extraction
        name = user['name'] if user and 'name' in user.keys() else (user[1] if user else 'User')
        level = user['level'] if user and 'level' in user.keys() else (user[9] if user else 1)
        xp = user['xp'] if user and 'xp' in user.keys() else (user[10] if user else 0)
        total_score = user['total_score'] if user and 'total_score' in user.keys() else (user[6] if user else 0)
        hint_balance = user['hint_balance'] if user and 'hint_balance' in user.keys() else (user[7] if user else 0)
        wins = user['wins'] if user and 'wins' in user.keys() else (user[5] if user else 0)
        games_played = user['games_played'] if user and 'games_played' in user.keys() else (user[4] if user else 0)
        words_found = user['words_found'] if user and 'words_found' in user.keys() else (user[18] if user else 0)
        streak = user['streak'] if user and 'streak' in user.keys() else (user[11] if user else 0)

        txt = (f"👤 <b>PROFILE</b>\n\n"
               f"Name: {html.escape(name)}{premium_badge}\n"
               f"Level: {level} | XP: {xp}\n"
               f"Score: {total_score} pts\n"
               f"Balance: {hint_balance} pts\n"
               f"Wins: {wins} | Games: {games_played}\n"
               f"Words Found: {words_found}\n"
               f"Streak: {streak} days 🔥")
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "achievements":
        user = db.get_user(uid)
        achievements = json.loads(user['achievements'] if user and 'achievements' in user.keys() else "[]")
        txt = "🏅 <b>ACHIEVEMENTS</b>\n\n"
        for ach_id, ach in ACHIEVEMENTS.items():
            status = "✅" if ach_id in achievements else "🔒"
            txt += f"{status} {ach['icon']} <b>{ach['name']}</b>\n{ach['desc']}\nReward: {ach['reward']} pts\n\n"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "daily":
        success, reward = db.claim_daily(uid)
        if not success:
            bot.answer_callback_query(c.id, "Already claimed!", show_alert=True)
            return
        user = db.get_user(uid)
        premium_msg = " (2x Premium)" if db.is_premium(uid) else ""
        streak_val = user['streak'] if user and 'streak' in user.keys() else (user[11] if user else 0)
        txt = f"🎁 +{reward} pts{premium_msg}\nStreak: {streak_val} days!"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "shop":
        txt = "🛒 <b>SHOP - REAL MONEY (₹)</b>\n\nSelect item to purchase:"
        try:
            bot.send_message(uid, txt, reply_markup=shop_menu())
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt, reply_markup=shop_menu())
            bot.answer_callback_query(c.id)
        return

    if data.startswith("shop_"):
        item_id = data.replace("shop_", "")
        item = SHOP_ITEMS.get(item_id)
        if not item:
            bot.answer_callback_query(c.id, "Invalid item!")
            return

        txt = (f"💳 <b>PURCHASE: {item['name']}</b>\n\n"
               f"Price: <b>₹{item['price']}</b>\n\n"
               f"📱 Send payment to:\n"
               f"<b>UPI:</b> <code>ruhvaan@slc</code>\n\n"
               f"After payment, send screenshot to @{SUPPORT_GROUP.split('/')[-1]}")

        # Save purchase and return generated purchase id
        pid = db.add_purchase(uid, item['type'], item['price'])

        notify_owner(
            f"🛒 <b>NEW SHOP ORDER</b>\n\n"
            f"User: {html.escape(c.from_user.first_name or 'User')}\n"
            f"ID: <code>{uid}</code>\n"
            f"Item: {item['name']}\n"
            f"Price: ₹{item['price']}\n"
            f"Purchase ID: #{pid}\n\n"
            f"Use /shoplist to view all orders"
        )

        bot.send_message(uid, txt + f"\n\n📦 Your purchase id: #{pid}\nKeep this id for support.")
        bot.answer_callback_query(c.id, f"Order created: #{pid}")
        return

    if data == "redeem_menu":
        user = db.get_user(uid)
        balance = user['total_score'] if user and 'total_score' in user.keys() else (user[6] if user and len(user) > 6 else 0)
        min_required = REDEEM_MIN_PREMIUM if db.is_premium(uid) else REDEEM_MIN_NON_PREMIUM
        txt = (f"💰 <b>REDEEM POINTS</b>\n\n"
               f"Balance: {balance} pts\n"
               f"Rate: 100 pts = ₹1\n"
               f"Min: {min_required} pts ({'premium' if db.is_premium(uid) else 'non-premium'})\n\n"
               f"Process: Click button below to start")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🚀 Start Redeem", callback_data="redeem_start"))
        kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "redeem_start":
        user_states[uid] = {'type': 'redeem_points'}
        bot.send_message(uid, "💰 Enter points to redeem (see minimums in Redeem menu):")
        bot.answer_callback_query(c.id)
        return

    if data == "review_menu":
        txt = "⭐ <b>SUBMIT REVIEW</b>\n\nProcess: Click button to start or view approved reviews."
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✍️ Write Review", callback_data="review_start"))
        kb.add(InlineKeyboardButton("📢 View Reviews", callback_data="view_reviews"))
        kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "review_start":
        user_states[uid] = {'type': 'review_rating'}
        bot.send_message(uid, "⭐ Send rating (1-5):\n1 = Poor, 5 = Excellent")
        bot.answer_callback_query(c.id)
        return

    if data == "view_reviews":
        reviews = db.get_reviews(approved_only=True)
        if not reviews:
            bot.answer_callback_query(c.id, "No reviews yet!", show_alert=True)
            return
        try:
            for r in reviews[:10]:
                txt = f"⭐ {r['rating']} • {r['username']}\n{(r['text'] or '')[:600]}\n"
                bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent reviews to you!")
        except Exception:
            logger.exception("Error sending reviews")
            bot.answer_callback_query(c.id, "Error sending reviews", show_alert=True)
        return

    if data == "referral":
        botinfo = bot.get_me()
        username_me = botinfo.username if botinfo and hasattr(botinfo, 'username') else ''
        ref_link = f"https://t.me/{username_me}?start=ref{uid}"
        txt = f"👥 <b>INVITE</b>\n\nEarn {REFERRAL_BONUS} pts after they verify & play!\n\n<code>{ref_link}</code>"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "commands":
        txt = ("📋 <b>COMMANDS LIST</b>\n\n"
               "<b>🎮 Game:</b>\n"
               "/new - Start game\n"
               "/stop - End game\n\n"
               "<b>👤 User:</b>\n"
               "/stats - Profile\n"
               "/leaderboard - Top 10\n"
               "/daily - Daily reward\n"
               "/referral - Invite link\n\n"
               "<b>📖 Dictionary:</b>\n"
               "/define <word> - Word definition\n\n"
               "<b>👨‍💼 Admin:</b>\n"
               "/givepremium <id> <days> - Give premium\n"
               "/checkpremium <id> - Check premium\n"
               "/shoplist - View shop orders\n"
               "/addpoints <id> <pts>  (adds to hint balance)\n"
               "/addscore <id> <pts>   (adds to total_score)\n"
               "/givehints <id> <amt>\n"
               "/broadcast <msg>\n"
               "/listreviews\n"
               "/redeemlist")
        try:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id, "Commands sent!")
        except Exception:
            try:
                bot.send_message(uid, txt)
                bot.answer_callback_query(c.id, "Commands sent to PM!")
            except Exception:
                bot.answer_callback_query(c.id, "Unable to send commands.", show_alert=True)
        return

    if data == "jee_pyq":
        txt = ("📚 <b>JEE Mains PYQ Resources</b>\n\n"
               "Choose a source to practice previous year questions:\n"
               "• ExamSide: https://www.examside.com/jeemain\n"
               "• ExamGoal: https://www.examgoal.com/\n"
               "• Marks App: https://play.google.com/store/apps/details?id=com.marksapp\n"
               "• NTA Abhyas: https://play.google.com/store/apps/details?id=com.mhrd.nta\n")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("ExamSide", url="https://www.examside.com/jeemain"))
        kb.add(InlineKeyboardButton("ExamGoal", url="https://www.examgoal.com/"))
        kb.add(InlineKeyboardButton("Marks App", url="https://play.google.com/store/apps/details?id=com.marksapp"))
        kb.add(InlineKeyboardButton("NTA Abhyas", url="https://play.google.com/store/apps/details?id=com.mhrd.nta"))
        try:
            bot.send_message(cid, txt, reply_markup=kb, disable_web_page_preview=True)
            bot.answer_callback_query(c.id)
        except Exception:
            bot.answer_callback_query(c.id, "Unable to open PYQ links.", show_alert=True)
        return

    # Game mode selection
    if data.startswith("play_"):
        mode = data.replace("play_", "")
        custom_words = None
        is_hard = False
        theme = "default"

        if mode == "normal":
            mode_name = "NORMAL"
        elif mode == "hard":
            mode_name = "HARD"
            is_hard = True
        elif mode in ("chemistry","physics","math","jee"):
            mode_name = mode.upper()
            # use random sample from ALL_WORDS to provide subject-like variety without fixed lists
            if ALL_WORDS:
                custom_words = random.sample(ALL_WORDS, min(200, len(ALL_WORDS)))
            # if premium user starts the game, give gold theme
            if db.is_premium(uid):
                theme = "gold"
        else:
            mode_name = "NORMAL"

        start_game(cid, uid, mode_name, is_hard, custom_words, theme=theme)
        bot.answer_callback_query(c.id, f"✅ {mode_name} mode started!")
        return

    # Game actions
    if data == "g_guess":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        try:
            # old flow: send ForceReply - still supported
            bot.send_message(cid, "💬 Type the word you found:", reply_markup=ForceReply(selective=True))
            bot.answer_callback_query(c.id)
        except Exception:
            bot.answer_callback_query(c.id, "Error!", show_alert=True)
        return

    if data == "g_hint":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        user = db.get_user(uid)

        cost = 25 if db.is_premium(uid) else HINT_COST
        user_hint_balance = user['hint_balance'] if user and 'hint_balance' in user.keys() else (user[7] if user and len(user) > 7 else 0)
        if user_hint_balance < cost:
            bot.answer_callback_query(c.id, f"Need {cost} pts!", show_alert=True)
            return
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All found!", show_alert=True)
            return
        # premium partial hint: reveal one letter position instead of full word
        reveal = random.choice(hidden)
        if db.is_premium(uid):
            # reveal a random position letter
            pos = random.randint(0, len(reveal)-1)
            masked = "".join([reveal[i] if i == pos else ("•" if 0 < i < len(reveal)-1 else reveal[i]) for i in range(len(reveal))])
            hint_text = f"💡 <b>Partial Hint:</b> <code>{masked}</code> (-{cost} pts)"
        else:
            hint_text = f"💡 <b>Hint:</b> <code>{reveal}</code> (-{cost} pts)"

        db.update_user(uid, hint_balance=user_hint_balance - cost)
        bot.send_message(cid, hint_text)
        bot.answer_callback_query(c.id)
        return

    if data == "g_score":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        game = games[cid]
        if not game.players:
            bot.answer_callback_query(c.id, "No scores yet!", show_alert=True)
            return
        scores = sorted(game.players.items(), key=lambda x: x[1], reverse=True)
        txt = "📊 <b>CURRENT SCORES</b>\n\n"
        for i, (u, pts) in enumerate(scores, 1):
            try:
                name = get_display_name(u)
            except Exception:
                name = str(u)
            txt += f"{i}. {html.escape(str(name))} - {pts} pts\n"
        bot.send_message(cid, txt)
        bot.answer_callback_query(c.id)
        return

    if data == "g_stop":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        end_game(cid, reason="stopped")
        bot.send_message(cid, "🛑 <b>Game stopped!</b>")
        bot.answer_callback_query(c.id, "Game ended!")
        return

    bot.answer_callback_query(c.id)

# ---------------------------
# FEATURE: AI-assisted suggestions for errors (/suggest_fix)
# ---------------------------
@bot.message_handler(commands=['suggest_fix'])
def cmd_suggest_fix(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Usage: /suggest_fix <error_id>")
        return
    try:
        eid = int(args[1])
        conn = db._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM errors WHERE error_id=?", (eid,))
        row = c.fetchone()
        conn.close()
        if not row:
            bot.reply_to(m, "Error not found")
            return

        if not OPENAI_API_KEY:
            bot.reply_to(m, "OpenAI not configured (OPENAI_API_KEY).")
            return

        # Build prompt (sanitize to avoid leaking secrets)
        tb = (row['tb'] or "")[:3000]
        message = (row['message'] or "")[:1000]
        prompt = (
            "You are a concise Python/Telegram-bot debugging assistant. "
            "Provide actionable fixes and code suggestions for the error below. "
            "Do NOT reveal any secrets or tokens. Keep response short (max 800 tokens).\n\n"
            f"Error message:\n{message}\n\nTraceback:\n{tb}\n\n"
            "Give suggested changes and example code snippets if relevant."
        )

        try:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            body = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.2,
            }
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body, timeout=30)
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"]
                bot.reply_to(m, f"🤖 Suggestion:\n{reply[:4000]}")
            else:
                bot.reply_to(m, f"OpenAI API error: {r.status_code} {r.text}")
        except Exception as e:
            bot.reply_to(m, f"Error contacting OpenAI: {e}")
            tb2 = traceback.format_exc()
            try:
                db.log_error("openai_request_error", str(e), tb2, context=f"error_id:{eid}")
            except Exception:
                pass
    except Exception as e:
        bot.reply_to(m, f"Invalid id: {e}")

# ---------------------------
# RUN CODE FROM TELEGRAM (OWNER ONLY) - improved security & languages
# ---------------------------
def _apply_resource_limits():
    """
    Apply lightweight resource limits for child processes (POSIX only).
    """
    if resource:
        try:
            # CPU time: 5s
            resource.setrlimit(resource.RLIMIT_CPU, (5, 10))
            # Address space (virtual memory): 200MB
            resource.setrlimit(resource.RLIMIT_AS, (200 * 1024 * 1024, 300 * 1024 * 1024))
        except Exception:
            pass

@bot.message_handler(commands=['run'])
def cmd_run(m):
    """
    OWNER only. Run a short Python script sent as a reply to a message or inline after the command.
    SECURITY: restricted to OWNER_ID only. Runs in subprocess with timeout and sandbox limits when possible.
    """
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return

    # get code either from reply or from command text
    code = ""
    if m.reply_to_message and m.reply_to_message.text:
        code = m.reply_to_message.text
    else:
        parts = m.text.split(maxsplit=1)
        if len(parts) > 1:
            code = parts[1]

    if not code:
        bot.reply_to(m, "Usage: reply to a message containing Python code with /run, or /run <code>")
        return

    # create a temp file and execute python in subprocess
    fname = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tf:
            tf.write(code)
            tf.flush()
            fname = tf.name

        # run with timeout (8s) and capture output; apply resource limits via preexec_fn on POSIX
        preexec = _apply_resource_limits if resource else None
        proc = subprocess.run(
            [sys.executable, fname],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=8,
            preexec_fn=preexec
        )
        out = proc.stdout.decode('utf-8', errors='replace')
        err = proc.stderr.decode('utf-8', errors='replace')
        result = ""
        if out:
            result += f"📤 STDOUT:\n{out}\n"
        if err:
            result += f"⚠️ STDERR:\n{err}\n"
        if not result:
            result = "✅ Executed. No output."
        # trim
        bot.reply_to(m, result[:3900])
    except subprocess.TimeoutExpired:
        bot.reply_to(m, "⏱ Execution timed out (8s).")
    except Exception as e:
        tb = traceback.format_exc()
        bot.reply_to(m, f"❌ Error running code: {e}\n\n{tb[:1500]}")
    finally:
        try:
            if fname:
                os.unlink(fname)
        except Exception:
            pass

# New: run code for multiple languages (owner-only)
@bot.message_handler(commands=['runlang'])
def cmd_runlang(m):
    """
    Owner-only. Usage:
      /runlang python <code>  OR reply to a message with /runlang python
      /runlang node <js code> OR reply to a message with /runlang node
    Executes in a subprocess with timeouts and resource limits where possible.
    """
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return

    parts = m.text.split(maxsplit=2)
    lang = None
    code = ""
    if m.reply_to_message and m.reply_to_message.text:
        # reply mode: /runlang python (reply message contains code)
        if len(parts) >= 2:
            lang = parts[1].lower()
            code = m.reply_to_message.text
        else:
            bot.reply_to(m, "Usage: reply to a message with /runlang <python|node>")
            return
    else:
        if len(parts) >= 3:
            lang = parts[1].lower()
            code = parts[2]
        else:
            bot.reply_to(m, "Usage: /runlang <python|node> <code> OR reply to a message with /runlang <lang>")
            return

    if not code:
        bot.reply_to(m, "No code provided.")
        return

    fname = None
    try:
        if lang == "python":
            suffix = ".py"
            cmd = [sys.executable]
        elif lang in ("node", "js", "javascript"):
            suffix = ".js"
            cmd = ["node"]
        else:
            bot.reply_to(m, "Unsupported language. Supported: python, node")
            return

        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as tf:
            tf.write(code)
            tf.flush()
            fname = tf.name

        cmd.append(fname)
        preexec = _apply_resource_limits if resource else None
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
            preexec_fn=preexec
        )
        out = proc.stdout.decode('utf-8', errors='replace')
        err = proc.stderr.decode('utf-8', errors='replace')
        resp = ""
        if out:
            resp += f"📤 STDOUT:\n{out}\n"
        if err:
            resp += f"⚠️ STDERR:\n{err}\n"
        if not resp:
            resp = "✅ Executed. No output."
        bot.reply_to(m, resp[:3900])
    except subprocess.TimeoutExpired:
        bot.reply_to(m, "⏱ Execution timed out.")
    except FileNotFoundError as e:
        bot.reply_to(m, f"❌ Runtime not found: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        bot.reply_to(m, f"❌ Error running code: {e}\n\n{tb[:1500]}")
    finally:
        try:
            if fname:
                os.unlink(fname)
        except Exception:
            pass

# New: npm install wrapper (OWNER only)
@bot.message_handler(commands=['npm_install'])
def cmd_npm_install(m):
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /npm_install <package[@version]> or /npm_install <package1 package2 ...>")
        return
    pkg = parts[1].strip()
    try:
        bot.reply_to(m, f"🔧 Running npm install: {pkg} ...")
        proc = subprocess.run(["npm", "install", pkg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        out = proc.stdout.decode('utf-8', errors='replace')
        err = proc.stderr.decode('utf-8', errors='replace')
        resp = ""
        if out:
            resp += f"📤 STDOUT:\n{out}\n"
        if err:
            resp += f"⚠️ STDERR:\n{err}\n"
        if not resp:
            resp = "✅ Done (no output)."
        bot.reply_to(m, resp[:3900])
    except subprocess.TimeoutExpired:
        bot.reply_to(m, "⏱ npm install timed out.")
    except FileNotFoundError:
        bot.reply_to(m, "❌ npm not found on this system.")
    except Exception as e:
        bot.reply_to(m, f"❌ Error running npm: {e}")

# New: improved pip installer with chunked replies and support hints for frontend tools
@bot.message_handler(commands=['pip_install', 'pip'])
def cmd_pip_install(m):
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, "Usage: /pip_install <package[:version] or requirements text>\nExample: /pip_install requests==2.31.0")
        return
    pkg = args[1].strip()
    try:
        bot.reply_to(m, f"🔧 Installing: {pkg} ...")
        proc = subprocess.run([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        out = proc.stdout.decode('utf-8', errors='replace')
        err = proc.stderr.decode('utf-8', errors='replace')
        resp = ""
        if out:
            resp += f"📤 STDOUT:\n{out}\n"
        if err:
            resp += f"⚠️ STDERR:\n{err}\n"
        if not resp:
            resp = "✅ Done (no output)."
        # send in chunks if too large
        if len(resp) <= 3900:
            bot.reply_to(m, resp)
        else:
            for i in range(0, len(resp), 3800):
                bot.reply_to(m, resp[i:i+3800])
    except subprocess.TimeoutExpired:
        bot.reply_to(m, "⏱ pip install timed out.")
    except Exception as e:
        bot.reply_to(m, f"❌ Error running pip: {e}")

# ---------------------------
# FALLBACK: DIRECT GUESS HANDLING
# ---------------------------
@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'), content_types=['text'])
def direct_guess_handler(m):
    """
    If a game is active in this chat, treat plain text messages as attempts to guess a word.
    This allows users to simply type the word without pressing any button.
    """
    try:
        if m.chat.id in games:
            handle_guess(m)
    except Exception:
        tb = traceback.format_exc()
        logger.exception("Error in direct_guess_handler")
        try:
            db.log_error("direct_guess_error", "Error in direct_guess_handler", tb, context=f"chat:{m.chat.id}")
        except Exception:
            pass

# ---------------------------
# LEADERBOARD IMAGE
# ---------------------------
@bot.message_handler(commands=['leaderboard_image'])
def cmd_leaderboard_image(m):
    top = db.get_top_players(10)
    if not top:
        bot.reply_to(m, "No players yet.")
        return

    try:
        w,h = 620, 80 + 36*len(top)
        img = Image.new("RGB",(w,h),"#0f1724")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",18)
        except Exception:
            font = ImageFont.load_default()

        draw.text((20,10),"🏆 TOP PLAYERS", fill="#ffd700", font=font)
        y = 50
        for i,row in enumerate(top,1):
            try:
                uid = row[0]
                name = get_display_name(uid)
                score = row[2]
                level = row[3]
                is_prem = bool(row[4])
            except Exception:
                name = str(row)
                score = 0
                level = 1
                is_prem = False
            txt = f"{i}. {name}{' 👑' if is_prem else ''} — {score} pts (L{level})"
            draw.text((20,y), txt, fill="#e6eef8", font=font)
            y += 34

        bio = io.BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)
        bio.name = "leaderboard.png"
        bot.send_photo(m.chat.id, bio)
    except Exception as e:
        bot.reply_to(m, f"Error generating image: {e}")
        tb = traceback.format_exc()
        try:
            db.log_error("leaderboard_image_error", str(e), tb)
        except Exception:
            pass

# ---------------------------
# SETTINGS: /set_config and /get_config
# ---------------------------
@bot.message_handler(commands=['set_config'])
def cmd_set_config(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(m, "Usage: /set_config <key> <value_or_json>")
        return
    key = parts[1]
    val_raw = parts[2]
    # try to parse JSON value; else store as string
    try:
        parsed = json.loads(val_raw)
        store_val = json.dumps(parsed)
    except Exception:
        store_val = val_raw
    try:
        db.set_setting(key, store_val)
        bot.reply_to(m, f"✅ Setting saved: {key}")
    except Exception as e:
        bot.reply_to(m, f"Error saving setting: {e}")

@bot.message_handler(commands=['get_config'])
def cmd_get_config(m):
    if not db.is_admin(m.from_user.id):
        return
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Usage: /get_config <key>")
        return
    key = parts[1]
    val = db.get_setting(key)
    if val is None:
        bot.reply_to(m, "Not found.")
    else:
        # try to pretty print JSON
        try:
            parsed = json.loads(val)
            bot.reply_to(m, f"{key} =\n{json.dumps(parsed, indent=2)[:3900]}")
        except Exception:
            bot.reply_to(m, f"{key} = {val}")

# ---------------------------
# FLASK (health)
# ---------------------------
@app.route('/')
def health():
    return "✅ Word Vortex Bot Running!", 200

@app.route('/health')
def health_check():
    return {"status": "ok", "bot": "word_vortex", "version": "10.5", "games": len(games)}, 200

# ---------------------------
# NOTIFICATIONS & MISC
# ---------------------------
def notify_owner(text: str):
    """
    Prefer sending notifications to NOTIFICATION_GROUP (if configured).
    If not configured or sending fails, fallback to OWNER_ID.
    """
    tried = False
    if NOTIFICATION_GROUP:
        try:
            bot.send_message(NOTIFICATION_GROUP, text)
            tried = True
        except Exception:
            logger.debug("Failed to send to NOTIFICATION_GROUP")
    if not tried and OWNER_ID:
        try:
            bot.send_message(OWNER_ID, text)
        except Exception:
            logger.debug("Failed to send to OWNER_ID")

# ---------------------------
# ADMIN SELF-TEST COMMAND
# ---------------------------
@bot.message_handler(commands=['selftest'])
def cmd_selftest(m):
    if not db.is_admin(m.from_user.id):
        return
    out = []
    out.append(f"Time: {datetime.now().isoformat()}")
    try:
        out.append(f"DB file: {db.db}")
        users = db.get_all_users()
        out.append(f"Users in DB: {len(users)}")
    except Exception as e:
        out.append(f"DB error: {e}")
    # test notification target
    try:
        if NOTIFICATION_GROUP:
            bot.send_message(NOTIFICATION_GROUP, "🔔 Self-test message from bot (this is a test).")
            out.append("Notification to group: OK")
        else:
            out.append("Notification group: Not configured")
    except Exception as e:
        out.append(f"Notification send failed: {e}")
    bot.reply_to(m, "\n".join(out))

# ---------------------------
# NEW: /cmd to list commands via message (user asked)
@bot.message_handler(commands=['cmd'])
def cmd_list_all(m):
    """
    Send the same commands list as the UI when user types /cmd
    """
    txt = ("📋 <b>COMMANDS</b>\n\n"
           "/start - Start/Help\n"
           "/new - Start a new game\n"
           "/stop - Stop current game\n"
           "/stats - Profile\n"
           "/leaderboard - Top players\n"
           "/daily - Claim daily\n"
           "/referral - Invite link\n"
           "/define <word> - Dictionary\n"
           "/leaderboard_image - Image leaderboard\n"
           "\nAdmin commands (admins only):\n"
           "/shoplist - View shop orders\n"
           "/listreviews - List reviews\n"
           "/approvereview <id> - Approve review\n"
           "/redeemlist - Pending redeems\n"
           "/selftest - Run diagnostics\n")
    try:
        bot.reply_to(m, txt)
    except Exception:
        pass

# ---------------------------
# RUN
# ---------------------------
if __name__ == "__main__":
    logger.info("🚀 Starting Word Vortex v10.5 - Fixed & Enhanced!")
    logger.info("✅ Verify Loop FIXED")
    logger.info("✅ Premium Commands Added")
    logger.info("✅ Shop = Real Money (₹)")
    logger.info("✅ Direct guesses, 10-min timer, auto-delete enabled")
    logger.info("✅ Improvements: more achievements, purchase ids, pip installer, patch show/test commands")

    def run_bot():
        # be explicit about allowed_updates to ensure callback queries are delivered
        while True:
            try:
                bot.infinity_polling(timeout=60, long_polling_timeout=60)
            except Exception:
                logger.exception("Polling stopped unexpectedly")
                time.sleep(5)

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
