import os
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot de Lyrics + Letras.com Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- EL RASTREADOR DE LETRAS.COM (Versión 2.0 Bilingüe) ---
def extraer_significado_letras(artista, cancion):
    try:
        # Formateo de URL (Letras.com usa minúsculas y guiones)
        art_fmt = artista.lower().replace(" ", "-").replace("'", "")
        can_fmt = cancion.lower().replace(" ", "-").replace("'", "")
        
        # Apuntamos directo a la pestaña de significado
        url = f"https://www.letras.com/{art_fmt}/{can_fmt}/significado/"
        
        # Disfraz para que Cloudflare no nos bloquee y pidiendo preferencia en español
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            significado_texto = ""
            
            # Buscamos títulos que contengan significado, meaning o el nombre de la canción
            titulos = soup.find_all(['h1', 'h2', 'h3', 'h4'])
            for tag in titulos:
                texto_tag = tag.text.lower()
                if 'significado' in texto_tag or 'meaning' in texto_tag or cancion.lower() in texto_tag:
                    # Encontramos el título. Ahora sacamos todos los párrafos (<p>) que le siguen
                    hermanos = tag.find_next_siblings(['p', 'div'])
                    for hermano in hermanos:
                        texto_limpio = hermano.text.strip()
                        # Solo agarramos bloques de texto largos (evita botones o publicidad)
                        if len(texto_limpio) > 40:
                            significado_texto += texto_limpio + "\n\n"
                    
                    if significado_texto:
                        break # Ya encontramos el texto, salimos del ciclo

            # Plan B: Si no había un título claro, buscamos párrafos largos en la página
            if not significado_texto:
                parrafos = soup.find_all('p')
                for p in parrafos:
                    if len(p.text.strip()) > 100:
                        significado_texto += p.text.strip() + "\n\n"

            if significado_texto:
                return significado_texto[:3800].strip()
            else:
                return "Llegué a la página, pero la estructura de Letras.com no me dejó raspar el texto exacto. 🚧"
        else:
            return f"Letras.com devolvió un error (Código {res.status_code}). Puede que esta canción no tenga significado publicado."
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
        # Búsqueda ultra rápida con LRCLIB
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
    
    # Fundamental: quita el relojito de carga al instante
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
            
            # Botón para buscar el significado en Letras.com
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
            
            # Llamamos a nuestra función V2.0 raspa-páginas
            significado = extraer_significado_letras(artista, titulo)
            
            await query.message.reply_text(f"✨ *Desde Letras.com:*\n\n{significado}", parse_mode="Markdown")
        except Exception as e:
            print(f"Error sacando significado: {e}")
            await query.message.reply_text("❌ Ocurrió un error consultando la página de Letras.com.")

# --- ARRANQUE DEL SISTEMA ---
if __name__ == '__main__':
    # Arranca Flask en segundo plano
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Enciende el bot
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    
    print("Bot de Lyrics y Significados Iniciado con Éxito...")
    bot_app.run_polling()
