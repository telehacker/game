"""
WORDS GRID ROBOT - ULTIMATE PREMIUM EDITION
Version: 5.0 (Enterprise)
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

# ==========================================
# ⚙️ CONFIGURATION & SETUP
# ==========================================

# Initialize Flask App (YE LINE MISSING THI YA NEECHE THI)
app = Flask(__name__)

# Environment Variables (Render Friendly)
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8208557623:AAHWSJEYb57_OblzITT9jHAgvtu_vyGraaY')
OWNER_ID = int(os.environ.get('OWNER_ID', 8271254197)) # Apna Numeric ID dalein
CHANNEL_USERNAME = os.environ.get('CHANNEL_USERNAME', '@Ruhvaan_Updates') # E.g., @Ruhvaan_Updates
FORCE_JOIN = True # Set False to disable force join

# Initialize Bot
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
BAD_WORDS = ["SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI", "BOOBS"]
GAME_DURATION = 600 # 10 Minutes
COOLDOWN = 2 # Seconds between guesses

# ==========================================
# 🗄️ DATABASE MANAGER (Robust SQLite)
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
        # User Table
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
        # Game History (For Analytics)
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
            c.execute("INSERT INTO users VALUES (?, ?, ?, 0, 0, 0, 100, 0)", (user_id, name, join_date))
            conn.commit()
            user = (user_id, name, join_date, 0, 0, 0, 100, 0)
        conn.close()
        return user

    def update_stats(self, user_id, score_delta=0, hint_delta=0, win=False):
        conn = self.connect()
        c = conn.cursor()
        c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", 
                  (score_delta, hint_delta, user_id))
        if win:
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
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

db = DatabaseManager()

# ==========================================
# 🎨 ADVANCED IMAGE GENERATOR
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
        cols = len(grid[0])
        
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
            # Render/Linux paths usually have these
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if not os.path.exists(font_path): font_path = "arial.ttf" # Fallback for local
            
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
        # Smart Filter: 4-9 chars, alpha only, no bad words
        ALL_WORDS = [w for w in raw_words if 4 <= len(w) <= 9 and w.isalpha() and w not in BAD_WORDS]
        logger.info(f"Loaded {len(ALL_WORDS)} words.")
    except Exception as e:
        logger.error(f"Word Fetch Error: {e}")
        ALL_WORDS = ['PYTHON', 'JAVA', 'SCRIPT', 'ROBOT', 'FUTURE', 'SPACE', 'GALAXY', 'NEBULA']

# Initial Load
fetch_words()

games = {} # Session Storage

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
        self.players_scores = {} # Temporary session scores
        
        self.generate()

    def generate(self):
        if not ALL_WORDS: fetch_words()
        self.words = random.sample(ALL_WORDS, self.word_count)
        self.grid = [[' ' for _ in range(self.size)] for _ in range(self.size)]
        
        # Directions: N, S, E, W, NE, NW, SE, SW
        dirs = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]
        sorted_words = sorted(self.words, key=len, reverse=True)
        
        for word in sorted_words:
            placed = False
            attempts = 0
            while not placed and attempts < 100:
                attempts += 1
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)
                dr, dc = random.choice(dirs)
                
                if self._can_place(row, col, dr, dc, word):
                    self._place(row, col, dr, dc, word)
                    placed = True
        
        # Fill empty
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
        # Format: W--- (4)
        hints = []
        for w in self.words:
            if w in self.found:
                hints.append(f"✅ <s>{w}</s>")
            else:
                masked = w[0] + ("-" * (len(w)-1))
                hints.append(f"<code>{masked}</code> ({len(w)})")
        return "\n".join(hints)

# ==========================================
# 🛡️ MIDDLEWARE & UTILS
# ==========================================
def is_subscribed(user_id):
    if not FORCE_JOIN: return True
    if user_id == OWNER_ID: return True
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['creator', 'administrator', 'member']
    except:
        return True # Fail safe: allow if check fails

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

# ==========================================
# 🎮 TELEGRAM HANDLERS (UI LAYER)
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def show_main_menu(m):
    user = db.get_user(m.from_user.id, m.from_user.first_name)
    
    # Premium Welcome Message
    txt = (f"👋 <b>Hello, {html.escape(m.from_user.first_name)}!</b>\n\n"
           "🧩 <b>Welcome to Word Vortex</b>\n"
           "The most advanced multiplayer word search bot on Telegram.\n\n"
           "👇 <b>What would you like to do?</b>")
    
    markup = InlineKeyboardMarkup(row_width=2)
    # Row 1
    markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'),
               InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'))
    # Row 2
    markup.add(InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'),
               InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'))
    # Row 3
    # SUPPORT_GROUP_LINK may be defined elsewhere in your code/environment
    try:
        markup.add(InlineKeyboardButton("👨‍💻 Support / Issue", url=SUPPORT_GROUP_LINK))
    except:
        markup.add(InlineKeyboardButton("👨‍💻 Support / Issue", url="https://t.me/Ruhvaan"))

    # Send as Photo if possible, else text
    try:
        IMG_URL = "https://img.freepik.com/free-vector/word-search-game-background_23-2148066576.jpg"
        bot.send_photo(m.chat.id, IMG_URL, caption=txt, reply_markup=markup)
    except:
        bot.reply_to(m, txt, reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    cid = c.message.chat.id
    mid = c.message.message_id
    uid = c.from_user.id
    
    # Join Check
    if c.data == "check_join":
        if is_subscribed(uid):
            bot.answer_callback_query(c.id, "✅ Verified! Welcome.", show_alert=True)
            bot.delete_message(cid, mid)
            show_main_menu(c.message)
        else:
            bot.answer_callback_query(c.id, "❌ You haven't joined yet!", show_alert=True)
        return

    # Main Menu Navigation
    if c.data == 'help_play':
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
        bot.edit_message_caption(txt, cid, mid, reply_markup=markup)
        
    elif c.data == 'help_cmd':
        txt = ("<b>🤖 Command List:</b>\n\n"
               "<b>Game:</b>\n"
               "• <code>/new</code> - Start Normal Game\n"
               "• <code>/new_hard</code> - Start Hard Game\n"
               "• <code>/hint</code> - Buy Hint (50 pts)\n"
               "• <code>/endgame</code> - Force Stop\n\n"
               "<b>Profile:</b>\n"
               "• <code>/mystats</code> - View Profile\n"
               "• <code>/leaderboard</code> - Top 10\n"
               "• <code>/balance</code> - Check Points\n\n"
               "<b>Admin:</b>\n"
               "• <code>/admin</code> - Admin Panel")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        bot.edit_message_caption(txt, cid, mid, reply_markup=markup)

    elif c.data == 'menu_lb':
        top = db.get_top_players(10)
        txt = "🏆 <b>Global Leaderboard</b>\n\n"
        for idx, (name, score) in enumerate(top, 1):
            txt += f"{idx}. <b>{html.escape(name)}</b> : {score} pts\n"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔙 Back", callback_data='menu_back'))
        bot.edit_message_caption(txt, cid, mid, reply_markup=markup)

    elif c.data == 'menu_back':
        txt = f"👋 <b>Welcome Back!</b>\nSelect an option below."
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton("🎮 Play Game", callback_data='help_play'),
                   InlineKeyboardButton("🤖 Commands", callback_data='help_cmd'))
        markup.add(InlineKeyboardButton("🏆 Leaderboard", callback_data='menu_lb'),
                   InlineKeyboardButton("👤 My Stats", callback_data='menu_stats'))
        markup.add(InlineKeyboardButton("👨‍💻 Support", url="https://t.me/Ruhvaan"))
        
        bot.edit_message_caption(txt, cid, mid, reply_markup=markup)

    # Game callbacks (placed inside the same handler so elifs are valid)
    elif c.data == 'game_guess':
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ Game Over or Expired.", show_alert=True)
            return
        # Force Reply for typing
        try:
            username = c.from_user.username or c.from_user.first_name
            msg = bot.send_message(cid, f"@{username} Type the word now:", reply_markup=ForceReply(selective=True))
            bot.register_next_step_handler(msg, process_word_guess)
        except Exception:
            bot.answer_callback_query(c.id, "❌ Could not start input.", show_alert=True)
        
    elif c.data == 'game_hint':
        if cid not in games:
            bot.answer_callback_query(c.id, "❌ No active game.", show_alert=True)
            return
        user_data = db.get_user(uid, c.from_user.first_name)
        if user_data[6] < 50:
            bot.answer_callback_query(c.id, f"❌ Need 50 pts. Balance: {user_data[6]}", show_alert=True)
            return
        
        game = games[cid]
        hidden = [w for w in game.words if w not in game.found]
        if not hidden:
            bot.answer_callback_query(c.id, "All words found!", show_alert=True)
            return
            
        reveal = random.choice(hidden)
        db.update_stats(uid, score_delta=0, hint_delta=-50)
        bot.answer_callback_query(c.id, f"💡 HINT: Look for '{reveal}'", show_alert=True)
        bot.send_message(cid, f"💡 <b>HINT REVEALED!</b>\nWord: <code>{reveal}</code>\nUser: {html.escape(c.from_user.first_name)} (-50 pts)")

# ==========================================
# 🎮 GAME COMMANDS
# ==========================================

@bot.message_handler(commands=['new', 'new_hard'])
@require_subscription
def start_game(m):
    cid = m.chat.id
    
    # Check Active Game
    if cid in games:
        if time.time() - games[cid].last_activity < GAME_DURATION:
            bot.reply_to(m, "⚠️ A game is already active here! Finish it or use /endgame.")
            return
    
    # Check Ban
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    if u[7] == 1: # is_banned
        bot.reply_to(m, "🚫 You are banned from playing.")
        return

    bot.send_chat_action(cid, 'upload_photo')
    is_hard = 'hard' in m.text
    
    # Initialize Game
    session = GameSession(cid, is_hard)
    games[cid] = session
    
    # Generate Grid Image
    img_bio = GridRenderer.draw(session.grid, is_hard)
    
    # Caption
    caption = (f"🔥 <b>WORD VORTEX STARTED!</b>\n"
               f"Mode: {'Hard (10x10)' if is_hard else 'Normal (8x8)'}\n"
               f"⏱ Time Limit: 10 Minutes\n\n"
               f"<b>👇 WORDS TO FIND:</b>\n"
               f"{session.get_hint_text()}")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 Found It!", callback_data='game_guess'))
    markup.add(InlineKeyboardButton("💡 Hint (-50)", callback_data='game_hint'),
               InlineKeyboardButton("📊 Score", callback_data='game_score'))
    
    bot.send_photo(cid, img_bio, caption=caption, reply_markup=markup)

def process_word_guess(m):
    cid = m.chat.id
    if cid not in games: return
    
    word = m.text.strip().upper()
    game = games[cid]
    uid = m.from_user.id
    user_name = m.from_user.first_name
    
    # Anti-Spam / Cleanup
    try: bot.delete_message(cid, m.message_id)
    except: pass
    
    if word in game.words:
        if word in game.found:
            msg = bot.send_message(cid, f"⚠️ <b>{word}</b> is already found!")
            threading.Timer(3, lambda: bot.delete_message(cid, msg.message_id)).start()
        else:
            # Correct Guess
            game.found.add(word)
            game.last_activity = time.time()
            
            # Scoring Logic
            points = 2
            if len(game.found) == 1: points = 3 # First Blood
            if len(game.found) == len(game.words): points = 5 # Finisher
            
            db.update_stats(uid, score_delta=points)
            
            reply = bot.send_message(cid, f"✨ <b>Excellent!</b> {html.escape(user_name)} found <code>{word}</code> (+{points} pts) 🎯")
            threading.Timer(5, lambda: bot.delete_message(cid, reply.message_id)).start()
            
            # Check Win
            if len(game.found) == len(game.words):
                end_game_session(cid, "win", uid)
    else:
        # Wrong Guess (Optional: Penalty?)
        pass

def end_game_session(cid, reason, winner_id=None):
    if cid not in games: return
    game = games[cid]
    
    if reason == "win":
        winner = db.get_user(winner_id, "Unknown")
        db.update_stats(winner_id, win=True) # Add win count
        txt = (f"🏆 <b>GAME OVER! VICTORY!</b>\n\n"
               f"👑 <b>MVP:</b> {html.escape(winner[1])}\n"
               f"✅ All {len(game.words)} words found!\n\n"
               f"Type <code>/new</code> to play again.")
        bot.send_message(cid, txt)
    
    elif reason == "stopped":
        bot.send_message(cid, "🛑 Game stopped manually.")
        
    del games[cid]

# ==========================================
# 🛠 ADMIN & UTILITY COMMANDS
# ==========================================

@bot.message_handler(commands=['issue'])
def report_issue(m):
    issue = m.text.replace("/issue", "").strip()
    if not issue:
        bot.reply_to(m, "Usage: `/issue <message>`")
        return
    
    if OWNER_ID:
        try:
            bot.send_message(OWNER_ID, f"🚨 <b>REPORT</b>\nFROM: {m.from_user.first_name} ({m.from_user.id})\nMSG: {issue}")
            bot.reply_to(m, "✅ Report sent to Developer.")
        except:
            bot.reply_to(m, "❌ Could not send. Join support chat.")

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if m.from_user.id != OWNER_ID: return
    
    txt = (f"⚙️ <b>ADMIN PANEL</b>\n"
           f"Users: {len(db.get_all_users())}\n"
           f"Active Games: {len(games)}\n\n"
           "<b>Commands:</b>\n"
           "/broadcast <msg> - Send to all\n"
           "/ban <id> - Ban User\n"
           "/unban <id> - Unban User\n"
           "/add_points <id> <amount>")
    bot.reply_to(m, txt)

@bot.message_handler(commands=['broadcast'])
def broadcast(m):
    if m.from_user.id != OWNER_ID: return
    msg = m.text.replace("/broadcast", "").strip()
    if not msg: return
    
    users = db.get_all_users()
    count = 0
    for uid in users:
        try:
            bot.send_message(uid, f"📢 <b>ANNOUNCEMENT:</b>\n\n{msg}")
            count += 1
            time.sleep(0.05) # Rate limit safety
        except: pass
    bot.reply_to(m, f"✅ Sent to {count} users.")

@bot.message_handler(commands=['mystats'])
def my_stats(m):
    u = db.get_user(m.from_user.id, m.from_user.first_name)
    txt = (f"👤 <b>PROFILE: {html.escape(u[1])}</b>\n"
           f"🆔 ID: <code>{u[0]}</code>\n"
           f"📅 Joined: {u[2]}\n"
           f"-------------------\n"
           f"🏆 Wins: {u[4]}\n"
           f"⭐️ Score: {u[5]}\n"
           f"💰 Balance: {u[6]}")
    bot.reply_to(m, txt)

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
        # Check permissions (Admin or Starter should ideally do this, but open for now)
        end_game_session(cid, "stopped")
    else:
        bot.reply_to(m, "No active game to stop.")

# ==========================================
# 🚀 SERVER STARTUP
# ==========================================

# Flask Server for Render Keep-Alive
@app.route('/')
def index():
    return "Word Vortex Bot is Running! 🚀"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Start Web Server in Thread
    t = threading.Thread(target=run_flask)
    t.start()
    
    print("✅ System Online. Connected to Telegram.")
    print("✅ Database Loaded.")
    print("✅ Image Engine Ready.")
    
    # Start Polling
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"⚠️ Polling Error: {e}")
            time.sleep(5)
