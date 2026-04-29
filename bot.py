import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, PreCheckoutQueryHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

TOKEN = "8622205755:AAF7iBVUB0j3Lru_lvM2KhjfVgqfYohDWiE"               # ⚠️ INSERISCI QUI IL TUO TOKEN
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
            quota REAL, stake INTEGER, analisi TEXT, dove TEXT, data TEXT,
            msg_pubblico INTEGER DEFAULT 0,
            msg_privato INTEGER DEFAULT 0,
            esito TEXT DEFAULT 'in_attesa'
        )
    """)
    # Per sicurezza in caso di database vecchio
    try: c.execute("ALTER TABLE proposte ADD COLUMN msg_pubblico INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE proposte ADD COLUMN msg_privato INTEGER DEFAULT 0")
    except: pass
    try: c.execute("ALTER TABLE proposte ADD COLUMN esito TEXT DEFAULT 'in_attesa'")
    except: pass

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

def salva_proposta_iniziale(d):
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

def aggiorna_id_messaggi(pid, msg_pubblico, msg_privato):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE proposte SET msg_pubblico = ?, msg_privato = ? WHERE id = ?", (msg_pubblico, msg_privato, pid))
    conn.commit()
    conn.close()

def salva_abbonato(user_id, username, giorni_da_aggiungere):
    inizio = datetime.now()
    scadenza = inizio + timedelta(days=giorni_da_aggiungere)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
def kb_sport(): return ReplyKeyboardMarkup([["⚽ Calcio", "🏀 Basket"], ["🎾 Tennis", "🏆 Altro"]], resize_keyboard=True, one_time_keyboard=True)
def kb_stake(): return ReplyKeyboardMarkup([["1", "2", "3"], ["4", "5"]], resize_keyboard=True, one_time_keyboard=True)
def kb_dove(): return ReplyKeyboardMarkup([["📢 Pubblico", "💎 Privato"], ["📢💎 Entrambi"]], resize_keyboard=True, one_time_keyboard=True)

# -------------------------
# COMANDI BASE
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == TUO_ID:
        await update.message.reply_text(
            "👋 Ciao Carmine, bentornato!\n\n"
            "🛠 **Comandi Admin:**\n"
            "/nuovafoto - Carica schedina\n"
            "/risultato - Imposta vincente/perdente\n"
            "/statistiche - Controlla incassi e iscritti\n"
            "/cancel - Annulla operazione in corso",
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
# SISTEMA VIP
# -------------------------
async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"🥉 1 Settimana - {PIANI_VIP['settimana']['euro']}", callback_data="vip_settimana")],
        [InlineKeyboardButton(f"🥈 1 Mese - {PIANI_VIP['mese']['euro']}", callback_data="vip_mese")],
        [InlineKeyboardButton(f"🥇 3 Mesi - {PIANI_VIP['trimestre']['euro']}", callback_data="vip_trimestre")]
    ]
    await update.message.reply_text("💎 **Abbonamento VIP**\nScegli il piano per continuare:", reply_markup=InlineKeyboardMarkup(keyboard))

async def scelta_piano_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("vip_"): return
    scelta = query.data.replace("vip_", "")
    piano = PIANI_VIP[scelta]
    
    istruzioni = (f"Hai scelto l'abbonamento per **{piano['nome']}** al costo di **{piano['euro']}** ({piano['stelle']} ⭐).\n\n"
                  "⬇️ *Procedi con il pagamento qui sotto* ⬇️")
    await query.message.reply_text(istruzioni)
    
    prices = [LabeledPrice(f"Accesso VIP {piano['nome']}", piano['stelle'])]
    try:
        await context.bot.send_invoice(
            chat_id=query.message.chat_id, title="Canale VIP Scommesse 💎",
            description=f"Accesso automatico per {piano['giorni']} giorni.",
            payload=f"abbonamento_{scelta}", provider_token="", currency="XTR", prices=prices
        )
    except Exception as e: await query.message.reply_text(f"⚠️ Errore: {e}")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True) if "abbonamento_" in query.invoice_payload else await query.answer(ok=False, error_message="Errore payload.")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    payload = update.message.successful_payment.invoice_payload
    piano = PIANI_VIP.get(payload.replace("abbonamento_", ""), PIANI_VIP["mese"])
    
    salva_abbonato(user.id, user.username or user.first_name, piano["giorni"])
    try:
        invite_link = await context.bot.create_chat_invite_link(chat_id=int(CHANNEL_PRIVATE), member_limit=1)
        await update.message.reply_text(f"✅ Pagamento ricevuto!\nEcco il tuo link d'accesso:\n\n{invite_link.invite_link}")
        await context.bot.send_message(chat_id=TUO_ID, text=f"💰 INCASSO: {user.first_name} ha pagato {piano['stelle']} ⭐!")
    except: pass

# -------------------------
# FLUSSO FOTO
# -------------------------
@admin_only
async def nuovafoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🏟 Scegli lo sport:", reply_markup=kb_sport())
    return F_SPORT

async def f_sport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sport"] = update.message.text.strip()
    await update.message.reply_text("📸 Allega la foto:", reply_markup=ReplyKeyboardRemove())
    return F_FOTO

async def f_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return F_FOTO
    context.user_data["foto_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("🎯 Difficoltà (1-5):", reply_markup=kb_stake())
    return F_STAKE

async def f_stake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["stake"] = int(update.message.text.strip())
    await update.message.reply_text("📍 Dove pubblichiamo?", reply_markup=kb_dove())
    return F_DOVE

async def f_dove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mappa = {"📢 Pubblico": "pubblico", "💎 Privato": "privato", "📢💎 Entrambi": "entrambi"}
    d = context.user_data
    d["dove"] = mappa.get(update.message.text.strip(), "pubblico")
    stelle = "⭐" * int(d["stake"])
    caption = f"🏟 {d['sport']}\n🎯 Difficoltà: {stelle}"
    pid = salva_proposta_iniziale(d)

    await update.message.reply_text("⏳ Pubblicando...", reply_markup=ReplyKeyboardRemove())
    
    msg_pubblico_id = 0
    msg_privato_id = 0

    if d["dove"] in ("pubblico", "entrambi"):
        msg = await context.bot.send_photo(chat_id=int(CHANNEL_PUBLIC), photo=d["foto_id"], caption=caption)
        msg_pubblico_id = msg.message_id
            
    if d["dove"] in ("privato", "entrambi"):
        msg = await context.bot.send_photo(chat_id=int(CHANNEL_PRIVATE), photo=d["foto_id"], caption=caption)
        msg_privato_id = msg.message_id

    aggiorna_id_messaggi(pid, msg_pubblico_id, msg_privato_id)
    await update.message.reply_text(f"✅ Schedina #{pid} pubblicata e pronta per i risultati!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Annullato.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------------
# GESTIONE RISULTATI
# -------------------------
@admin_only
async def comando_risultato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, sport, data FROM proposte WHERE esito = 'in_attesa' ORDER BY id DESC LIMIT 5")
    scommesse = c.fetchall()
    conn.close()

    if not scommesse:
        await update.message.reply_text("Tutte le scommesse recenti hanno già un risultato!")
        return

    keyboard = []
    for s in scommesse:
        keyboard.append([InlineKeyboardButton(f"#{s[0]} - {s[1]} ({s[2]})", callback_data=f"sel_ris_{s[0]}")])
    
    await update.message.reply_text("Seleziona la schedina da aggiornare:", reply_markup=InlineKeyboardMarkup(keyboard))

async def gestisci_risultati_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("sel_ris_"):
        pid = data.split("_")[2]
        keyboard = [
            [InlineKeyboardButton("✅ VINCENTE", callback_data=f"esito_win_{pid}")],
            [InlineKeyboardButton("❌ PERDENTE", callback_data=f"esito_lose_{pid}")],
            [InlineKeyboardButton("🔄 RIMBORSATA", callback_data=f"esito_void_{pid}")]
        ]
        await query.message.edit_text(f"Che esito ha avuto la schedina #{pid}?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("esito_"):
        parti = data.split("_")
        esito_tipo = parti[1]
        pid = int(parti[2])

        icone = {"win": "✅ VINCENTE ✅", "lose": "❌ PERDENTE ❌", "void": "🔄 RIMBORSATA 🔄"}
        testo_esito = icone[esito_tipo]

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT sport, stake, msg_pubblico, msg_privato FROM proposte WHERE id = ?", (pid,))
        row = c.fetchone()
        
        if not row: return
        sport, stake, msg_pubblico, msg_privato = row
        stelle = "⭐" * stake
        
        nuova_caption = f"🏟 {sport}\n🎯 Difficoltà: {stelle}\n\n{testo_esito}"

        log_errori = ""

        if msg_pubblico and msg_pubblico != 0:
            try: 
                await context.bot.edit_message_caption(chat_id=int(CHANNEL_PUBLIC), message_id=msg_pubblico, caption=nuova_caption)
            except Exception as e: log_errori += f"\nPubblico: {e}"

        if msg_privato and msg_privato != 0:
            try: 
                await context.bot.edit_message_caption(chat_id=int(CHANNEL_PRIVATE), message_id=msg_privato, caption=nuova_caption)
            except Exception as e: log_errori += f"\nPrivato: {e}"

        c.execute("UPDATE proposte SET esito = ? WHERE id = ?", (esito_tipo, pid))
        conn.commit()
        conn.close()

        if log_errori == "":
            await query.message.edit_text(f"✅ Schedina #{pid} aggiornata come {esito_tipo.upper()} nei canali!")
        else:
            await query.message.edit_text(f"⚠️ Schedina elaborata, ma errori su Telegram:{log_errori}")

# -------------------------
# PANNELLO ADMIN & JOBS
# -------------------------
@admin_only
async def statistiche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM abbonati")
    tot = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM abbonati WHERE data_scadenza > ?", (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    attivi = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"📊 **Statistiche**\n👥 Totale storici: {tot}\n✅ Attivi ora: {attivi}")

async def controlla_scadenze(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    adesso = datetime.now()
    
    # 1. Trova chi espellere
    c.execute("SELECT user_id FROM abbonati WHERE data_scadenza < ?", (adesso.strftime("%Y-%m-%d %H:%M"),))
    for utente in c.fetchall():
        try:
            await context.bot.ban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=utente[0])
            await context.bot.unban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=utente[0])
            await context.bot.send_message(chat_id=utente[0], text="⚠️ Il tuo VIP è terminato. Usa /vip per rinnovare!")
            c.execute("DELETE FROM abbonati WHERE user_id = ?", (utente[0],))
        except: pass
    
    # 2. Avvisi 2 giorni prima
    tra_due_giorni = adesso + timedelta(days=2)
    c.execute("SELECT user_id FROM abbonati WHERE data_scadenza < ? AND avvisato = 0", (tra_due_giorni.strftime("%Y-%m-%d %H:%M"),))
    for utente in c.fetchall():
        try:
            await context.bot.send_message(chat_id=utente[0], text="⏳ Il tuo VIP scadrà tra 2 giorni.\nRinnova con /vip!")
            c.execute("UPDATE abbonati SET avvisato = 1 WHERE user_id = ?", (utente[0],))
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
    app.add_handler(CommandHandler("risultato", comando_risultato))
    
    app.add_handler(CallbackQueryHandler(scelta_piano_callback, pattern="^vip_"))
    app.add_handler(CallbackQueryHandler(gestisci_risultati_callback, pattern="^(sel_ris|esito)_"))
    
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(conv_foto)

    app.job_queue.run_repeating(controlla_scadenze, interval=3600, first=10)

    print("Bot avviato e pronto!")
    app.run_polling()

if __name__ == "__main__":
    main()
