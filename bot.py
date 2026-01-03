#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  WORD VORTEX ULTIMATE v10.5 - COMPLETE + NEW FEATURES            ║
║  ✅ How to Play guide                                             ║
║  ✅ Force channel join (mandatory)                                ║
║  ✅ Owner notifications (start, verify, group)                    ║
║  ✅ /define word - Dictionary feature                             ║
║  ✅ Enhanced scoring system                                       ║
║  ✅ Per-feature help                                              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os, sys, time, html, io, random, logging, sqlite3, json, threading
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
import requests
from PIL import Image, ImageDraw, ImageFont
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHZzgByv218uShEzAHBtGjpCJ8_cedldVk")
if not TOKEN:
    print("❌ TELEGRAM_TOKEN not set")
    sys.exit(1)

OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
NOTIFICATION_GROUP = int(os.environ.get("NOTIFICATION_GROUP", "-1003682940543")) or OWNER_ID  # Group for notifications
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = True  # Always force join
SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG_URL = "https://image2url.com/r2/default/images/1767379923930-426fd806-ba8a-41fd-b181-56fa31150621.jpg"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enhanced Game Constants
FIRST_BLOOD = 15  # Increased
NORMAL_PTS = 3    # Increased
FINISHER = 10     # Increased
HINT_COST = 50
COOLDOWN = 2
DAILY_REWARD = 100
STREAK_BONUS = 20
REFERRAL_BONUS = 200
COMBO_BONUS = 5   # Bonus for consecutive words
SPEED_BONUS = 5   # Bonus for quick finds
BAD_WORDS = {"SEX","PORN","NUDE","XXX","DICK","COCK","PUSSY","FUCK","SHIT","BITCH","ASS","HENTAI","BOOBS"}

# Word Pools
PHYSICS_WORDS = ["FORCE","ENERGY","MOMENTUM","VELOCITY","WAVE","PHOTON","GRAVITY","ATOM","QUANTUM","ELECTRON"]
CHEMISTRY_WORDS = ["MOLECULE","REACTION","BOND","ION","ACID","BASE","SALT","ELECTRON","PROTON","NEUTRON"]
MATH_WORDS = ["INTEGRAL","DERIVATIVE","MATRIX","VECTOR","CALCULUS","LIMIT","ALGORITHM","THEOREM","PROOF"]
JEE_WORDS = ["KINEMATICS","THERMODYNAMICS","DIFFERENTIAL","ELECTROSTATICS","OPTICS","MECHANICS"]

# Achievements Data
ACHIEVEMENTS = {
    "first_win": {"name": "First Victory", "icon": "🥇", "desc": "Win your first game", "reward": 50},
    "word_finder": {"name": "Word Finder", "icon": "📚", "desc": "Find 50 words", "reward": 100},
    "speed_demon": {"name": "Speed Demon", "icon": "⚡", "desc": "Find word in 5 seconds", "reward": 75},
    "streak_master": {"name": "Streak Master", "icon": "🔥", "desc": "7-day login streak", "reward": 150},
    "millionaire": {"name": "Millionaire", "icon": "💰", "desc": "Earn 10000 points", "reward": 500},
}

# Shop Items
SHOP_ITEMS = {
    "hints_5": {"name": "5 Hints Pack", "price": 200, "type": "hints", "value": 5},
    "hints_20": {"name": "20 Hints Pack", "price": 700, "type": "hints", "value": 20},
    "xp_boost": {"name": "XP Booster (2x)", "price": 500, "type": "boost", "value": 2},
    "premium_1d": {"name": "Premium 1 Day", "price": 300, "type": "premium", "value": 1},
    "premium_7d": {"name": "Premium 7 Days", "price": 1500, "type": "premium", "value": 7},
}

