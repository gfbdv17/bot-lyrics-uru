import os
import threading
import time
import lyricsgenius
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- CONFIGURACIÓN DE APIS ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")
TOKEN_GENIUS = os.getenv("GENIUS_ACCESS_TOKEN")

# Inicializamos Genius (con timeout para que no se quede pegado)
genius = lyricsgenius.Genius(TOKEN_GENIUS, timeout=15, retries=3)

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot de Lyrics URU está Vivo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- FUNCIONES DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Qué más, Gianfi! Soy tu bot de letras y significados.\n\n"
        "Dime el nombre de una canción o artista y te la busco al toque."
    )

async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    espera = await update.message.reply_text(f"🔍 Buscando '{query}' en la base de datos...")
    
    try:
        # Buscamos 5 opciones para que elijas la correcta
        resultados = genius.search_songs(query, per_page=5)
        
        if not resultados or not resultados['hits']:
            await espera.edit_text("No encontré nada con ese nombre. Prueba escribiendo 'Artista Canción'.")
            return

        botones = []
        for hit in resultados['hits']:
            song = hit['result']
            # Limitamos el texto del botón para que Telegram no dé error
            label = f"{song['title']} - {song['primary_artist']['name']}"[:60]
            botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
        
        markup = InlineKeyboardMarkup(botones)
        await espera.edit_text("Encontré estas opciones. Elige la que buscas:", reply_markup=markup)
        
    except Exception as e:
        print(f"Error en búsqueda: {e}")
        await espera.edit_text("Hubo un problema al conectar con Genius. Intenta de nuevo.")

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # IMPORTANTE: Esto quita el relojito de carga del botón de inmediato
    await query.answer()

    # CASO 1: El usuario eligió una canción para ver la letra
    if data.startswith("ly_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("⏳ Cargando letra... esto puede tardar unos segundos.")
        
        try:
            # Obtenemos la canción y la letra
            song = genius.song(song_id)['song']
            lyrics = genius.lyrics(song_id=song_id)
            
            if not lyrics:
                await query.edit_message_text("No pude encontrar la letra detallada para esta canción. 😕")
                return

            # Limpieza básica: Quitamos el 'Embed' y otros textos que Genius mete al final
            lyrics_limpia = lyrics.split('Embed')[0]
            
            # Telegram solo permite 4096 caracteres. Cortamos a 3800 por seguridad.
            encabezado = f"🎵 {song['full_title']}\n\n"
            cuerpo = lyrics_limpia[:3800]
            texto_final = encabezado + cuerpo
            
            # Botón para pedir el significado
            btns = [[InlineKeyboardButton("Analizar Significado (IA) 🧠", callback_data=f"mn_{song_id}")]]
            
            # NO usamos parse_mode="Markdown" porque los símbolos de las letras rompen el bot
            await query.edit_message_text(texto_final, reply_markup=InlineKeyboardMarkup(btns))
            
        except Exception as e:
            print(f"Error cargando letra: {e}")
            await query.edit_message_text("❌ Error al cargar la letra. Intenta con otra de las opciones.")

    # CASO 2: El usuario quiere el significado (IA)
    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        song = genius.song(song_id)['song']
        
        await query.message.reply_text(f"🧠 Analizando el significado de '{song['title']}'...")
        
        # Simulación de análisis (puedes conectar Gemini aquí luego)
        analisis = (
            f"La canción *{song['title']}* de *{song['primary_artist']['name']}* es una obra que "
            "mezcla metáforas sobre la vida cotidiana con sentimientos profundos. "
            "Según el contexto, busca transmitir una sensación de libertad y reflexión personal. "
            "Es una de las piezas más comentadas por su lírica única."
        )
        
        await query.message.reply_text(f"✨ *Análisis de IA:*\n\n{analisis}", parse_mode="Markdown")

# --- ARRANQUE DEL SISTEMA ---

if __name__ == '__main__':
    # 1. Iniciamos el servidor web en un hilo aparte
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # 2. Configuramos el bot de Telegram
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    # Comandos y mensajes
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    
    # 3. Encendemos el bot
    print("Bot de Lyrics iniciado correctamente...")
    bot_app.run_polling()
