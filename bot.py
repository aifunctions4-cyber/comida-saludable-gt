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
                        id BIGSERIAL PRIMARY KEY,
                        sender_id TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        receipt_url TEXT,
                        download_token TEXT UNIQUE,
                        download_used BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        reviewed_at TIMESTAMPTZ,
                        downloaded_at TIMESTAMPTZ
                    )
                    """
                )

                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_reset_orders_sender
                    ON reset_dulce_orders (sender_id)
                    """
                )

            conn.commit()

        print("Base de datos PostgreSQL inicializada correctamente")

    except Exception as e:
        print("ERROR INICIALIZANDO POSTGRESQL:", str(e))


def obtener_usuario_db(sender_id):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    INSERT INTO instagram_users (sender_id)
                    VALUES (%s)
                    ON CONFLICT (sender_id) DO NOTHING
                    """,
                    (sender_id,)
                )

                cur.execute(
                    """
                    SELECT
                        free_recipe_used,
                        paid_access,
                        last_recipe,
                        reset_dulce_purchased
                    FROM instagram_users
                    WHERE sender_id = %s
                    """,
                    (sender_id,)
                )

                fila = cur.fetchone()

            conn.commit()

        if not fila:
            return {
                "free_recipe_used": False,
                "paid_access": False,
                "last_recipe": None,
                "reset_dulce_purchased": False
            }

        return {
            "free_recipe_used": bool(fila[0]),
            "paid_access": bool(fila[1]),
            "last_recipe": fila[2],
            "reset_dulce_purchased": bool(fila[3])
        }

    except Exception as e:
        print("ERROR OBTENIENDO USUARIO DB:", str(e))

        # En caso de error de base de datos no regalamos
        # recetas ilimitadas accidentalmente.
        return None


def marcar_receta_gratuita_usada(sender_id, receta):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    INSERT INTO instagram_users (
                        sender_id,
                        free_recipe_used,
                        last_recipe,
                        updated_at
                    )
                    VALUES (%s, TRUE, %s, NOW())

                    ON CONFLICT (sender_id)
                    DO UPDATE SET
                        free_recipe_used = TRUE,
                        last_recipe = EXCLUDED.last_recipe,
                        updated_at = NOW()
                    """,
                    (
                        sender_id,
                        receta
                    )
                )

            conn.commit()

        print("Receta gratuita registrada para:", sender_id)

    except Exception as e:
        print("ERROR REGISTRANDO RECETA GRATUITA:", str(e))


def actualizar_ultima_receta(sender_id, receta):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    UPDATE instagram_users
                    SET
                        last_recipe = %s,
                        updated_at = NOW()
                    WHERE sender_id = %s
                    """,
                    (
                        receta,
                        sender_id
                    )
                )

            conn.commit()

    except Exception as e:
        print("ERROR ACTUALIZANDO RECETA:", str(e))


# --------------------------------------------------
# RESET DULCE: PEDIDOS, COMPROBANTES Y DESCARGAS
# --------------------------------------------------

def obtener_ultimo_pedido_reset(sender_id):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, status, receipt_url, download_token, download_used
                    FROM reset_dulce_orders
                    WHERE sender_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (sender_id,)
                )
                fila = cur.fetchone()

        if not fila:
            return None

        return {
            "id": fila[0],
            "status": fila[1],
            "receipt_url": fila[2],
            "download_token": fila[3],
            "download_used": bool(fila[4])
        }

    except Exception as e:
        print("ERROR OBTENIENDO PEDIDO RESET DULCE:", str(e))
        return None


def crear_o_actualizar_pedido_pendiente(sender_id, receipt_url):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT id
                    FROM reset_dulce_orders
                    WHERE sender_id = %s
                      AND status = 'pending'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (sender_id,)
                )
                fila = cur.fetchone()

                if fila:
                    order_id = fila[0]
                    cur.execute(
                        """
                        UPDATE reset_dulce_orders
                        SET receipt_url = %s,
                            created_at = NOW()
                        WHERE id = %s
                        """,
                        (receipt_url, order_id)
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO reset_dulce_orders (
                            sender_id,
                            status,
                            receipt_url
                        )
                        VALUES (%s, 'pending', %s)
                        RETURNING id
                        """,
                        (sender_id, receipt_url)
                    )
                    order_id = cur.fetchone()[0]

            conn.commit()

        return order_id

    except Exception as e:
        print("ERROR CREANDO PEDIDO PENDIENTE:", str(e))
        return None


def aprobar_pedido_reset(order_id):
    token = secrets.token_urlsafe(32)

    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT sender_id, status
                    FROM reset_dulce_orders
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (order_id,)
                )
                fila = cur.fetchone()

                if not fila:
                    return None

                sender_id, status = fila

                if status == "approved":
                    cur.execute(
                        """
                        SELECT download_token
                        FROM reset_dulce_orders
                        WHERE id = %s
                        """,
                        (order_id,)
                    )
                    token_existente = cur.fetchone()[0]
                    return {
                        "sender_id": sender_id,
                        "token": token_existente,
                        "already_approved": True
                    }

                if status != "pending":
                    return None

                cur.execute(
                    """
                    UPDATE reset_dulce_orders
                    SET status = 'approved',
                        download_token = %s,
                        download_used = FALSE,
                        reviewed_at = NOW()
                    WHERE id = %s
                    """,
                    (token, order_id)
                )

                cur.execute(
                    """
                    UPDATE instagram_users
                    SET reset_dulce_purchased = TRUE,
                        updated_at = NOW()
                    WHERE sender_id = %s
                    """,
                    (sender_id,)
                )

            conn.commit()

        return {
            "sender_id": sender_id,
            "token": token,
            "already_approved": False
        }

    except Exception as e:
        print("ERROR APROBANDO PEDIDO:", str(e))
        return None