# Per-Feature Help
FEATURE_HELP = {
    "play": """🎮 <b>HOW TO PLAY</b>

1️⃣ Click "🎮 Play" button
2️⃣ Select game mode (Normal/Hard/Chemistry/Physics/Math/JEE)
3️⃣ Grid image will appear with hidden words
4️⃣ Find words in the grid (horizontal, vertical, diagonal)
5️⃣ Click "🔍 Found It!" and type the word
6️⃣ Earn points for each word found!

<b>🏆 SCORING:</b>
🥇 First Blood: +15 pts (first word)
⚡ Normal Word: +3 pts
🎯 Finisher: +10 pts (last word)
⚡ Speed Bonus: +5 pts (find in 10 sec)
🔥 Combo Bonus: +5 pts (consecutive finds)

<b>🎯 MODES:</b>
⚡ Normal - 8x8 grid, 6 words
🔥 Hard - 10x10 grid, 8 words
🧪 Chemistry - Chemistry terms
⚛️ Physics - Physics vocabulary
📐 Math - Mathematics terms
🎓 JEE - JEE preparation words""",

    "achievements": """🏅 <b>ACHIEVEMENTS GUIDE</b>

Unlock badges by completing challenges!

<b>Available Achievements:</b>
🥇 <b>First Victory</b> - Win your first game (+50 pts)
📚 <b>Word Finder</b> - Find 50 total words (+100 pts)
⚡ <b>Speed Demon</b> - Find a word in 5 seconds (+75 pts)
🔥 <b>Streak Master</b> - Maintain 7-day login streak (+150 pts)
💰 <b>Millionaire</b> - Earn 10,000 total points (+500 pts)

Achievements unlock automatically when you reach the milestone!""",

    "shop": """🛒 <b>SHOP GUIDE</b>

Buy power-ups and boosters!

<b>Available Items:</b>
💡 5 Hints Pack - 200 pts
💡 20 Hints Pack - 700 pts
⚡ XP Booster 2x - 500 pts
👑 Premium 1 Day - 300 pts
👑 Premium 7 Days - 1500 pts

<b>How to Buy:</b>
1. Click "🛒 Shop" button
2. Select item
3. Confirm purchase
4. Item delivered instantly!""",

    "redeem": """💰 <b>REDEEM GUIDE</b>

Cash out your points to real money!

<b>Conversion Rate:</b>
10 points = ₹1

<b>Minimum:</b> 500 points (₹50)

<b>How to Redeem:</b>
1. Click "💰 Redeem" button
2. Click "🚀 Start Redeem"
3. Enter points (min 500)
4. Enter your UPI ID
5. Wait 24-48 hours for payment

<b>Supported UPI:</b>
• PayTM • PhonePe • GooglePay
• Any bank UPI""",

    "daily": """🎁 <b>DAILY REWARD GUIDE</b>

Claim free points every day!

<b>Base Reward:</b> 100 pts

<b>Streak Bonus:</b>
Day 1: +100 pts
Day 2: +120 pts
Day 3: +140 pts
...
Day 7+: +240 pts

<b>How to Claim:</b>
Click "🎁 Daily" button once per day

Keep your streak alive for bigger rewards!""",

    "referral": """👥 <b>REFERRAL GUIDE</b>

Invite friends and earn!

<b>Reward:</b> 200 pts per friend

<b>How it Works:</b>
1. Click "👥 Invite" button
2. Copy your unique link
3. Share with friends
4. When they join, you get 200 pts!

No duplicate rewards - each friend counted once.""",
}

# User states for multi-step interactions
user_states = {}

