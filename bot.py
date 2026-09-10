import os
import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Biblioteca privada de Comida Saludable GT
VECTOR_STORE_ID = "vs_6a9b49945b088191b211d8b71fdb9d0d"

client = OpenAI(api_key=OPENAI_API_KEY)


# --------------------------------------------------
# INSTRUCCIONES DE COMIDA SALUDABLE GT
# --------------------------------------------------

SYSTEM_PROMPT = """
Eres el asistente virtual de Comida Saludable GT.

Tu función principal es ayudar a las personas a crear y descubrir recetas,
ideas de comidas y menús saludables adaptados a lo que buscan.

Tienes acceso mediante una herramienta interna a una biblioteca privada de
contenido aprobado por Comida Saludable GT.


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

Si el mensaje ya contiene suficiente información, NO hagas preguntas
adicionales y crea la receta directamente.

Ejemplo:

Usuario:
"Quiero una cena saludable."

Puedes preguntar:

"¡Claro! 😊 Para adaptarla mejor a lo que buscas:

1. ¿Hay algún ingrediente que quieras usar o evitar?
2. ¿La prefieres rápida, ligera o tienes alguna otra preferencia?"

Pero si el usuario dice:

"Tengo pollo, aguacate y tomate. Quiero una cena rápida sin lácteos."

No necesitas preguntar nada.
Crea directamente una receta tomando en cuenta esa información.

No conviertas la conversación en un cuestionario.
El objetivo es facilitarle las cosas a la persona.


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
# GENERAR RESPUESTA CON OPENAI + FILE SEARCH
# --------------------------------------------------

def generar_respuesta(mensaje_usuario):

    try:

        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions=SYSTEM_PROMPT,
            input=mensaje_usuario,
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
            return (
                "¡Hola! 👋 Cuéntame qué te gustaría preparar: "
                "una receta, un postre, un snack o un menú saludable."
            )

        return respuesta

    except Exception as e:

        print("ERROR OPENAI:", str(e))

        return (
            "Gracias por escribirnos 🌿. "
            "En este momento tuve un pequeño inconveniente para responder. "
            "Cuéntame qué tipo de receta estás buscando."
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