def rechazar_pedido_reset(order_id):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE reset_dulce_orders
                    SET status = 'rejected',
                        reviewed_at = NOW()
                    WHERE id = %s
                      AND status = 'pending'
                    RETURNING sender_id
                    """,
                    (order_id,)
                )
                fila = cur.fetchone()

            conn.commit()

        if not fila:
            return None

        return fila[0]

    except Exception as e:
        print("ERROR RECHAZANDO PEDIDO:", str(e))
        return None


def consumir_token_descarga(token):
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT id, download_used, status
                    FROM reset_dulce_orders
                    WHERE download_token = %s
                    FOR UPDATE
                    """,
                    (token,)
                )
                fila = cur.fetchone()

                if not fila:
                    return False, "invalid"

                order_id, download_used, status = fila

                if status != "approved":
                    return False, "not_approved"

                if download_used:
                    return False, "used"

                cur.execute(
                    """
                    UPDATE reset_dulce_orders
                    SET download_used = TRUE,
                        downloaded_at = NOW()
                    WHERE id = %s
                    """,
                    (order_id,)
                )

            conn.commit()

        return True, "ok"

    except Exception as e:
        print("ERROR CONSUMIENDO TOKEN:", str(e))
        return False, "error"


def enviar_telegram_texto(texto, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram todavía no está configurado")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "text": texto
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        response = requests.post(url, json=payload, timeout=15)
        print("Telegram sendMessage:", response.status_code, response.text)
        return response.ok
    except Exception as e:
        print("ERROR TELEGRAM TEXTO:", str(e))
        return False


def enviar_comprobante_a_telegram(order_id, sender_id, receipt_url):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Telegram todavía no está configurado")
        return False

    botones = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ APROBAR",
                    "callback_data": f"approve:{order_id}"
                },
                {
                    "text": "❌ RECHAZAR",
                    "callback_data": f"reject:{order_id}"
                }
            ]
        ]
    }

    caption = (
        "🛒 NUEVA COMPRA — RESET DULCE\n"
        f"Pedido: #{order_id}\n"
        f"Instagram ID: {sender_id}\n"
        f"Precio: {RESET_DULCE_PRICE}\n\n"
        "Revisa el comprobante y decide:"
    )

    # Primero intentamos que Telegram cargue directamente la imagen.
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    payload_photo = {
        "chat_id": TELEGRAM_ADMIN_CHAT_ID,
        "photo": receipt_url,
        "caption": caption,
        "reply_markup": botones
    }

    try:
        response = requests.post(url_photo, json=payload_photo, timeout=20)

        if response.ok:
            print("Comprobante enviado a Telegram")
            return True

        print(
            "Telegram no pudo cargar la foto directamente:",
            response.status_code,
            response.text
        )

    except Exception as e:
        print("ERROR TELEGRAM FOTO:", str(e))

    # Respaldo: mandamos aviso y botones aunque la foto no pueda cargarse.
    texto = (
        caption
        + "\n\nNo pude cargar automáticamente la imagen en Telegram. "
        + "Puedes revisar el comprobante en la conversación de Instagram."
    )

    return enviar_telegram_texto(texto, botones)


def actualizar_mensaje_telegram_procesado(callback, texto_estado):
    if not TELEGRAM_BOT_TOKEN:
        return False

    mensaje = callback.get("message") or {}
    chat_id = (mensaje.get("chat") or {}).get("id")
    message_id = mensaje.get("message_id")

    if not chat_id or not message_id:
        return False

    if "caption" in mensaje:
        metodo = "editMessageCaption"
        campo = "caption"
        original = mensaje.get("caption") or ""
    else:
        metodo = "editMessageText"
        campo = "text"
        original = mensaje.get("text") or ""

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        campo: f"{original}\n\n{texto_estado}".strip(),
        "reply_markup": {"inline_keyboard": []}
    }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{metodo}",
            json=payload,
            timeout=15
        )
        print("Telegram mensaje procesado:", response.status_code, response.text)
        return response.ok
    except Exception as e:
        print("ERROR ACTUALIZANDO MENSAJE TELEGRAM:", str(e))
        return False


def responder_callback_telegram(callback_query_id, texto):
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"

    try:
        requests.post(
            url,
            json={
                "callback_query_id": callback_query_id,
                "text": texto
            },
            timeout=10
        )
    except Exception as e:
        print("ERROR RESPONDIENDO CALLBACK TELEGRAM:", str(e))


def extraer_url_imagen_instagram(message):
    attachments = message.get("attachments") or []

    for attachment in attachments:
        if attachment.get("type") != "image":
            continue

        payload = attachment.get("payload") or {}
        url = payload.get("url")

        if url:
            return url

    return None