# ═══════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.db = "word_vortex_v105.db"
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db, check_same_thread=False)

    def _init(self):
        conn = self._conn()
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, name TEXT, username TEXT,
            join_date TEXT, games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0, total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100, gems INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0, last_daily TEXT,
            referrer_id INTEGER, is_premium INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0, achievements TEXT DEFAULT '[]',
            words_found INTEGER DEFAULT 0, verified INTEGER DEFAULT 0
        )""")

        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")

        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, text TEXT,
            rating INTEGER, created_at TEXT, approved INTEGER DEFAULT 0
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS redeem_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, points INTEGER,
            amount_inr INTEGER, upi_id TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, paid_at TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS referrals (
            referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER, referred_id INTEGER,
            created_at TEXT, UNIQUE(referrer_id, referred_id)
        )""")

        conn.commit()
        conn.close()

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

    def update_user(self, user_id: int, **kwargs):
        conn = self._conn()
        c = conn.cursor()
        for key, val in kwargs.items():
            c.execute(f"UPDATE users SET {key} = ? WHERE user_id=?", (val, user_id))
        conn.commit()
        conn.close()

    def add_score(self, user_id: int, points: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", 
                 (points, points, user_id))
        conn.commit()
        conn.close()

    def add_xp(self, user_id: int, xp: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT xp, level FROM users WHERE user_id=?", (user_id,))
        curr_xp, level = c.fetchone()
        new_xp = curr_xp + xp
        new_level = level
        if new_xp >= level * 1000:
            new_level = level + 1
            try:
                bot.send_message(user_id, f"🎉 <b>LEVEL UP!</b> You're now level {new_level}!")
            except:
                pass
        c.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (new_xp, new_level, user_id))
        conn.commit()
        conn.close()

    def add_achievement(self, user_id: int, ach_id: str) -> bool:
        """Returns True if new achievement"""
        user = self.get_user(user_id)
        achievements = json.loads(user[16] if user[16] else "[]")
        if ach_id in achievements:
            return False
        achievements.append(ach_id)
        self.update_user(user_id, achievements=json.dumps(achievements))
        return True

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
        c.execute("SELECT name, total_score, level FROM users ORDER BY total_score DESC LIMIT ?", (limit,))
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

    def approve_review(self, review_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE reviews SET approved=1 WHERE review_id=?", (review_id,))
        conn.commit()
        conn.close()

    def add_redeem(self, user_id: int, username: str, points: int, upi: str):
        conn = self._conn()
        c = conn.cursor()
        amount = points // 10
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

    def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        conn = self._conn()
        c = conn.cursor()
        try:
            c.execute("""INSERT INTO referrals (referrer_id, referred_id, created_at)
                        VALUES (?, ?, ?)""",
                     (referrer_id, referred_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?",
                     (REFERRAL_BONUS, referrer_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def claim_daily(self, user_id: int) -> Tuple[bool, int]:
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT last_daily, streak FROM users WHERE user_id=?", (user_id,))
        last_daily, streak = c.fetchone()

        today = datetime.now().strftime("%Y-%m-%d")
        if last_daily == today:
            conn.close()
            return False, 0

        if last_daily:
            last_date = datetime.strptime(last_daily, "%Y-%m-%d")
            days_diff = (datetime.now() - last_date).days
            if days_diff == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        reward = DAILY_REWARD + (streak * STREAK_BONUS)
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

db = Database()

# ═══════════════════════════════════════════════════════════════════
# NOTIFICATION SYSTEM
# ═══════════════════════════════════════════════════════════════════
def notify_owner(message: str):
    """Send notification to owner/notification group"""
    if NOTIFICATION_GROUP:
        try:
            bot.send_message(NOTIFICATION_GROUP, message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

# ═══════════════════════════════════════════════════════════════════
# WORD SOURCE
# ═══════════════════════════════════════════════════════════════════
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
    except:
        pass
    ALL_WORDS = ["PYTHON","JAVA","ROBOT","SPACE","GALAXY","QUANTUM","ENERGY","MATRIX","VECTOR","DIGITAL"]
    logger.info("⚠️ Using fallback wordlist")

load_words()

# ═══════════════════════════════════════════════════════════════════
# IMAGE RENDERER
# ═══════════════════════════════════════════════════════════════════
class ImageRenderer:
    @staticmethod
    def draw_grid(grid: List[List[str]], placements: Dict, found: set,
                  mode="NORMAL", words_left=0):
        cell = 50
        header = 90
        footer = 70
        pad = 20
        rows = len(grid)
        cols = len(grid[0]) if rows else 0

        w = cols * cell + pad * 2
        h = header + footer + rows * cell + pad * 2

        img = Image.new("RGB", (w, h), "#0a1628")
        draw = ImageDraw.Draw(img)

        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            if not os.path.exists(font_path):
                raise Exception("Font not found")
            title_font = ImageFont.truetype(font_path, 32)
            letter_font = ImageFont.truetype(font_path, 28)
            small_font = ImageFont.truetype(font_path, 16)
        except:
            title_font = ImageFont.load_default()
            letter_font = ImageFont.load_default()
            small_font = ImageFont.load_default()

        # Header
        draw.rectangle([0, 0, w, header], fill="#1a2942")
        title = "WORD GRID (FIND WORDS)"
        try:
            bbox = draw.textbbox((0, 0), title, font=title_font)
            draw.text(((w - (bbox[2]-bbox[0]))//2, 25), title, fill="#e0e0e0", font=title_font)
        except:
            draw.text((w//2 - 100, 25), title, fill="#e0e0e0", font=title_font)

        mode_text = f"⚡ {mode.upper()}"
        draw.text((pad, header-30), mode_text, fill="#ffa500", font=small_font)
        draw.text((w-150, header-30), f"Left: {words_left}", fill="#4CAF50", font=small_font)

        grid_y = header + pad

        # Grid
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell
                y = grid_y + r * cell

                shadow = 3
                draw.rectangle([x+shadow, y+shadow, x+cell+shadow, y+cell+shadow], fill="#000000")
                draw.rectangle([x, y, x+cell, y+cell], fill="#1e3a5f", outline="#3d5a7f", width=2)

                ch = grid[r][c]
                try:
                    bbox = draw.textbbox((0, 0), ch, font=letter_font)
                    tx = x + (cell - (bbox[2]-bbox[0]))//2
                    ty = y + (cell - (bbox[3]-bbox[1]))//2
                except:
                    tx = x + cell//2 - 8
                    ty = y + cell//2 - 10
                draw.text((tx, ty), ch, fill="#d0d0d0", font=letter_font)

        # Yellow neon lines
        if placements and found:
            for word, coords in placements.items():
                if word in found and coords:
                    a, b = coords[0], coords[-1]
                    x1 = pad + a[1]*cell + cell//2
                    y1 = grid_y + a[0]*cell + cell//2
                    x2 = pad + b[1]*cell + cell//2
                    y2 = grid_y + b[0]*cell + cell//2

                    shadow = 4
                    draw.line([(x1+shadow,y1+shadow), (x2+shadow,y2+shadow)], fill="#1a1a00", width=12)
                    draw.line([(x1,y1), (x2,y2)], fill="#ffff00", width=9)
                    draw.line([(x1,y1), (x2,y2)], fill="#ffff66", width=5)
                    draw.line([(x1,y1), (x2,y2)], fill="#ffffcc", width=2)

                    for px, py in [(x1,y1), (x2,y2)]:
                        draw.ellipse([px-10+shadow, py-10+shadow, px+10+shadow, py+10+shadow], fill="#1a1a00")
                        draw.ellipse([px-10, py-10, px+10, py+10], fill="#ffff00")
                        draw.ellipse([px-6, py-6, px+6, py+6], fill="#ffff66")
                        draw.ellipse([px-3, py-3, px+3, py+3], fill="#ffffff")

        # Footer
        draw.rectangle([0, h-footer, w, h], fill="#0d1929")
        draw.text((w//2 - 100, h-footer+25), "Made by @Ruhvaan • Word Vortex v10.5",
                 fill="#7f8c8d", font=small_font)

        bio = io.BytesIO()
        img.save(bio, "PNG", quality=95)
        bio.seek(0)
        bio.name = "grid.png"
        return bio

# ═══════════════════════════════════════════════════════════════════
# GAME SESSION
# ═══════════════════════════════════════════════════════════════════
games = {}

class GameSession:
    def __init__(self, chat_id: int, mode="normal", is_hard=False, custom_words=None):
        self.chat_id = chat_id
        self.mode = mode
        self.is_hard = is_hard
        self.size = 10 if is_hard else 8
        self.word_count = 8 if is_hard else 6
        self.start_time = time.time()
        self.grid: List[List[str]] = []
        self.placements: Dict[str, List[Tuple[int,int]]] = {}
        self.words: List[str] = []
        self.found: set = set()
        self.players: Dict[int, int] = {}
        self.last_guess: Dict[int, float] = {}
        self.last_find_time: Dict[int, float] = {}
        self.combo_count: Dict[int, int] = {}
        self.message_id: Optional[int] = None

        word_pool = custom_words if custom_words else ALL_WORDS
        self._generate(word_pool)

    def _generate(self, pool):
        valid = [w for w in pool if 4 <= len(w) <= 9]
        if len(valid) < self.word_count:
            valid = valid * 3
        self.words = random.sample(valid, min(self.word_count, len(valid)))

        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]

        for word in sorted(self.words, key=len, reverse=True):
            for _ in range(500):
                r, c = random.randint(0, self.size-1), random.randint(0, self.size-1)
                dr, dc = random.choice(dirs)

                if self._can_place(r, c, dr, dc, word):
                    coords = []
                    for i, ch in enumerate(word):
                        rr, cc = r + i*dr, c + i*dc
                        self.grid[rr][cc] = ch
                        coords.append((rr, cc))
                    self.placements[word] = coords
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
                masked = w[0] + "•"*(len(w)-2) + w[-1] if len(w)>2 else w[0]+"•"
                lines.append(f"❌ {masked} ({len(w)})")
        return "\n".join(lines)

def start_game(chat_id, starter_id, mode="normal", is_hard=False, custom_words=None):
    if chat_id in games:
        try:
            bot.send_message(chat_id, "⚠️ Game already active! Use /stop to end it.")
        except:
            pass
        return None

    session = GameSession(chat_id, mode, is_hard, custom_words)
    games[chat_id] = session

    user = db.get_user(starter_id)
    db.update_user(starter_id, games_played=user[4]+1)

    try:
        img = ImageRenderer.draw_grid(
            session.grid, session.placements, session.found,
            mode, len(session.words)
        )

        caption = (f"🎮 <b>GAME STARTED!</b>\n"
                  f"Mode: <b>{mode.upper()}</b>\n"
                  f"Words: {len(session.words)}\n\n"
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
        return session
    except Exception as e:
        logger.exception("Start game failed")
        del games[chat_id]
        try:
            bot.send_message(chat_id, f"❌ Failed to start game: {str(e)}")
        except:
            pass
        return None

def update_game(chat_id):
    if chat_id not in games:
        return
    session = games[chat_id]

    try:
        img = ImageRenderer.draw_grid(
            session.grid, session.placements, session.found,
            session.mode, len(session.words)-len(session.found)
        )

        caption = (f"🎮 <b>WORD GRID</b>\n"
                  f"Found: {len(session.found)}/{len(session.words)}\n\n"
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
            except:
                msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
                session.message_id = msg.message_id
        else:
            msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
            session.message_id = msg.message_id

    except Exception as e:
        logger.exception("Update failed")

def handle_guess(msg):
    cid = msg.chat.id
    if cid not in games:
        return

    session = games[cid]
    uid = msg.from_user.id
    name = msg.from_user.first_name or "Player"
    word = (msg.text or "").strip().upper()

    if not word:
        return

    last = session.last_guess.get(uid, 0)
    if time.time() - last < COOLDOWN:
        bot.reply_to(msg, f"⏳ Wait {COOLDOWN}s")
        return
    session.last_guess[uid] = time.time()

    if word not in session.words:
        bot.reply_to(msg, f"❌ '{word}' not in list!")
        session.combo_count[uid] = 0  # Reset combo
        return

    if word in session.found:
        bot.reply_to(msg, f"✅ Already found!")
        return

    session.found.add(word)

    # Calculate points with bonuses
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

    # Speed bonus
    find_time = time.time()
    last_find = session.last_find_time.get(uid, session.start_time)
    if find_time - last_find < 10:
        pts += SPEED_BONUS
        bonuses.append("⚡SPEED +5")
    session.last_find_time[uid] = find_time

    # Combo bonus
    session.combo_count[uid] = session.combo_count.get(uid, 0) + 1
    if session.combo_count[uid] >= 2:
        pts += COMBO_BONUS
        bonuses.append(f"🔥COMBO x{session.combo_count[uid]}")

    session.players[uid] = session.players.get(uid, 0) + pts
    db.add_score(uid, pts)
    db.add_xp(uid, pts * 10)

    # Update words found
    user = db.get_user(uid)
    db.update_user(uid, words_found=user[17]+1)

    # Check achievements
    if user[5] == 0 and len(session.found) == len(session.words):
        if db.add_achievement(uid, "first_win"):
            bot.send_message(cid, f"🏆 <b>Achievement Unlocked!</b>\n{ACHIEVEMENTS['first_win']['icon']} {ACHIEVEMENTS['first_win']['name']}")

    bonus_text = " • " + " • ".join(bonuses) if bonuses else ""
    bot.send_message(cid, f"🎉 <b>{html.escape(name)}</b> found <code>{word}</code>!\n+{pts} pts{bonus_text}")

    update_game(cid)

    if len(session.found) == len(session.words):
        winner = max(session.players.items(), key=lambda x: x[1])
        winner_user = db.get_user(winner[0])
        db.update_user(winner[0], wins=winner_user[5]+1)

        bot.send_message(cid, f"🏆 <b>GAME COMPLETE!</b>\n\nWinner: {html.escape(winner_user[1])}\nScore: {winner[1]} pts")
        del games[cid]

# ═══════════════════════════════════════════════════════════════════
# CHANNEL JOIN CHECK
# ═══════════════════════════════════════════════════════════════════
def is_subscribed(user_id: int) -> bool:
    if not CHANNEL_USERNAME:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ("creator", "administrator", "member")
    except:
        return False

def must_join_menu():
    kb = InlineKeyboardMarkup()
    if CHANNEL_USERNAME:
        kb.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"))
    kb.add(InlineKeyboardButton("✅ Verify Membership", callback_data="verify"))
    return kb

# ═══════════════════════════════════════════════════════════════════
# MENUS
# ═══════════════════════════════════════════════════════════════════

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
        InlineKeyboardButton("ℹ️ Help", callback_data="help_menu")
    )
    kb.row(InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP))

    return kb

def help_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("🎮 Play", callback_data="help_play"),
        InlineKeyboardButton("🏅 Achievements", callback_data="help_achievements")
    )
    kb.row(
        InlineKeyboardButton("🛒 Shop", callback_data="help_shop"),
        InlineKeyboardButton("💰 Redeem", callback_data="help_redeem")
    )
    kb.row(
        InlineKeyboardButton("🎁 Daily", callback_data="help_daily"),
        InlineKeyboardButton("👥 Referral", callback_data="help_referral")
    )
    kb.row(InlineKeyboardButton("« Back", callback_data="back_main"))
    return kb

def game_modes_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("⚡ Normal (8x8)", callback_data="play_normal"),
        InlineKeyboardButton("🔥 Hard (10x10)", callback_data="play_hard")
    )
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
    for item_id, item in SHOP_ITEMS.items():
        kb.add(InlineKeyboardButton(
            f"{item['name']} - {item['price']} pts",
            callback_data=f"shop_buy_{item_id}"
        ))
    kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
    return kb

# ═══════════════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════════════

@bot.message_handler(commands=['start','help'])
def cmd_start(m):
    name = m.from_user.first_name or "Player"
    username = m.from_user.username or ""
    uid = m.from_user.id

    # Check channel join first
    if not is_subscribed(uid):
        txt = (f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n"
               f"⚠️ <b>You must join our channel to use this bot!</b>\n\n"
               f"1️⃣ Click 'Join Channel' button\n"
               f"2️⃣ Join the channel\n"
               f"3️⃣ Click 'Verify Membership'")
        try:
            bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=must_join_menu())
        except:
            bot.send_message(m.chat.id, txt, reply_markup=must_join_menu())
        return

    # Handle referral
    if ' ' in m.text:
        ref_code = m.text.split()[1]
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                if referrer_id != uid:
                    success = db.add_referral(referrer_id, uid)
                    if success:
                        db.update_user(uid, referrer_id=referrer_id)
                        try:
                            bot.send_message(referrer_id,
                                f"🎉 +{REFERRAL_BONUS} pts!\n{name} joined using your link!")
                        except:
                            pass
            except:
                pass

    db.get_user(uid, name, username)

    # Send notification to owner
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
           f"• Shop with power-ups\n"
           f"• Real money rewards\n"
           f"• Dictionary (/define word)\n\n"
           f"Tap a button to start!")

    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=main_menu())
    except:
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
    start_game(m.chat.id, m.from_user.id)

@bot.message_handler(commands=['stop','end'])
def cmd_stop(m):
    if m.chat.id in games:
        del games[m.chat.id]
        bot.reply_to(m, "🛑 Game stopped!")
    else:
        bot.reply_to(m, "❌ No active game!")

@bot.message_handler(commands=['stats','profile'])
def cmd_stats(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name)
    xp_needed = user[9] * 1000
    xp_progress = (user[10] / xp_needed * 100) if xp_needed > 0 else 0

    txt = (f"👤 <b>PROFILE</b>\n\n"
           f"Name: {html.escape(user[1])}\n"
           f"Level: {user[9]} 🏅\n"
           f"XP: {user[10]}/{xp_needed} ({xp_progress:.1f}%)\n\n"
           f"Score: {user[6]} pts\n"
           f"Balance: {user[7]} pts\n"
           f"Games: {user[4]} • Wins: {user[5]}\n"
           f"Words Found: {user[17]}\n"
           f"Streak: {user[11]} days 🔥")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['leaderboard','lb'])
def cmd_leaderboard(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>TOP 10 PLAYERS</b>\n\n"
    medals = ["🥇","🥈","🥉"]
    for i, (name, score, level) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        txt += f"{medal} {html.escape(name)} • Lvl {level} • {score} pts\n"
    bot.reply_to(m, txt if top else "No players yet!")

@bot.message_handler(commands=['daily'])
def cmd_daily(m):
    success, reward = db.claim_daily(m.from_user.id)
    if not success:
        bot.reply_to(m, "❌ Already claimed today!\nCome back tomorrow!")
        return
    user = db.get_user(m.from_user.id)

    # Check streak achievement
    if user[11] >= 7:
        if db.add_achievement(m.from_user.id, "streak_master"):
            bot.send_message(m.chat.id, f"🏆 <b>Achievement Unlocked!</b>\n{ACHIEVEMENTS['streak_master']['icon']} {ACHIEVEMENTS['streak_master']['name']}")

    txt = f"🎁 <b>DAILY REWARD!</b>\n\n+{reward} pts\nStreak: {user[11]} days 🔥"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['referral','invite'])
def cmd_referral(m):
    uid = m.from_user.id
    ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
    txt = (f"👥 <b>INVITE & EARN</b>\n\n"
           f"Earn {REFERRAL_BONUS} pts per friend!\n\n"
           f"Your link:\n<code>{ref_link}</code>")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}"))
    bot.reply_to(m, txt, reply_markup=kb)

# Admin Commands
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
    except:
        bot.reply_to(m, "Invalid user ID")

@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(m):
    if not db.is_admin(m.from_user.id):
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Usage: /addpoints <user_id> <points>")
        return
    try:
        user_id = int(args[1])
        points = int(args[2])
        db.add_score(user_id, points)
        bot.reply_to(m, f"✅ Added {points} points to user {user_id}")
        try:
            bot.send_message(user_id, f"🎁 You received {points} points from admin!")
        except:
            pass
    except:
        bot.reply_to(m, "Invalid input")

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
        except:
            fail += 1
    bot.reply_to(m, f"📢 Broadcast complete!\nSuccess: {success}\nFailed: {fail}")

@bot.message_handler(commands=['listreviews'])
def cmd_listreviews(m):
    if not db.is_admin(m.from_user.id):
        return
    reviews = db.get_reviews(approved_only=False)
    if not reviews:
        bot.reply_to(m, "No reviews yet!")
        return
    txt = "📝 <b>ALL REVIEWS</b>\n\n"
    for r in reviews[:10]:
        status = "✅" if r[5] else "⏳"
        txt += f"{status} ID:{r[0]} | {r[2]} | ⭐{r[3]}\n{r[4][:50]}...\n\n"
    txt += "Use /approvereview <id> to approve"
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
    except:
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
    except:
        bot.reply_to(m, "Invalid ID")

# Handle text messages for multi-step interactions
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
        except:
            bot.reply_to(m, "❌ Please send rating 1-5")

    elif state['type'] == 'review_text':
        text = m.text
        rating = state['rating']
        db.add_review(uid, m.from_user.first_name or "User", text, rating)
        del user_states[uid]

        # Notify owner
        notify_owner(
            f"⭐ <b>NEW REVIEW</b>\n\n"
            f"User: {html.escape(m.from_user.first_name or 'User')}\n"
            f"Rating: {'⭐' * rating}\n"
            f"Review: {html.escape(text)}\n\n"
            f"Use /approvereview to approve"
        )

        bot.reply_to(m, "⭐ Thank you for your review! Owner will see it.")

    elif state['type'] == 'redeem_points':
        try:
            points = int(m.text)
            if points < 500:
                bot.reply_to(m, "❌ Minimum 500 points!")
                del user_states[uid]
                return
            user = db.get_user(uid)
            if user[6] < points:
                bot.reply_to(m, f"❌ You only have {user[6]} points!")
                del user_states[uid]
                return
            user_states[uid] = {'type': 'redeem_upi', 'points': points}
            bot.reply_to(m, "💳 Now send your UPI ID:\nExample: yourname@paytm")
        except:
            bot.reply_to(m, "❌ Invalid number!")
            del user_states[uid]

    elif state['type'] == 'redeem_upi':
        upi = m.text
        points = state['points']
        user = db.get_user(uid)
        db.add_redeem(uid, m.from_user.first_name or "User", points, upi)
        db.update_user(uid, total_score=user[6]-points)
        del user_states[uid]

        # Notify owner
        notify_owner(
            f"💰 <b>NEW REDEEM REQUEST</b>\n\n"
            f"User: {html.escape(m.from_user.first_name or 'User')}\n"
            f"ID: <code>{uid}</code>\n"
            f"Points: {points}\n"
            f"Amount: ₹{points//10}\n"
            f"UPI: <code>{upi}</code>\n\n"
            f"Use /redeemlist to see all"
        )

        bot.reply_to(m, f"✅ Redeem request submitted!\n\nPoints: {points}\nAmount: ₹{points//10}\nUPI: {upi}\n\nOwner will process within 24-48 hours.")

# ═══════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data

    if data == "verify":
        if is_subscribed(uid):
            db.update_user(uid, verified=1)

            # Send notification
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
            except:
                pass
            # Resend start
            cmd_start(c.message)
        else:
            bot.answer_callback_query(c.id, "❌ Please join channel first!", show_alert=True)
        return

    # Check subscription for other actions
    if not is_subscribed(uid) and data not in ["verify"]:
        bot.answer_callback_query(c.id, "⚠️ Join channel first!", show_alert=True)
        return

    if data == "play":
        try:
            bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=game_modes_menu())
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(uid, "🎮 Select mode:", reply_markup=game_modes_menu())
            bot.answer_callback_query(c.id, "Sent to PM!")
        return

    if data == "howtoplay":
        try:
            bot.send_message(uid, FEATURE_HELP['play'])
            bot.answer_callback_query(c.id, "Sent to PM!")
        except:
            bot.send_message(cid, FEATURE_HELP['play'])
            bot.answer_callback_query(c.id)
        return

    if data == "help_menu":
        try:
            bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=help_menu())
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(uid, "ℹ️ <b>SELECT FEATURE FOR HELP:</b>", reply_markup=help_menu())
            bot.answer_callback_query(c.id)
        return

    if data.startswith("help_"):
        feature = data.replace("help_", "")
        help_text = FEATURE_HELP.get(feature, "No help available")
        try:
            bot.send_message(uid, help_text)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, help_text)
            bot.answer_callback_query(c.id)
        return

    if data == "back_main":
        try:
            bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=main_menu())
            bot.answer_callback_query(c.id)
        except:
            pass
        return

    if data == "leaderboard":
        top = db.get_top_players(10)
        txt = "🏆 <b>TOP 10</b>\n\n"
        for i, (name, score, level) in enumerate(top, 1):
            txt += f"{i}. {html.escape(name)} • {score} pts\n"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "profile":
        user = db.get_user(uid)
        txt = (f"👤 <b>PROFILE</b>\n\n"
               f"Name: {html.escape(user[1])}\n"
               f"Level: {user[9]} | XP: {user[10]}\n"
               f"Score: {user[6]} pts\n"
               f"Balance: {user[7]} pts\n"
               f"Wins: {user[5]} | Games: {user[4]}")
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "achievements":
        user = db.get_user(uid)
        achievements = json.loads(user[16] if user[16] else "[]")
        txt = "🏅 <b>ACHIEVEMENTS</b>\n\n"
        for ach_id, ach in ACHIEVEMENTS.items():
            status = "✅" if ach_id in achievements else "🔒"
            txt += f"{status} {ach['icon']} <b>{ach['name']}</b>\n{ach['desc']}\nReward: {ach['reward']} pts\n\n"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "daily":
        success, reward = db.claim_daily(uid)
        if not success:
            bot.answer_callback_query(c.id, "Already claimed!", show_alert=True)
            return
        user = db.get_user(uid)
        txt = f"🎁 +{reward} pts\nStreak: {user[11]} days!"
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    if data == "shop":
        txt = "🛒 <b>SHOP</b>\n\nSelect item to buy:"
        try:
            bot.send_message(uid, txt, reply_markup=shop_menu())
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt, reply_markup=shop_menu())
            bot.answer_callback_query(c.id)
        return

    if data.startswith("shop_buy_"):
        item_id = data.replace("shop_buy_", "")
        item = SHOP_ITEMS.get(item_id)
        if not item:
            bot.answer_callback_query(c.id, "Invalid item!")
            return

        user = db.get_user(uid)
        if user[6] < item['price']:
            bot.answer_callback_query(c.id, f"Need {item['price']} pts! You have {user[6]}", show_alert=True)
            return

        # Process purchase
        db.update_user(uid, total_score=user[6]-item['price'])
        if item['type'] == 'hints':
            db.update_user(uid, hint_balance=user[7]+item['value'])

        bot.answer_callback_query(c.id, f"✅ Purchased {item['name']}!", show_alert=True)
        bot.send_message(uid, f"🛒 <b>Purchase Complete!</b>\n\n{item['name']}\n-{item['price']} pts")
        return

    if data == "redeem_menu":
        user = db.get_user(uid)
        txt = (f"💰 <b>REDEEM POINTS</b>\n\n"
               f"Balance: {user[6]} pts\n"
               f"Rate: 10 pts = ₹1\n"
               f"Min: 500 pts\n\n"
               f"Process: Click button below to start")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🚀 Start Redeem", callback_data="redeem_start"))
        kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "redeem_start":
        user_states[uid] = {'type': 'redeem_points'}
        bot.send_message(uid, "💰 Enter points to redeem (min 500):")
        bot.answer_callback_query(c.id)
        return

    if data == "review_menu":
        txt = "⭐ <b>SUBMIT REVIEW</b>\n\nProcess: Click button to start"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("✍️ Write Review", callback_data="review_start"))
        kb.add(InlineKeyboardButton("« Back", callback_data="back_main"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "review_start":
        user_states[uid] = {'type': 'review_rating'}
        bot.send_message(uid, "⭐ Send rating (1-5):\n1 = Poor, 5 = Excellent")
        bot.answer_callback_query(c.id)
        return

    if data == "referral":
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
        txt = f"👥 <b>INVITE</b>\n\nEarn {REFERRAL_BONUS} pts!\n\n<code>{ref_link}</code>"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}"))
        try:
            bot.send_message(uid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        except:
            bot.send_message(cid, txt, reply_markup=kb)
            bot.answer_callback_query(c.id)
        return

    if data == "commands":
        txt = ("📋 <b>COMMANDS</b>\n\n"
               "<b>Game:</b> /new, /stop\n"
               "<b>User:</b> /stats, /leaderboard, /daily, /referral\n"
               "<b>Dictionary:</b> /define <word>\n\n"
               "<b>Admin:</b>\n"
               "/addadmin <id>\n"
               "/addpoints <id> <pts>\n"
               "/broadcast <msg>\n"
               "/listreviews\n"
               "/redeemlist")
        try:
            bot.send_message(uid, txt)
            bot.answer_callback_query(c.id, "Sent to PM!")
        except:
            bot.send_message(cid, txt)
            bot.answer_callback_query(c.id)
        return

    # Game modes
    if data.startswith("play_"):
        mode = data.replace("play_", "")
        custom_words = None
        is_hard = False

        if mode == "normal":
            mode_name = "NORMAL"
        elif mode == "hard":
            mode_name = "HARD"
            is_hard = True
        elif mode == "chemistry":
            mode_name = "CHEMISTRY"
            custom_words = CHEMISTRY_WORDS
        elif mode == "physics":
            mode_name = "PHYSICS"
            custom_words = PHYSICS_WORDS
        elif mode == "math":
            mode_name = "MATH"
            custom_words = MATH_WORDS
        elif mode == "jee":
            mode_name = "JEE"
            custom_words = JEE_WORDS
        else:
            mode_name = "NORMAL"

        start_game(cid, uid, mode_name, is_hard, custom_words)
        bot.answer_callback_query(c.id, f"✅ {mode_name} mode started!")
        return

    # Game actions
    if data == "g_guess":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        try:
            msg = bot.send_message(cid, "💬 Type the word you found:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, handle_guess)
            bot.answer_callback_query(c.id)
        except:
            bot.answer_callback_query(c.id, "Error!", show_alert=True)
        return

    if data == "g_hint":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        user = db.get_user(uid)
        if user[7] < HINT_COST:
            bot.answer_callback_query(c.id, f"Need {HINT_COST} pts!", show_alert=True)
            return
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All found!", show_alert=True)
            return
        reveal = random.choice(hidden)
        db.update_user(uid, hint_balance=user[7]-HINT_COST)
        bot.send_message(cid, f"💡 <b>Hint:</b> <code>{reveal}</code> (-{HINT_COST} pts)")
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
            name = db.get_user(u)[1]
            txt += f"{i}. {html.escape(name)} - {pts} pts\n"
        bot.send_message(cid, txt)
        bot.answer_callback_query(c.id)
        return

    if data == "g_stop":
        if cid not in games:
            bot.answer_callback_query(c.id, "No game!", show_alert=True)
            return
        del games[cid]
        bot.send_message(cid, "🛑 <b>Game stopped!</b>")
        bot.answer_callback_query(c.id, "Game ended!")
        return

    bot.answer_callback_query(c.id)

# ═══════════════════════════════════════════════════════════════════
# FLASK HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════

@app.route('/')
def health():
    return "✅ Word Vortex Bot Running!", 200

@app.route('/health')
def health_check():
    return {"status": "ok", "bot": "word_vortex", "version": "10.5", "games": len(games)}, 200

# ═══════════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("🚀 Starting Word Vortex v10.5 - FINAL COMPLETE EDITION!")
    logger.info("✅ Force channel join enabled")
    logger.info("✅ Owner notifications enabled")
    logger.info("✅ Enhanced scoring & dictionary feature")
    logger.info("✅ Flask server starting on port 10000")

    # Bot in separate thread
    def run_bot():
        bot.infinity_polling()

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    # Flask server
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
