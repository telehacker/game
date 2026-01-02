# (Full file — only the relevant image-send fixes were added)
"""
WORDS GRID ROBOT - ULTIMATE PREMIUM EDITION
Version: 5.0 (Enterprise) - BUTTONS FIX, PUZZLE IMAGE, JOIN BUTTON
Developer: Ruhvaan
"""

import telebot
import random
import string
import requests
import threading
import sqlite3
import time
import os
import html
import io
import logging
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from PIL import Image, ImageDraw, ImageFont
import tempfile

# ==========================================
# ⚙️ CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN', '8208557623:AAETc5E4MQIxYscfSHy4emnhkniqUbgIbag')
try:
    OWNER_ID = int(os.environ.get('OWNER_ID', '8271254197'))
except Exception:
    OWNER_ID = None

CHANNEL_USERNAME = os.environ.get('CHANNEL_USERNAME', '@Ruhvaan_Updates')
FORCE_JOIN = os.environ.get('FORCE_JOIN', 'False').lower() in ('1', 'true', 'yes')

SUPPORT_GROUP_LINK = os.environ.get('SUPPORT_GROUP_LINK', 'https://t.me/Ruhvaan')
START_IMG_URL = os.environ.get('START_IMG_URL', 'https://img.freepik.com/free-vector/word-search-puzzle_23-2149040310.jpg')

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BAD_WORDS = {"SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"}
GAME_DURATION = 600
COOLDOWN = 2
HINT_COST = 50

PLANS = [
    {"points": 50, "price_rs": 10},
    {"points": 120, "price_rs": 20},
    {"points": 350, "price_rs": 50},
    {"points": 800, "price_rs": 100},
]