# --------------------------------------------------
# MEMORIA CORTA DE CONVERSACION
# --------------------------------------------------

# Esta memoria vive solamente dentro del proceso de Railway.
# PostgreSQL se utiliza para conservar permanentemente
# el estado de la receta gratuita.

memoria_conversaciones = {}

# 60 minutos
MEMORIA_DURACION = 60 * 60

# Máximo de mensajes anteriores enviados como contexto
MAX_MENSAJES_MEMORIA = 6


def obtener_memoria(sender_id):

    ahora = time.time()

    datos = memoria_conversaciones.get(sender_id)

    if not datos:
        return []

    ultima_actividad = datos.get("ultima_actividad", 0)

    if ahora - ultima_actividad > MEMORIA_DURACION:
        memoria_conversaciones.pop(sender_id, None)
        return []

    return datos.get("mensajes", [])


def guardar_en_memoria(sender_id, rol, contenido):

    ahora = time.time()

    datos = memoria_conversaciones.get(
        sender_id,
        {
            "mensajes": [],
            "ultima_actividad": ahora
        }
    )

    datos["mensajes"].append(
        {
            "role": rol,
            "content": contenido
        }
    )

    datos["mensajes"] = datos["mensajes"][-MAX_MENSAJES_MEMORIA:]

    datos["ultima_actividad"] = ahora

    memoria_conversaciones[sender_id] = datos


def limpiar_memorias_expiradas():

    ahora = time.time()

    expiradas = []

    for sender_id, datos in list(memoria_conversaciones.items()):

        ultima_actividad = datos.get("ultima_actividad", 0)

        if ahora - ultima_actividad > MEMORIA_DURACION:
            expiradas.append(sender_id)

    for sender_id in expiradas:
        memoria_conversaciones.pop(sender_id, None)


# --------------------------------------------------
# DETECTAR SI LA RESPUESTA ES UNA RECETA COMPLETA
# --------------------------------------------------

def es_receta_completa(texto):

    texto_normalizado = texto.lower()

    tiene_ingredientes = "ingredientes" in texto_normalizado

    tiene_preparacion = (
        "preparación" in texto_normalizado
        or "preparacion" in texto_normalizado
    )

    return (
        tiene_ingredientes
        and tiene_preparacion
        and len(texto.strip()) >= 150
    )


# --------------------------------------------------
# CLASIFICAR MENSAJE DESPUES DE LA RECETA GRATIS
# --------------------------------------------------

def clasificar_mensaje_posterior(
    mensaje_usuario,
    historial,
    ultima_receta
):

    try:

        contexto = ""

        for mensaje in historial[-4:]:
            contexto += (
                f'{mensaje["role"]}: '
                f'{mensaje["content"]}\n'
            )

        ultima_receta_texto = ultima_receta or "No disponible"

        instrucciones = """
Clasifica el mensaje actual de una persona que ya recibió
una receta personalizada gratuita.

Debes responder ÚNICAMENTE con una de estas tres palabras:

AJUSTE
NUEVA
OTRO

AJUSTE:
La persona quiere modificar, sustituir, quitar, agregar,
aclarar o adaptar algo de la MISMA receta que ya recibió.

Ejemplos:
- no quiero tomate
- cambia el aguacate
- no tengo cebolla
- ¿puedo usar otra verdura?
- hazla para 4 personas
- ¿puedo hacerla sin lácteos?
- ¿cuánto tiempo cocino el pollo?
- explícame mejor el paso 2

NUEVA:
La persona solicita otra receta, otro plato, otra comida,
otro desayuno, almuerzo, cena, snack, postre, menú o una
preparación diferente.

Ejemplos:
- dame otra receta
- quiero otra cena
- ahora dame un desayuno
- quiero algo con pescado
- dame un postre
- hazme otra opción
- dame una receta diferente

OTRO:
Saludos, agradecimientos, conversación general, preguntas
que no solicitan una nueva receta completa, o temas que no
corresponden claramente a AJUSTE o NUEVA.

No expliques tu decisión.
"""

        entrada = f"""
RECETA ANTERIOR:
{ultima_receta_texto}

CONTEXTO RECIENTE:
{contexto}

MENSAJE ACTUAL:
{mensaje_usuario}
"""

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=instrucciones,
            input=entrada
        )

        clasificacion = response.output_text.strip().upper()

        if clasificacion.startswith("AJUSTE"):
            return "AJUSTE"

        if clasificacion.startswith("NUEVA"):
            return "NUEVA"

        return "OTRO"

    except Exception as e:

        print("ERROR CLASIFICANDO MENSAJE:", str(e))

        # Ante una falla no generamos automáticamente
        # otra receta gratuita.
        return "OTRO"


# --------------------------------------------------
# INSTRUCCIONES DE COMIDA SALUDABLE GT
# --------------------------------------------------

