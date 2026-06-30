import os
import json
import re
from datetime import datetime
from collections import defaultdict
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SHEET_ID = os.environ.get("SHEET_ID")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")
WORKSHEET_NAME = "Hoja 1"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

MESES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}


def get_worksheet():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet(WORKSHEET_NAME)


def parse_gasto(texto):
    texto = texto.strip()
    patron = r"^gasto\s+(\d+(?:[.,]\d+)?)\s+(\S+)\s*(.*)$"
    match = re.match(patron, texto, re.IGNORECASE)
    if not match:
        return None
    monto_str, categoria, descripcion = match.groups()
    monto = float(monto_str.replace(",", "."))
    descripcion = descripcion.strip() if descripcion else "-"
    return monto, categoria, descripcion


def get_resumen():
    ws = get_worksheet()
    filas = ws.get_all_values()

    ahora = datetime.now()
    mes_actual = ahora.month
    anio_actual = ahora.year

    totales = defaultdict(float)
    total_mes = 0.0

    for fila in filas[1:]:  # saltar encabezado
        if len(fila) < 3:
            continue
        try:
            fecha_str = fila[0]
            monto = float(fila[1])
            categoria = fila[2].lower()

            fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
            if fecha.month == mes_actual and fecha.year == anio_actual:
                totales[categoria] += monto
                total_mes += monto
        except:
            continue

    if total_mes == 0:
        return f"📭 No hay gastos registrados en {MESES[mes_actual]}."

    nombre_mes = MESES[mes_actual]
    lineas = [f"📊 Resumen de {nombre_mes} {anio_actual}\n"]
    for cat, monto in sorted(totales.items(), key=lambda x: -x[1]):
        lineas.append(f"🏷️ {cat}: ${monto:,.0f}")
    lineas.append(f"\n💰 Total del mes: ${total_mes:,.0f}")

    return "\n".join(lineas)


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()

    # Comando: resumen
    if incoming_msg.lower() == "resumen":
        try:
            resumen = get_resumen()
            resp.message(resumen)
        except Exception as e:
            resp.message(f"⚠️ Error al obtener el resumen: {str(e)}")
        return str(resp)

    # Comando: gasto
    parsed = parse_gasto(incoming_msg)
    if parsed is None:
        resp.message(
            "No entendí el mensaje 🤔\n\n"
            "Comandos disponibles:\n\n"
            "▪️ Registrar gasto:\n"
            "*gasto MONTO CATEGORIA DESCRIPCION*\n"
            "Ej: gasto 500 comida almuerzo\n\n"
            "▪️ Ver resumen del mes:\n"
            "*resumen*"
        )
        return str(resp)

    monto, categoria, descripcion = parsed
    try:
        ws = get_worksheet()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        ws.append_row([fecha, monto, categoria, descripcion])
        resp.message(
            f"✅ Gasto registrado\n"
            f"💰 Monto: ${monto:,.0f}\n"
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
