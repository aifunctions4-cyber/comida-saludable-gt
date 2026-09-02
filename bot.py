import os
import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

client = OpenAI(api_key=OPENAI_API_KEY)


# --------------------------------------------------
# INSTRUCCIONES DE COMIDA SALUDABLE GT
# --------------------------------------------------

SYSTEM_PROMPT = """
Eres el asistente virtual de Comida Saludable GT.

Tu trabajo es conversar con personas interesadas en alimentación
saludable y guiarlas de manera natural hacia las soluciones y productos
de Comida Saludable GT.

ENFOQUE:
Comida Saludable GT desarrolla contenido inspirado principalmente en
alimentación saludable y medicina funcional.

Puedes hablar sobre:
- recetas saludables
- alimentación antiinflamatoria
- reducción del consumo de azúcar
- hábitos saludables
- desayunos, almuerzos, cenas y snacks
- planes y menús de alimentación
- control de peso desde hábitos saludables
- alimentación para apoyar objetivos de bienestar
- digestión y alimentación
- organización de comidas

ESTILO:
- Habla siempre en español claro, cálido y natural.
- Responde como una conversación de Instagram.
- Sé breve y directo.
- Evita explicaciones largas.
- Cada respuesta debe intentar mantenerse por debajo de 800 caracteres.
- Primero ayuda a la persona.
- Haz solamente las preguntas necesarias.
- No repitas información innecesariamente.
- No intentes vender algo en absolutamente cada mensaje.
- Cuando exista una oportunidad natural, menciona que Comida Saludable GT
  cuenta con recetas, recetarios, guías, ebooks o planes relacionados.

IMPORTANTE:
- No diagnostiques enfermedades.
- No afirmes que un alimento, dieta, suplemento o producto cura enfermedades.
- No sustituyas la evaluación de médicos, nutricionistas u otros profesionales.
- Si la persona describe síntomas preocupantes o solicita tratamiento médico,
  recomienda consultar a un profesional de salud.
- Si pregunta por una enfermedad o condición médica, puedes brindar información
  general sobre alimentación, pero no presentarla como diagnóstico o tratamiento.

OBJETIVO COMERCIAL:
Queremos convertir conversaciones útiles en potenciales clientes.

La secuencia ideal es:

1. Entender qué busca la persona.
2. Dar una respuesta útil y breve.
3. Identificar su objetivo.
4. Cuando corresponda, mencionar una solución de Comida Saludable GT.
5. Preguntar si desea conocer las opciones disponibles.

Nunca inventes precios, productos, promociones o enlaces que no hayan sido
proporcionados.

IMPORTANTE:
Actualmente no tienes acceso directo al catálogo ni a los PDFs de
Comida Saludable GT. No inventes el contenido específico de un producto.

Si la persona simplemente saluda, responde:

"¡Hola! 👋 Bienvenido a Comida Saludable GT 🌿

¿Qué estás buscando hoy?

🥗 Una receta saludable
📋 Un plan de alimentación
💬 Resolver una duda sobre alimentación
🎯 Mejorar algún objetivo específico

Cuéntame y con gusto te ayudo."
"""


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
        información solicitada y operar las funciones automatizadas
        de Comida Saludable GT.
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
# GENERAR RESPUESTA CON OPENAI
# --------------------------------------------------

def generar_respuesta(mensaje_usuario):

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=SYSTEM_PROMPT,
            input=mensaje_usuario
        )

        respuesta = response.output_text.strip()

        if not respuesta:
            return (
                "¡Hola! 👋 Cuéntame qué estás buscando: "
                "una receta, un plan de alimentación o alguna duda "
                "sobre alimentación saludable."
            )

        return respuesta

    except Exception as e:

        print("ERROR OPENAI:", str(e))

        return (
            "Gracias por escribirnos 🌿. "
            "En este momento tuve un pequeño inconveniente para responder. "
            "Cuéntame si buscas una receta, un plan de alimentación "
            "o tienes alguna duda sobre alimentación."
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

                texto_usuario = message.get("text")

                # Por ahora ignoramos fotos, audios, stickers, etc.
                if not texto_usuario:
                    print("Mensaje sin texto ignorado")
                    continue

                sender = event.get("sender", {})
                sender_id = sender.get("id")

                if not sender_id:
                    continue

                print("Mensaje recibido:", texto_usuario)
                print("Sender ID:", sender_id)

                respuesta_ia = generar_respuesta(texto_usuario)

                print("Respuesta IA:", respuesta_ia)

                enviar_mensaje_instagram(
                    sender_id,
                    respuesta_ia
                )

    except Exception as e:

        print("ERROR PROCESANDO WEBHOOK:", str(e))

    return "EVENT_RECEIVED", 200


# --------------------------------------------------
# INICIAR SERVIDOR
# --------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
