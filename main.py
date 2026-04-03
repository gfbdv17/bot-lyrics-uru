import os, threading, lyricsgenius, json
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN_TG = os.getenv("TELEGRAM_BOT_TOKEN")
TOKEN_GS = os.getenv("GENIUS_ACCESS_TOKEN")
genius = lyricsgenius.Genius(TOKEN_GS)

app = Flask('')
@app.route('/')
def home(): return "Lyrics Bot Online!"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Habla Gianfi! Dime qué canción buscas.")

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    msg = await update.message.reply_text(f"Buscando '{query}'...")
    res = genius.search_songs(query, per_page=5)
    if not res['hits']:
        await msg.edit_text("No encontré nada. Prueba con 'Artista - Canción'.")
        return
    btns = [[InlineKeyboardButton(h['result']['full_title'], callback_data=f"ly_{h['result']['id']}")] for h in res['hits']]
    await msg.edit_text("Elige la opción correcta:", reply_markup=InlineKeyboardMarkup(btns))

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("ly_"):
        sid = q.data.split("_")[1]
        s = genius.song(sid)['song']
        l = genius.lyrics(song_id=sid)
        txt = f"🎵 *{s['full_title']}*\n\n{l[:3500]}"
        btns = [[InlineKeyboardButton("Analizar Significado 🧠", callback_data=f"mn_{sid}")]]
        await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")
    elif q.data.startswith("mn_"):
        sid = q.data.split("_")[1]
        s = genius.song(sid)['song']
        # Simulación de IA (puedes mejorar esto luego con Gemini)
        desc = f"La canción *{s['title']}* es una pieza clave de *{s['primary_artist']['name']}*. "
        desc += "Explora sentimientos profundos que han resonado mucho en la cultura actual."
        await q.message.reply_text(f"🧠 *Análisis de IA:*\n\n{desc}", parse_mode="Markdown")

if __name__ == '__main__':
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    bot = Application.builder().token(TOKEN_TG).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar))
    bot.add_handler(CallbackQueryHandler(callback))
    bot.run_polling()
