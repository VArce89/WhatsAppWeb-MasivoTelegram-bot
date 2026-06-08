#!/bin/bash

# Detener el script si ocurre algún error
set -e

echo "========================================="
echo "1. Actualizando paquetes del sistema..."
echo "========================================="
sudo apt update && sudo apt upgrade -y

echo "========================================="
echo "2. Instalando dependencias esenciales..."
echo "========================================="
sudo apt install -y python3-pip python3-venv wget curl unzip libxi6 libgconf-2-4 libnss3 libxrender1 libxtst6 libatk1.0-0 libgtk-3-0 libasound2

echo "========================================="
echo "3. Instalando Google Chrome Oficial..."
echo "========================================="
# Descarga e instala la versión estable de Chrome para Linux de 64 bits
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb -y
rm google-chrome-stable_current_amd64.deb

echo "========================================="
echo "4. Creando Entorno Virtual de Python..."
echo "========================================="
# Evita conflictos con las librerías nativas del sistema operativo
python3 -m venv venv
source venv/bin/activate

echo "========================================="
echo "5. Instalando librerías desde requirements.txt..."
echo "========================================="
pip install --upgrade pip
pip install -r requirements.txt

echo "========================================="
echo "✅ INSTALACIÓN COMPLETADA CON ÉXITO"
echo "========================================="
