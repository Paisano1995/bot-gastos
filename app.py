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
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
}

MESES_NOMBRE = {v: k.capitalize() for k, v in MESES.items()}

# Estado temporal para confirmar borrado (en memoria)
esperando_confirmacion = {}


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


def get_resumen(mes=None, anio=None):
    ws = get_worksheet()
    filas = ws.get_all_values()

    ahora = datetime.now()
    mes_objetivo = mes if mes else ahora.month
    anio_objetivo = anio if anio else ahora.year

    totales = defaultdict(float)
    total = 0.0

    for fila in filas[1:]:
        if len(fila) < 3:
            continue
        try:
            fecha = datetime.strptime(fila[0], "%Y-%m-%d %H:%M")
            monto = float(fila[1])
            categoria = fila[2].lower()
            if fecha.month == mes_objetivo and fecha.year == anio_objetivo:
                totales[categoria] += monto
                total += monto
        except:
            continue

    nombre_mes = MESES_NOMBRE[mes_objetivo]
    if total == 0:
        return f"📭 No hay gastos registrados en {nombre_mes} {anio_objetivo}."

    lineas = [f"📊 Resumen de {nombre_mes} {anio_objetivo}\n"]
    for cat, monto in sorted(totales.items(), key=lambda x: -x[1]):
        lineas.append(f"🏷️ {cat}: ${monto:,.0f}")
    lineas.append(f"\n💰 Total: ${total:,.0f}")

    return "\n".join(lineas)


def borrar_todo():
    ws = get_worksheet()
    filas = ws.get_all_values()
    if len(filas) <= 1:
        return "📭 No hay registros para borrar."
    # Mantener solo la primera fila (encabezados)
    ws.delete_rows(2, len(filas))
    return f"🗑️ Se borraron {len(filas) - 1} registros. La planilla quedó vacía."


@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    remitente = request.values.get("From", "")
    resp = MessagingResponse()

    msg_lower = incoming_msg.lower()

    # Confirmar borrado
    if msg_lower == "confirmar borrado":
        if esperando_confirmacion.get(remitente):
            esperando_confirmacion[remitente] = False
            try:
                resultado = borrar_todo()
                resp.message(resultado)
            except Exception as e:
                resp.message(f"⚠️ Error al borrar: {str(e)}")
        else:
            resp.message("No hay ningún borrado pendiente de confirmar.")
        return str(resp)

    # Borrar todo
    if msg_lower == "borrar todo":
        esperando_confirmacion[remitente] = True
        resp.message(
            "⚠️ *¿Estás seguro?*\n\n"
            "Esto va a eliminar *todos* los registros de la planilla.\n\n"
            "Respondé *confirmar borrado* para continuar, o cualquier otra cosa para cancelar."
        )
        return str(resp)

    # Cancelar borrado si estaba esperando confirmación
    if esperando_confirmacion.get(remitente):
        esperando_confirmacion[remitente] = False

    # Resumen del mes actual
    if msg_lower == "resumen":
        try:
            resp.message(get_resumen())
        except Exception as e:
            resp.message(f"⚠️ Error: {str(e)}")
        return str(resp)

    # Resumen de un mes específico: "resumen enero", "resumen marzo 2025"
    match_mes = re.match(r"^resumen\s+(\w+)(?:\s+(\d{4}))?$", msg_lower)
    if match_mes:
        nombre_mes = match_mes.group(1)
        anio_str = match_mes.group(2)
        if nombre_mes in MESES:
            mes_num = MESES[nombre_mes]
            anio = int(anio_str) if anio_str else datetime.now().year
            try:
                resp.message(get_resumen(mes=mes_num, anio=anio))
            except Exception as e:
                resp.message(f"⚠️ Error: {str(e)}")
        else:
            resp.message(f"No reconozco el mes '{nombre_mes}'. Usá el nombre en español, ej: *resumen enero*")
        return str(resp)

    # Registrar gasto
    parsed = parse_gasto(incoming_msg)
    if parsed is None:
        resp.message(
            "No entendí el mensaje 🤔\n\n"
            "Comandos disponibles:\n\n"
            "▪️ Registrar gasto:\n"
            "*gasto MONTO CATEGORIA DESCRIPCION*\n"
            "Ej: gasto 500 comida almuerzo\n\n"
            "▪️ Ver resumen del mes actual:\n"
            "*resumen*\n\n"
            "▪️ Ver resumen de un mes específico:\n"
            "*resumen enero*\n"
            "*resumen marzo 2025*\n\n"
            "▪️ Borrar todos los registros:\n"
            "*borrar todo*"
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
