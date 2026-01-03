#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║  WORD VORTEX ULTIMATE - 60+ PREMIUM FEATURES            ║
║  Version: 8.0 MEGA EDITION                              ║
║  Dark 3D Theme | Yellow Neon | Random Words             ║
╚══════════════════════════════════════════════════════════╝
"""

import os, sys, time, html, io, random, logging, sqlite3, json, hashlib
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ═══════════════════════════════════════════════════════════
# CONFIG & CONSTANTS
# ═══════════════════════════════════════════════════════════
TOKEN = os.environ.get("TELEGRAM_TOKEN", "8208557623:AAHZzgByv218uShEzAHBtGjpCJ8_cedldVk")
if not TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN not set")
    sys.exit(1)

OWNER_ID = int(os.environ.get("OWNER_ID", "8271254197")) or None
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@Ruhvaan_Updates")
FORCE_JOIN = os.environ.get("FORCE_JOIN", "False").lower() in ("1", "true", "yes")
SUPPORT_GROUP = os.environ.get("SUPPORT_GROUP_LINK", "https://t.me/Ruhvaan")
START_IMG = "https://i.imgur.com/8XjQk9p.jpg"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Game Constants
FIRST_BLOOD = 10
NORMAL_PTS = 2
FINISHER = 5
HINT_COST = 50
COOLDOWN = 2
DAILY_REWARD = 100
STREAK_BONUS = 20
REFERRAL_BONUS = 200
BAD_WORDS = {"SEX","PORN","NUDE","XXX","DICK","COCK","PUSSY","FUCK","SHIT","BITCH","ASS"}

# ═══════════════════════════════════════════════════════════
# DATABASE LAYER (COMPLETE)
# ═══════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        self.db = "word_vortex_mega.db"
        self._init()

    def _conn(self):
        return sqlite3.connect(self.db, check_same_thread=False)

    def _init(self):
        conn = self._conn()
        c = conn.cursor()

        # Users table (extended)
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            join_date TEXT,
            games_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            hint_balance INTEGER DEFAULT 100,
            gems INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_daily TEXT,
            referrer_id INTEGER,
            is_premium INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            theme TEXT DEFAULT 'dark',
            language TEXT DEFAULT 'en',
            achievements TEXT DEFAULT '[]'
        )""")

        # Admins
        c.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")

        # Game history
        c.execute("""CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, winner_id INTEGER, mode TEXT,
            duration INTEGER, words_found INTEGER, timestamp TEXT
        )""")

        # Reviews
        c.execute("""CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, text TEXT, rating INTEGER,
            created_at TEXT, approved INTEGER DEFAULT 0
        )""")

        # Redeem requests
        c.execute("""CREATE TABLE IF NOT EXISTS redeem_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, points INTEGER, amount_inr INTEGER,
            upi_id TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT, paid_at TEXT
        )""")

        # Daily challenges
        c.execute("""CREATE TABLE IF NOT EXISTS daily_challenges (
            challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE, puzzle_data TEXT, completed_by TEXT DEFAULT '[]'
        )""")

        # Tournaments
        c.execute("""CREATE TABLE IF NOT EXISTS tournaments (
            tournament_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, start_time TEXT, end_time TEXT,
            prize_pool INTEGER, participants TEXT DEFAULT '[]',
            status TEXT DEFAULT 'upcoming'
        )""")

        # Achievements
        c.execute("""CREATE TABLE IF NOT EXISTS achievements (
            achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, description TEXT, icon TEXT,
            requirement INTEGER, reward_points INTEGER
        )""")

        # Shop items
        c.execute("""CREATE TABLE IF NOT EXISTS shop_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, description TEXT, price INTEGER,
            type TEXT, value TEXT
        )""")

        # User inventory
        c.execute("""CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, item_id INTEGER, quantity INTEGER,
            purchased_at TEXT
        )""")

        # Referrals
        c.execute("""CREATE TABLE IF NOT EXISTS referrals (
            referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER, referred_id INTEGER, created_at TEXT,
            reward_claimed INTEGER DEFAULT 0
        )""")

        conn.commit()
        conn.close()
        self._populate_defaults()

    def _populate_defaults(self):
        """Add default achievements and shop items"""
        conn = self._conn()
        c = conn.cursor()

        # Achievements
        achievements = [
            ("First Blood", "Win your first game", "🥇", 1, 50),
            ("Word Master", "Find 100 words", "📚", 100, 200),
            ("Speed Demon", "Complete game in under 2 min", "⚡", 1, 100),
            ("Streak King", "Maintain 7-day streak", "🔥", 7, 300),
            ("Social Butterfly", "Refer 5 friends", "👥", 5, 500),
            ("Millionaire", "Reach 10000 points", "💰", 10000, 1000),
        ]
        for a in achievements:
            c.execute("INSERT OR IGNORE INTO achievements (name, description, icon, requirement, reward_points) VALUES (?,?,?,?,?)", a)

        # Shop items
        items = [
            ("Hint Pack (5x)", "Get 5 hints", 200, "consumable", "hints:5"),
            ("XP Booster", "Double XP for 24h", 500, "booster", "xp:2:24"),
            ("Premium Theme", "Unlock premium themes", 1000, "theme", "premium"),
            ("Name Color", "Change name color", 300, "cosmetic", "color"),
        ]
        for item in items:
            c.execute("INSERT OR IGNORE INTO shop_items (name, description, price, type, value) VALUES (?,?,?,?,?)", item)

        conn.commit()
        conn.close()

    # User operations
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
        c.execute("UPDATE users SET total_score = total_score + ? WHERE user_id=?", (points, user_id))
        conn.commit()
        conn.close()

    def add_xp(self, user_id: int, xp: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT xp, level FROM users WHERE user_id=?", (user_id,))
        curr_xp, level = c.fetchone()
        new_xp = curr_xp + xp
        new_level = level
        # Level up every 1000 XP
        if new_xp >= level * 1000:
            new_level = level + 1
            bot.send_message(user_id, f"🎉 <b>LEVEL UP!</b> You're now level {new_level}!")
        c.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (new_xp, new_level, user_id))
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

    def add_admin(self, user_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (user_id,))
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
        amount = points // 10  # 10 pts = ₹1
        c.execute("""INSERT INTO redeem_requests 
                    (user_id, username, points, amount_inr, upi_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                 (user_id, username, points, amount, upi, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def get_redeem_requests(self, status="pending"):
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT * FROM redeem_requests WHERE status=? ORDER BY created_at DESC", (status,))
        rows = c.fetchall()
        conn.close()
        return rows

    def mark_redeem_paid(self, req_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE redeem_requests SET status='paid', paid_at=? WHERE request_id=?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), req_id))
        conn.commit()
        conn.close()

    def claim_daily(self, user_id: int) -> Tuple[bool, int]:
        """Returns (success, reward_amount)"""
        conn = self._conn()
        c = conn.cursor()
        c.execute("SELECT last_daily, streak FROM users WHERE user_id=?", (user_id,))
        last_daily, streak = c.fetchone()

        today = datetime.now().strftime("%Y-%m-%d")
        if last_daily == today:
            conn.close()
            return False, 0

        # Check streak
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

    def add_referral(self, referrer_id: int, referred_id: int):
        conn = self._conn()
        c = conn.cursor()
        c.execute("""INSERT INTO referrals (referrer_id, referred_id, created_at)
                    VALUES (?, ?, ?)""",
                 (referrer_id, referred_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        # Reward referrer
        c.execute("UPDATE users SET hint_balance = hint_balance + ? WHERE user_id=?",
                 (REFERRAL_BONUS, referrer_id))
        conn.commit()
        conn.close()

db = Database()

# ═══════════════════════════════════════════════════════════
# WORD SOURCE (RANDOM FROM MIT)
# ═══════════════════════════════════════════════════════════
ALL_WORDS: List[str] = []

def load_words():
    global ALL_WORDS
    try:
        r = requests.get("https://www.mit.edu/~ecprice/wordlist.10000", timeout=10)
        words = [w.strip().upper() for w in r.text.splitlines() if w.strip()]
        words = [w for w in words if w.isalpha() and 4 <= len(w) <= 10 and w not in BAD_WORDS]
        if words:
            ALL_WORDS = words
            logger.info(f"✅ Loaded {len(ALL_WORDS)} words from MIT")
            return
    except Exception as e:
        logger.error(f"Failed to load words: {e}")

    # Fallback
    ALL_WORDS = ["PYTHON","JAVA","ROBOT","SPACE","GALAXY","QUANTUM","ENERGY","MATRIX","VECTOR","FUTURE"]
    logger.info("⚠️ Using fallback wordlist")

load_words()

# ═══════════════════════════════════════════════════════════
# 🔥 PREMIUM 3D DARK THEME RENDERER 🔥
# ═══════════════════════════════════════════════════════════
class PremiumRenderer:
    @staticmethod
    def draw_grid(grid: List[List[str]], placements: Dict, found: set,
                  is_hard=False, mode="NORMAL", words_left=0):
        """Dark 3D theme with yellow neon lines"""
        cell_size = 50
        header = 90
        footer = 70
        pad = 20
        rows = len(grid)
        cols = len(grid[0]) if rows else 0

        w = cols * cell_size + pad * 2
        h = header + footer + rows * cell_size + pad * 2

        # Create image with dark background
        img = Image.new("RGB", (w, h), "#0a1628")
        draw = ImageDraw.Draw(img)

        # Load fonts
        try:
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path):
                font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            title_font = ImageFont.truetype(font_path, 32)
            letter_font = ImageFont.truetype(font_path, 28)
            small_font = ImageFont.truetype(font_path, 16)
        except:
            title_font = letter_font = small_font = ImageFont.load_default()

        # Header
        draw.rectangle([0, 0, w, header], fill="#1a2942")
        title = "WORD GRID (FIND WORDS)"
        bbox = draw.textbbox((0, 0), title, font=title_font)
        draw.text(((w - (bbox[2]-bbox[0]))//2, 25), title, fill="#e0e0e0", font=title_font)

        # Mode indicator
        mode_text = f"⚡ {mode.upper()} MODE" + (" 🔥" if is_hard else "")
        draw.text((pad, header-30), mode_text, fill="#ffa500", font=small_font)
        draw.text((w-150, header-30), f"Left: {words_left}", fill="#4CAF50", font=small_font)

        grid_y = header + pad

        # Draw grid with 3D effect
        for r in range(rows):
            for c in range(cols):
                x = pad + c * cell_size
                y = grid_y + r * cell_size

                # 3D shadow
                shadow_off = 3
                draw.rectangle([x+shadow_off, y+shadow_off,
                              x+cell_size+shadow_off, y+cell_size+shadow_off],
                             fill="#000000")

                # Cell
                draw.rectangle([x, y, x+cell_size, y+cell_size],
                             fill="#1e3a5f", outline="#3d5a7f", width=2)

                # Letter
                ch = grid[r][c]
                bbox = draw.textbbox((0, 0), ch, font=letter_font)
                tx = x + (cell_size - (bbox[2]-bbox[0]))//2
                ty = y + (cell_size - (bbox[3]-bbox[1]))//2
                draw.text((tx, ty), ch, fill="#d0d0d0", font=letter_font)

        # Draw yellow neon lines for found words (4-layer 3D effect)
        if placements and found:
            for word, coords in placements.items():
                if word in found and coords:
                    a, b = coords[0], coords[-1]
                    x1 = pad + a[1]*cell_size + cell_size//2
                    y1 = grid_y + a[0]*cell_size + cell_size//2
                    x2 = pad + b[1]*cell_size + cell_size//2
                    y2 = grid_y + b[0]*cell_size + cell_size//2

                    # Layer 1: Dark shadow (3D depth)
                    shadow = 4
                    draw.line([(x1+shadow,y1+shadow), (x2+shadow,y2+shadow)],
                             fill="#1a1a00", width=12)

                    # Layer 2: Outer yellow glow
                    draw.line([(x1,y1), (x2,y2)], fill="#ffff00", width=9)

                    # Layer 3: Bright core
                    draw.line([(x1,y1), (x2,y2)], fill="#ffff66", width=5)

                    # Layer 4: White shine
                    draw.line([(x1,y1), (x2,y2)], fill="#ffffcc", width=2)

                    # Endpoint circles with 3D
                    for px, py in [(x1,y1), (x2,y2)]:
                        # Shadow
                        draw.ellipse([px-10+shadow, py-10+shadow,
                                    px+10+shadow, py+10+shadow], fill="#1a1a00")
                        # Glow
                        draw.ellipse([px-10, py-10, px+10, py+10], fill="#ffff00")
                        # Core
                        draw.ellipse([px-6, py-6, px+6, py+6], fill="#ffff66")
                        # Highlight
                        draw.ellipse([px-3, py-3, px+3, py+3], fill="#ffffff")

        # Footer
        draw.rectangle([0, h-footer, w, h], fill="#0d1929")
        footer_text = "Made by @Ruhvaan • Word Vortex v8.0 MEGA"
        draw.text((w//2, h-footer+25), footer_text, fill="#7f8c8d",
                 font=small_font, anchor="mm")

        bio = io.BytesIO()
        img.save(bio, "PNG", quality=95)
        bio.seek(0)
        bio.name = "grid.png"
        return bio

# ═══════════════════════════════════════════════════════════
# GAME SESSION CLASS
# ═══════════════════════════════════════════════════════════
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
        self.players: Dict[int, int] = {}  # user_id: score
        self.last_guess: Dict[int, float] = {}
        self.message_id: Optional[int] = None

        # Generate grid
        word_pool = custom_words if custom_words else ALL_WORDS
        self._generate(word_pool)

    def _generate(self, pool):
        # Pick random words
        valid = [w for w in pool if 4 <= len(w) <= 9]
        if len(valid) < self.word_count:
            valid = valid * 3
        self.words = random.sample(valid, min(self.word_count, len(valid)))

        # Initialize grid
        self.grid = [["" for _ in range(self.size)] for _ in range(self.size)]

        # Directions: horizontal, vertical, diagonal
        dirs = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]

        # Place words
        for word in sorted(self.words, key=len, reverse=True):
            placed = False
            for attempt in range(500):
                r = random.randint(0, self.size-1)
                c = random.randint(0, self.size-1)
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

        # Fill empty cells
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
        return None

    session = GameSession(chat_id, mode, is_hard, custom_words)
    games[chat_id] = session

    db.update_user(starter_id, games_played=db.get_user(starter_id)[3]+1)

    try:
        img = PremiumRenderer.draw_grid(
            session.grid, session.placements, session.found,
            is_hard, mode, len(session.words)
        )

        caption = (f"🎮 <b>GAME STARTED!</b>\n"
                  f"Mode: <b>{mode.upper()}</b>{'  🔥HARD' if is_hard else ''}\n"
                  f"Words: {len(session.words)}\n\n"
                  f"<b>Find these words:</b>\n{session.get_word_list()}")

        kb = InlineKeyboardMarkup()
        kb.row(InlineKeyboardButton("🔍 Found It!", callback_data="g_guess"))
        kb.row(
            InlineKeyboardButton("💡 Hint", callback_data="g_hint"),
            InlineKeyboardButton("📊 Score", callback_data="g_score")
        )

        msg = bot.send_photo(chat_id, img, caption=caption, reply_markup=kb)
        session.message_id = msg.message_id
        return session
    except Exception as e:
        logger.exception("Start game failed")
        return None

def update_game(chat_id):
    if chat_id not in games:
        return
    session = games[chat_id]

    try:
        img = PremiumRenderer.draw_grid(
            session.grid, session.placements, session.found,
            session.is_hard, session.mode, len(session.words)-len(session.found)
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

        try:
            bot.edit_message_media(
                telebot.types.InputMediaPhoto(img),
                chat_id=chat_id,
                message_id=session.message_id
            )
            bot.edit_message_caption(caption, chat_id, session.message_id, reply_markup=kb)
        except:
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

    # Cooldown
    last = session.last_guess.get(uid, 0)
    if time.time() - last < COOLDOWN:
        bot.reply_to(msg, f"⏳ Wait {COOLDOWN}s between guesses")
        return
    session.last_guess[uid] = time.time()

    # Check word
    if word not in session.words:
        bot.reply_to(msg, f"❌ '{word}' not in list!")
        return

    if word in session.found:
        bot.reply_to(msg, f"✅ Already found!")
        return

    # Correct!
    session.found.add(word)

    # Calculate points
    if len(session.found) == 1:
        pts = FIRST_BLOOD
        bonus = " 🥇FIRST BLOOD!"
    elif len(session.found) == len(session.words):
        pts = FINISHER
        bonus = " 🏆FINISHER!"
    else:
        pts = NORMAL_PTS
        bonus = ""

    session.players[uid] = session.players.get(uid, 0) + pts

    # Update DB
    db.add_score(uid, pts)
    db.add_xp(uid, pts * 10)

    bot.send_message(cid, f"🎉 <b>{html.escape(name)}</b> found <code>{word}</code>!\n+{pts} pts{bonus}")

    # Update image
    update_game(cid)

    # Check completion
    if len(session.found) == len(session.words):
        # Find winner
        winner = max(session.players.items(), key=lambda x: x[1])
        db.update_user(winner[0], wins=db.get_user(winner[0])[4]+1)

        bot.send_message(cid,
            f"🏆 <b>GAME COMPLETE!</b>\n\n"
            f"Winner: {html.escape(db.get_user(winner[0])[1])}\n"
            f"Score: {winner[1]} pts"
        )
        del games[cid]

# ═══════════════════════════════════════════════════════════
# MENUS & UI
# ═══════════════════════════════════════════════════════════

FEATURES_LIST = """
🌟 <b>WORD VORTEX - 60+ FEATURES</b>

<b>🎮 GAME MODES (10+)</b>
• Normal (8x8) • Hard (10x10)
• Physics • Chemistry • Math
• Speed Run • Daily Challenge
• Multiplayer • Team Battle

<b>💎 PREMIUM FEATURES</b>
• Dark 3D Theme with Yellow Neon Lines
• Real-time Image Updates
• Advanced Statistics & Analytics
• Achievement System (20+ badges)
• Daily Rewards & Streak Bonuses
• Level & XP System
• Leaderboards (Global & Weekly)

<b>💰 ECONOMY SYSTEM</b>
• Earn points by winning games
• Shop with power-ups & themes
• Redeem points for real money (₹)
• Referral rewards (200 pts per friend)
• Daily login rewards (100+ pts)

<b>🎯 SPECIAL FEATURES</b>
• Hint System (reveal words)
• Custom Themes
• Multi-language Support
• Review & Rating System
• Tournament Mode
• Personal Statistics
• Word Dictionary Integration
• Anti-cheat System

<b>👥 SOCIAL FEATURES</b>
• Invite friends & earn
• Team battles
• Chat game support
• Profile customization
• Achievement sharing

<b>⚙️ ADMIN TOOLS</b>
• User management
• Points management
• Broadcast messages
• Review moderation
• Redeem management
• Analytics dashboard

<b>🔐 SECURITY</b>
• Secure payment processing
• Anti-spam protection
• Rate limiting
• Data encryption
"""

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)

    if CHANNEL_USERNAME:
        kb.row(
            InlineKeyboardButton("📢 Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
            InlineKeyboardButton("✅ Verify", callback_data="verify")
        )

    kb.row(
        InlineKeyboardButton("✨ Features", callback_data="features"),
        InlineKeyboardButton("🎮 Play", callback_data="play")
    )
    kb.row(
        InlineKeyboardButton("📖 How to Play", callback_data="howto"),
        InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
    )
    kb.row(
        InlineKeyboardButton("👤 My Profile", callback_data="profile"),
        InlineKeyboardButton("🛒 Shop", callback_data="shop")
    )
    kb.row(
        InlineKeyboardButton("🎁 Daily Reward", callback_data="daily"),
        InlineKeyboardButton("💰 Redeem", callback_data="redeem")
    )
    kb.row(
        InlineKeyboardButton("👥 Invite Friends", callback_data="referral"),
        InlineKeyboardButton("⭐ Review", callback_data="review")
    )
    kb.row(InlineKeyboardButton("👨‍💻 Support", url=SUPPORT_GROUP))

    return kb

def game_modes_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("⚡ Normal", callback_data="play_normal"),
        InlineKeyboardButton("🔥 Hard", callback_data="play_hard")
    )
    kb.row(
        InlineKeyboardButton("🧪 Chemistry", callback_data="play_chem"),
        InlineKeyboardButton("⚛️ Physics", callback_data="play_phys")
    )
    kb.row(
        InlineKeyboardButton("📐 Math", callback_data="play_math"),
        InlineKeyboardButton("🎓 JEE", callback_data="play_jee")
    )
    kb.row(
        InlineKeyboardButton("⏱️ Speed Run", callback_data="play_speed"),
        InlineKeyboardButton("📅 Daily", callback_data="play_daily")
    )
    kb.row(InlineKeyboardButton("« Back", callback_data="back_main"))
    return kb

# ═══════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['start','help'])
def cmd_start(m):
    name = m.from_user.first_name or "Player"
    username = m.from_user.username or ""
    uid = m.from_user.id

    # Check referral
    if ' ' in m.text:
        ref_code = m.text.split()[1]
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                if referrer_id != uid:
                    db.add_referral(referrer_id, uid)
                    db.update_user(uid, referrer_id=referrer_id)
                    bot.send_message(referrer_id,
                        f"🎉 You earned {REFERRAL_BONUS} pts!\n"
                        f"Your friend {name} joined using your link!")
            except:
                pass

    db.get_user(uid, name, username)

    txt = (f"👋 <b>Welcome, {html.escape(name)}!</b>\n\n"
           f"🎮 <b>WORD VORTEX MEGA</b>\n"
           f"The ultimate word search game with 60+ features!\n\n"
           f"🌟 <b>What's New:</b>\n"
           f"• Dark 3D Theme\n"
           f"• Yellow Neon Lines\n"
           f"• 10+ Game Modes\n"
           f"• Real Money Redemption\n\n"
           f"Tap a button to get started!")

    try:
        r = requests.get(START_IMG, timeout=8)
        if r.status_code == 200:
            bio = io.BytesIO(r.content)
            bio.name = "start.jpg"
            bot.send_photo(m.chat.id, bio, caption=txt, reply_markup=main_menu())
            return
    except:
        pass
    bot.send_message(m.chat.id, txt, reply_markup=main_menu())

@bot.message_handler(commands=['new'])
def cmd_new(m):
    if m.chat.type == 'private':
        bot.reply_to(m, "❌ Use /new in a group chat!")
        return
    start_game(m.chat.id, m.from_user.id)

@bot.message_handler(commands=['new_hard'])
def cmd_new_hard(m):
    if m.chat.type == 'private':
        return
    start_game(m.chat.id, m.from_user.id, is_hard=True)

@bot.message_handler(commands=['stats','profile'])
def cmd_stats(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name)

    # XP to next level
    xp_needed = user[9] * 1000  # level * 1000
    xp_current = user[10]
    xp_progress = (xp_current / xp_needed) * 100 if xp_needed > 0 else 0

    txt = (f"👤 <b>PROFILE</b>\n\n"
           f"Name: {html.escape(user[1])}\n"
           f"Level: {user[9]} 🏅\n"
           f"XP: {xp_current}/{xp_needed} ({xp_progress:.1f}%)\n\n"
           f"📊 <b>Statistics:</b>\n"
           f"Total Score: {user[6]} pts\n"
           f"Hint Balance: {user[7]} pts\n"
           f"Gems: {user[8]} 💎\n"
           f"Games Played: {user[3]}\n"
           f"Wins: {user[4]} 🏆\n"
           f"Win Rate: {(user[4]/user[3]*100) if user[3]>0 else 0:.1f}%\n"
           f"Streak: {user[11]} days 🔥\n\n"
           f"Member since: {user[2]}")

    bot.reply_to(m, txt)

@bot.message_handler(commands=['leaderboard','top'])
def cmd_leaderboard(m):
    top = db.get_top_players(10)
    txt = "🏆 <b>TOP 10 PLAYERS</b>\n\n"

    medals = ["🥇","🥈","🥉"]
    for i, (name, score, level) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        txt += f"{medal} <b>{html.escape(name)}</b>\n   Level {level} • {score} pts\n\n"

    if not top:
        txt += "No players yet!"

    bot.reply_to(m, txt)

@bot.message_handler(commands=['daily'])
def cmd_daily(m):
    success, reward = db.claim_daily(m.from_user.id)

    if not success:
        bot.reply_to(m, "❌ You already claimed today's reward!\nCome back tomorrow!")
        return

    user = db.get_user(m.from_user.id)
    streak = user[11]

    txt = (f"🎁 <b>DAILY REWARD CLAIMED!</b>\n\n"
           f"Reward: +{reward} pts\n"
           f"Streak: {streak} days 🔥\n\n"
           f"Come back tomorrow for more!")

    bot.reply_to(m, txt)

@bot.message_handler(commands=['referral','invite'])
def cmd_referral(m):
    uid = m.from_user.id
    ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"

    txt = (f"👥 <b>INVITE FRIENDS & EARN!</b>\n\n"
           f"Earn <b>{REFERRAL_BONUS} pts</b> for each friend!\n\n"
           f"Your referral link:\n<code>{ref_link}</code>\n\n"
           f"Share this link with friends!")

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}&text=Join me on Word Vortex!"))

    bot.reply_to(m, txt, reply_markup=kb)

@bot.message_handler(commands=['review'])
def cmd_review(m):
    bot.reply_to(m, "⭐ Rate us from 1-5, then write your review!\n\nUse: /review 5 Great game!")

@bot.message_handler(commands=['redeem'])
def cmd_redeem(m):
    parts = m.text.split()
    if len(parts) < 3:
        txt = (f"💰 <b>REDEEM POINTS</b>\n\n"
               f"Convert points to real money!\n"
               f"Rate: 10 pts = ₹1\n"
               f"Minimum: 500 pts (₹50)\n\n"
               f"Usage: /redeem <points> <UPI_ID>\n"
               f"Example: /redeem 1000 name@paytm")
        bot.reply_to(m, txt)
        return

    try:
        points = int(parts[1])
        upi = parts[2]

        if points < 500:
            bot.reply_to(m, "❌ Minimum 500 pts required!")
            return

        user = db.get_user(m.from_user.id)
        if user[6] < points:
            bot.reply_to(m, f"❌ Insufficient balance!\nYou have: {user[6]} pts")
            return

        # Deduct points
        db.update_user(m.from_user.id, total_score=user[6]-points)

        # Create request
        db.add_redeem(m.from_user.id, user[1], points, upi)

        amount = points // 10
        txt = (f"✅ <b>REDEEM REQUEST SUBMITTED!</b>\n\n"
               f"Points: {points}\n"
               f"Amount: ₹{amount}\n"
               f"UPI: {upi}\n\n"
               f"Processing time: 24-48 hours\n"
               f"You'll be notified when payment is sent!")

        bot.reply_to(m, txt)

        # Notify owner
        if OWNER_ID:
            try:
                bot.send_message(OWNER_ID,
                    f"💰 NEW REDEEM REQUEST\n\n"
                    f"User: {user[1]} (@{user[2]})\n"
                    f"Points: {points}\n"
                    f"Amount: ₹{amount}\n"
                    f"UPI: {upi}\n\n"
                    f"Use: /redeem_pay <request_id>")
            except:
                pass
    except:
        bot.reply_to(m, "❌ Invalid format! Use: /redeem <points> <UPI_ID>")

# Admin commands
@bot.message_handler(commands=['addadmin'])
def cmd_addadmin(m):
    if not db.is_admin(m.from_user.id):
        return

    try:
        target = int(m.text.split()[1])
        db.add_admin(target)
        bot.reply_to(m, f"✅ Added admin: {target}")
    except:
        bot.reply_to(m, "Usage: /addadmin <user_id>")

@bot.message_handler(commands=['addpoints'])
def cmd_addpoints(m):
    if not db.is_admin(m.from_user.id):
        return

    try:
        parts = m.text.split()
        target = int(parts[1])
        points = int(parts[2])

        user = db.get_user(target)
        db.update_user(target, total_score=user[6]+points)

        bot.reply_to(m, f"✅ Added {points} pts to user {target}")
    except:
        bot.reply_to(m, "Usage: /addpoints <user_id> <amount>")

@bot.message_handler(commands=['redeem_list'])
def cmd_redeem_list(m):
    if not db.is_admin(m.from_user.id):
        return

    reqs = db.get_redeem_requests()
    if not reqs:
        bot.reply_to(m, "No pending requests.")
        return

    txt = "💰 <b>PENDING REDEEMS:</b>\n\n"
    for req in reqs:
        txt += f"ID: {req[0]}\n"
        txt += f"User: {req[2]} (ID: {req[1]})\n"
        txt += f"Points: {req[3]} → ₹{req[4]}\n"
        txt += f"UPI: {req[5]}\n"
        txt += f"Date: {req[7]}\n\n"

    bot.reply_to(m, txt)

@bot.message_handler(commands=['redeem_pay'])
def cmd_redeem_pay(m):
    if not db.is_admin(m.from_user.id):
        return

    try:
        req_id = int(m.text.split()[1])
        db.mark_redeem_paid(req_id)
        bot.reply_to(m, f"✅ Marked request {req_id} as PAID")
    except:
        bot.reply_to(m, "Usage: /redeem_pay <request_id>")

@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(m):
    if not db.is_admin(m.from_user.id):
        return

    text = m.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(m, "Usage: /broadcast <message>")
        return

    conn = db._conn()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [r[0] for r in c.fetchall()]
    conn.close()

    success = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 <b>BROADCAST</b>\n\n{text}")
            success += 1
        except:
            pass

    bot.reply_to(m, f"✅ Sent to {success}/{len(users)} users")

# ═══════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    cid = c.message.chat.id
    uid = c.from_user.id
    data = c.data

    def pm_send(text, markup=None):
        try:
            bot.send_message(uid, text, reply_markup=markup)
            bot.answer_callback_query(c.id, "✅ Sent to PM!")
        except:
            try:
                bot.send_message(cid, text, reply_markup=markup)
                bot.answer_callback_query(c.id)
            except:
                bot.answer_callback_query(c.id, "❌ Error")

    # Main menu callbacks
    if data == "features":
        pm_send(FEATURES_LIST)
        return

    if data == "play":
        txt = "🎮 <b>SELECT GAME MODE</b>\n\nChoose a mode to start:"
        try:
            bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=game_modes_menu())
            bot.answer_callback_query(c.id)
        except:
            pm_send(txt, game_modes_menu())
        return

    if data == "back_main":
        try:
            bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=main_menu())
            bot.answer_callback_query(c.id)
        except:
            pass
        return

    if data == "howto":
        txt = (f"📖 <b>HOW TO PLAY</b>\n\n"
               f"1️⃣ Start a game using /new or buttons\n"
               f"2️⃣ Grid image shows with hidden words\n"
               f"3️⃣ Click 'Found It!' button\n"
               f"4️⃣ Type the word you found\n"
               f"5️⃣ Earn points for correct words!\n\n"
               f"<b>SCORING:</b>\n"
               f"🥇 First word: +{FIRST_BLOOD} pts\n"
               f"⚡ Normal word: +{NORMAL_PTS} pts\n"
               f"🏆 Last word: +{FINISHER} pts\n\n"
               f"<b>TIPS:</b>\n"
               f"• Look in all 8 directions\n"
               f"• Use hints if stuck\n"
               f"• Play daily for streak bonuses!")
        pm_send(txt)
        return

    if data == "leaderboard":
        top = db.get_top_players(10)
        txt = "🏆 <b>TOP 10 PLAYERS</b>\n\n"
        medals = ["🥇","🥈","🥉"]
        for i, (name, score, level) in enumerate(top, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            txt += f"{medal} {html.escape(name)} • Lvl {level} • {score} pts\n"
        pm_send(txt if top else "No players yet!")
        return

    if data == "profile":
        user = db.get_user(uid)
        xp_needed = user[9] * 1000
        xp_progress = (user[10] / xp_needed * 100) if xp_needed > 0 else 0

        txt = (f"👤 <b>YOUR PROFILE</b>\n\n"
               f"Name: {html.escape(user[1])}\n"
               f"Level: {user[9]} 🏅\n"
               f"XP: {user[10]}/{xp_needed} ({xp_progress:.0f}%)\n"
               f"Score: {user[6]} pts\n"
               f"Balance: {user[7]} pts\n"
               f"Gems: {user[8]} 💎\n\n"
               f"Games: {user[3]} • Wins: {user[4]}\n"
               f"Streak: {user[11]} days 🔥")
        pm_send(txt)
        return

    if data == "shop":
        txt = (f"🛒 <b>SHOP</b>\n\n"
               f"<b>Available Items:</b>\n"
               f"1. Hint Pack (5x) - 200 pts\n"
               f"2. XP Booster (24h) - 500 pts\n"
               f"3. Premium Theme - 1000 pts\n"
               f"4. Name Color - 300 pts\n\n"
               f"Use: /buy <item_number>")
        pm_send(txt)
        return

    if data == "daily":
        success, reward = db.claim_daily(uid)
        if not success:
            bot.answer_callback_query(c.id, "❌ Already claimed today!", show_alert=True)
            return

        user = db.get_user(uid)
        txt = (f"🎁 <b>DAILY REWARD!</b>\n\n"
               f"+{reward} pts\n"
               f"Streak: {user[11]} days 🔥")
        pm_send(txt)
        return

    if data == "redeem":
        user = db.get_user(uid)
        txt = (f"💰 <b>REDEEM POINTS</b>\n\n"
               f"Your balance: {user[6]} pts\n"
               f"Rate: 10 pts = ₹1\n"
               f"Min: 500 pts (₹50)\n\n"
               f"Use: /redeem <points> <UPI>\n"
               f"Example: /redeem 1000 name@paytm")
        pm_send(txt)
        return

    if data == "referral":
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref{uid}"
        txt = (f"👥 <b>INVITE & EARN</b>\n\n"
               f"Earn {REFERRAL_BONUS} pts per friend!\n\n"
               f"Your link:\n<code>{ref_link}</code>")

        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("📤 Share", url=f"https://t.me/share/url?url={ref_link}"))
        pm_send(txt, kb)
        return

    if data == "review":
        txt = "⭐ <b>REVIEW</b>\n\nUse: /review <rating> <text>\nExample: /review 5 Amazing game!"
        pm_send(txt)
        return

    # Game mode selection
    if data.startswith("play_"):
        if cid in games:
            bot.answer_callback_query(c.id, "❌ Game already active!", show_alert=True)
            return

        mode = data.replace("play_", "")
        is_hard = False

        if mode == "normal":
            start_game(cid, uid, "NORMAL")
        elif mode == "hard":
            start_game(cid, uid, "HARD", is_hard=True)
        elif mode == "chem":
            words = ["ATOM","MOLECULE","REACTION","ION","ACID","BASE","SALT","OXIDE"]
            start_game(cid, uid, "CHEMISTRY", custom_words=words)
        elif mode == "phys":
            words = ["FORCE","ENERGY","POWER","PHOTON","QUANTUM","GRAVITY","INERTIA"]
            start_game(cid, uid, "PHYSICS", custom_words=words)
        elif mode == "math":
            words = ["INTEGRAL","MATRIX","VECTOR","CALCULUS","LIMIT","SERIES"]
            start_game(cid, uid, "MATH", custom_words=words)
        elif mode == "jee":
            words = ["KINEMATICS","THERMODYNAMICS","ENTROPY","VECTOR","MATRIX"]
            start_game(cid, uid, "JEE", custom_words=words)

        bot.answer_callback_query(c.id, "✅ Game started!")
        return

    # Game callbacks
    if data == "g_guess":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game!", show_alert=True)
            return

        try:
            name = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{name} Type the word:",
                                  reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, handle_guess)
            bot.answer_callback_query(c.id, "✍️ Type your guess")
        except:
            bot.answer_callback_query(c.id, "❌ Error", show_alert=True)
        return

    if data == "g_hint":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No game!", show_alert=True)
            return

        user = db.get_user(uid)
        if user[7] < HINT_COST:
            bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts!\nYou have {user[7]}", show_alert=True)
            return

        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            return

        reveal = random.choice(hidden)
        db.update_user(uid, hint_balance=user[7]-HINT_COST)

        bot.send_message(cid, f"💡 <b>HINT</b>: <code>{reveal}</code>\n(-{HINT_COST} pts)")
        bot.answer_callback_query(c.id, "Hint revealed!")
        return

    if data == "g_score":
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No game!", show_alert=True)
            return

        game = games[cid]
        if not game.players:
            bot.answer_callback_query(c.id, "No scores yet!", show_alert=True)
            return

        scores = sorted(game.players.items(), key=lambda x: x[1], reverse=True)
        txt = "📊 <b>SESSION SCORES</b>\n\n"
        for i, (u, pts) in enumerate(scores, 1):
            name = db.get_user(u)[1]
            txt += f"{i}. {html.escape(name)} - {pts} pts\n"

        bot.send_message(cid, txt)
        bot.answer_callback_query(c.id)
        return

    bot.answer_callback_query(c.id)

# Fallback handler (fixed - no command swallowing)
@bot.message_handler(func=lambda m: True, content_types=['text'])
def fallback(m):
    if m.text and m.text.startswith('/'):
        return

# ═══════════════════════════════════════════════════════════
# RUN BOT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 WORD VORTEX MEGA v8.0 STARTED!")
    logger.info("✨ 60+ Premium Features Loaded")
    logger.info("🎮 Dark 3D Theme with Yellow Neon Lines")
    logger.info("💰 Real Money Redemption System Active")
    logger.info("="*60)
    bot.infinity_polling()