# ==========================================
# 🗄️ DATABASE MANAGER
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
        c.execute('''CREATE TABLE IF NOT EXISTS game_history (
            game_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            winner_id INTEGER,
            timestamp TEXT
        )''')
        conn.commit()
        conn.close()

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

    def update_stats(self, user_id, score_delta=0, hint_delta=0, win=False, games_played_delta=0):
        conn = self.connect()
        c = conn.cursor()
        if score_delta != 0 or hint_delta != 0:
            c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", 
                      (score_delta, hint_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
        if games_played_delta != 0:
            c.execute("UPDATE users SET games_played = games_played + ? WHERE user_id=?", (games_played_delta, user_id))
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

    def toggle_ban(self, user_id, status):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned = ? WHERE user_id=?", (status, user_id))
        conn.commit()
        conn.close()

    def record_game(self, chat_id, winner_id):
        conn = self.connect()
        c = conn.cursor()
        c.execute("INSERT INTO game_history (chat_id, winner_id, timestamp) VALUES (?, ?, ?)",
                  (chat_id, winner_id, time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

db = DatabaseManager()

# ==========================================
# 🎨 IMAGE GENERATOR
# ==========================================
class GridRenderer:
    @staticmethod
    def draw(grid, is_hard=False):
        # Configuration
        cell_size = 60
        header_height = 100
        footer_height = 50
        padding = 30
        
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        
        width = (cols * cell_size) + (padding * 2)
        height = (rows * cell_size) + header_height + footer_height + (padding * 2)
        
        # Colors
        BG_COLOR = "#FFFFFF"
        GRID_COLOR = "#3498db"
        TEXT_COLOR = "#2c3e50"
        HEADER_BG = "#ecf0f1"
        
        # Create Canvas
        img = Image.new('RGB', (width, height), BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Load Fonts
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

        # Draw Header
        draw.rectangle([0, 0, width, header_height], fill=HEADER_BG)
        title_text = "WORD VORTEX"
        bbox = draw.textbbox((0,0), title_text, font=header_font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw)/2, 30), title_text, fill="#2980b9", font=header_font)
        
        # Draw Mode Subtitle
        mode_text = "HARD MODE" if is_hard else "NORMAL MODE"
        bbox2 = draw.textbbox((0,0), mode_text, font=footer_font)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((width - tw2)/2, 75), mode_text, fill="#7f8c8d", font=footer_font)

        # Draw Grid
        grid_start_y = header_height + padding
        
        for r in range(rows):
            for c in range(cols):
                x = padding + (c * cell_size)
                y = grid_start_y + (r * cell_size)
                
                # Draw Box
                shape = [x, y, x + cell_size, y + cell_size]
                draw.rectangle(shape, outline=GRID_COLOR, width=2)
                
                # Draw Letter
                char = grid[r][c]
                bbox_char = draw.textbbox((0,0), char, font=letter_font)
                cw = bbox_char[2] - bbox_char[0]
                ch = bbox_char[3] - bbox_char[1]
                
                # Center text perfectly
                draw.text((x + (cell_size - cw)/2, y + (cell_size - ch)/2 - 5), char, fill=TEXT_COLOR, font=letter_font)

        # Draw Footer
        draw.text((padding, height - 30), "Made by @Ruhvaan", fill="#95a5a6", font=footer_font)
        draw.text((width - 100, height - 30), "v5.0", fill="#95a5a6", font=footer_font)

        # Output
        bio = io.BytesIO()
        img.save(bio, 'JPEG', quality=95)
        bio.seek(0)
        # Important: give BytesIO a name attribute so telebot treats it as a file
        try:
            bio.name = 'grid.jpg'
        except Exception:
            pass
        return bio

# ==========================================
# 🧠 GAME LOGIC ENGINE
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

games = {}

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
        self.players_scores = {}
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
# 🛡️ UTILS
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

def safe_edit_message(caption, cid, mid, reply_markup=None):
    try:
        bot.edit_message_caption(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup)
        return True
    except Exception:
        try:
            bot.edit_message_text(caption, chat_id=cid, message_id=mid, reply_markup=reply_markup, parse_mode='HTML')
            return True
        except Exception:
            return False

# ==========================================
# 🎮 HANDLERS (MAIN MENU & CALLBACKS)
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def show_main_menu(m):
    db.get_user(m.from_user.id, m.from_user.first_name)
    txt = (f"👋 <b>Hello, {html.escape(m.from_user.first_name)}!</b>\n\n"
           "🧩 <b>Welcome to Word Vortex</b>\n"
           "The most advanced multiplayer word search bot on Telegram.\n\n"
           "👇 <b>What would you like to do?</b>")
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'),
               InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'))
    markup.add(InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'),
               InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'))
    markup.add(InlineKeyboardButton("🐞 Report Issue", callback_data='open_issue'),
               InlineKeyboardButton("💳 Buy Points", callback_data='open_plans'))
    markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
               InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
    markup.add(InlineKeyboardButton("👨‍💻 Support / Owner", url=SUPPORT_GROUP_LINK))
    try:
        bot.send_photo(m.chat.id, START_IMG_URL, caption=txt, reply_markup=markup)
    except Exception:
        # If remote URL fails to send, fallback to simple text menu
        logger.exception("Failed to send START_IMG_URL; falling back to text menu")
        bot.reply_to(m, txt, reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    cid = c.message.chat.id
    mid = c.message.message_id
    uid = c.from_user.id
    data = c.data

    if data == "check_join":
        if is_subscribed(uid):
            bot.answer_callback_query(c.id, "✅ Verified! Welcome.", show_alert=True)
            try:
                bot.delete_message(cid, mid)
            except:
                pass
            show_main_menu(c.message)
        else:
            bot.answer_callback_query(c.id, "❌ You haven't joined yet!", show_alert=True)
        return

    if data == 'open_issue':
        try:
            bot.answer_callback_query(c.id, "✍️ Please type your issue below.", show_alert=False)
            bot.send_message(cid, f"@{c.from_user.username or c.from_user.first_name} Please type your issue or use /issue <message>:", reply_markup=ForceReply(selective=True))
        except:
            bot.answer_callback_query(c.id, "❌ Unable to open issue prompt.", show_alert=True)
        return

    if data == 'open_plans':
        txt = "💳 Points Plans:\n\n"
        for p in PLANS:
            txt += f"- {p['points']} pts : ₹{p['price_rs']}\n"
        txt += f"\nTo buy, contact the owner: {SUPPORT_GROUP_LINK}"
        bot.answer_callback_query(c.id, txt, show_alert=True)
        return

    if data == 'help_play':
        txt = ("<b>📖 How to Play:</b>\n\n"
               "1️⃣ <b>Start:</b> Type <code>/new</code> in a group.\n"
               "2️⃣ <b>Search:</b> Look at the image grid carefully.\n"
               "3️⃣ <b>Solve:</b> Click 'Found It' & type the word.\n\n"
               "<b>🏆 Scoring Rules:</b>\n"
               "• First Word: +3 Pts\n"
               "• Normal Word: +2 Pts\n"
               "• Last Word: +5 Pts")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        success = safe_edit_message(txt, cid, mid, reply_markup=markup)
        if not success:
            bot.answer_callback_query(c.id, "❌ Could not open play help.", show_alert=True)
        else:
            bot.answer_callback_query(c.id, "Opened.", show_alert=False)
        return

    if data == 'help_cmd':
        txt = ("<b>🤖 Command List:</b>\n\n"
               "/start, /help - Open menu\n"
               "/ping - Check bot ping\n"
               "/new - Start a game\n"
               "/new_hard - Start hard game\n               /hint - Buy hint (-50)\n"
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
               "/addpoints <username_or_id> <amount> (Owner)")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        success = safe_edit_message(txt, cid, mid, reply_markup=markup)
        if not success:
            bot.answer_callback_query(c.id, "❌ Could not open commands.", show_alert=True)
        return

    if data == 'menu_lb':
        top = db.get_top_players(10)
        txt = "🏆 <b>Global Leaderboard</b>\n\n"
        for idx, (name, score) in enumerate(top, 1):
            txt += f"{idx}. <b>{html.escape(name)}</b> : {score} pts\n"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        safe_edit_message(txt, cid, mid, reply_markup=markup)
        return

    if data == 'menu_stats' or data == 'menu_back':
        txt = (f"👋 <b>Welcome Back!</b>\nSelect an option below.")
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'),
                   InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'))
        markup.add(InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'),
                   InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'))
        markup.add(InlineKeyboardButton("🐞 Report Issue", callback_data='open_issue'),
                   InlineKeyboardButton("💳 Buy Points", callback_data='open_plans'))
        markup.add(InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
                   InlineKeyboardButton("🔄 Check Join", callback_data='check_join'))
        safe_edit_message(txt, cid, mid, reply_markup=markup)
        return

    # Game callbacks: guess, hint, score
    if data == 'game_guess':
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ Game Over or Expired.", show_alert=True)
            return
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
            bot.answer_callback_query(c.id, "✍️ Type your guess.", show_alert=False)
        except:
            bot.answer_callback_query(c.id, "❌ Could not open input.", show_alert=True)
        return

    if data == 'game_hint':
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        user_data = db.get_user(uid, c.from_user.first_name)
        if user_data and user_data[6] < HINT_COST:
            bot.answer_callback_query(c.id, f"❌ Need {HINT_COST} pts. Balance: {user_data[6]}", show_alert=True)
            return
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            return
        reveal = random.choice(hidden)
        db.update_stats(uid, score_delta=0, hint_delta=-HINT_COST)
        bot.answer_callback_query(c.id, f"💡 HINT: {reveal}", show_alert=True)
        bot.send_message(cid, f"💡 <b>HINT:</b> <code>{reveal}</code>\nUser: {html.escape(c.from_user.first_name)} (-{HINT_COST} pts)")
        return

    if data == 'game_score':
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        game = games[cid]
        if not game.players_scores:
            bot.answer_callback_query(c.id, "No scores yet. Be the first!", show_alert=True)
            return
        leaderboard = sorted(game.players_scores.items(), key=lambda x: x[1], reverse=True)
        txt = "📊 <b>Session Leaderboard</b>\n\n"
        for idx, (uid_score, pts) in enumerate(leaderboard, 1):
            try:
                user = db.get_user(uid_score, "Player")
                name = user[1] if user else str(uid_score)
            except:
                name = str(uid_score)
            medal = "🥇" if idx==1 else "🥈" if idx==2 else "🥉" if idx==3 else f"{idx}."
            txt += f"{medal} <b>{html.escape(name)}</b> - {pts} pts\n"
        bot.answer_callback_query(c.id, txt, show_alert=True)
        return

# ==========================================
# 🎮 GAME COMMANDS
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

    # Generate Grid Image
    img_bio = GridRenderer.draw(session.grid, is_hard)
    # Ensure pointer at start
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

    # Try sending BytesIO directly; if it fails, write a temp file and send that
    try:
        bot.send_photo(cid, img_bio, caption=caption, reply_markup=markup)
    except Exception as e:
        logger.exception("send_photo with BytesIO failed, trying temp file fallback")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tf:
                tf.write(img_bio.getvalue())
                temp_path = tf.name
            with open(temp_path, 'rb') as f:
                bot.send_photo(cid, f, caption=caption, reply_markup=markup)
            try:
                os.unlink(temp_path)
            except:
                pass
        except Exception as e2:
            logger.exception("fallback send_photo failed")
            # Last resort: send text
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

# (other commands remain — omitted in this paste for brevity but are unchanged)

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
        except: pass
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
            points = 2
            if len(game.found) == 1: points = 3
            if len(game.found) == len(game.words): points = 5
            prev = game.players_scores.get(uid, 0)
            game.players_scores[uid] = prev + points
            db.update_stats(uid, score_delta=points)
            reply = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(user_name)} found <code>{word}</code> (+{points} pts) 🎯")
            threading.Timer(5, lambda: bot.delete_message(cid, reply.message_id)).start()
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
