import os
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "")


@app.route("/", methods=["GET"])
def home():
    return "Comida Saludable GT - Bot funcionando correctamente", 200


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
    <body style="font-family: Arial; max-width: 900px; margin: 40px auto;
                 line-height: 1.6; padding: 0 20px;">

        <h1>Política de Privacidad</h1>

        <h3>Comida Saludable GT</h3>

        <p>
        Esta Política de Privacidad explica cómo Comida Saludable GT procesa
        información relacionada con las interacciones realizadas a través
        de nuestra cuenta de Instagram.
        </p>

        <h2>Información que procesamos</h2>

        <p>
        Podemos procesar mensajes, identificadores de usuario y otra información
        proporcionada voluntariamente cuando una persona interactúa con nuestra
        cuenta de Instagram.
        </p>

        <h2>Uso de la información</h2>

        <p>
        Utilizamos esta información para responder mensajes, brindar información
        solicitada y operar las funciones automatizadas de Comida Saludable GT.
        </p>

        <h2>Compartición de información</h2>

        <p>
        No vendemos información personal. La información puede ser procesada por
        proveedores tecnológicos necesarios para operar nuestro servicio.
        </p>

        <h2>Eliminación de datos</h2>

        <p>
        Los usuarios pueden solicitar la eliminación de su información contactando
        directamente a Comida Saludable GT mediante nuestra cuenta oficial de Instagram.
        </p>

        <h2>Contacto</h2>

        <p>
        Para consultas relacionadas con esta política puedes contactar a
        Comida Saludable GT.
        </p>

    </body>
    </html>
    """, 200


def enviar_mensaje(recipient_id, texto):

    url = "https://graph.instagram.com/v24.0/me/messages"

    headers = {
        "Authorization": f"Bearer {INSTAGRAM_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": texto
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
            response.text,
            flush=True
        )

        return response

    except Exception as e:

        print(
            "Error enviando mensaje:",
            str(e),
            flush=True
        )

        return None


@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    # Verificación del webhook por Meta
    if request.method == "GET":

        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:

            print(
                "Webhook verificado correctamente",
                flush=True
            )

            return challenge, 200

        return "Verificación fallida", 403


    # Eventos enviados por Instagram
    data = request.get_json(silent=True) or {}

    print(
        "Evento recibido de Meta:",
        data,
        flush=True
    )

    try:

        entries = data.get("entry", [])

        for entry in entries:

            messaging_events = entry.get("messaging", [])

            for event in messaging_events:

                message = event.get("message", {})

                # IMPORTANTE:
                # Ignorar mensajes enviados por nuestro propio bot.
                if message.get("is_echo") is True:

                    print(
                        "Evento is_echo ignorado",
                        flush=True
                    )

                    continue

                sender = event.get("sender", {})
                sender_id = sender.get("id")

                texto = message.get("text")

                if not sender_id or not texto:
                    continue

                print(
                    "Mensaje recibido:",
                    texto,
                    flush=True
                )

                print(
                    "Sender ID:",
                    sender_id,
                    flush=True
                )

                respuesta = (
                    "¡Hola! 👋 Gracias por escribir a Comida Saludable GT. "
                    "¿En qué podemos ayudarte?"
                )

                enviar_mensaje(
                    sender_id,
                    respuesta
                )

    except Exception as e:

        print(
            "Error procesando webhook:",
            str(e),
            flush=True
        )

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            8080
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
