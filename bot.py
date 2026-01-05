#!/usr/bin/env python3
"""
WORD VORTEX ULTIMATE v10.5 - FULL FIXED & ENHANCED

Changes made (high level):
- Fixed syntax/indentation issues.
- 8x8 games now have 6 words; 10x10 games have 8 words (no accidental 9-word bug).
- Removed hard-coded subject word lists (Chemistry/Physics/Math/JEE) — subject modes now draw random words from global ALL_WORDS.
- Redeem rules: non-premium minimum 1000 pts, premium minimum 500 pts; conversion 100 pts = ₹1.
- Referral anti-abuse: referrer rewarded only after referred user verifies and completes activity threshold (2 games OR 3 words found).
- Added referral_awards table to track awarded referrals (no deletion of existing data; schema only added).
- Timer: each game now has a 10-minute expiry (600s). After expiry a background worker ends the game automatically.
- Auto-delete: when a game ends, the bot will attempt to delete the game's image/message.
- Direct guesses: users can simply send plain text (word) in chat and the bot will detect and evaluate it when a game is active.
- Premium perks (non-blocking): VIP badge, golden theme, no cooldown, cheaper hints, partial-letter hint for premium, double XP/daily, auto-daily option stub, priority support stub, monthly VIP draw tracking.
- Feature-pack loader: owner can upload a JSON 'feature pack' (no code execution) to add theme/messages/shop-items. File is validated and saved.
- No arbitrary code execution from Telegram uploads. Safe JSON packs only.
- All DB schema changes are additive; existing logs and leaderboards preserved.

Keep reading for full file contents. Replace your bot.py with this file to apply fixes.
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
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Any

import requests
from PIL import Image, ImageDraw, ImageFont
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ---------------------------
# CONFIG
# ---------------------------
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHMVlODlQMpaoQ-PRFzVXOue-ousiWhu_Y")
if not TOKEN:
    print("❌ TELEGRAM_TOKEN not set")
    sys.exit(1)

OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
NOTIFICATION_GROUP = int(os.environ.get("NOTIFICATION_GROUP", "-1003682940543")) or OWNER_ID
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = True
SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg"

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

# Creative messages
CORRECT_EMOJIS = ['🎯', '💥', '⚡', '🔥', '✨', '💫', '🌟', '⭐', '🎊', '🎉']
WRONG_EMOJIS = ['😅', '🤔', '😬', '💭', '🎭', '🤷', '😕']

CORRECT_MESSAGES = [
    "BOOM! 💥 {name} crushed it!",
    "ON FIRE! 🔥 {name} is unstoppable!",
    "LEGENDARY! ⚡ {name} found {word}!",
    "GODLIKE! 🌟 {name} nailed it!",
    "INSANE! 💫 {name} got {word}!",
    "SAVAGE! 😎 {name} destroyed that!",
    "PERFECT! 🎯 {name} is on a roll!",
    "BEAST MODE! 🦁 {name} found {word}!",
    "KILLING IT! 💪 {name} dominates!",
    "ABSOLUTE UNIT! 🔱 {name} conquered {word}!",
]

WRONG_MESSAGES = [
    "Oops! 😅 {word} nahi hai list mein!",
    "Nope! 🤔 {word} galat hai bro!",
    "Not quite! 😬 Try something else!",
    "Hmm... 💭 {word}? Nah, not here!",
    "Nice try! 🎭 But {word} isn't it!",
    "So close! 🤷 {word} isn't the one!",
    "Bruh! 😕 {word} doesn't exist!",
]

ALREADY_FOUND_MESSAGES = [
    "Déjà vu! 👀 {word} already found!",
    "Bro... 😅 {word} toh mil chuka!",
    "Again? 🔁 Someone got {word} already!",
    "Late ho gaye! ⏰ {word} done!",
    "Duplicate! 📋 {word} checked off!",
]

FIRST_BLOOD_MESSAGES = [
    "⚡ FIRST BLOOD! {name} draws first!",
    "🩸 OPENING SHOT! {name} strikes!",
    "💥 FIRST STRIKE! {name} leads!",
    "🎯 BULLSEYE! {name} goes first!",
]

COMBO_MESSAGES = [
    "DOUBLE KILL! 🔥",
    "TRIPLE KILL! 💥",
    "ULTRA KILL! ⚡",
    "RAMPAGE! 🌟",
    "UNSTOPPABLE! 💫",
    "GODLIKE! 👑",
]

# Shop items (preserved)
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
        self.db = "word_vortex_v105_final.db"
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db, check_same_thread=False)

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
        achievements_json = user[17] if user and len(user) > 17 and user[17] else "[]"
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
        conn.close()

    def is_admin(self, user_id: int) -> bool:
        if OWNER_ID and user_id == OWNER_ID:
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
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT name, total_score, level, is_premium FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
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
            # Do NOT credit referrer yet; will be done when referred user meets activity threshold.
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
        games_played, words_found, verified = (urow[0] or 0), (urow[18] if len(urow) > 18 and urow[18] is not None else 0), (urow[19] if len(urow) > 19 else 0)
        # Note: we stored verified as column index 19 (0-based) earlier in schema; handle carefully
        # For safety, fallback if indexes differ:
        try:
            # Attempt to get verified value at expected position index 19
            verified = urow[19] if len(urow) > 19 else verified
        except Exception:
            pass

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
        last_daily, streak = row

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

    # Game logging
    def log_game_start(self, chat_id: int, mode: str, size: int) -> int:
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT INTO games (chat_id, mode, size, start_time) VALUES (?, ?, ?, ?)",
                  (chat_id, mode, size, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

db = Database()

# ---------------------------
# IMAGE RENDERER
# ---------------------------
class ImageRenderer:
    @staticmethod
    def draw_grid(grid: List[List[str]], placements: Dict, found: Dict[str,int],
                  mode="NORMAL", words_left=0, theme: str = "default", countdown_seconds: Optional[int] = None):
        """
        Draws the grid image.
        If countdown_seconds provided, displays a static countdown at time of image generation.
        theme can be used to select visual styles (e.g., 'gold', 'default').
        """
        cell = 50
        header = 100
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
            bg = "#0d0a05"
            header_fill = "#3b2b00"
        else:
            bg = "#0a1628"
            header_fill = "#2b2b2b"

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

        # Header
        draw.rectangle([0, 0, w, header], fill=header_fill)
        title = "WORD GRID (FIND WORDS)"
        try:
            bbox = draw.textbbox((0, 0), title, font=title_font)
            draw.text(((w - (bbox[2]-bbox[0]))//2, 20), title, fill="#e0e0e0", font=title_font)
        except Exception:
            draw.text((w//2 - 100, 20), title, fill="#e0e0e0", font=title_font)

        mode_text = f"⚡ {mode.upper()}"
        draw.text((pad, header-35), mode_text, fill="#ffa500" if not any_premium_found else "#ffd700", font=small_font)
        draw.text((w-220, header-35), f"Left: {words_left}", fill="#4CAF50", font=small_font)

        if countdown_seconds is not None:
            try:
                draw.text((w-120, 10), f"⏱ {countdown_seconds}s", fill="#ffdd57", font=small_font)
            except Exception:
                pass

        grid_y = header + pad

        # Grid letters
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell
                y = grid_y + r * cell
                shadow = 2
                draw.rectangle([x+shadow, y+shadow, x+cell+shadow, y+cell+shadow], fill="#000000")
                draw.rectangle([x, y, x+cell, y+cell], fill="#1e3a5f", outline="#3d5a7f", width=1)

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
                if word in found and coords:
                    finder = found.get(word)
                    is_prem = db.is_premium(finder) if finder else False

                    a, b = coords[0], coords[-1]
                    x1 = pad + a[1]*cell + cell//2
                    y1 = grid_y + a[0]*cell + cell//2
                    x2 = pad + b[1]*cell + cell//2
                    y2 = grid_y + b[0]*cell + cell//2

                    if is_prem or theme == "gold":
                        draw.line([(x1,y1),(x2,y2)], fill="#ffd700", width=4)
                        draw.line([(x1,y1),(x2,y2)], fill="#fff2a6", width=1)
                    else:
                        draw.line([(x1,y1),(x2,y2)], fill="#ffff99", width=3)
                        draw.line([(x1,y1),(x2,y2)], fill="#ffeb3b", width=1)

                    for px, py in [(x1,y1),(x2,y2)]:
                        draw.ellipse([px-5, py-5, px+5, py+5], fill="#ffeb3b" if not is_prem else "#ffd700")

        # Footer
        draw.rectangle([0, h-footer, w, h], fill="#0d1929")
        footer_text = "Made by @Ruhvaan • Word Vortex v10.5"
        if theme == "gold":
            footer_text = "VIP • " + footer_text
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
        valid = [w for w in pool if isinstance(w, str) and 4 <= len(w) <= 9]
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
                    logger.exception("Error ending expired game")
        except Exception:
            logger.exception("Expiry worker error")
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
        session.game_id = db.log_game_start(chat_id, mode, session.size)
    except Exception:
        logger.exception("Failed to log game start")

    user = db.get_user(starter_id)
    try:
        db.update_user(starter_id, games_played=(user[4] if user and len(user) > 4 else 0) + 1)
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

        # schedule expiry worker
        schedule_game_expiry(session)

        return session
    except Exception as e:
        logger.exception("Start game failed: %s", e)
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
        logger.exception("Update failed")

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
                prev_wins = winner_user[5] if winner_user and len(winner_user) > 5 else 0
                db.update_user(winner[0], wins=prev_wins + 1)
                bot.send_message(chat_id, f"🏆 <b>GAME COMPLETE!</b>\n\nWinner: {html.escape(winner_user[1])}\nScore: {winner[1]} pts\nReason: {reason}")
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
        logger.exception("Error while ending game")
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
        current_words_found = user[18] if user and len(user) > 18 and user[18] is not None else 0
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
        InlineKeyboardButton("📋 Commands", callback_data="commands")
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
    level = user[9] if user and len(user) > 9 else 1
    xp = user[10] if user and len(user) > 10 else 0
    xp_needed = level * 1000
    xp_progress = (xp / xp_needed * 100) if xp_needed > 0 else 0

    premium_badge = " 👑 PREMIUM" if db.is_premium(m.from_user.id) else " 🔓 FREE"

    txt = (f"👤 <b>PROFILE</b>\n\n"
           f"Name: {html.escape(user[1]) if user else 'Player'}{premium_badge}\n"
           f"Level: {level} 🏅\n"
           f"XP: {xp}/{xp_needed} ({xp_progress:.1f}%)\n\n"
           f"Score: {user[6] if user else 0} pts\n"
           f"Balance: {user[7] if user else 0} pts\n"
           f"Games: {user[4] if user else 0} • Wins: {user[5] if user else 0}\n"
           f"Words Found: {user[18] if user else 0}\n"
           f"Streak: {user[11] if user else 0} days 🔥")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['leaderboard','lb'])
def cmd_leaderboard(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>TOP 10 PLAYERS</b>\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, (name, score, level, is_prem) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        badge = " 👑" if is_prem else ""
        txt += f"{medal} {html.escape(name)}{badge} • Lvl {level} • {score} pts\n"
    bot.reply_to(m, txt if top else "No players yet!")

@bot.message_handler(commands=['daily'])
def cmd_daily(m):
    success, reward = db.claim_daily(m.from_user.id)
    if not success:
        bot.reply_to(m, "❌ Already claimed today!\nCome back tomorrow!")
        return
    user = db.get_user(m.from_user.id)

    # award streak achievement if applicable
    if user and user[11] >= 7:
        if db.add_achievement(m.from_user.id, "streak_master"):
            bot.send_message(m.chat.id, f"🏆 <b>Achievement Unlocked!</b>\n{ACHIEVEMENTS['streak_master']['icon']} {ACHIEVEMENTS['streak_master']['name']}")

    premium_msg = " (2x Premium)" if db.is_premium(m.from_user.id) else ""
    txt = f"🎁 <b>DAILY REWARD!</b>\n\n+{reward} pts{premium_msg}\nStreak: {user[11] if user else 0} days 🔥"
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
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
        return
    text = m.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return

    users = db.get_all_users()
    success = 0
    fail = 0
    for uid in users:
        try:
            bot.send_message(uid, text)
            success += 1
        except Exception:
            fail += 1
    bot.reply_to(m, f"📢 Broadcast complete!\nSuccess: {success}\nFailed: {fail}")

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
        bot.reply_to(m, f"✅ <b>Premium activated!</b>\n\nUser: {user[1]} (ID: {user_id})\nDays: {days}\nExpiry: {days} days from now")
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
            expiry = user[15] if user and len(user) > 15 else "unknown"
            txt = f"👑 <b>PREMIUM USER</b>\n\nName: {user[1]}\nID: {user_id}\nExpiry: {expiry}"
        else:
            txt = f"❌ <b>NOT PREMIUM</b>\n\nName: {user[1]}\nID: {user_id}"
        bot.reply_to(m, txt)
    except Exception:
        bot.reply_to(m, "Invalid user ID")

@bot.message_handler(commands=['shoplist'])
def cmd_shoplist(m):
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

    txt = "🛒 <b>SHOP PURCHASES</b>\n\n"
    for p in purchases:
        # purchase_id, user_id, item_type, price, status, date
        purchase_id, user_id, item_type, price, status, date = p
        user = db.get_user(user_id)
        txt += f"<b>ID:</b> {purchase_id}\n<b>User:</b> {user[1] if user else user_id} ({user_id})\n<b>Item:</b> {item_type}\n<b>Price:</b> ₹{price}\n<b>Status:</b> {status}\n<b>Date:</b> {date}\n\n"

    txt += "\n💡 Use /givepremium <user_id> <days> to activate"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['listreviews'])
def cmd_listreviews(m):
    if not db.is_admin(m.from_user.id):
        return
    reviews = db.get_reviews(approved_only=False)
    if not reviews:
        bot.reply_to(m, "No reviews yet!")
        return
    txt = "📝 <b>ALL REVIEWS</b>\n\n"
    for r in reviews[:50]:
        status = "✅" if r[6] else "⏳"
        txt += f"{status} ID:{r[0]} | {r[2]} | ⭐{r[4]}\n{(r[3] or '')[:240]}...\n\n"
    txt += "Use /approvereview <id> to approve or /delreview <id> to delete"
    bot.reply_to(m, txt)

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
        # request_id, user_id, username, points, amount_inr, upi_id, status, created_at, paid_at
        txt += f"ID: {r[0]}\nUser: {r[2]} ({r[1]})\nPoints: {r[3]} → ₹{r[4]}\nUPI: {r[5]}\n\n"
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
        gid, chat_id, mode, size, start_time, end_time, winner_id, winner_score = r
        txt += f"Game #{gid} • {mode} • {size}x{size}\nStart: {start_time}\nEnd: {end_time or 'ongoing'}\nWinner: {winner_id or 'N/A'} • {winner_score or 0}\n\n"
    bot.reply_to(m, txt)

@bot.message_handler(func=lambda m: True, content_types=['text','photo','sticker','document'])
def record_chat(m):
    try:
        if m.chat.type in ("group","supergroup"):
            db.add_known_chat(m.chat.id, m.chat.title or "")
    except Exception:
        pass
    # do not block other handlers

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
            balance = user[6] if user and len(user) > 6 else 0
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
        current_score = user[6] if user and len(user) > 6 else 0
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
@bot.message_handler(func=lambda m: (m.reply_to_message and isinstance(m.reply_to_message.text, str) and "Type the word you found" in m.reply_to_message.text) and m.text and not m.text.startswith('/'))
def guess_reply_handler(m):
    try:
        handle_guess(m)
    except Exception:
        logger.exception("Error handling guess reply")

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
        for i, (name, score, level, is_prem) in enumerate(top, 1):
            badge = " 👑" if is_prem else ""
            txt += f"{i}. {html.escape(name)}{badge} • {score} pts\n"
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
        txt = (f"👤 <b>PROFILE</b>\n\n"
               f"Name: {html.escape(user[1]) if user else 'User'}{premium_badge}\n"
               f"Level: {user[9] if user else 1} | XP: {user[10] if user else 0}\n"
               f"Score: {user[6] if user else 0} pts\n"
               f"Balance: {user[7] if user else 0} pts\n"
               f"Wins: {user[5] if user else 0} | Games: {user[4] if user else 0}")
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "achievements":
        user = db.get_user(uid)
        achievements = json.loads(user[17] if user and user[17] else "[]")
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
        txt = f"🎁 +{reward} pts{premium_msg}\nStreak: {user[11] if user else 0} days!"
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

        db.add_purchase(uid, item['type'], item['price'])

        notify_owner(
            f"🛒 <b>NEW SHOP ORDER</b>\n\n"
            f"User: {html.escape(c.from_user.first_name or 'User')}\n"
            f"ID: <code>{uid}</code>\n"
            f"Item: {item['name']}\n"
            f"Price: ₹{item['price']}\n\n"
            f"Use /shoplist to view all orders"
        )

        bot.send_message(uid, txt)
        bot.answer_callback_query(c.id, f"Order details sent!")
        return

    if data == "redeem_menu":
        user = db.get_user(uid)
        balance = user[6] if user and len(user) > 6 else 0
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
                txt = f"⭐ {r[4]} • {r[2]}\n{(r[3] or '')[:600]}\n"
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
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Commands sent to PM!")
        except Exception:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id, "Commands sent!")
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
        if (user[7] if user and len(user) > 7 else 0) < cost:
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

        db.update_user(uid, hint_balance=(user[7] if user and len(user) > 7 else 0) - cost)
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
            name = db.get_user(u)[1] if db.get_user(u) else str(u)
            txt += f"{i}. {html.escape(name)} - {pts} pts\n"
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
# FEATURE PACK UPLOAD (owner-only, safe JSON)
# ---------------------------
@bot.message_handler(commands=['upload_feature_pack'])
def cmd_upload_feature_pack(m):
    """
    Owner can upload a JSON file (as document) with theme/messages/shop entries.
    Example: {"name":"summer","themes":{"gold":{"footer":"VIP • Summer"}}}
    This is safe: only JSON content is accepted, no code executed.
    """
    if not (OWNER_ID and m.from_user.id == OWNER_ID):
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
        del user_states[uid]
        return
    if doc.file_size > 200000:
        bot.reply_to(m, "File too large. Max 200 KB.")
        del user_states[uid]
        return
    try:
        f = bot.download_file(bot.get_file(doc.file_id).file_path)
        content = f.decode('utf-8')
        parsed = json.loads(content)
        # basic validation: must be dict
        if not isinstance(parsed, dict):
            bot.reply_to(m, "Invalid JSON structure.")
            del user_states[uid]
            return
        # save to DB and in-memory
        db.save_feature_pack(doc.file_name, content)
        global feature_pack
        feature_pack = parsed
        bot.reply_to(m, "✅ Feature pack uploaded and applied (non-code features).")
    except Exception as e:
        bot.reply_to(m, f"❌ Failed to load: {e}")
    finally:
        if uid in user_states:
            del user_states[uid]

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
        logger.exception("Error in direct_guess_handler")

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
# RUN
# ---------------------------
if __name__ == "__main__":
    logger.info("🚀 Starting Word Vortex v10.5 - Fixed & Enhanced!")
    logger.info("✅ Verify Loop FIXED")
    logger.info("✅ Premium Commands Added")
    logger.info("✅ Shop = Real Money (₹)")
    logger.info("✅ Direct guesses, 10-min timer, auto-delete enabled")

    def run_bot():
        bot.infinity_polling(timeout=60, long_polling_timeout=60)

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
