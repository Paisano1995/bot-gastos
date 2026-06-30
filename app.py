import os
import json
import re
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ----------------------------------------------------------------------
# CONFIGURACIÓN: estas dos variables se configuran como "Environment
# Variables" en Render, NO se escriben acá directamente.
# ----------------------------------------------------------------------
SHEET_ID = os.environ.get("SHEET_ID")                # ID de tu Google Sheet
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")  # Contenido del JSON de la cuenta de servicio

# Nombre de la hoja (pestaña) dentro del archivo de Sheets
WORKSHEET_NAME = "Hoja 1"  # Cambialo si tu pestaña se llama distinto

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_worksheet():
    """Conecta con Google Sheets usando las credenciales de la cuenta de servicio."""
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet(WORKSHEET_NAME)


def parse_mensaje(texto):
    """
    Espera mensajes con el formato:
        gasto 500 comida almuerzo con amigos
    Devuelve (monto, categoria, descripcion) o None si no matchea.
    """
    texto = texto.strip()
    patron = r"^gasto\s+(\d+(?:[.,]\d+)?)\s+(\S+)\s*(.*)$"
    match = re.match(patron, texto, re.IGNORECASE)
    if not match:
        return None

    monto_str, categoria, descripcion = match.groups()
    monto = float(monto_str.replace(",", "."))
    descripcion = descripcion.strip() if descripcion else "-"
    return monto, categoria, descripcion


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "")
    resp = MessagingResponse()

    parsed = parse_mensaje(incoming_msg)

    if parsed is None:
        resp.message(
            "No entendí el mensaje 🤔\n\n"
            "Usá este formato:\n"
            "*gasto MONTO CATEGORIA DESCRIPCION*\n\n"
            "Ejemplo:\n"
            "gasto 500 comida almuerzo con amigos"
        )
        return str(resp)

    monto, categoria, descripcion = parsed

    try:
        ws = get_worksheet()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_row([fecha, monto, categoria, descripcion])

        resp.message(
            f"✅ Gasto registrado\n"
            f"💰 Monto: {monto}\n"
            f"🏷️ Categoría: {categoria}\n"
            f"📝 Descripción: {descripcion}"
        )
    except Exception as e:
        resp.message(f"⚠️ Error al guardar el gasto: {str(e)}")

    return str(resp)


@app.route("/", methods=["GET"])
def home():
    return "Bot de gastos funcionando ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
