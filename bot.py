import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, PreCheckoutQueryHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

TOKEN = "8622205755:AAF7iBVUB0j3Lru_lvM2KhjfVgqfYohDWiE"  # ⚠️ INSERISCI QUI IL TUO TOKEN
CHANNEL_PUBLIC = "-1003987538719"       # 📢 IL TUO CANALE PUBBLICO
CHANNEL_PRIVATE = "-1003880676633"      # 💎 IL TUO CANALE PRIVATO
TUO_ID = 739892534                      # ✅ IL TUO ID TELEGRAM

# ---- IMPOSTAZIONI PIANI VIP ----
PIANI_VIP = {
    "settimana": {"nome": "1 Settimana", "stelle": 100, "euro": "2,00€", "giorni": 7},
    "mese": {"nome": "1 Mese", "stelle": 250, "euro": "5,00€", "giorni": 30},
    "trimestre": {"nome": "3 Mesi", "stelle": 600, "euro": "12,00€", "giorni": 90}
}

logging.basicConfig(level=logging.INFO)

# Stati per le foto
F_SPORT, F_FOTO, F_STAKE, F_DOVE = range(100, 104)

# -------------------------
# DATABASE
# -------------------------
if not os.path.exists("data"):
    os.makedirs("data")
DB_PATH = "data/scommesse.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS proposte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT, sport TEXT, partita TEXT, pronostico TEXT,
            quota REAL, stake INTEGER, analisi TEXT, dove TEXT, data TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS abbonati (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            data_inizio TEXT,
            data_scadenza TEXT,
            avvisato INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def salva_proposta(d):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO proposte (tipo, sport, partita, pronostico, quota, stake, analisi, dove, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("foto", d.get("sport"), "—", "—", 0.0, int(d.get("stake", 1)), "", d.get("dove", "pubblico"), datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid

def salva_abbonato(user_id, username, giorni_da_aggiungere):
    inizio = datetime.now()
    scadenza = inizio + timedelta(days=giorni_da_aggiungere)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Se è già abbonato, sommiamo i giorni alla sua vecchia scadenza (se non è già scaduto)
    c.execute("SELECT data_scadenza FROM abbonati WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    if res:
        scadenza_attuale = datetime.strptime(res[0], "%Y-%m-%d %H:%M")
        if scadenza_attuale > inizio:
            scadenza = scadenza_attuale + timedelta(days=giorni_da_aggiungere)
            
    c.execute("""
        INSERT OR REPLACE INTO abbonati (user_id, username, data_inizio, data_scadenza, avvisato)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, username, inizio.strftime("%Y-%m-%d %H:%M"), scadenza.strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_abbonato(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT data_inizio, data_scadenza FROM abbonati WHERE user_id = ?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TUO_ID:
            await update.message.reply_text("❌ Comando riservato all'admin.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper

# -------------------------
# Tastiere
# -------------------------
def kb_sport():
    return ReplyKeyboardMarkup([["⚽ Calcio", "🏀 Basket"], ["🎾 Tennis", "🏆 Altro"]], resize_keyboard=True, one_time_keyboard=True)
def kb_stake():
    return ReplyKeyboardMarkup([["1", "2", "3"], ["4", "5"]], resize_keyboard=True, one_time_keyboard=True)
def kb_dove():
    return ReplyKeyboardMarkup([["📢 Pubblico", "💎 Privato"], ["📢💎 Entrambi"]], resize_keyboard=True, one_time_keyboard=True)

# -------------------------
# COMANDI BASE
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == TUO_ID:
        await update.message.reply_text(
            "👋 Ciao Carmine, bentornato!\n\n"
            "🛠 **Comandi Admin:**\n"
            "/nuovafoto - Carica schedina\n"
            "/statistiche - Controlla incassi e iscritti\n"
            "/cancel - Annulla operazione",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        testo_benvenuto = (
            "👋 Benvenuto nel Bot Ufficiale!\n\n"
            "💎 **Accesso al Canale VIP**\n"
            "Entra per ricevere tutti i miei pronostici esclusivi.\n\n"
            "👉 Scrivi /vip per abbonarti\n"
            "👉 Scrivi /profilo per controllare il tuo stato"
        )
        await update.message.reply_text(testo_benvenuto)

async def profilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    dati = get_abbonato(user.id)
    
    if not dati:
        await update.message.reply_text("❌ Non hai nessun abbonamento attivo.\nScrivi /vip per abbonarti!")
        return

    scadenza_str = dati[1]
    scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d %H:%M")
    
    if datetime.now() > scadenza:
        await update.message.reply_text("⚠️ Il tuo abbonamento è scaduto.\nScrivi /vip per rinnovare!")
    else:
        giorni_rimasti = (scadenza - datetime.now()).days
        await update.message.reply_text(
            f"👤 **Profilo di {user.first_name}**\n\n"
            f"✅ **Stato:** VIP Attivo\n"
            f"⏳ **Scadenza:** {scadenza.strftime('%d/%m/%Y')}\n"
            f"📅 **Giorni rimanenti:** {giorni_rimasti}"
        )

# -------------------------
# SISTEMA VIP A PIANI
# -------------------------
async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"🥉 1 Settimana - {PIANI_VIP['settimana']['euro']}", callback_data="vip_settimana")],
        [InlineKeyboardButton(f"🥈 1 Mese - {PIANI_VIP['mese']['euro']}", callback_data="vip_mese")],
        [InlineKeyboardButton(f"🥇 3 Mesi - {PIANI_VIP['trimestre']['euro']}", callback_data="vip_trimestre")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    testo = (
        "💎 **Abbonamento al Canale VIP**\n\n"
        "Scegli il piano che preferisci. I prezzi sono mostrati in Euro per comodità, "
        "ma pagherai tramite le **Telegram Stars (⭐)** in totale sicurezza.\n\n"
        "Seleziona un'opzione qui sotto per ricevere le istruzioni:"
    )
    await update.message.reply_text(testo, reply_markup=reply_markup)

async def scelta_piano_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    scelta = query.data.replace("vip_", "")
    if scelta not in PIANI_VIP: return
    
    piano = PIANI_VIP[scelta]
    
    # Istruzioni scritte chiaramente all'utente
    istruzioni = (
        f"Hai scelto l'abbonamento per **{piano['nome']}**.\n"
        f"Il costo è di **{piano['euro']}** (pari a {piano['stelle']} ⭐).\n\n"
        "ℹ️ **COME ABBONARSI:**\n"
        "1. Clicca sul pulsante Paga nella fattura qui sotto.\n"
        "2. Se non hai le Telegram Stars, potrai ricaricarle all'istante tramite **Apple Pay, Google Pay o carta di credito** direttamente dal tuo telefono.\n"
        "3. Appena fatto, il bot ti manderà in automatico il link segreto per entrare!\n\n"
        "⬇️ *Procedi con il pagamento qui sotto* ⬇️"
    )
    
    await query.message.reply_text(istruzioni)
    
    prices = [LabeledPrice(f"Accesso VIP {piano['nome']}", piano['stelle'])]
    
    try:
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Canale VIP Scommesse 💎",
            description=f"Accesso garantito e automatico per {piano['giorni']} giorni.",
            payload=f"abbonamento_{scelta}",
            provider_token="", # Vuoto per Telegram Stars
            currency="XTR",    
            prices=prices
        )
    except Exception as e:
        await query.message.reply_text(f"⚠️ Errore fattura: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if "abbonamento_" not in query.invoice_payload:
        await query.answer(ok=False, error_message="Errore nel payload.")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    payload = update.message.successful_payment.invoice_payload
    scelta_piano = payload.replace("abbonamento_", "")
    
    # Prende i giorni del piano scelto, se c'è un errore dà 30 di default
    piano = PIANI_VIP.get(scelta_piano, PIANI_VIP["mese"])
    giorni_acquistati = piano["giorni"]
    
    salva_abbonato(user.id, user.username or user.first_name, giorni_acquistati)
    
    try:
        invite_link = await context.bot.create_chat_invite_link(chat_id=int(CHANNEL_PRIVATE), member_limit=1)
        await update.message.reply_text(
            f"✅ Pagamento ricevuto correttamente!\n\n"
            f"Benvenuto nel gruppo VIP 💎\nEcco il tuo link d'accesso esclusivo:\n\n{invite_link.invite_link}"
        )
        await context.bot.send_message(chat_id=TUO_ID, text=f"💰 NUOVO INCASSO!\n{user.first_name} ha acquistato il piano {piano['nome']} ({piano['stelle']} ⭐)!")
    except Exception as e:
        await context.bot.send_message(chat_id=TUO_ID, text=f"⚠️ ERRORE LINK VIP per {user.first_name}: {e}")

# -------------------------
# FLUSSO FOTO (Admin)
# -------------------------
@admin_only
async def nuovafoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🏟 Scegli lo sport:", reply_markup=kb_sport())
    return F_SPORT

async def f_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scelta = update.message.text.strip()
    if scelta not in ["⚽ Calcio", "🏀 Basket", "🎾 Tennis", "🏆 Altro"]:
        return F_SPORT
    context.user_data["sport"] = scelta
    await update.message.reply_text("📸 Allega la foto:", reply_markup=ReplyKeyboardRemove())
    return F_FOTO

async def f_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return F_FOTO
    context.user_data["foto_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("🎯 Difficoltà (1-5):", reply_markup=kb_stake())
    return F_STAKE

async def f_stake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = update.message.text.strip()
    if testo not in {"1", "2", "3", "4", "5"}: return F_STAKE
    context.user_data["stake"] = int(testo)
    await update.message.reply_text("📍 Dove pubblichiamo?", reply_markup=kb_dove())
    return F_DOVE

async def f_dove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mappa = {"📢 Pubblico": "pubblico", "💎 Privato": "privato", "📢💎 Entrambi": "entrambi"}
    scelta = update.message.text.strip()
    if scelta not in mappa: return F_DOVE

    d = context.user_data
    d["dove"] = mappa[scelta]
    stelle = "⭐" * int(d["stake"])
    caption = f"🏟 {d['sport']}\n🎯 Difficoltà: {stelle}"
    salva_proposta(d)

    await update.message.reply_text("⏳ Pubblicando...", reply_markup=ReplyKeyboardRemove())
    try:
        if d["dove"] in ("pubblico", "entrambi"):
            await context.bot.send_photo(chat_id=int(CHANNEL_PUBLIC), photo=d["foto_id"], caption=caption)
    except: pass
    try:
        if d["dove"] in ("privato", "entrambi"):
            await context.bot.send_photo(chat_id=int(CHANNEL_PRIVATE), photo=d["foto_id"], caption=caption)
    except: pass

    await update.message.reply_text(f"✅ Finito!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Annullato.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------------
# PANNELLO ADMIN (Statistiche modificate per i vari piani)
# -------------------------
@admin_only
async def statistiche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM abbonati")
    tot_abbonati = c.fetchone()[0]
    
    adesso = datetime.now()
    c.execute("SELECT COUNT(*) FROM abbonati WHERE data_scadenza > ?", (adesso.strftime("%Y-%m-%d %H:%M"),))
    attivi = c.fetchone()[0]
    conn.close()
    
    await update.message.reply_text(
        f"📊 **Statistiche Bot**\n\n"
        f"👥 Totale clienti storici: {tot_abbonati}\n"
        f"✅ Abbonamenti attivi ora: {attivi}"
    )

# -------------------------
# CONTROLLO SCADENZE ORARIE
# -------------------------
async def controlla_scadenze(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    adesso = datetime.now()
    
    c.execute("SELECT user_id FROM abbonati WHERE data_scadenza < ?", (adesso.strftime("%Y-%m-%d %H:%M"),))
    scaduti = c.fetchall()
    for utente in scaduti:
        user_id = utente[0]
        try:
            await context.bot.ban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=user_id)
            await context.bot.unban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=user_id)
            await context.bot.send_message(chat_id=user_id, text="⚠️ Il tuo abbonamento VIP è terminato.\nSei stato rimosso dal canale. Usa /vip per rinnovare!")
            c.execute("DELETE FROM abbonati WHERE user_id = ?", (user_id,))
        except: pass
    
    tra_due_giorni = adesso + timedelta(days=2)
    c.execute("SELECT user_id FROM abbonati WHERE data_scadenza < ? AND avvisato = 0", (tra_due_giorni.strftime("%Y-%m-%d %H:%M"),))
    da_avvisare = c.fetchall()
    for utente in da_avvisare:
        user_id = utente[0]
        try:
            await context.bot.send_message(chat_id=user_id, text="⏳ Ciao! Il tuo abbonamento VIP scadrà tra meno di 2 giorni.\nScrivi /vip per rinnovarlo ed estendere la tua scadenza!")
            c.execute("UPDATE abbonati SET avvisato = 1 WHERE user_id = ?", (user_id,))
        except: pass

    conn.commit()
    conn.close()

# -------------------------
# MAIN
# -------------------------
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv_foto = ConversationHandler(
        entry_points=[CommandHandler("nuovafoto", nuovafoto)],
        states={
            F_SPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, f_sport)],
            F_FOTO: [MessageHandler(filters.PHOTO, f_foto)],
            F_STAKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, f_stake)],
            F_DOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, f_dove)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profilo", profilo))
    app.add_handler(CommandHandler("statistiche", statistiche))
    app.add_handler(CommandHandler("vip", vip_command))
    
    # Questo intercetta i bottoni Inline scelti dall'utente
    app.add_handler(CallbackQueryHandler(scelta_piano_callback, pattern="^vip_"))
    
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(conv_foto)

    job_queue = app.job_queue
    job_queue.run_repeating(controlla_scadenze, interval=3600, first=10)

    print("Bot avviato e pronto!")
    app.run_polling()

if __name__ == "__main__":
    main()
