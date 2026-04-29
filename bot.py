import logging
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, MessageHandler, PreCheckoutQueryHandler,
    ContextTypes, ConversationHandler, filters
)

TOKEN = "8622205755:AAF7iBVUB0j3Lru_lvM2KhjfVgqfYohDWiE"               # ⚠️ INSERISCI QUI IL TUO TOKEN
CHANNEL_PUBLIC = "-1003987538719"       # 📢 IL TUO CANALE PUBBLICO
CHANNEL_PRIVATE = "-1003880676633"      # 💎 IL TUO CANALE PRIVATO
TUO_ID = 739892534                      # ✅ IL TUO ID TELEGRAM

# ---- IMPOSTAZIONI ABBONAMENTO ----
PREZZO_STELLE = 250  # 250 Telegram Stars (equivalgono a circa 5 Euro)

logging.basicConfig(level=logging.INFO)

# Stati per le foto
F_SPORT, F_FOTO, F_STAKE, F_DOVE = range(100, 104)

# -------------------------
# Tastiere Personalizzate
# -------------------------
def kb_sport():
    return ReplyKeyboardMarkup(
        [["⚽ Calcio", "🏀 Basket"], ["🎾 Tennis", "🏆 Altro"]], 
        resize_keyboard=True, one_time_keyboard=True
    )

def kb_stake():
    return ReplyKeyboardMarkup(
        [["1", "2", "3"], ["4", "5"]], 
        resize_keyboard=True, one_time_keyboard=True
    )

def kb_dove():
    return ReplyKeyboardMarkup(
        [["📢 Pubblico", "💎 Privato"], ["📢💎 Entrambi"]], 
        resize_keyboard=True, one_time_keyboard=True
    )

# -------------------------
# DATABASE
# -------------------------
def init_db():
    conn = sqlite3.connect("scommesse.db")
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
            data_inizio TEXT
        )
    """)
    conn.commit()
    conn.close()

def salva_proposta(d):
    conn = sqlite3.connect("scommesse.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO proposte (tipo, sport, partita, pronostico, quota, stake, analisi, dove, data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("foto", d.get("sport"), "—", "—", 0.0, int(d.get("stake", 1)), "", d.get("dove", "pubblico"), datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit()
    pid = c.lastrowid
    conn.close()
    return pid

def salva_abbonato(user_id, username):
    conn = sqlite3.connect("scommesse.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO abbonati (user_id, username, data_inizio)
        VALUES (?, ?, ?)
    """, (user_id, username, datetime.now().strftime("%d/%m/%Y %H:%M")))
    conn.commit()
    conn.close()