SYSTEM_PROMPT = """
Eres el asistente virtual de Comida Saludable GT.

Tu función principal es ayudar a las personas a crear y descubrir recetas,
ideas de comidas y menús saludables adaptados a lo que buscan.

Tienes acceso mediante una herramienta interna a una biblioteca privada de
contenido aprobado por Comida Saludable GT.


CONTEXTO DE LA CONVERSACION:

Puedes recibir los mensajes recientes de la conversación actual.

Utiliza ese contexto para recordar lo que la persona acaba de decir, por ejemplo:
- ingredientes que tiene
- ingredientes que no quiere
- preferencias
- cantidad de personas
- tiempo disponible
- tipo de comida que busca
- respuestas que haya dado a tus preguntas anteriores

No vuelvas a preguntar algo que la persona ya respondió.

Si el contexto reciente y el mensaje actual contienen suficiente información,
crea la receta directamente.


PERSONALIZACION DE RECETAS:

Nuestro objetivo no es dar simplemente una receta general.

Cuando sea útil, adapta la receta tomando en cuenta información como:
- ingredientes que la persona tiene disponibles
- ingredientes que desea evitar
- gustos y preferencias
- tipo de comida que quiere preparar
- cantidad de personas
- tiempo disponible para cocinar
- preferencia por una preparación rápida, sencilla o más elaborada
- preferencias alimentarias generales
- deseo de reducir azúcar añadido
- otras necesidades culinarias que la persona indique


REGLA DE LAS 2 PREGUNTAS:

Puedes hacer un máximo de 2 preguntas antes de crear una receta.

Haz preguntas solamente cuando realmente necesites información adicional
para ofrecer una opción más adecuada.

Las preguntas deben adaptarse a lo que la persona ya dijo.

No hagas siempre las mismas preguntas.

Nunca preguntes algo que la persona ya explicó.

Si el mensaje actual y el contexto reciente contienen suficiente información,
NO hagas preguntas adicionales y crea la receta directamente.

No conviertas la conversación en un cuestionario.

Después de que la persona responda tus preguntas, utiliza esas respuestas
para crear la receta. No vuelvas a iniciar otra ronda de preguntas.


AJUSTES A UNA RECETA YA ENTREGADA:

Si la persona está haciendo un pequeño cambio o sustitución a una receta
que acaba de recibir, responde específicamente al cambio solicitado.

Por ejemplo:
- quitar un ingrediente
- cambiar una verdura
- sustituir un ingrediente
- cambiar cantidades
- adaptar el número de porciones
- aclarar un paso de preparación

Para cambios pequeños, no es necesario volver a escribir toda la receta.

Explica únicamente qué debe cambiar y, cuando sea útil, cómo afecta
la preparación.

Si la persona pide explícitamente que vuelvas a escribir la receta completa
con los cambios, puedes hacerlo.


USA EL CONOCIMIENTO DISPONIBLE PARA:

- buscar recetas e ideas relacionadas con lo que pide la persona
- utilizar ingredientes y combinaciones útiles
- proponer desayunos, almuerzos, cenas, snacks y postres
- proponer opciones sin azúcar añadido cuando corresponda
- sugerir sustituciones de ingredientes
- crear menús e ideas de comidas
- crear recetas a partir de ingredientes disponibles
- adaptar recetas según las preferencias indicadas por la persona


IMPORTANTE:

No copies literalmente las recetas de las fuentes internas.

Usa el conocimiento recuperado para crear respuestas útiles, naturales y
redactadas con tus propias palabras.

Cuando una persona pida una receta y tengas suficiente información,
intenta incluir:
- nombre de la receta
- ingredientes
- preparación sencilla

Si solicita varias ideas, puedes ofrecer varias opciones breves.


FORMATO PARA INSTAGRAM:

- No uses Markdown.
- No uses #, ##, ###, ####, **, __ ni otros símbolos de Markdown.
- No pongas asteriscos alrededor de títulos o palabras.
- Usa texto limpio y fácil de leer.
- Usa saltos de línea para organizar la respuesta.
- Puedes utilizar emojis moderadamente.
- Para listas utiliza viñetas simples como •.
- Evita bloques de texto demasiado largos.


FUENTES Y BIBLIOTECA:

- Nunca menciones PDFs.
- Nunca menciones documentos.
- Nunca menciones archivos.
- Nunca menciones Vector Store.
- Nunca menciones File Search.
- Nunca menciones la biblioteca interna.
- Nunca menciones nombres de archivos.
- Nunca menciones autores de las fuentes internas.
- Nunca digas "inspirada en una receta".
- Nunca digas "basada en una receta".
- Nunca digas "según el recetario".
- Nunca digas "según los documentos".
- Nunca digas "encontré esta receta".
- Nunca expliques de dónde obtuviste la información.
- Presenta directamente la receta como contenido de Comida Saludable GT.
- Redacta siempre con tus propias palabras.
- No reproduzcas extensamente texto literal de las fuentes internas.


ALCANCE:

Comida Saludable GT se enfoca principalmente en recetas y alimentación.

Puedes ayudar con:
- recetas saludables
- desayunos
- almuerzos
- cenas
- snacks
- postres
- recetas sin azúcar añadido
- ideas de alimentación antiinflamatoria
- organización de comidas
- sustituciones de ingredientes
- menús saludables
- ideas para aprovechar ingredientes disponibles


LIMITES DE SALUD:

NO eres un servicio médico.

La personalización de una receta se refiere a preferencias, ingredientes,
objetivos generales de alimentación y necesidades culinarias.

Nunca presentes una receta como personalizada para tratar una enfermedad
o condición médica.

No debes:
- diagnosticar enfermedades
- crear tratamientos médicos
- prescribir medicamentos
- prescribir suplementos
- indicar dosis de medicamentos o suplementos
- afirmar que una receta cura una enfermedad
- afirmar que una receta trata una enfermedad
- prometer resultados médicos

Si alguien pide una receta para tratar, curar o controlar una enfermedad,
explica brevemente que Comida Saludable GT puede ayudar con recetas e ideas
generales de alimentación según sus preferencias, pero no proporciona
tratamientos médicos ni sustituye la atención de un profesional de salud.


ESTILO:

- Habla siempre en español claro, cálido y natural.
- Responde como una conversación de Instagram.
- Sé útil, práctico y directo.
- Evita explicaciones innecesariamente largas.
- Usa emojis con moderación.
- Cada respuesta debe intentar mantenerse por debajo de 800 caracteres.
- Haz solamente las preguntas necesarias.
- Nunca hagas más de 2 preguntas antes de proponer una receta.
- No repitas información innecesariamente.


OBJETIVO COMERCIAL:

Primero ayuda a la persona.

Cuando exista una oportunidad natural, puedes mencionar que Comida Saludable GT
cuenta con recetarios, ebooks u otros productos relacionados.

No intentes vender algo en absolutamente cada mensaje.

Nunca inventes:
- precios
- promociones
- enlaces de compra
- productos que no hayan sido definidos

Cuando posteriormente se incorporen productos específicos, podrás orientar
a la persona hacia el producto correspondiente.


SI LA PERSONA SIMPLEMENTE SALUDA:

Responde:

"¡Hola! 👋 Bienvenido a Comida Saludable GT 🌿

¿Qué te gustaría preparar hoy?

🥗 Una receta saludable
🍰 Un postre saludable
🥑 Una idea con ingredientes que ya tienes
📋 Un menú saludable

Cuéntame qué buscas y con gusto te ayudo."
"""


