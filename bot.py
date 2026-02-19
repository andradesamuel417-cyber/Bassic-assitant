import datetime
import os
import pickle
import pytz
import re
import dateparser


from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.ext import CommandHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from telegram.ext import ConversationHandler


from datetime import timedelta
from dotenv import load_dotenv




from dateparser.search import search_dates
from datetime import datetime, time
from googleapiclient.discovery import build

import os
from dotenv import load_dotenv


import os
from telegram.ext import ApplicationBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("No se encontró la variable de entorno BOT_TOKEN")  # evita crasheos silenciosos

print("TOKEN cargado correctamente")  # temporal, solo para debug

app = ApplicationBuilder().token(BOT_TOKEN).build()



TOKEN = os.getenv("BOT_TOKEN")
SCOPES = ['https://www.googleapis.com/auth/calendar']

TIMEZONE = pytz.timezone("America/Guayaquil")

ASK_DURATION = 1


# -------- GOOGLE SERVICE --------
def get_service():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    service = build('calendar', 'v3', credentials=creds)
    return service


def check_conflict(service, start_time, end_time):
    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    return len(events) > 0


# -------- TELEGRAM HANDLERS --------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 😎 Soy tu asistente KSXD.\n\n"
        "Escríbeme algo como:\n"
        "👉 mañana a las 3 reunión con Juan"
    )


async def crear_evento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    # -------- EXTRAER FECHA --------
    date_match = re.search(
        r'(\d{1,2}\s+de\s+\w+|mañana|hoy|pasado mañana)',
        text
    )

    if not date_match:
        await update.message.reply_text(
            "No pude entender la fecha 😅\n"
            "Ejemplo: 21 de febrero a las 6 reunión"
        )
        return ConversationHandler.END

    date_part = date_match.group(0)

    parsed_date = dateparser.parse(
        date_part,
        languages=['es'],
        settings={
            'TIMEZONE': 'America/Guayaquil',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future'
        }
    )

    if not parsed_date:
        await update.message.reply_text("No pude interpretar la fecha 😅")
        return ConversationHandler.END

    # -------- EXTRAER HORA --------
    hour_match = re.search(r'a las (\d{1,2})', text)
    am_pm_match = re.search(r'(am|pm)', text)

    if hour_match:
        hour = int(hour_match.group(1))

        if am_pm_match:
            if am_pm_match.group(1) == "pm" and hour != 12:
                hour += 12
            if am_pm_match.group(1) == "am" and hour == 12:
                hour = 0
        else:
            if 1 <= hour <= 7:
                hour += 12

        parsed_date = parsed_date.replace(hour=hour, minute=0, second=0)
    else:
        parsed_date = parsed_date.replace(hour=9, minute=0, second=0)

    # -------- DESCRIPCIÓN --------
    description = text.replace(date_part, "").strip()
    if hour_match:
        description = re.sub(r'a las \d{1,2}(\s?(am|pm))?', '', description)

    if not description:
        description = "Evento sin título"

    # Guardamos datos temporalmente
    context.user_data["pending_event"] = {
        "summary": description,
        "start": parsed_date
    }

    await update.message.reply_text("⏳ ¿Cuántas horas durará el evento?")
    return ASK_DURATION

#-------Función duración-----
async def recibir_duracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hours = float(update.message.text)

        event_data = context.user_data.get("pending_event")
        if not event_data:
            await update.message.reply_text("Error interno.")
            return ConversationHandler.END

        start_time = event_data["start"]
        end_time = start_time + timedelta(hours=hours)

        service = get_service()

        # Verificar conflicto con duración real
        if check_conflict(service, start_time, end_time):
            await update.message.reply_text("❌ Ya tienes un evento en ese horario.")
            return ConversationHandler.END

        event = {
            'summary': event_data["summary"],
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': "America/Guayaquil",
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': "America/Guayaquil",
            },
        }

        service.events().insert(calendarId='primary', body=event).execute()

        await update.message.reply_text(
            f"✅ Evento creado:\n\n"
            f"📅 {event_data['summary']}\n"
            f"🕒 {start_time.strftime('%d/%m/%Y %H:%M')}\n"
            f"⏳ Duración: {hours} horas"
        )

    except ValueError:
        await update.message.reply_text("Escribe un número válido (ej: 1.5)")
        return ASK_DURATION

    return ConversationHandler.END


