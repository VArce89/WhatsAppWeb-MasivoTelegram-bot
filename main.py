import os
import random
import time
import urllib.parse
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuración de Logs
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN_TELEGRAM = "TU_TOKEN_DE_TELEGRAM_AQUI"
DB_NAME = "campana_whatsapp.db"
driver = None
CHAT_ID_ADMIN = None  # Se guardará automáticamente cuando uses /start desde tu celular

# ==========================================
# BASE DE DATOS (GESTIÓN DE CLIENTES Y FECHAS)
# ==========================================
def inicializar_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            telefono TEXT PRIMARY KEY,
            mensaje TEXT,
            proximo_envio TEXT,
            frecuencia_dias INTEGER,
            activo INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def guardar_o_actualizar_cliente(telefono, mensaje, fecha_inicio, frecuencia):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Si el cliente ya existe, actualiza sus datos de envío pero conserva su estado 'activo'
    cursor.execute('''
        INSERT INTO clientes (telefono, mensaje, proximo_envio, frecuencia_dias, activo)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(telefono) DO UPDATE SET
            mensaje = excluded.mensaje,
            proximo_envio = excluded.proximo_envio,
            frecuencia_dias = excluded.frecuencia_dias
    ''', (telefono, mensaje, fecha_inicio, frecuencia))
    conn.commit()
    conn.close()

# ==========================================
# SELENIUM CONTROLLER
# ==========================================
def iniciar_selenium():
    global driver
    options = webdriver.ChromeOptions()
    options.add_argument('--user-data-dir=./User_Data')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

# ==========================================
# BOT DE TELEGRAM: COMANDOS
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global driver, CHAT_ID_ADMIN
    CHAT_ID_ADMIN = update.effective_chat.id
    await update.message.reply_text("🤖 Sistema de envíos programados activo en la VPS.\nIniciando navegador...")
    
    try:
        if driver is None:
            iniciar_selenium()
        
        driver.get('https://web.whatsapp.com/')
        await asyncio.sleep(5)
        driver.save_screenshot('screenshot.png')
        
        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, '//div[@data-tab="3"]')))
            await update.message.reply_text("✅ WhatsApp Web conectado correctamente.")
        except TimeoutException:
            await update.message.reply_text("⚠️ Sesión no detectada. Escanea este QR:")
            await update.message.reply_photo(photo=open('screenshot.png', 'rb'))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def cargar_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    documento = update.message.document
    if documento.file_name.endswith('.xlsx'):
        file = await context.bot.get_file(documento.file_id)
        ruta_temporal = "temp_contactos.xlsx"
        await file.download_to_drive(ruta_temporal)
        
        try:
            df = pd.read_excel(ruta_temporal)
            columnas_req = ['Telefono', 'Mensaje', 'Fecha_Inicio', 'Frecuencia_Dias']
            if not all(col in df.columns for col in columnas_req):
                await update.message.reply_text("❌ Estructura incorrecta. Asegúrate de incluir: Telefono, Mensaje, Fecha_Inicio, Frecuencia_Dias")
                return
            
            inicializar_db()
            contador = 0
            for _, fila in df.iterrows():
                tel = str(fila['Telefono']).replace('+', '').replace(' ', '').replace('-', '').split('.')[0]
                msg = fila['Mensaje']
                # Validar y formatear la fecha
                fecha_obj = pd.to_datetime(fila['Fecha_Inicio'])
                fecha_str = fecha_obj.strftime('%Y-%m-%d')
                frecuencia = int(fila['Frecuencia_Dias'])
                
                if pd.isna(tel) or pd.isna(msg):
                    continue
                
                guardar_o_actualizar_cliente(tel, msg, fecha_str, frecuencia)
                contador += 1
                
            os.remove(ruta_temporal)
            await update.message.reply_text(f"📊 ¡Éxito! Se registraron/actualizaron {contador} clientes en la base de datos.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error al procesar el archivo Excel: {e}")
    else:
        await update.message.reply_text("❌ Por favor, envía un archivo .xlsx válido.")

# Comando para DESACTIVAR un cliente de forma manual
async def desactivar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso correcto: /desactivar [Número de Teléfono]\nEjemplo: /desactivar 59170000001")
        return
    
    telefono = context.args[0].replace('+', '').replace(' ', '')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET activo = 0 WHERE telefono = ?", (telefono,))
    modificados = conn.total_changes
    conn.commit()
    conn.close()
    
    if modificados > 0:
        await update.message.reply_text(f"🛑 El cliente {telefono} ha sido DESACTIVADO. No recibirá más mensajes automáticos.")
    else:
        await update.message.reply_text(f"❓ No encontré al cliente {telefono} en la base de datos.")

