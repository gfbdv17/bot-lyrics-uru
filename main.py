import os
import time
import feedparser
import subprocess
import requests
import threading
import json
import re
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home(): return "Bot MLB Multibatazo está Vivo y Escuchando!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURACIÓN ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CANAL = os.getenv("TELEGRAM_CHANNEL_ID") 
URL_CANAL = "https://t.me/homerunsmlb" 
RSS_URL = "https://nitter.net/MLBHRVIDEOS/rss" 

def formatear_titulo_personalizado(texto_original):
    patron = r"^(.*?)\s*-\s*(.*?)\s*\((\d+)\)"
    match = re.search(patron, texto_original)
    if match:
        jugador = match.group(1).strip()
        equipo = match.group(2).strip()
        numero = int(match.group(3))
        sufijo = 'th' if 11 <= (numero % 100) <= 13 else {1:'st', 2:'nd', 3:'rd'}.get(numero % 10, 'th')
        hashtag_equipo = equipo.replace(" ", "")
        return f"{jugador} {numero}{sufijo} Home Run of the Season #{hashtag_equipo} #MLB"
    return f"{texto_original} #MLB"

def enriquecer_con_statcast(texto_tweet):
    titulo = formatear_titulo_personalizado(texto_tweet)
    try:
        schedule_url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
        data = requests.get(schedule_url).json()
        if 'dates' in data and len(data['dates']) > 0:
            for game in data['dates'][0]['games']:
                pbp = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game['gamePk']}/feed/live").json()
                plays = pbp.get('liveData', {}).get('plays', {}).get('allPlays', [])
                for play in plays:
                    if play.get('result', {}).get('event', '') == 'Home Run':
                        if play['matchup']['batter']['fullName'].lower() in texto_tweet.lower():
                            h = play.get('playEvents', [])[-1].get('hitData', {})
                            p = play.get('playEvents', [])[-1].get('pitchData', {})
                            return (f"{titulo}\n\n"
                                    f"Distance: {h.get('totalDistance', 'N/A')}ft\n"
                                    f"Exit Velocity: {h.get('launchSpeed', 'N/A')} MPH\n"
                                    f"Launch Angle: {h.get('launchAngle', 'N/A')}°\n"
                                    f"Pitch: {p.get('startSpeed', 'N/A')}mph {p.get('details', {}).get('type', {}).get('description', 'Unk')} "
                                    f"({play['matchup']['pitcher']['fullName']})")
    except: pass
    return titulo

def descargar_video_hd(url, identificador_unico=""):
    archivo = f"video_{int(time.time())}_{identificador_unico}.mp4"
    comando = ["yt-dlp", "-f", "best[ext=mp4][height<=720]/best[ext=mp4]/best", "--no-warnings", "-o", archivo, url]
    try:
        subprocess.run(comando, check=True)
        return archivo
    except: return None

# MODIFICACIÓN: Ahora recibe el chat_id como parámetro para saber a quién enviarlo (Canal o Usuario)
def enviar_a_telegram(ruta_video, texto, chat_id_destino):
    url_api = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
    teclado = {"inline_keyboard": [[{"text": "HOMERUNS MLB", "url": URL_CANAL}]]}
    with open(ruta_video, 'rb') as video:
        datos = {
            "chat_id": chat_id_destino, "caption": texto, "reply_markup": json.dumps(teclado),
            "supports_streaming": True, "width": 1280, "height": 720
        }
        requests.post(url_api, data=datos, files={"video": video})

# --- RADAR AUTOMÁTICO DE FONDO ---
def bot_loop():
    print("Bot MLB Multibatazo Iniciado en Segundo Plano...")
    feed_inicial = feedparser.parse(RSS_URL)
    ultimo_link_procesado = feed_inicial.entries[0].link if feed_inicial.entries else None
    
    while True:
        try:
            feed = feedparser.parse(RSS_URL)
            nuevos_items = []
            
            for entry in feed.entries:
                if entry.link == ultimo_link_procesado:
                    break
                nuevos_items.append(entry)
            
            for item in reversed(nuevos_items):
                link_x = item.link.replace("nitter.net", "x.com")
                texto_base = item.title.replace("R to @MLBHRVIDEOS: ", "")
                
                print(f"Procesando nuevo jonrón para el canal: {texto_base}")
                texto_final = enriquecer_con_statcast(texto_base)
                video = descargar_video_hd(link_x, "canal")
                
                if video and os.path.exists(video):
                    enviar_a_telegram(video, texto_final, CANAL) # Envía al canal
                    os.remove(video)
                    ultimo_link_procesado = item.link
                    time.sleep(5)
        except Exception as e:
            print(f"Error en el loop: {e}")
            
        time.sleep(300)

# --- COMANDOS INTERACTIVOS ---
def procesar_ultimo_homerun_usuario(chat_id):
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.entries:
            item = feed.entries[0] # Siempre agarramos el índice 0 (el más reciente)
            link_x = item.link.replace("nitter.net", "x.com")
            texto_base = item.title.replace("R to @MLBHRVIDEOS: ", "")
            
            texto_final = enriquecer_con_statcast(texto_base)
            video = descargar_video_hd(link_x, "privado")
            
            if video and os.path.exists(video):
                enviar_a_telegram(video, texto_final, chat_id) # Te lo envía directo a ti
                os.remove(video)
    except Exception as e:
        print(f"Error sirviendo el homerun por comando: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Mensaje instantáneo confirmando que el bot está activo
    await update.message.reply_text(
        "✅ <b>¡El radar de Grandes Ligas está LIVE!</b>\n\n"
        "⏳ <i>Buscando y descargando la repetición del último bambinazo para ti...</i>", 
        parse_mode="HTML"
    )
    
    # 2. Iniciamos el proceso pesado (descarga) en un hilo aparte para no bloquear Telegram
    chat_id_usuario = update.message.chat_id
    threading.Thread(target=procesar_ultimo_homerun_usuario, args=(chat_id_usuario,), daemon=True).start()

if __name__ == "__main__":
    # Movemos el servidor web a un hilo para que no bloquee el código principal
    threading.Thread(target=run_web_server, daemon=True).start()
    
    # Arrancamos el radar de posteos automáticos en otro hilo
    threading.Thread(target=bot_loop, daemon=True).start()
    
    # El hilo principal se encarga de escuchar los comandos de Telegram
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    
    print("Sistema activo. Esperando comandos...")
    bot_app.run_polling()