#-------Función /list----------
async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa: /list 21 de febrero")
        return

    date_text = " ".join(context.args).lower()

    parsed_date = dateparser.parse(
        date_text,
        languages=['es'],
        settings={
            'TIMEZONE': 'America/Guayaquil',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future'
        }
    )

    if not parsed_date:
        await update.message.reply_text("No pude entender la fecha 😅")
        return

    start_day = parsed_date.replace(hour=0, minute=0, second=0)
    end_day = parsed_date.replace(hour=23, minute=59, second=59)

    service = get_service()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_day.isoformat(),
        timeMax=end_day.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    if not events:
        await update.message.reply_text("No tienes eventos ese día 🎉")
        return

    # Guardamos eventos en memoria temporal
    context.user_data["last_events"] = events

    message = "📅 Eventos:\n\n"
    keyboard = []

    for i, event in enumerate(events):
        start = event['start'].get('dateTime', event['start'].get('date'))
        dt = dateparser.parse(start)

        message += f"{i+1}. {event['summary']} - {dt.strftime('%H:%M')}\n"

        keyboard.append([
            InlineKeyboardButton(
                f"🗑 Eliminar {i+1}",
                callback_data=f"delete_{i}"
            )
        ])

    # Botón cancelar general
    keyboard.append([
        InlineKeyboardButton("❌ No eliminar", callback_data="cancel_all")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        message + "\n\nSelecciona el evento que quieres eliminar:",
        reply_markup=reply_markup
    )



#--------------Función delete----------
async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "last_events" not in context.user_data:
        await update.message.reply_text("Primero usa /list para ver eventos.")
        return

    if not context.args:
        await update.message.reply_text("Usa: /delete 1")
        return

    try:
        index = int(context.args[0]) - 1
        events = context.user_data["last_events"]

        if index < 0 or index >= len(events):
            await update.message.reply_text("Número inválido.")
            return

        event = events[index]
        service = get_service()

        service.events().delete(
            calendarId='primary',
            eventId=event['id']
        ).execute()

        await update.message.reply_text("🗑 Evento eliminado correctamente.")

    except ValueError:
        await update.message.reply_text("Debes poner un número.")

#--------Manejador de botones.----
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("delete_"):
        index = int(data.split("_")[1])
        events = context.user_data.get("last_events")

        if not events or index >= len(events):
            await query.edit_message_text("Evento no encontrado.")
            return

        event = events[index]

        # Guardamos el evento pendiente de eliminar
        context.user_data["pending_delete"] = event

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="confirm_delete"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel_delete"),
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"¿Seguro que quieres eliminar:\n\n{event['summary']}?",
            reply_markup=reply_markup
        )

    elif data == "confirm_delete":
        event = context.user_data.get("pending_delete")

        if not event:
            await query.edit_message_text("No hay evento pendiente.")
            return

        service = get_service()

        service.events().delete(
            calendarId='primary',
            eventId=event['id']
        ).execute()

        await query.edit_message_text("🗑 Evento eliminado correctamente.")

    elif data == "cancel_delete":
        await query.edit_message_text("❌ Eliminación cancelada.")
    
    elif data == "cancel_all":
        await query.edit_message_text("👍 Operación cancelada.")

#---------Hoy----------
async def hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("America/Guayaquil")
    now = datetime.now(tz)

    start_day = tz.localize(datetime.combine(now.date(), time.min))
    end_day = tz.localize(datetime.combine(now.date(), time.max))

    service = get_service()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=start_day.isoformat(),
        timeMax=end_day.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    if not events:
        await update.message.reply_text("🎉 No tienes eventos hoy.")
        return

    message = f"📅 Agenda de hoy ({now.strftime('%d %B %Y')})\n\n"

    for i, event in enumerate(events):
        start_raw = event['start'].get('dateTime', event['start'].get('date'))
        end_raw = event['end'].get('dateTime', event['end'].get('date'))

        dt_start = dateparser.parse(start_raw)
        dt_end = dateparser.parse(end_raw)

        if 'dateTime' in event['start']:
            duration = dt_end - dt_start
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60

            message += (
                f"{i+1}. {event['summary']} - "
                f"{dt_start.strftime('%H:%M')} "
                f"({hours}h {minutes}m)\n"
            )
        else:
            # Evento de todo el día
            message += (
                f"{i+1}. {event['summary']} - "
                f"📅 Todo el día\n"
            )




# -------- MAIN --------

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(30)
    .read_timeout(30)
    .write_timeout(30)
    .build()
)

app.add_handler(CommandHandler("start", start))
conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, crear_evento)],
    states={
        ASK_DURATION: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_duracion)
        ],
    },
    fallbacks=[],
)

app.add_handler(conv_handler)

app.add_handler(CommandHandler("list", list_events))
app.add_handler(CommandHandler("delete", delete_event))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(CommandHandler("hoy", hoy))




print("🤖 Bot corriendo...")
app.run_polling()


