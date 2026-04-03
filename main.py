import os
import threading
import requests
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ¡SOLO NECESITAMOS TELEGRAM! Cero tokens de Genius.
TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot de Letras Libre y Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- FUNCIONES DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Qué más! Soy tu bot de letras ultrarrápido.\n\n"
        "Dime el nombre de la canción o el artista."
    )

async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    espera = await update.message.reply_text(f"🔍 Buscando '{query}' en la base de datos libre...")
    
    try:
        # Usamos LRCLIB, sin restricciones y muy rápido
        url = f"https://lrclib.net/api/search?q={query}"
        respuesta = requests.get(url).json()
        
        if not respuesta:
            await espera.edit_text("No encontré nada. Intenta escribir 'Artista - Canción'.")
            return

        botones = []
        # Tomamos los primeros 5 resultados que sí tengan letra
        for song in respuesta[:5]:
            if song.get('plainLyrics'):
                # Reducimos el nombre para que el botón no explote
                label = f"{song['trackName']} - {song['artistName']}"[:60]
                botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
        
        if not botones:
            await espera.edit_text("Encontré la canción, pero no tiene la letra registrada todavía. 😕")
            return

        markup = InlineKeyboardMarkup(botones)
        await espera.edit_text("¡Listo! Elige tu canción:", reply_markup=markup)
        
    except Exception as e:
        print(f"Error de conexión: {e}")
        await espera.edit_text("Hubo un problema de conexión. Intenta de nuevo.")

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # Fundamental para destrabar el botón al instante
    await query.answer()

    # CASO 1: Obtener letra
    if data.startswith("ly_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("⏳ Descargando letra...")
        
        try:
            url = f"https://lrclib.net/api/get/{song_id}"
            cancion = requests.get(url).json()
            
            titulo = cancion.get('trackName', 'Desconocido')
            artista = cancion.get('artistName', 'Desconocido')
            letra = cancion.get('plainLyrics', 'Letra no disponible.')
            
            encabezado = f"🎵 {titulo} - {artista}\n\n"
            texto_final = encabezado + letra[:3800] # Evitamos el límite de Telegram
            
            btns = [[InlineKeyboardButton("Analizar Significado (IA) 🧠", callback_data=f"mn_{song_id}")]]
            
            await query.edit_message_text(texto_final, reply_markup=InlineKeyboardMarkup(btns))
            
        except Exception as e:
            print(f"Error cargando letra: {e}")
            await query.edit_message_text("❌ Error al cargar la letra.")

    # CASO 2: Significado de la canción
    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        await query.message.reply_text("🧠 Generando análisis...")
        
        try:
            url = f"https://lrclib.net/api/get/{song_id}"
            cancion = requests.get(url).json()
            titulo = cancion.get('trackName', 'el tema')
            artista = cancion.get('artistName', 'el artista')
            
            # Significado simulado de IA 
            analisis = (
                f"*{titulo}* de *{artista}* es una canción que conecta directamente con las emociones de sus oyentes. "
                "La lírica suele apuntar a vivencias personales, relaciones o críticas sociales, dependiendo del estilo "
                "del álbum. La estructura del tema está diseñada para dejar un mensaje claro entre sus versos."
            )
            
            await query.message.reply_text(f"✨ *Análisis de IA:*\n\n{analisis}", parse_mode="Markdown")
        except:
            await query.message.reply_text("❌ Ocurrió un error al analizar el tema.")

# --- ARRANQUE ---
if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    
    print("Bot de Lyrics Iniciado con Éxito...")
    bot_app.run_polling()
