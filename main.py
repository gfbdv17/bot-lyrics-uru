import os
import time
import threading
import requests
import re
import logging
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

TOKEN_TELEGRAM = os.getenv("TELEGRAM_BOT_TOKEN")

# --- SERVIDOR WEB PARA RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot de Lyrics Activo!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


# --- SCRAPER DE LETRAS.COM ---

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
        url_principal   = f"https://www.letras.com/{art_fmt}/{can_fmt}/"

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

            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                texto_tag = tag.text.lower()
                if 'significado' in texto_tag or 'meaning' in texto_tag or cancion.lower() in texto_tag:
                    for hermano in tag.find_next_siblings(['p', 'div']):
                        texto_limpio = hermano.text.strip()
                        if len(texto_limpio) > 40:
                            significado_texto += texto_limpio + "\n\n"
                    if significado_texto:
                        break

            if not significado_texto:
                for p in soup.find_all('p'):
                    if len(p.text.strip()) > 100:
                        significado_texto += p.text.strip() + "\n\n"

            if significado_texto:
                return significado_texto[:3800].strip()
            else:
                return "No hay un significado redactado para esta canción en Letras.com. 🚧"

        elif res.status_code == 404:
            return f"Letras.com no tiene análisis para <b>{cancion}</b>."
        else:
            return f"Error {res.status_code}. Conexión bloqueada temporalmente."

    except Exception as e:
        log.error(f"Error scraping Letras.com: {e}")
        return "Hubo un error técnico al consultar Letras.com."


# ─────────────────────────────────────────
#  HELPERS DE TECLADOS (estilo colorido)
# ─────────────────────────────────────────

def teclado_inicio():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎵  Buscar Canción", callback_data="ir_buscar")],
        [InlineKeyboardButton("📖  Cómo funciona",  callback_data="como_funciona")],
    ])

def teclado_resultados(canciones):
    """Lista de resultados con colores alternados."""
    paleta = ['🔵', '🟢', '🔴', '🟡', '🟣', '🟠', '🎵', '🎤', '🎧', '🎸']
    botones = []
    for i, song in enumerate(canciones[:10]):
        if song.get('plainLyrics'):
            color = paleta[i % len(paleta)]
            label = f"{color}  {song['trackName']} — {song['artistName']}"[:62]
            botones.append([InlineKeyboardButton(label, callback_data=f"ly_{song['id']}")])
    botones.append([InlineKeyboardButton("🔙  Volver al inicio", callback_data="inicio")])
    return InlineKeyboardMarkup(botones)

def teclado_letra(song_id):
    """Botones bajo la letra: significado (verde) y nueva búsqueda (azul)."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢  Extraer Significado (Letras.com)", callback_data=f"mn_{song_id}")],
        [InlineKeyboardButton("🔵  Buscar otra canción",              callback_data="ir_buscar")],
        [InlineKeyboardButton("🔙  Inicio",                           callback_data="inicio")],
    ])

def teclado_volver(song_id=None):
    """Botón de retorno al inicio o a la letra."""
    filas = [[InlineKeyboardButton("🔙  Volver al inicio", callback_data="inicio")]]
    if song_id:
        filas.insert(0, [InlineKeyboardButton("🎵  Ver letra de nuevo", callback_data=f"ly_{song_id}")])
    return InlineKeyboardMarkup(filas)


# ─────────────────────────────────────────
#  HANDLERS
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.effective_user.first_name
    mensaje = (
        f"¡Hola <b>{nombre}</b>! 👋\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎵 <b>Lyrics & Meaning Hub</b>\n"
        "Tu herramienta para encontrar letras y descubrir el significado de cualquier canción.\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Elige una opción para empezar 👇"
    )
    await update.message.reply_text(mensaje, parse_mode="HTML", reply_markup=teclado_inicio())


async def buscar_cancion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el texto libre que escribe el usuario."""
    query_texto = update.message.text.strip()
    if not query_texto:
        return

    espera = await update.message.reply_text(
        "⏳ <i>Buscando en la base de datos...</i>", parse_mode="HTML"
    )

    try:
        respuesta = requests.get(
            f"https://lrclib.net/api/search?q={query_texto}",
            timeout=10
        ).json()

        canciones_con_letra = [s for s in respuesta if s.get('plainLyrics')]

        if not canciones_con_letra:
            await espera.edit_text(
                "😕 No encontré canciones con letra para esa búsqueda.\n"
                "Intenta escribir <b>Artista - Canción</b>.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙  Volver al inicio", callback_data="inicio")]
                ])
            )
            return

        texto_menu = (
            "💿 <b>Resultados encontrados</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Elige la pista correcta 👇"
        )
        await espera.edit_text(
            texto_menu,
            reply_markup=teclado_resultados(canciones_con_letra),
            parse_mode="HTML"
        )

    except Exception as e:
        log.error(f"Error buscando canción: {e}")
        await espera.edit_text("❌ Error de conexión con la base de datos. Intenta de nuevo.")