def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != TUO_ID:
            await update.message.reply_text("❌ Comando riservato all'admin.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper

# -------------------------
# COMANDI BASE
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == TUO_ID:
        await update.message.reply_text(
            "👋 Ciao Carmine, bot attivo!\n\n"
            "Comandi Admin:\n"
            "/nuovafoto - Carica schedina\n"
            "/testvip - Testa l'ingresso al VIP gratis\n"
            "/cancel - Annulla operazione",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await update.message.reply_text(
            "👋 Benvenuto nel Bot Ufficiale!\n\n"
            "💎 Vuoi accedere ai miei pronostici esclusivi?\n"
            "Scrivi /vip per abbonarti e accedere al Canale Privato!"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operazione annullata.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------------
# SISTEMA ABBONAMENTI VIP (TELEGRAM STARS) E TEST
# -------------------------
async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    prices = [LabeledPrice("Abbonamento Mensile VIP", PREZZO_STELLE)]
    
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Canale VIP Scommesse 💎",
            description="Accesso esclusivo di 30 giorni a tutte le mie giocate e analisi.",
            payload="abbonamento_mensile_vip",
            provider_token="", # Vuoto per Telegram Stars
            currency="XTR",    
            prices=prices
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Errore nell'invio della fattura: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != 'abbonamento_mensile_vip':
        await query.answer(ok=False, error_message="Errore nel payload dell'abbonamento.")
    else:
        await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    salva_abbonato(user.id, user.username or user.first_name)
    
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=int(CHANNEL_PRIVATE),
            name=f"VIP {user.first_name}",
            member_limit=1
        )
        
        await update.message.reply_text(
            f"✅ Pagamento ricevuto con successo!\n\n"
            f"Benvenuto nel gruppo VIP 💎\n"
            f"Ecco il tuo link d'accesso personale:\n\n{invite_link.invite_link}"
        )
        
        await context.bot.send_message(
            chat_id=TUO_ID,
            text=f"💰 NUOVO INCASSO!\nL'utente {user.first_name} si è abbonato pagando {PREZZO_STELLE} ⭐!"
        )
        
    except Exception as e:
        await update.message.reply_text("Pagamento ricevuto, ma errore nel generare il link. Contatta l'admin.")
        await context.bot.send_message(chat_id=TUO_ID, text=f"⚠️ ERRORE GENERAZIONE LINK: {e}")

@admin_only
async def testvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simula l'ingresso di un VIP senza pagare per testare il sistema."""
    user = update.message.from_user
    
    salva_abbonato(user.id, user.username or user.first_name)
    
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=int(CHANNEL_PRIVATE),
            name=f"TEST VIP {user.first_name}",
            member_limit=1
        )
        
        await update.message.reply_text(
            f"🛠 **TEST VIP COMPLETATO** 🛠\n\n"
            f"✅ Simulazione pagamento andata a buon fine!\n"
            f"Ecco il link d'accesso generato dal bot (valido per 1 solo utilizzo):\n\n"
            f"{invite_link.invite_link}\n\n"
            f"Puoi inviare questo link a un amico per vedere se riesce a entrare nel canale privato."
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Errore nella generazione del link: {e}")

# -------------------------
# FLUSSO FOTO (Tuo comando Admin)
# -------------------------
@admin_only
async def nuovafoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🏟 Scegli lo sport:", reply_markup=kb_sport())
    return F_SPORT

async def f_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scelta = update.message.text.strip()
    valid_sports = ["⚽ Calcio", "🏀 Basket", "🎾 Tennis", "🏆 Altro"]
    if scelta not in valid_sports:
        await update.message.reply_text("Usa i bottoni per favore!", reply_markup=kb_sport())
        return F_SPORT
    context.user_data["sport"] = scelta
    await update.message.reply_text("📸 Allega la foto della schedina:", reply_markup=ReplyKeyboardRemove())
    return F_FOTO

async def f_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Non hai mandato una foto. Riprova.")
        return F_FOTO
    context.user_data["foto_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("🎯 Scegli la difficoltà (1-5):", reply_markup=kb_stake())
    return F_STAKE

async def f_stake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = update.message.text.strip()
    if testo not in {"1", "2", "3", "4", "5"}:
        await update.message.reply_text("Usa i bottoni per favore!", reply_markup=kb_stake())
        return F_STAKE
    context.user_data["stake"] = int(testo)
    await update.message.reply_text("📍 Dove pubblichiamo?", reply_markup=kb_dove())
    return F_DOVE

async def f_dove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scelta = update.message.text.strip()
    mappa_dove = {"📢 Pubblico": "pubblico", "💎 Privato": "privato", "📢💎 Entrambi": "entrambi"}
    if scelta not in mappa_dove:
        await update.message.reply_text("Usa i bottoni per favore!", reply_markup=kb_dove())
        return F_DOVE

    context.user_data["dove"] = mappa_dove[scelta]
    d = context.user_data
    stelle = "⭐" * int(d["stake"])
    caption = f"🏟 {d['sport']}\n🎯 Difficoltà: {stelle}"
    pid = salva_proposta(d)

    await update.message.reply_text("⏳ Sto provando a pubblicare sui canali...", reply_markup=ReplyKeyboardRemove())

    try:
        if d["dove"] in ("pubblico", "entrambi"):
            id_pubblico = int(CHANNEL_PUBLIC)
            await context.bot.send_photo(chat_id=id_pubblico, photo=d["foto_id"], caption=caption)
            await update.message.reply_text(f"✅ Pubblicato sul canale Pubblico!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ ERRORE PUBBLICAZIONE PUBBLICO:\n{e}")

    try:
        if d["dove"] in ("privato", "entrambi"):
            id_privato = int(CHANNEL_PRIVATE)
            await context.bot.send_photo(chat_id=id_privato, photo=d["foto_id"], caption=caption)
            await update.message.reply_text(f"✅ Pubblicato sul canale Privato!")
            
    except Exception as e:
        await update.message.reply_text(f"❌ ERRORE PUBBLICAZIONE PRIVATO:\n{e}")

    await update.message.reply_text(f"🏁 Finito! Schedina salvata nel db con ID #{pid}")
    return ConversationHandler.END

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
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CommandHandler("testvip", testvip))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(conv_foto)

    print("Bot avviato e pronto!")
    app.run_polling()

if __name__ == "__main__":
    main()