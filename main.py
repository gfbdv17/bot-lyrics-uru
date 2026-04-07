import os
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot de Lyrics + Letras.com Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- EL RASTREADOR DE LETRAS.COM ---
def extraer_significado_letras(artista, cancion):
    try:
        # Letras.com usa URLs con guiones en vez de espacios
        art_fmt = artista.lower().replace(" ", "-").replace("'", "")
        can_fmt = cancion.lower().replace(" ", "-").replace("'", "")
        url = f"https://www.letras.com/{art_fmt}/{can_fmt}/"
        
        # Nos disfrazamos de navegador para que no nos bloqueen de inmediato
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            significado = ""
            
            # Buscamos en la página web algún subtítulo que diga "Significado"
            for tag in soup.find_all(['h2', 'h3']):
                if tag.text and 'significado' in tag.text.lower():
                    # Si lo encontramos, nos robamos el bloque de texto que le sigue
                    cuerpo = tag.find_next_sibling('div')
                    if cuerpo:
                        significado = cuerpo.text.strip()
                        break
            
            if significado:
                return significado[:3800]
            else:
                return f"Revisé Letras.com a fondo, pero los editores no le han escrito un significado oficial a '{cancion}'."
        else:
            return "No pude encontrar la página exacta de esta canción en Letras.com."
    except Exception as e:
        return "Hubo un error raspando Letras.com. (A veces sus servidores bloquean a los bots 🚧)."

# --- LÓGICA DE TELEGRAM ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Epa! Soy tu bot de Letras y ahora busco significados reales en Letras.com.\n\nDime la canción.")

async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    espera = await update.message.reply_text("🔍 Buscando...")
    
    try:
        # Seguimos usando LRCLIB para la búsqueda porque no falla nunca
        respuesta = requests.get(f"https://lrclib.net/api/search?q={query}").json()
        if not respuesta:
            await espera.edit_text("No encontré nada. Intenta 'Artista - Canción'.")
            return

        botones = []
        for song in respuesta[:5]:
            if song.get('plainLyrics'):
                label = f"{song['trackName']} - {song['artistName']}"[:60]
                botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
        
        if not botones:
            await espera.edit_text("La canción no tiene letra registrada.")
            return

        await espera.edit_text("Elige tu canción:", reply_markup=InlineKeyboardMarkup(botones))
    except:
        await espera.edit_text("Error de conexión.")

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("ly_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("⏳ Descargando letra...")
        try:
            cancion = requests.get(f"https://lrclib.net/api/get/{song_id}").json()
            titulo = cancion.get('trackName', 'Desconocido')
            artista = cancion.get('artistName', 'Desconocido')
            letra = cancion.get('plainLyrics', 'No disponible.')
            
            texto_final = f"🎵 {titulo} - {artista}\n\n{letra[:3800]}"
            btns = [[InlineKeyboardButton("Buscar Significado en Letras.com 🔎", callback_data=f"mn_{song_id}")]]
            await query.edit_message_text(texto_final, reply_markup=InlineKeyboardMarkup(btns))
        except:
            await query.edit_message_text("❌ Error al cargar letra.")

    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        await query.message.reply_text("🔎 Viajando a Letras.com para extraer el significado...")
        try:
            cancion = requests.get(f"https://lrclib.net/api/get/{song_id}").json()
            artista = cancion.get('artistName', '')
            titulo = cancion.get('trackName', '')
            
            # Llamamos a nuestra función raspa-páginas
            significado = extraer_significado_letras(artista, titulo)
            await query.message.reply_text(f"✨ *Desde Letras.com:*\n\n{significado}", parse_mode="Markdown")
        except Exception as e:
            await query.message.reply_text("❌ Ocurrió un error consultando Letras.com.")

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    bot_app.run_polling()