# --------------------------------------------------
# MENSAJE DE LIMITE GRATUITO
# --------------------------------------------------

MENSAJE_LIMITE_GRATUITO = f"""
Ya utilizaste tu receta personalizada gratuita 🌿

Puedo seguir ayudándote con cambios, sustituciones o dudas sobre esa misma receta.

Si quieres seguir descubriendo opciones saludables, tenemos RESET DULCE 📕
Una guía digital de 2 semanas con recetas, menús, sustituciones, meal prep, salsas y lista de compras.

Precio: {RESET_DULCE_PRICE}

Puedes comprarla aquí:
{RESET_DULCE_PAYMENT_URL}

Después de pagar, vuelve a este chat y envíame una captura de tu comprobante 📸
""".strip()


# --------------------------------------------------
# PAGINA PRINCIPAL
# --------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return "Comida Saludable GT - Bot funcionando correctamente", 200


# --------------------------------------------------
# POLITICA DE PRIVACIDAD
# --------------------------------------------------

@app.route("/privacy", methods=["GET"])
def privacy():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Política de Privacidad - Comida Saludable GT</title>
    </head>

    <body style="
        font-family: Arial, sans-serif;
        max-width: 900px;
        margin: 40px auto;
        padding: 0 20px;
        line-height: 1.6;
    ">

        <h1>Política de Privacidad</h1>

        <h3>Comida Saludable GT</h3>

        <p>
        Esta Política de Privacidad explica cómo Comida Saludable GT
        procesa información relacionada con las interacciones realizadas
        a través de nuestra cuenta de Instagram.
        </p>

        <h2>Información que procesamos</h2>

        <p>
        Podemos procesar mensajes, identificadores de usuario y otra
        información proporcionada voluntariamente cuando una persona
        interactúa con nuestra cuenta de Instagram.
        </p>

        <h2>Uso de la información</h2>

        <p>
        Utilizamos esta información para responder mensajes, brindar
        información solicitada, recordar el estado de acceso a funciones
        del servicio y operar las funciones automatizadas de
        Comida Saludable GT.
        </p>

        <h2>Compartición de información</h2>

        <p>
        No vendemos información personal. La información puede ser
        procesada por proveedores tecnológicos necesarios para operar
        nuestro servicio.
        </p>

        <h2>Eliminación de datos</h2>

        <p>
        Los usuarios pueden solicitar la eliminación de su información
        contactando directamente a Comida Saludable GT mediante nuestra
        cuenta oficial de Instagram.
        </p>

        <h2>Contacto</h2>

        <p>
        Para consultas relacionadas con privacidad puede comunicarse con
        Comida Saludable GT.
        </p>

    </body>
    </html>
    """, 200


# --------------------------------------------------
# GENERAR RESPUESTA CON OPENAI + FILE SEARCH + MEMORIA
# --------------------------------------------------

def generar_respuesta_normal(
    sender_id,
    mensaje_usuario,
    historial
):

    mensajes = []

    for mensaje in historial:
        mensajes.append(
            {
                "role": mensaje["role"],
                "content": mensaje["content"]
            }
        )

    mensajes.append(
        {
            "role": "user",
            "content": mensaje_usuario
        }
    )

    response = client.responses.create(
        model="gpt-5.6-luna",
        instructions=SYSTEM_PROMPT,
        input=mensajes,
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [VECTOR_STORE_ID],
                "max_num_results": 5
            }
        ]
    )

    respuesta = response.output_text.strip()

    if not respuesta:
        respuesta = (
            "¡Hola! 👋 Cuéntame qué te gustaría preparar: "
            "una receta, un postre, un snack o un menú saludable."
        )

    return respuesta


def generar_respuesta(sender_id, mensaje_usuario):

    try:

        limpiar_memorias_expiradas()

        historial = obtener_memoria(sender_id)

        usuario = obtener_usuario_db(sender_id)

        # Si PostgreSQL no está disponible, evitamos entregar
        # recetas ilimitadas accidentalmente.
        if usuario is None:

            respuesta = (
                "Gracias por escribirnos 🌿. "
                "En este momento tuve un pequeño inconveniente para "
                "consultar tu acceso. Inténtalo nuevamente en unos minutos."
            )

            return respuesta

        free_recipe_used = usuario["free_recipe_used"]
        paid_access = usuario["paid_access"]
        ultima_receta = usuario["last_recipe"]

        # --------------------------------------------------
        # USUARIO QUE YA UTILIZO SU RECETA GRATIS
        # --------------------------------------------------

        if free_recipe_used:

            clasificacion = clasificar_mensaje_posterior(
                mensaje_usuario,
                historial,
                ultima_receta
            )

            print(
                "Clasificación usuario con receta usada:",
                clasificacion
            )

            # Solicita una receta completamente nueva
            if clasificacion == "NUEVA":

                guardar_en_memoria(
                    sender_id,
                    "user",
                    mensaje_usuario
                )

                guardar_en_memoria(
                    sender_id,
                    "assistant",
                    MENSAJE_LIMITE_GRATUITO
                )

                return MENSAJE_LIMITE_GRATUITO

            # AJUSTE u OTRO pueden continuar normalmente.
            respuesta = generar_respuesta_normal(
                sender_id,
                mensaje_usuario,
                historial
            )

            guardar_en_memoria(
                sender_id,
                "user",
                mensaje_usuario
            )

            guardar_en_memoria(
                sender_id,
                "assistant",
                respuesta
            )

            # Si fue un ajuste y el modelo reescribió
            # una receta completa, guardamos la versión nueva.
            if (
                clasificacion == "AJUSTE"
                and es_receta_completa(respuesta)
            ):
                actualizar_ultima_receta(
                    sender_id,
                    respuesta
                )

            return respuesta

        # --------------------------------------------------
        # USUARIO NUEVO O USUARIO CON ACCESO PAGADO
        # --------------------------------------------------

        respuesta = generar_respuesta_normal(
            sender_id,
            mensaje_usuario,
            historial
        )

        guardar_en_memoria(
            sender_id,
            "user",
            mensaje_usuario
        )

        guardar_en_memoria(
            sender_id,
            "assistant",
            respuesta
        )

        # RESET DULCE no da acceso a recetas personalizadas adicionales.
        # paid_access se conserva en la tabla por compatibilidad histórica,
        # pero no evita el límite de una receta gratuita.

        # Solo marcamos la receta gratis cuando realmente
        # se entregó una receta completa.
        # Las preguntas previas NO consumen la receta.
        if es_receta_completa(respuesta):

            marcar_receta_gratuita_usada(
                sender_id,
                respuesta
            )

        return respuesta

    except Exception as e:

        print("ERROR GENERANDO RESPUESTA:", str(e))

        return (
            "Gracias por escribirnos 🌿. "
            "En este momento tuve un pequeño inconveniente para responder. "
            "Inténtalo nuevamente en unos minutos."
        )


# --------------------------------------------------
# DIVIDIR MENSAJES LARGOS
# --------------------------------------------------

def dividir_mensaje(texto, limite=900):

    texto = texto.strip()

    if len(texto) <= limite:
        return [texto]

    partes = []

    while len(texto) > limite:

        corte = texto.rfind("\n", 0, limite)

        if corte == -1:
            corte = texto.rfind(". ", 0, limite)

        if corte == -1:
            corte = texto.rfind(" ", 0, limite)

        if corte == -1:
            corte = limite

        parte = texto[:corte].strip()

        if parte:
            partes.append(parte)

        texto = texto[corte:].strip()

    if texto:
        partes.append(texto)

    return partes


# --------------------------------------------------
# ENVIAR MENSAJE A INSTAGRAM
# --------------------------------------------------

def enviar_mensaje_instagram(recipient_id, texto):

    url = "https://graph.instagram.com/v24.0/me/messages"

    headers = {
        "Authorization": f"Bearer {INSTAGRAM_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    partes = dividir_mensaje(texto)

    for parte in partes:

        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": parte
            }
        }

        try:

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=15
            )

            print(
                "Respuesta API Instagram:",
                response.status_code,
                response.text
            )

            if response.status_code != 200:
                print("ERROR enviando mensaje a Instagram")
                return response

        except Exception as e:

            print("ERROR INSTAGRAM:", str(e))
            return None

    return True


# --------------------------------------------------
# DESCARGA UNICA DE RESET DULCE
# --------------------------------------------------

@app.route("/descargar/reset-dulce/<token>", methods=["GET"])
def descargar_reset_dulce(token):
    # Un GET solo muestra la página de confirmación.
    # Así una previsualización de Instagram no consume la descarga.
    try:
        with obtener_conexion_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, download_used
                    FROM reset_dulce_orders
                    WHERE download_token = %s
                    """,
                    (token,)
                )
                fila = cur.fetchone()
    except Exception as e:
        print("ERROR VALIDANDO TOKEN DE DESCARGA:", str(e))
        return "No pudimos validar el enlace. Inténtalo nuevamente.", 503

    if not fila:
        abort(404)

    status, download_used = fila

    if status != "approved":
        abort(404)

    if download_used:
        return (
            "Este enlace de descarga ya fue utilizado. "
            "Si necesitas ayuda, escríbenos por Instagram.",
            410
        )

    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RESET DULCE</title>
    </head>
    <body style="font-family:Arial,sans-serif;max-width:620px;margin:60px auto;padding:0 24px;text-align:center;line-height:1.5;">
        <h1>RESET DULCE 🌿</h1>
        <p>Tu ebook está listo.</p>
        <p>Presiona el botón para descargarlo.</p>
        <form action="/descargar/reset-dulce/{token}/archivo" method="post">
            <button type="submit" style="border:0;border-radius:10px;padding:15px 24px;font-size:17px;cursor:pointer;">
                📕 Descargar RESET DULCE
            </button>
        </form>
        <p style="margin-top:24px;font-size:14px;">El enlace permite una sola descarga. Guarda el PDF en tu dispositivo.</p>
    </body>
    </html>
    """, 200


@app.route("/descargar/reset-dulce/<token>/archivo", methods=["POST"])
def descargar_archivo_reset_dulce(token):
    if not os.path.isfile(RESET_DULCE_PDF_PATH):
        print("PDF RESET DULCE no encontrado:", RESET_DULCE_PDF_PATH)
        return (
            "El archivo todavía no está disponible. "
            "Por favor comunícate con Comida Saludable GT.",
            503
        )

    valido, motivo = consumir_token_descarga(token)

    if not valido:
        if motivo == "used":
            return (
                "Este enlace de descarga ya fue utilizado. "
                "Si necesitas ayuda, escríbenos por Instagram.",
                410
            )
        abort(404)

    return send_file(
        RESET_DULCE_PDF_PATH,
        as_attachment=True,
        download_name="RESET_DULCE_Comida_Saludable_GT.pdf",
        mimetype="application/pdf"
    )


# --------------------------------------------------
# WEBHOOK PRIVADO DE TELEGRAM
# --------------------------------------------------

@app.route("/telegram/webhook/<secret>", methods=["POST"])
def telegram_webhook(secret):

    if not TELEGRAM_WEBHOOK_SECRET or secret != TELEGRAM_WEBHOOK_SECRET:
        return "NO AUTORIZADO", 403

    data = request.get_json(silent=True) or {}

    # --------------------------------------------------
    # MENSAJES NORMALES DEL ADMINISTRADOR EN TELEGRAM
    # --------------------------------------------------
    telegram_message = data.get("message") or data.get("edited_message")

    if telegram_message:
        chat = telegram_message.get("chat") or {}
        from_user = telegram_message.get("from") or {}
        chat_id = str(chat.get("id", ""))
        from_user_id = str(from_user.get("id", ""))
        texto = (telegram_message.get("text") or "").strip()

        # El bot privado solamente responde al administrador configurado.
        if (
            str(TELEGRAM_ADMIN_CHAT_ID) != chat_id
            or str(TELEGRAM_ADMIN_CHAT_ID) != from_user_id
        ):
            return "OK", 200

        if texto.startswith("/start"):
            enviar_telegram_texto(
                "✅ Comida Saludable GT Pagos está conectado correctamente.\n\n"
                "Cuando un cliente envíe por Instagram una captura de su "
                "comprobante de RESET DULCE, recibirás aquí el aviso con "
                "los botones APROBAR y RECHAZAR."
            )
        elif texto:
            enviar_telegram_texto(
                "🌿 Bot de pagos activo.\n\n"
                "No necesitas escribir comandos. Cuando llegue un comprobante "
                "desde Instagram, aparecerá aquí para revisarlo."
            )

        return "OK", 200

    # --------------------------------------------------
    # BOTONES APROBAR / RECHAZAR
    # --------------------------------------------------
    callback = data.get("callback_query")

    if not callback:
        return "OK", 200

    callback_id = callback.get("id")
    callback_data = callback.get("data", "")

    from_user = callback.get("from") or {}
    chat_id = str(from_user.get("id", ""))

    # Solo tú puedes usar los botones de aprobación.
    if str(TELEGRAM_ADMIN_CHAT_ID) != chat_id:
        responder_callback_telegram(
            callback_id,
            "No tienes permiso para aprobar esta compra."
        )
        return "OK", 200

    try:
        accion, order_id_texto = callback_data.split(":", 1)
        order_id = int(order_id_texto)
    except Exception:
        responder_callback_telegram(callback_id, "Solicitud inválida.")
        return "OK", 200

    if accion == "approve":

        resultado = aprobar_pedido_reset(order_id)

        if not resultado:
            responder_callback_telegram(
                callback_id,
                "No pude aprobar este pedido."
            )
            return "OK", 200

        sender_id = resultado["sender_id"]
        token = resultado["token"]

        enlace = f"{PUBLIC_BASE_URL}/descargar/reset-dulce/{token}"

        mensaje_cliente = (
            "✅ ¡Tu pago fue confirmado! 🌿\n\n"
            "Gracias por comprar RESET DULCE.\n\n"
            "📕 Descarga tu ebook aquí:\n"
            f"{enlace}\n\n"
            "Este enlace es personal y permite una sola descarga. "
            "Guarda el PDF después de descargarlo."
        )

        enviar_mensaje_instagram(sender_id, mensaje_cliente)

        actualizar_mensaje_telegram_procesado(
            callback,
            f"✅ PEDIDO #{order_id} APROBADO\n"
            "El enlace de RESET DULCE fue enviado al cliente por Instagram."
        )

        responder_callback_telegram(
            callback_id,
            "✅ Compra aprobada y enlace enviado."
        )

        return "OK", 200

    if accion == "reject":

        sender_id = rechazar_pedido_reset(order_id)

        if not sender_id:
            responder_callback_telegram(
                callback_id,
                "Este pedido ya fue procesado o no existe."
            )
            return "OK", 200

        mensaje_cliente = (
            "No pudimos confirmar el comprobante enviado. 🌿\n\n"
            "Por favor revisa que corresponda al pago de RESET DULCE "
            f"por {RESET_DULCE_PRICE} y envía nuevamente una captura clara."
        )

        enviar_mensaje_instagram(sender_id, mensaje_cliente)

        actualizar_mensaje_telegram_procesado(
            callback,
            f"❌ PEDIDO #{order_id} RECHAZADO\n"
            "Se avisó al cliente por Instagram."
        )

        responder_callback_telegram(
            callback_id,
            "❌ Comprobante rechazado. Se avisó al cliente."
        )

        return "OK", 200

    responder_callback_telegram(callback_id, "Acción desconocida.")
    return "OK", 200


# --------------------------------------------------
# WEBHOOK META / INSTAGRAM
# --------------------------------------------------

@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    # Verificación inicial de Meta
    if request.method == "GET":

        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("Webhook verificado correctamente")
            return challenge, 200

        return "Verificación fallida", 403

    # Eventos enviados por Instagram
    data = request.get_json(silent=True) or {}

    print("Evento recibido de Meta:", data)

    try:

        entries = data.get("entry", [])

        for entry in entries:

            messaging_events = entry.get("messaging", [])

            for event in messaging_events:

                message = event.get("message")

                # Ignorar eventos que no contienen mensaje
                if not message:
                    continue

                # Ignorar mensajes enviados por el propio bot
                if message.get("is_echo"):
                    print("Echo ignorado correctamente")
                    continue

                sender = event.get("sender", {})
                sender_id = sender.get("id")

                if not sender_id:
                    continue

                texto_usuario = message.get("text")
                imagen_url = extraer_url_imagen_instagram(message)

                # --------------------------------------------------
                # COMPROBANTE DE PAGO ENVIADO COMO IMAGEN
                # --------------------------------------------------
                if imagen_url:

                    usuario = obtener_usuario_db(sender_id)

                    if usuario is None:
                        enviar_mensaje_instagram(
                            sender_id,
                            "Recibí tu imagen 🌿, pero tuve un inconveniente "
                            "para registrar la solicitud. Inténtalo nuevamente "
                            "en unos minutos."
                        )
                        continue

                    # Si ya compró RESET DULCE, no creamos otra compra.
                    if usuario.get("reset_dulce_purchased"):
                        enviar_mensaje_instagram(
                            sender_id,
                            "Tu compra de RESET DULCE ya fue aprobada 🌿. "
                            "Si necesitas ayuda con tu descarga, escríbenos aquí."
                        )
                        continue

                    order_id = crear_o_actualizar_pedido_pendiente(
                        sender_id,
                        imagen_url
                    )

                    if not order_id:
                        enviar_mensaje_instagram(
                            sender_id,
                            "Recibí tu comprobante 🌿, pero tuve un inconveniente "
                            "para registrarlo. Por favor intenta enviarlo nuevamente."
                        )
                        continue

                    enviar_mensaje_instagram(
                        sender_id,
                        "¡Gracias! 🌿 Recibimos tu comprobante de pago.\n\n"
                        "Estamos validando tu compra. En cuanto sea confirmada, "
                        "recibirás aquí mismo tu acceso a RESET DULCE."
                    )

                    enviar_comprobante_a_telegram(
                        order_id,
                        sender_id,
                        imagen_url
                    )

                    continue

                # --------------------------------------------------
                # MENSAJE DE TEXTO NORMAL
                # --------------------------------------------------
                if texto_usuario:

                    print("Mensaje recibido:", texto_usuario)
                    print("Sender ID:", sender_id)

                    respuesta_ia = generar_respuesta(
                        sender_id,
                        texto_usuario
                    )

                    print("Respuesta IA:", respuesta_ia)

                    enviar_mensaje_instagram(
                        sender_id,
                        respuesta_ia
                    )

                    continue

                print("Mensaje sin texto o imagen ignorado")

    except Exception as e:

        print("ERROR PROCESANDO WEBHOOK:", str(e))

    return "EVENT_RECEIVED", 200


# --------------------------------------------------
# INICIALIZAR POSTGRESQL
# --------------------------------------------------

inicializar_base_datos()


# --------------------------------------------------
# INICIAR SERVIDOR
# --------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )