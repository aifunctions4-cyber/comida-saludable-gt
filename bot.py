import os
import time
import secrets
import requests
import psycopg

from flask import Flask, request, send_file, abort
from openai import OpenAI


app = Flask(__name__)


# --------------------------------------------------
# VARIABLES DE ENTORNO
# --------------------------------------------------

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Telegram privado del administrador.
# Se configurarán después directamente en Railway.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# URL pública de este servicio en Railway.
PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://comida-saludable-gt-production.up.railway.app"
).rstrip("/")

# RESET DULCE
RESET_DULCE_PAYMENT_URL = (
    "https://app.recurrente.com/s/steeven-gil/o/reset-dulce-ebook-digital"
)
RESET_DULCE_PRICE = "Q60"

# Cuando creemos el Volume de Railway, montaremos el PDF en esta ruta.
RESET_DULCE_PDF_PATH = os.environ.get(
    "RESET_DULCE_PDF_PATH",
    "/data/RESET_DULCE.pdf"
)


# Biblioteca privada de Comida Saludable GT
VECTOR_STORE_ID = "vs_6a9b49945b088191b211d8b71fdb9d0d"


client = OpenAI(api_key=OPENAI_API_KEY)


# --------------------------------------------------
# BASE DE DATOS POSTGRESQL
# --------------------------------------------------

def obtener_conexion_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")

    return psycopg.connect(DATABASE_URL)


def inicializar_base_datos():
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS instagram_users (
                        sender_id TEXT PRIMARY KEY,
                        free_recipe_used BOOLEAN NOT NULL DEFAULT FALSE,
                        paid_access BOOLEAN NOT NULL DEFAULT FALSE,
                        last_recipe TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # RESET DULCE se maneja aparte del límite de receta gratuita.
                # Comprar el ebook NO habilita recetas ilimitadas.
                cur.execute(
                    """
                    ALTER TABLE instagram_users
                    ADD COLUMN IF NOT EXISTS reset_dulce_purchased
                    BOOLEAN NOT NULL DEFAULT FALSE
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reset_dulce_orders (