async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    await query.answer()

    # ── Inicio ──
    if data == "inicio":
        nombre = query.from_user.first_name
        mensaje = (
            f"¡Hola <b>{nombre}</b>! 👋\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎵 <b>Lyrics & Meaning Hub</b>\n"
            "Tu herramienta para encontrar letras y descubrir el significado de cualquier canción.\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Elige una opción para empezar 👇"
        )
        await query.edit_message_text(mensaje, parse_mode="HTML", reply_markup=teclado_inicio())

    # ── Ir a buscar ──
    elif data == "ir_buscar":
        await query.edit_message_text(
            "🔍 <b>Modo búsqueda activado</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Escribe el nombre de la canción o el artista en el chat:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙  Volver", callback_data="inicio")]
            ])
        )

    # ── Cómo funciona ──
    elif data == "como_funciona":
        await query.edit_message_text(
            "📖 <b>¿Cómo usar este bot?</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1️⃣ Escribe el nombre de un artista o canción\n"
            "2️⃣ Elige la pista correcta de la lista\n"
            "3️⃣ Lee la letra completa\n"
            "4️⃣ Extrae el significado desde Letras.com\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 <i>Tip: Escribe \"Artista - Canción\" para resultados más precisos.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎵  Empezar a buscar", callback_data="ir_buscar")],
                [InlineKeyboardButton("🔙  Volver",           callback_data="inicio")],
            ])
        )

    # ── Ver letra ──
    elif data.startswith("ly_"):
        song_id = data.split("_")[1]
        await query.edit_message_text("⏳ <i>Cargando letra...</i>", parse_mode="HTML")

        try:
            cancion = requests.get(
                f"https://lrclib.net/api/get/{song_id}", timeout=10
            ).json()

            titulo  = cancion.get('trackName', 'Desconocido')
            artista = cancion.get('artistName', 'Desconocido')
            letra   = cancion.get('plainLyrics', 'No disponible.')

            texto_final = (
                f"🎵 <b>{titulo}</b>\n"
                f"👤 <i>{artista}</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{letra[:3600]}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "¿Qué inspiró esta canción? 👇"
            )

            await query.edit_message_text(
                texto_final,
                reply_markup=teclado_letra(song_id),
                parse_mode="HTML"
            )

        except Exception as e:
            log.error(f"Error cargando letra: {e}")
            await query.edit_message_text(
                "❌ Error al cargar la letra.",
                reply_markup=teclado_volver()
            )

    # ── Extraer significado ──
    elif data.startswith("mn_"):
        song_id = data.split("_")[1]
        await query.edit_message_text(
            "🔎 <i>Consultando Letras.com...</i>", parse_mode="HTML"
        )

        try:
            cancion = requests.get(
                f"https://lrclib.net/api/get/{song_id}", timeout=10
            ).json()

            artista = cancion.get('artistName', '')
            titulo  = cancion.get('trackName', '')

            significado = extraer_significado_letras(artista, titulo)

            texto_sig = (
                f"🧠 <b>Significado: {titulo}</b>\n"
                f"👤 <i>{artista}</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{significado}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Fuente: Letras.com</i>"
            )

            await query.edit_message_text(
                texto_sig,
                parse_mode="HTML",
                reply_markup=teclado_volver(song_id)
            )

        except Exception as e:
            log.error(f"Error sacando significado: {e}")
            await query.edit_message_text(
                "❌ Error consultando Letras.com.",
                reply_markup=teclado_volver()
            )


# ─────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────

if __name__ == '__main__':
    threading.Thread(target=run_web_server, daemon=True).start()

    bot_app = Application.builder().token(TOKEN_TELEGRAM).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_cancion))
    bot_app.add_handler(CallbackQueryHandler(manejar_botones))

    log.info("Bot de Lyrics iniciado.")
    bot_app.run_polling()
