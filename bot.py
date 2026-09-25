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
