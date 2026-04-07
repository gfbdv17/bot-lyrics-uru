import os
import threading
import requests
import re
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot de Lyrics URU + Letras.com Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- EL RASTREADOR DE LETRAS.COM (Versión 3.1 - HTML Fix) ---

def limpiar_para_url(texto):
    # 1. Quita todo lo que esté entre paréntesis o corchetes (ej: "(Remix)")
    texto = re.sub(r'\(.*?\)|\[.*?\]', '', texto)
    # 2. Quita signos de puntuación raros, apóstrofes, comas...
    texto = re.sub(r'[^\w\s]', '', texto)
    # 3. Cambia espacios por guiones y quita espacios dobles
    texto = re.sub(r'\s+', '-', texto.strip().lower())
    return texto

def extraer_significado_letras(artista, cancion):
    try:
        # Formateo limpio de URL
        art_fmt = limpiar_para_url(artista)
        can_fmt = limpiar_para_url(cancion)
        
        # Dos opciones de búsqueda (¡Con el .html que descubriste!)
        url_significado = f"https://www.letras.com/{art_fmt}/{can_fmt}/significado.html"
        url_principal = f"https://www.letras.com/{art_fmt}/{can_fmt}/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        
        # Intento 1: Vamos directo a la pestaña de significado usando .html
        res = requests.get(url_significado, headers=headers, timeout=10)
        
        # Intento 2: Si da 404, buscamos en la página principal
        if res.status_code == 404:
            res = requests.get(url_principal, headers=headers, timeout=10)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            significado_texto = ""
            
            # Buscamos títulos que contengan significado, meaning o el nombre
            titulos = soup.find_all(['h1', 'h2', 'h3', 'h4'])
            for tag in titulos:
                texto_tag = tag.text.lower()
                if 'significado' in texto_tag or 'meaning' in texto_tag or cancion.lower() in texto_tag:
                    hermanos = tag.find_next_siblings(['p', 'div'])
                    for hermano in hermanos:
                        texto_limpio = hermano.text.strip()
                        if len(texto_limpio) > 40:
                            significado_texto += texto_limpio + "\n\n"
                    if significado_texto:
                        break

            # Plan B: Párrafos largos si no hay un título claro
            if not significado_texto:
                parrafos = soup.find_all('p')
                for p in parrafos:
                    if len(p.text.strip()) > 100:
                        significado_texto += p.text.strip() + "\n\n"

            if significado_texto:
                return significado_texto[:3800].strip()
            else:
                return "Pude entrar a la página de Letras.com, pero los editores no han escrito un significado para esta canción. 🚧"
        elif res.status_code == 404:
            return f"Error 404. Letras.com no tiene esta canción registrada bajo el nombre '{cancion}' de '{artista}'."
        else:
            return f"Error {res.status_code}. Letras.com bloqueó la conexión temporalmente."
            
    except Exception as e:
        return f"Hubo un error técnico raspando la web: {e}"

# --- LÓGICA DE TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "¡Bienvenido al lyrics bot hecho por @JoshHSmith! 🎵\n\n"
        "Extrae las letras y el significado de las canciones que quieras.\n\n"
        "🔍 Solo envíame el nombre de la canción o el artista para empezar."
    )
    await update.message.reply_text(mensaje)

async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    espera = await update.message.reply_text("🔍 Buscando en LRCLIB...")
    
    try:
        respuesta = requests.get(f"https://lrclib.net/api/search?q={query}").json()
        if not respuesta:
            await espera.edit_text("No encontré nada. Intenta escribir 'Artista - Canción'.")
            return

        botones = []
        for song in respuesta[:5]:
            if song.get('plainLyrics'):
                label = f"{song['trackName']} - {song['artistName']}"[:60]
                botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
        
        if not botones:
            await espera.edit_text("Encontré la canción pero no tiene letra disponible. 😕")
            return

        await espera.edit_text("¡Listo! Elige tu canción:", reply_markup=InlineKeyboardMarkup(botones))
    except Exception as e:
        print(f"Error: {e}")
        await espera.edit_text("Hubo un error de conexión con la base de datos.")

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
        except Exception as e:
            print(f"Error cargando letra: {e}")
            await query.edit_message_text("❌ Error al cargar la letra completa.")

    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        await query.message.reply_text("🔎 Viajando a Letras.com para extraer el significado...")
        
        try:
            cancion = requests.get(f"https://lrclib.net/api/get/{song_id}").json()
            artista = cancion.get('artistName', '')
            titulo = cancion.get('trackName', '')
            
            significado = extraer_significado_letras(artista, titulo)
            await query.message.reply_text(f"✨ *Desde Letras.com:*\n\n{significado}", parse_mode="Markdown")
        except Exception as e:
            print(f"Error sacando significado: {e}")
            await query.message.reply_text("❌ Ocurrió un error consultando la página de Letras.com.")

# --- ARRANQUE DEL SISTEMA ---
if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    print("Bot de Lyrics y Significados Iniciado con Éxito...")
    bot_app.run_polling()