# Comando para ACTIVAR de nuevo a un cliente
async def activar_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Uso correcto: /activar [Número de Teléfono]")
        return
    
    telefono = context.args[0].replace('+', '').replace(' ', '')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE clientes SET activo = 1 WHERE telefono = ?", (telefono,))
    modificados = conn.total_changes
    conn.commit()
    conn.close()
    
    if modificados > 0:
        await update.message.reply_text(f"✅ El cliente {telefono} ha sido REACTIVADO en la programación.")
    else:
        await update.message.reply_text(f"❓ No encontré al cliente {telefono} en la base de datos.")

# Ver lista de clientes inactivos o activos
async def lista_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT telefono, proximo_envio, frecuencia_dias, activo FROM clientes", conn)
    conn.close()
    
    if df.empty:
        await update.message.reply_text("La base de datos está vacía.")
        return
        
    texto = "📋 **ESTADO DE LA BASE DE DATOS:**\n\n"
    for _, fila in df.iterrows():
        estado = "✅ Activo" if fila['activo'] == 1 else "🛑 DESACTIVADO"
        texto += f"📞 `{fila['telefono']}` | Prox: {fila['proximo_envio']} | Cada {fila['frecuencia_dias']} días | {estado}\n"
    
    # Si el texto es muy largo, Telegram podría cortarlo (limite 4096 caract.)
    await update.message.reply_text(texto[:4000], parse_mode="Markdown")


# ==========================================
# PROCESADOR AUTOMÁTICO EN SEGUNDO PLANO
# ==========================================
async def tarea_programada_envios(context: ContextTypes.DEFAULT_TYPE):
    global driver, CHAT_ID_ADMIN
    if CHAT_ID_ADMIN is None or driver is None:
        return # Esperar a que el admin inicie el bot primero con /start
        
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Selecciona solo clientes ACTIVOS cuya fecha programada sea HOY o incluso FECHAS PASADAS (por si la VPS estuvo apagada)
    cursor.execute("SELECT telefono, mensaje, frecuencia_dias FROM clientes WHERE proximo_envio <= ? AND activo = 1", (hoy,))
    clientes_a_enviar = cursor.fetchall()
    
    if not clientes_a_enviar:
        return # Nada que enviar hoy

    await context.bot.send_message(chat_id=CHAT_ID_ADMIN, text=f"⏰ Iniciando envíos automáticos programados para hoy de forma autónoma ({len(clientes_a_enviar)} pendientes)...")

    for telefono, mensaje, frecuencia in clientes_a_enviar:
        try:
            mensaje_codificado = urllib.parse.quote(mensaje)
            url_destino = f"https://web.whatsapp.com/send?phone={telefono}&text={mensaje_codificado}"
            driver.get(url_destino)
            
            boton_enviar = WebDriverWait(driver, 25).until(
                EC.element_to_be_clickable((By.XPATH, '//span[@data-icon="send"]'))
            )
            boton_enviar.click()
            
            # Calcular la próxima fecha sumando la frecuencia de días
            nueva_fecha = (datetime.now() + timedelta(days=frecuencia)).strftime('%Y-%m-%d')
            
            # Actualizar la base de datos con su nueva fecha programada
            cursor.execute("UPDATE clientes SET proximo_envio = ? WHERE telefono = ?", (nueva_fecha, telefono))
            conn.commit()
            
            await context.bot.send_message(chat_id=CHAT_ID_ADMIN, text=f"✅ Enviado a {telefono}. Próxima fecha asignada: {nueva_fecha}")
            
            # Pausa Anti-Spam
            await asyncio.sleep(random.uniform(15, 25))
            
        except Exception as e:
            await context.bot.send_message(chat_id=CHAT_ID_ADMIN, text=f"❌ Error automatizado con {telefono}: No se pudo enviar.")
            
    conn.close()
    await context.bot.send_message(chat_id=CHAT_ID_ADMIN, text="🎉 Envíos programados del día completados.")


def main():
    inicializar_db()
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    # Handlers del Bot de Telegram móvil
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("desactivar", desactivar_cliente))
    app.add_handler(CommandHandler("activar", activar_cliente))
    app.add_handler(CommandHandler("lista", lista_clientes))
    app.add_handler(MessageHandler(filters.Document.ALL, cargar_excel))
    
    # PROGRAMADOR AUTOMÁTICO (Job Queue)
    # Revisa la base de datos cada 1 hora (3600 segundos) en busca de envíos listos para la fecha actual
    job_queue = app.job_queue
    job_queue.run_repeating(tarea_programada_envios, interval=3600, first=10)
    
    print("Sistema inteligente por Base de Datos ejecutándose en la VPS...")
    app.run_polling()

if __name__ == '__main__':
    main()
