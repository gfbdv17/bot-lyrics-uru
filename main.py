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
    return "Bot de Lyrics con Diseño Premium Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- EL RASTREADOR DE LETRAS.COM (Versión 3.1 - HTML Fix) ---

def limpiar_para_url(texto):
    texto = re.sub(r'\(.*?\)|\[.*?\]', '', texto)
    texto = re.sub(r'[^\w\s]', '', texto)
    texto = re.sub(r'\s+', '-', texto.strip().lower())
    return texto

def extraer_significado_letras(artista, cancion):
    try:
        art_fmt = limpiar_para_url(artista)
        can_fmt = limpiar_para_url(cancion)
        
        url_significado = f"https://www.letras.com/{art_fmt}/{can_fmt}/significado.html"
        url_principal = f"https://www.letras.com/{art_fmt}/{can_fmt}/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        
        res = requests.get(url_significado, headers=headers, timeout=10)
        
        if res.status_code == 404:
            res = requests.get(url_principal, headers=headers, timeout=10)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            significado_texto = ""
            
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

            if not significado_texto:
                parrafos = soup.find_all('p')
                for p in parrafos:
                    if len(p.text.strip()) > 100:
                        significado_texto += p.text.strip() + "\n\n"

            if significado_texto:
                return significado_texto[:3800].strip()
            else:
                return "Pude entrar a la página, pero no hay un significado redactado para esta canción. 🚧"
        elif res.status_code == 404:
            return f"Error 404. Letras.com no tiene un análisis para '{cancion}'."
        else:
            return f"Error {res.status_code}. Conexión bloqueada temporalmente."
            
    except Exception as e:
        return f"Hubo un error técnico raspando la web: {e}"

# --- LÓGICA DE TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.effective_user.first_name
    
    # Diseño Premium usando HTML y líneas
    mensaje = (
        f"¡Hola <b>{nombre}</b>! Bienvenido al bot 🎵\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Lyrics & Meaning Hub</b> es tu herramienta definitiva creada por @JoshHSmith. "
        "Busca cualquier canción para obtener su letra completa y extraer el análisis profundo "
        "directamente desde Letras.com.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <i>Escribe el nombre de un artista o canción para empezar.</i>"
    )
    await update.message.reply_text(mensaje, parse_mode="HTML")

async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    espera = await update.message.reply_text("⏳ <i>Buscando en la base de datos...</i>", parse_mode="HTML")
    
    try:
        respuesta = requests.get(f"https://lrclib.net/api/search?q={query}").json()
        if not respuesta:
            await espera.edit_text("No encontré nada. Intenta escribir 'Artista - Canción'.")
            return

        botones = []
        paleta = ['🔴', '🔵', '🟢', '🟡', '🟣', '🟠', '🎸', '🎹', '🎤', '🎧']
        
        for i, song in enumerate(respuesta[:10]):
            if song.get('plainLyrics'):
                color = paleta[i % len(paleta)]
                label = f"{color} {song['trackName']} - {song['artistName']}"[:60]
                botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
        
        if not botones:
            await espera.edit_text("Encontré la canción pero no tiene letra disponible. 😕")
            return

        # Menú de selección con estética
        texto_menu = (
            "<b>Resultados Encontrados</b> 💿\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Elige la pista correcta de la lista para ver la letra:"
        )
        await espera.edit_text(texto_menu, reply_markup=InlineKeyboardMarkup(botones), parse_mode="HTML")
    except Exception as e:
        print(f"Error: {e}")
        await espera.edit_text("Hubo un error de conexión con la base de datos.")

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    await query.answer()

    if data.startswith("ly_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("⏳ <i>Descargando letra...</i>", parse_mode="HTML")
        
        try:
            cancion = requests.get(f"https://lrclib.net/api/get/{song_id}").json()
            titulo = cancion.get('trackName', 'Desconocido')
            artista = cancion.get('artistName', 'Desconocido')
            letra = cancion.get('plainLyrics', 'No disponible.')
            
            # Formato tipo tarjeta de Spotify
            texto_final = (
                f"🎵 <b>{titulo}</b>\n"
                f"👤 <b>{artista}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{letra[:3600]}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>¿Qué inspiró esta canción? Descúbrelo abajo 👇</i>"
            )
            
            # Botón de significado con formato llamativo y un botón de cierre
            btns = [
                [InlineKeyboardButton("🔥 Extraer Significado (Letras.com) 🔥", callback_data=f"mn_{song_id}")],
                [InlineKeyboardButton("🔍 Buscar otra canción", callback_data="nueva_busqueda")]
            ]
            
            await query.edit_message_text(texto_final, reply_markup=InlineKeyboardMarkup(btns), parse_mode="HTML")
        except Exception as e:
            print(f"Error cargando letra: {e}")
            await query.edit_message_text("❌ Error al cargar la letra completa.")

    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("🔎 <i>Viajando a Letras.com...</i>", parse_mode="HTML")
        
        try:
            cancion = requests.get(f"https://lrclib.net/api/get/{song_id}").json()
            artista = cancion.get('artistName', '')
            titulo = cancion.get('trackName', '')
            
            significado = extraer_significado_letras(artista, titulo)
            
            # Resultado final con HTML
            texto_significado = (
                f"🧠 <b>Análisis de: {titulo}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{significado}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Fuente: Letras.com</i>"
            )
            
            await query.edit_message_text(texto_significado, parse_mode="HTML")
        except Exception as e:
            print(f"Error sacando significado: {e}")
            await query.edit_message_text("❌ Ocurrió un error consultando la página.")

    # Si el usuario presiona "Buscar otra canción"
    elif data == "nueva_busqueda":
        await query.edit_message_text("¡Listo! Escribe el nombre de otra canción para empezar de nuevo.")

# --- ARRANQUE DEL SISTEMA ---
if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()
    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))
    print("Bot de Lyrics Premium Iniciado...")
    bot_app.run_polling()
