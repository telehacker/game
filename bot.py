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
# Render environment variable se token lega
TOKEN = os.environ.get('TELEGRAM_TOKEN', '8325630565:AAFKPXU-eMezhm1dG_jAjRcuoLmQe-YGVoU') 
OWNER_ID = 8271254197  # <--- APNA ASLI ID YAHAN DALO

bot = telebot.TeleBot(TOKEN)

# --- FLASK SERVER (For Render Hosting) ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Alive & Running!"
def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- DATABASE SETUP ---
conn = sqlite3.connect('wordsgrid.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users 
             (user_id INTEGER PRIMARY KEY, name TEXT, games_played INTEGER, 
              wins INTEGER, total_score INTEGER, hint_balance INTEGER)''')
conn.commit()

# --- WORD LOADER & BAD WORD FILTER ---
ALL_WORDS = []
BAD_WORDS = ["SEX", "PORN", "NUDE", "XXX", "DICK", "COCK", "PUSSY", "FUCK", "SHIT", "BITCH", "ASS", "HENTAI"] 

def load_words():
    global ALL_WORDS
    try:
        url = "https://www.mit.edu/~ecprice/wordlist.10000"
        resp = requests.get(url)
        content = resp.content.decode("utf-8")
        ALL_WORDS = [w.upper() for w in content.splitlines() if 4 <= len(w) <= 9 and w.upper() not in BAD_WORDS]
        print(f"✅ Loaded {len(ALL_WORDS)} clean words.")
    except:
        ALL_WORDS = ['PHYSICS', 'CHEMISTRY', 'MATHS', 'ROBOT', 'FUTURE', 'SPACE']
threading.Thread(target=load_words).start()

# --- GAME STORAGE ---
games = {} 

# --- HELPER FUNCTIONS ---
def get_user(uid, name):
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users VALUES (?, ?, 0, 0, 0, 100)", (uid, name))
        conn.commit()
        return (uid, name, 0, 0, 0, 100)
    return user

def update_score(uid, pts):
    c.execute("UPDATE users SET total_score=total_score+?, hint_balance=hint_balance+? WHERE user_id=?", (pts, pts, uid))
    conn.commit()

# --- GAME LOGIC ---
def generate_grid(words, size=10):
    grid = [[' ']*size for _ in range(size)]
    dirs = [(0,1), (1,0), (1,1), (0,-1), (-1,0), (-1,-1), (-1,1), (1,-1)]
    words.sort(key=len, reverse=True)
    
    for word in words:
        placed = False
        for _ in range(100):
            r, c = random.randint(0, size-1), random.randint(0, size-1)
            dr, dc = random.choice(dirs)
            if all(0<=r+k*dr<size and 0<=c+k*dc<size and grid[r+k*dr][c+k*dc] in (' ', word[k]) for k in range(len(word))):
                for k in range(len(word)): grid[r+k*dr][c+k*dc] = word[k]
                placed = True; break
    
    for r in range(size):
        for c in range(size):
            if grid[r][c] == ' ': grid[r][c] = random.choice(string.ascii_uppercase)
    return grid

# --- PREMIUM COMMANDS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_name = html.escape(message.from_user.first_name)
    IMG_URL = "https://img.freepik.com/free-vector/word-search-game-background_23-2148066576.jpg" 
    
    txt = (
        f"👋 <b>Hello {user_name}!</b>\n\n"
        "🧩 <b>WORDS GRID ROBOT v2.0</b>\n"
        "The Ultimate Multiplayer Word Search Game.\n\n"
        "🕹 <b>HOW TO PLAY?</b>\n"
        "1. Click <b>'New Game'</b>.\n"
        "2. Find hidden words (e.g. <code>Q•••N</code>).\n"
        "3. Click <b>'Found It!'</b> & type word.\n"
        "4. Win Points! (⏳ 5 Mins Limit)\n\n"
        "👇 <b>MAIN MENU:</b>"
    )
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🎮 New Game", callback_data='btn_new'),
               InlineKeyboardButton("🔥 Hard Mode", callback_data='btn_hard'))
    markup.add(InlineKeyboardButton("📊 My Stats", callback_data='btn_stats'),
               InlineKeyboardButton("🏆 Leaderboard", callback_data='btn_lb'))
    markup.add(InlineKeyboardButton("🏅 Achievements", callback_data='btn_ach'),
               InlineKeyboardButton("💰 Balance", callback_data='btn_bal'))
    markup.add(InlineKeyboardButton("👨‍💻 Developer (Ruhvaan)", url="https://t.me/Ruhvaan"))
    
    try:
        bot.send_photo(message.chat.id, IMG_URL, caption=txt, parse_mode='HTML', reply_markup=markup)
    except:
        bot.reply_to(message, txt, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('btn_'))
def menu_callbacks(call):
    call.message.from_user = call.from_user 
    if call.data == 'btn_new':
        call.message.text = "/new"
        new_game(call.message)
    elif call.data == 'btn_hard':
        call.message.text = "/new_hard"
        new_game(call.message)
    elif call.data == 'btn_stats':
        stats(call.message)
    elif call.data == 'btn_lb':
        lb(call.message)
    elif call.data == 'btn_ach':
        achievements(call.message)
    elif call.data == 'btn_bal':
        balance(call.message)
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['new', 'new_hard'])
def new_game(m):
    cid = m.chat.id
    if cid in games:
        if time.time() - games[cid]['start_time'] < 300: 
            bot.reply_to(m, "⚠️ Game already running! Finish it or /endgame.")
            return

    if not ALL_WORDS: return bot.reply_to(m, "⚠️ System Booting... Try in 10s.")
    
    is_hard = 'hard' in m.text or 'Hard' in m.text
    size, count = (12, 10) if is_hard else (10, 6)
    words = random.sample(ALL_WORDS, count)
    grid = generate_grid(words, size)
    
    # --- SMART RANDOM HIDING ---
    display_list = []
    for w in words:
        safe_w = html.escape(w)
        length = len(safe_w)
        num_visible = max(1, int(length * 0.4)) 
        visible_indices = random.sample(range(length), num_visible)
        
        masked = ""
        for i in range(length):
            if i in visible_indices: masked += f"<b>{safe_w[i]}</b>"
            else: masked += "•"
        display_list.append(masked)
    
    safe_display = "  |  ".join(display_list)
    
    games[cid] = {
        'grid': grid, 'words': words, 'found': set(), 
        'mode': 'Hard' if is_hard else 'Normal',
        'start_time': time.time()
    }
    
    grid_str = "\n".join(["<code>" + " ".join(row) + "</code>" for row in grid])
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔍 I Found a Word!", callback_data='guess'))
    
    bot.send_message(cid, f"🧩 <b>{games[cid]['mode']} Game!</b> (⏱ 5 Mins)\n\n{grid_str}\n\n📝 <b>Find:</b> {safe_display}", 
                     parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'guess')
def guess_click(call):
    cid = call.message.chat.id
    if cid not in games: return bot.answer_callback_query(call.id, "Game Expired!", show_alert=True)
    if time.time() - games[cid]['start_time'] > 300:
        del games[cid]
        return bot.answer_callback_query(call.id, "⏰ Time's Up!", show_alert=True)

    msg = bot.send_message(cid, f"@{call.from_user.username} Type the word:", reply_markup=ForceReply(selective=True))
    bot.register_next_step_handler(msg, check_word)

def check_word(m):
    cid = m.chat.id
    if cid not in games: return
    
    word = m.text.strip().upper()
    game = games[cid]
    
    if word in game['words'] and word not in game['found']:
        game['found'].add(word)
        get_user(m.from_user.id, m.from_user.first_name)
        update_score(m.from_user.id, 10)
        
        reply = bot.reply_to(m, f"✨ <b>Excellent!</b> {html.escape(m.from_user.first_name)} found <code>{word}</code> (+10 pts) 🎯", parse_mode='HTML')
        
        try:
            threading.Timer(5.0, lambda: bot.delete_message(cid, reply.message_id)).start()
            bot.delete_message(cid, m.message_id) 
        except: pass
        
        if len(game['found']) == len(game['words']):
            c.execute("UPDATE users SET wins=wins+1 WHERE user_id=?", (m.from_user.id,))
            conn.commit()
            bot.send_message(cid, f"🎉 <b>GAME WON!</b>\nWinner: {html.escape(m.from_user.first_name)} (+50 Bonus) 🏆", parse_mode='HTML')
            del games[cid]

@bot.message_handler(commands=['issue'])
def issue(m):
    issue_txt = m.text.replace("/issue", "").strip()
    if not issue_txt: return bot.reply_to(m, "Usage: `/issue My issue here`")
    
    if OWNER_ID and isinstance(OWNER_ID, int):
        bot.send_message(OWNER_ID, f"🚨 <b>ISSUE</b>\n👤: {m.from_user.first_name}\n💬: {issue_txt}", parse_mode='HTML')
        bot.reply_to(m, "✅ Sent to Ruhvaan!")
    else:
        bot.reply_to(m, "❌ Config Error.")

@bot.message_handler(commands=['hint'])
def hint(m):
    cid = m.chat.id
    if cid not in games: return bot.reply_to(m, "Start game first.")
    u = get_user(m.from_user.id, m.from_user.first_name)
    if u[5] < 50: return bot.reply_to(m, f"❌ Need 50 pts. (Bal: {u[5]})")
    
    hidden = [w for w in games[cid]['words'] if w not in games[cid]['found']]
    if hidden:
        c.execute("UPDATE users SET hint_balance=hint_balance-50 WHERE user_id=?", (m.from_user.id,))
        conn.commit()
        bot.reply_to(m, f"💡 Hint: <b>{random.choice(hidden)}</b>", parse_mode='HTML')

@bot.message_handler(commands=['mystats'])
def stats(m):
    u = get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"👤 <b>{html.escape(u[1])}</b>\n🏆 Wins: {u[3]}\n⭐️ Score: {u[4]}\n💰 Hints: {u[5]}", parse_mode='HTML')

@bot.message_handler(commands=['balance'])
def balance(m):
    u = get_user(m.from_user.id, m.from_user.first_name)
    bot.reply_to(m, f"💰 <b>Hint Balance:</b> {u[5]} Points", parse_mode='HTML')

@bot.message_handler(commands=['leaderboard'])
def lb(m):
    c.execute("SELECT name, total_score FROM users ORDER BY total_score DESC LIMIT 10")
    top = c.fetchall()
    txt = "\n".join([f"{i+1}. {r[0]} - {r[1]}" for i,r in enumerate(top)]) if top else "No data."
    bot.reply_to(m, f"🏆 <b>Leaderboard</b>\n{txt}", parse_mode='HTML')

@bot.message_handler(commands=['ping'])
def ping(m):
    s = time.time()
    msg = bot.reply_to(m, "🏓 Pinging...")
    bot.edit_message_text(f"🏓 Pong! {round((time.time()-s)*1000)}ms", m.chat.id, msg.message_id)

@bot.message_handler(commands=['achievements'])
def achievements(m):
    u = get_user(m.from_user.id, m.from_user.first_name)
    wins = u[3]
    badges = []
    if wins >= 1: badges.append("🥉 Beginner")
    if wins >= 10: badges.append("🥈 Pro Player")
    if wins >= 50: badges.append("🥇 Word Master")
    if u[4] > 1000: badges.append("💎 Rich Kid")
    txt = "\n".join(badges) if badges else "Play more to unlock!"
    bot.reply_to(m, f"🏅 <b>Badges:</b>\n{txt}", parse_mode='HTML')

@bot.message_handler(commands=['status'])
def status(m):
    if m.from_user.id != OWNER_ID: return
    c.execute("SELECT COUNT(*) FROM users")
    bot.reply_to(m, f"⚙️ <b>System Status</b>\nActive Games: {len(games)}\nTotal Users: {c.fetchone()[0]}", parse_mode='HTML')

@bot.message_handler(commands=['settings'])
def settings(m):
    if m.from_user.id != OWNER_ID: return
    bot.reply_to(m, "⚙️ <b>Settings:</b>\nOnly Admin can view this.\n- Maintenance: OFF\n- Debug: OFF", parse_mode='HTML')

@bot.message_handler(commands=['define'])
def define(m):
    try:
        word = m.text.split()[1]
        d = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}").json()[0]['meanings'][0]['definitions'][0]['definition']
        bot.reply_to(m, f"📖 <b>{word.upper()}:</b> {d}", parse_mode='HTML')
    except: bot.reply_to(m, "❌ Not found.")

# --- MAIN LOOP ---
if __name__ == '__main__':
    threading.Thread(target=run_web).start()
    print("Bot is Premium & Live! 🚀")
    bot.infinity_polling()
