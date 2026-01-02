import telebot
import random
import string
import requests
import threading
import sqlite3
import time
import os
import html
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- CONFIGURATION ---
# Render environment variable se token lega, fallback ke liye string rakha hai
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8325630565:AAFKPXU-eMezhm1dG_jAjRcuoLmQe-YGVoU') 
OWNER_ID = 8271254197  # Replace with your actual Telegram User ID
bot = telebot.TeleBot(TOKEN)

# --- FLASK SERVER (For Render Port Binding) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- DATABASE SETUP ---
conn = sqlite3.connect('wordsgrid.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (user_id INTEGER PRIMARY KEY, name TEXT, games_played INTEGER, 
              wins INTEGER, total_score INTEGER, hint_balance INTEGER)''')
conn.commit()

# --- WORD LIST LOADER ---
ALL_WORDS = []
def load_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        resp = requests.get(url)
        content = resp.content.decode("utf-8")
        # Filter for words between 4 and 9 letters
        ALL_WORDS = [w.upper() for w in content.splitlines() if 4 <= len(w) <= 9]
        print(f"✅ Loaded {len(ALL_WORDS)} words.")
    except Exception as e:
        print(f"Error loading words: {e}")
        ALL_WORDS = ['PHYSICS', 'CHEMISTRY', 'MATHS', 'PYTHON', 'ROBOT', 'FUTURE']

# --- GAME STORAGE ---
games = {} 

# --- HELPER FUNCTIONS ---
def get_user(user_id, name):
    try:
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        if not user:
            # New user gets 100 hint points
            c.execute("INSERT INTO users VALUES (?, ?, 0, 0, 0, 100)", (user_id, name))
            conn.commit()
            return (user_id, name, 0, 0, 0, 100)
        return user
    except Exception as e:
        print(f"DB Error: {e}")
        return (user_id, name, 0, 0, 0, 100)

def update_score(user_id, points):
    try:
        c.execute("UPDATE users SET total_score = total_score + ?, hint_balance = hint_balance + ? WHERE user_id=?", (points, points, user_id))
        conn.commit()
    except: pass

def use_hint_points(user_id, cost):
    try:
        c.execute("UPDATE users SET hint_balance = hint_balance - ? WHERE user_id=?", (cost, user_id))
        conn.commit()
    except: pass

# --- GAME LOGIC ---
def generate_grid(words, size=10):
    grid = [[' ' for _ in range(size)] for _ in range(size)]
    directions = [(0,1), (1,0), (1,1), (0,-1)] 
    words = sorted(words, key=len, reverse=True)
    
    for word in words:
        placed = False
        attempts = 0
        while not placed and attempts < 100:
            attempts += 1
            row, col = random.randint(0, size-1), random.randint(0, size-1)
            dr, dc = random.choice(directions)
            
            valid = True
            for k in range(len(word)):
                r, c = row + k*dr, col + k*dc
                if not (0 <= r < size and 0 <= c < size) or (grid[r][c] != ' ' and grid[r][c] != word[k]):
                    valid = False
                    break
            
            if valid:
                for k in range(len(word)):
                    grid[row + k*dr][col + k*dc] = word[k]
                placed = True
                
    for r in range(size):
        for c in range(size):
            if grid[r][c] == ' ': grid[r][c] = random.choice(string.ascii_uppercase)
    return grid

# --- COMMANDS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    # Removing Markdown to avoid crashes with underscores
    txt = (
        "🎮 Words Grid Bot Help Menu\n\n"
        "🕹 Game Commands:\n"
        "/new - Start new game\n"
        "/new_hard - Start Hard Mode (12x12)\n"
        "/endgame - Stop current game\n"
        "/hint - Get a hint (Cost: 50 pts)\n\n"
        "📊 Stats & Tools:\n"
        "/mystats - Your profile stats\n"
        "/leaderboard - Top players\n"
        "/balance - Check hint points\n"
        "/achievements - Your badges\n"
        "/define <word> - Get definition\n\n"
        "⚙️ System:\n"
        "/ping - Check bot speed\n"
        "/issue <msg> - Report bug\n"
        "/status - Bot health (Owner only)"
    )
    bot.reply_to(message, txt)

@bot.message_handler(commands=['ping'])
def ping(message):
    start = time.time()
    msg = bot.reply_to(message, "🏓 Pinging...")
    end = time.time()
    bot.edit_message_text(f"🏓 Pong! Latency: {round((end-start)*1000)}ms", message.chat.id, msg.message_id)

@bot.message_handler(commands=['new', 'new_hard'])
def new_game(message):
    chat_id = message.chat.id
    is_hard = 'hard' in message.text
    size = 12 if is_hard else 10
    count = 10 if is_hard else 6
    
    if not ALL_WORDS:
        bot.reply_to(message, "⚠️ System booting... try in 5 seconds.")
        return

    words = random.sample(ALL_WORDS, count)
    grid = generate_grid(words, size)
    
    games[chat_id] = {
        'grid': grid, 'words': words, 'found': set(), 
        'players': {}, 'mode': 'Hard' if is_hard else 'Normal'
    }
    
    # Using HTML for monospaced font (<code>)
    grid_str = ""
    for row in grid:
        grid_str += "<code>" + " ".join(row) + "</code>\n"
    
    # Escaping words just in case
    safe_words = [html.escape(w) for w in words]
    words_display = ", ".join(safe_words)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 I Found a Word!", callback_data='guess'))
    
    msg_text = f"<b>🧩 {games[chat_id]['mode']} Game Started!</b>\n\n{grid_str}\n\n📝 <b>Find:</b> {words_display}"
    
    bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['mystats', 'balance', 'scorecard'])
def my_stats(message):
    uid = message.from_user.id
    user = get_user(uid, message.from_user.first_name)
    # Plain text response is safer
    txt = (
        f"👤 Player Profile: {user[1]}\n"
        f"🎮 Games Played: {user[2]}\n"
        f"🏆 Wins: {user[3]}\n"
        f"💰 Hint Balance: {user[5]} pts\n"
        f"⭐️ Total Score: {user[4]}"
    )
    bot.reply_to(message, txt)

@bot.message_handler(commands=['leaderboard'])
def leaderboard(message):
    try:
        c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT 10")
        top = c.fetchall()
        if not top:
            bot.reply_to(message, "No data yet.")
            return
        
        txt = "🏆 Global Leaderboard\n\n" + "\n".join([f"{i+1}. {r[0]} - {r[1]} pts" for i, r in enumerate(top)])
        bot.reply_to(message, txt)
    except:
        bot.reply_to(message, "Error fetching leaderboard.")

@bot.message_handler(commands=['hint'])
def get_hint(message):
    chat_id = message.chat.id
    uid = message.from_user.id
    
    if chat_id not in games:
        return bot.reply_to(message, "❌ No active game.")
        
    user = get_user(uid, message.from_user.first_name)
    if user[5] < 50:
        return bot.reply_to(message, f"❌ Not enough points! You have {user[5]}, need 50.")
    
    game = games[chat_id]
    hidden = [w for w in game['words'] if w not in game['found']]
    if not hidden:
        return bot.reply_to(message, "All words found already!")
        
    reveal = random.choice(hidden)
    use_hint_points(uid, 50)
    bot.reply_to(message, f"💡 HINT: Look for the word: {reveal} (-50 pts)")

@bot.message_handler(commands=['define'])
def define_word(message):
    try:
        if len(message.text.split()) < 2:
             bot.reply_to(message, "Use format: /define <word>")
             return
        word = message.text.split()[1]
        resp = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        data = resp.json()
        definition = data[0]['meanings'][0]['definitions'][0]['definition']
        bot.reply_to(message, f"📖 {word.upper()}: {definition}")
    except:
        bot.reply_to(message, "❌ Definition not found.")

@bot.message_handler(commands=['achievements'])
def achievements(message):
    uid = message.from_user.id
    user = get_user(uid, message.from_user.first_name)
    wins = user[3]
    
    badges = []
    if wins >= 1: badges.append("🥉 Beginner")
    if wins >= 10: badges.append("🥈 Pro Player")
    if wins >= 50: badges.append("🥇 Word Master")
    if user[4] > 1000: badges.append("💎 Rich Kid")
    
    txt = f"🏅 Achievements for {user[1]}\n\n" + ("\n".join(badges) if badges else "No badges yet. Keep playing!")
    bot.reply_to(message, txt)

@bot.message_handler(commands=['status'])
def system_status(message):
    if message.from_user.id != OWNER_ID: return
    c.execute("SELECT COUNT(*) FROM users")
    users_count = c.fetchone()[0]
    bot.reply_to(message, f"⚙️ System Status\nActive Games: {len(games)}\nTotal Users: {users_count}\nDatabase: Online")

@bot.message_handler(commands=['issue'])
def report_issue(message):
    issue = message.text.replace("/issue", "").strip()
    if issue:
        # Check if OWNER_ID is set
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"🚨 Issue Report\nFrom: {message.from_user.first_name}\nIssue: {issue}")
        bot.reply_to(message, "✅ Report sent to developer!")
    else:
        bot.reply_to(message, "Write issue after command. Ex: `/issue Bot is slow`")

@bot.message_handler(commands=['endgame'])
def end_game(message):
    chat_id = message.chat.id
    if chat_id in games:
        del games[chat_id]
        bot.reply_to(message, "🛑 Game stopped.")
    else:
        bot.reply_to(message, "No active game.")

# --- CALLBACKS & GAMEPLAY ---
@bot.callback_query_handler(func=lambda call: call.data == 'guess')
def guess_callback(call):
    msg = bot.send_message(call.message.chat.id, f"@{call.from_user.username} Type the word:", reply_markup=ForceReply(selective=True))
    bot.register_next_step_handler(msg, check_word_logic)

def check_word_logic(message):
    chat_id = message.chat.id
    if chat_id not in games: return
    
    word = message.text.strip().upper()
    game = games[chat_id]
    
    # Ensure user exists in DB before updating score
    get_user(message.from_user.id, message.from_user.first_name)
    
    if word in game['words'] and word not in game['found']:
        game['found'].add(word)
        # Update Score: +10 pts for finding word
        update_score(message.from_user.id, 10)
        
        # Use HTML for bold text to avoid underscore errors
        safe_name = html.escape(message.from_user.first_name)
        bot.reply_to(message, f"✅ <b>{word} Found!</b> (+10 pts)", parse_mode='HTML')
        
        if len(game['found']) == len(game['words']):
            c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (message.from_user.id,))
            conn.commit()
            bot.send_message(chat_id, f"🎉 <b>GAME OVER!</b>\nWinner: {safe_name}\n+50 Bonus Points!", parse_mode='HTML')
            del games[chat_id]

# --- MAIN EXECUTION ---
if __name__ == '__main__':
    # 1. Load Words
    t1 = threading.Thread(target=load_words)
    t1.start()
    
    # 2. Start Web Server (For Render)
    t2 = threading.Thread(target=run_web_server)
    t2.start()
    
    # 3. Start Bot Polling
    print("Bot Started...")
    bot.infinity_polling()
