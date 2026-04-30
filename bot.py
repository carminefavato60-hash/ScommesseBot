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

F_SPORT, F_TIPO, F_FOTO, F_STAKE, F_DOVE = range(100, 105)

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
    """, (d.get("tipo", "Singola"), d.get("sport"), "—", "—", 0.0, int(d.get("stake", 1)), "", d.get("dove", "pubblico"), datetime.now().strftime("%d/%m/%Y %H:%M")))
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
def kb_tipo(): return ReplyKeyboardMarkup([["🎯 Singola", "🔀 Multipla"]], resize_keyboard=True, one_time_keyboard=True)
def kb_stake(): return ReplyKeyboardMarkup([["1", "2", "3"], ["4", "5"]], resize_keyboard=True, one_time_keyboard=True)
def kb_dove(): return ReplyKeyboardMarkup([["📢 Pubblico", "💎 Privato"], ["📢💎 Entrambi"]], resize_keyboard=True, one_time_keyboard=True)

# -------------------------
# COMANDI BASE
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == TUO_ID:
        await update.message.reply_text(
            "👋 Ciao Carmine, bentornato!\n\n"
            "🛠 *Comandi Admin:*\n"
            "/nuovafoto - Carica schedina\n"
            "/risultato - Imposta vincente/perdente\n"
            "/eliminaschedina - Elimina una schedina\n"
            "/storico - Vedi il tuo storico privato\n"
            "/mandastoricoVIP - Pubblica storico nel canale VIP\n"
            "/statistiche - Controlla incassi e iscritti\n"
            "/pinpubblico - Fissa messaggio nel canale pubblico\n"
            "/pinvip - Fissa messaggio nel canale VIP\n"
            "/invito - Genera messaggio invito per il canale pubblico\n"
            "/cancel - Annulla operazione in corso",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "👋 Benvenuto nel Bot Ufficiale!\n\n"
            "💎 *Accesso al Canale VIP*\n"
            "Entra per ricevere tutti i miei pronostici esclusivi.\n\n"
            "👉 Scrivi /vip per abbonarti\n"
            "👉 Scrivi /profilo per controllare il tuo stato",
            parse_mode="Markdown"
        )

async def profilo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    dati = get_abbonato(user.id)
    if not dati:
        await update.message.reply_text("❌ Non hai nessun abbonamento attivo.\nScrivi /vip per abbonarti!")
        return
    scadenza = datetime.strptime(dati[1], "%Y-%m-%d %H:%M")
    if datetime.now() > scadenza:
        await update.message.reply_text("⚠️ Il tuo abbonamento è scaduto.\nScrivi /vip per rinnovare!")
    else:
        giorni_rimasti = (scadenza - datetime.now()).days
        await update.message.reply_text(
            f"👤 *Profilo di {user.first_name}*\n\n"
            f"✅ *Stato:* VIP Attivo\n"
            f"⏳ *Scadenza:* {scadenza.strftime('%d/%m/%Y')}\n"
            f"📅 *Giorni rimanenti:* {giorni_rimasti}",
            parse_mode="Markdown"
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Annullato.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# -------------------------
# SISTEMA VIP
# -------------------------
async def vip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(f"🥉 1 Settimana - {PIANI_VIP['settimana']['euro']}", callback_data="vip_settimana")],
        [InlineKeyboardButton(f"🥈 1 Mese - {PIANI_VIP['mese']['euro']}", callback_data="vip_mese")],
        [InlineKeyboardButton(f"🥇 3 Mesi - {PIANI_VIP['trimestre']['euro']}", callback_data="vip_trimestre")]
    ]
    testo = (
        "╔══════════════════════╗\n"
        "       💎  CANALE VIP  💎\n"
        "╚══════════════════════╝\n\n"
        "Stai seguendo il canale gratuito?\n"
        "Bene. Ma stai vedendo solo il *10%* di quello che faccio.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📢 *Canale GRATUITO*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "☑️ Solo alcune schedine selezionate\n"
        "☑️ Nessuna analisi approfondita\n"
        "☑️ Nessun avviso immediato\n"
        "☑️ Storico risultati limitato\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 *Canale VIP*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *Tutte* le schedine, nessuna esclusa\n"
        "✅ Le giocate più profittevoli\n"
        "✅ Notifica immediata appena pubblico\n"
        "✅ Storico completo vincite e perdite\n"
        "✅ 1-2 giocate al giorno, selezionate\n"
        "✅ Accesso immediato dopo il pagamento\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔥 *Il VIP si paga con la prima vincita.*\n"
        "Chi è già dentro lo sa.\n\n"
        "⬇️ *Scegli il tuo piano:*"
    )
    await update.message.reply_text(testo, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def scelta_piano_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("vip_"): return
    scelta = query.data.replace("vip_", "")
    piano = PIANI_VIP[scelta]
    istruzioni = (
        f"Hai scelto *{piano['nome']}* al costo di *{piano['euro']}* ({piano['stelle']} ⭐).\n\n"
        "ℹ️ *COME PAGARE:*\n"
        "1. Clicca sul pulsante *Paga* nella fattura qui sotto.\n"
        "2. Se non hai le Stelle, puoi ricaricarle con *Apple Pay, Google Pay o carta* direttamente da Telegram.\n"
        "3. Appena pagato, ricevi il link per entrare nel canale in automatico!\n\n"
        "⬇️ _Procedi con il pagamento qui sotto_ ⬇️"
    )
    await query.message.reply_text(istruzioni, parse_mode="Markdown")
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
        await context.bot.send_message(chat_id=TUO_ID, text=f"💰 INCASSO: {user.first_name} ha pagato {piano['stelle']} ⭐ ({piano['nome']})!")
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
    await update.message.reply_text("🎯 Tipo di giocata:", reply_markup=kb_tipo())
    return F_TIPO

async def f_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mappa = {"🎯 Singola": "Singola", "🔀 Multipla": "Multipla"}
    context.user_data["tipo"] = mappa.get(update.message.text.strip(), "Singola")
    await update.message.reply_text("📸 Allega la foto:", reply_markup=ReplyKeyboardRemove())
    return F_FOTO

async def f_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return F_FOTO
    context.user_data["foto_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("⭐ Difficoltà (1-5):", reply_markup=kb_stake())
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
    tipo_tag = "🎯 Singola" if d.get("tipo") == "Singola" else "🔀 Multipla"
    caption = f"🏟 {d['sport']}\n{tipo_tag}\n⭐ Difficoltà: {stelle}"
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
    await update.message.reply_text(f"✅ Schedina #{pid} pubblicata!")
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
        await update.message.reply_text("Tutte le scommesse hanno già un risultato!")
        return
    keyboard = [[InlineKeyboardButton(f"#{s[0]} - {s[1]} ({s[2]})", callback_data=f"sel_ris_{s[0]}")] for s in scommesse]
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
        c.execute("SELECT sport, tipo, stake, msg_pubblico, msg_privato FROM proposte WHERE id = ?", (pid,))
        row = c.fetchone()
        if not row: return
        sport, tipo, stake, msg_pubblico, msg_privato = row
        stelle = "⭐" * stake
        tipo_tag = "🎯 Singola" if tipo == "Singola" else "🔀 Multipla"
        nuova_caption = f"🏟 {sport}\n{tipo_tag}\n⭐ Difficoltà: {stelle}\n\n{testo_esito}"
        log_errori = ""

        if msg_pubblico and msg_pubblico != 0:
            try: await context.bot.edit_message_caption(chat_id=int(CHANNEL_PUBLIC), message_id=msg_pubblico, caption=nuova_caption)
            except Exception as e: log_errori += f"\nPubblico: {e}"
        if msg_privato and msg_privato != 0:
            try: await context.bot.edit_message_caption(chat_id=int(CHANNEL_PRIVATE), message_id=msg_privato, caption=nuova_caption)
            except Exception as e: log_errori += f"\nPrivato: {e}"

        c.execute("UPDATE proposte SET esito = ? WHERE id = ?", (esito_tipo, pid))
        conn.commit()
        conn.close()

        if log_errori == "":
            await query.message.edit_text(f"✅ Schedina #{pid} aggiornata come {esito_tipo.upper()} nei canali!")
        else:
            await query.message.edit_text(f"⚠️ Elaborata ma errori:{log_errori}")

# -------------------------
# ELIMINA SCHEDINA
# -------------------------
@admin_only
async def elimina_schedina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, sport, data, esito FROM proposte ORDER BY id DESC LIMIT 10")
    scommesse = c.fetchall()
    conn.close()

    if not scommesse:
        await update.message.reply_text("Nessuna schedina nel database.")
        return

    icone = {"win": "✅", "lose": "❌", "void": "🔄", "in_attesa": "⏳"}
    keyboard = []
    for s in scommesse:
        icona = icone.get(s[3], "⏳")
        keyboard.append([InlineKeyboardButton(
            f"🗑 #{s[0]} - {s[1]} {icona} ({s[2]})",
            callback_data=f"del_ris_{s[0]}"
        )])
    await update.message.reply_text(
        "Seleziona la schedina da eliminare definitivamente:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def conferma_elimina_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("del_ris_"):
        pid = data.split("_")[2]
        keyboard = [
            [InlineKeyboardButton("✅ SÌ, ELIMINA", callback_data=f"del_conf_{pid}")],
            [InlineKeyboardButton("❌ No, annulla", callback_data="del_annulla")]
        ]
        await query.message.edit_text(
            f"⚠️ Sei sicuro di voler eliminare la schedina #{pid}?\n\n"
            "Verrà rimossa definitivamente dal database e dallo storico.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("del_conf_"):
        pid = int(data.split("_")[2])
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM proposte WHERE id = ?", (pid,))
        conn.commit()
        conn.close()
        await query.message.edit_text(f"🗑 Schedina #{pid} eliminata definitivamente!")

    elif data == "del_annulla":
        await query.message.edit_text("❌ Eliminazione annullata.")

# -------------------------
# STORICO
# -------------------------
@admin_only
async def storico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, sport, tipo, data, esito, dove FROM proposte ORDER BY id DESC LIMIT 20")
    righe = c.fetchall()
    conn.close()
    if not righe:
        await update.message.reply_text("Nessuna schedina nel database.")
        return

    icone = {"win": "✅ VINCENTE", "lose": "❌ PERDENTE", "void": "🔄 RIMBORSATA", "in_attesa": "⏳ In attesa"}
    dove_icone = {"pubblico": "📢", "privato": "💎", "entrambi": "📢💎"}
    tipo_icone = {"Singola": "🎯", "Multipla": "🔀"}

    vinte = sum(1 for r in righe if r[4] == "win")
    perse = sum(1 for r in righe if r[4] == "lose")
    rimborsate = sum(1 for r in righe if r[4] == "void")
    in_attesa = sum(1 for r in righe if r[4] == "in_attesa")
    totale_concluse = vinte + perse

    testo = "📊 *Storico ultime 20 giocate:*\n\n"
    for r in righe:
        dove_tag = dove_icone.get(r[5], "📢")
        tipo_tag = tipo_icone.get(r[2], "🎯")
        testo += f"{dove_tag}{tipo_tag} {r[1]} — {icone.get(r[4], '⏳')} ({r[3]})\n"
    testo += f"\n━━━━━━━━━━━━━━━━━━━\n"
    testo += f"✅ Vinte: {vinte}  ❌ Perse: {perse}  🔄 Rimborsate: {rimborsate}  ⏳ In attesa: {in_attesa}\n"
    if totale_concluse > 0:
        percentuale = round((vinte / totale_concluse) * 100, 1)
        testo += f"📈 *Percentuale successo: {percentuale}%*"
    await update.message.reply_text(testo, parse_mode="Markdown")

@admin_only
async def manda_storico_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, sport, tipo, data, esito FROM proposte
        WHERE dove IN ('privato', 'entrambi')
        ORDER BY id DESC LIMIT 20
    """)
    righe = c.fetchall()
    conn.close()
    if not righe:
        await update.message.reply_text("Nessuna schedina VIP nel database.")
        return

    icone = {"win": "✅ VINCENTE", "lose": "❌ PERDENTE", "void": "🔄 RIMBORSATA", "in_attesa": "⏳ In attesa"}
    tipo_icone = {"Singola": "🎯", "Multipla": "🔀"}
    vinte = sum(1 for r in righe if r[4] == "win")
    perse = sum(1 for r in righe if r[4] == "lose")
    rimborsate = sum(1 for r in righe if r[4] == "void")
    totale_concluse = vinte + perse

    testo = (
        "╔══════════════════════╗\n"
        "    📊  STORICO RISULTATI  📊\n"
        "╚══════════════════════╝\n\n"
    )
    for r in righe:
        tipo_tag = tipo_icone.get(r[2], "🎯")
        testo += f"{tipo_tag} {r[1]} — {icone.get(r[4], '⏳')} ({r[3]})\n"
    testo += f"\n━━━━━━━━━━━━━━━━━━━\n"
    testo += f"✅ Vinte: {vinte}  ❌ Perse: {perse}  🔄 Rimborsate: {rimborsate}\n"
    if totale_concluse > 0:
        percentuale = round((vinte / totale_concluse) * 100, 1)
        testo += f"📈 *Percentuale successo: {percentuale}%*\n\n"
    testo += "💎 _Questi sono i risultati reali del canale VIP._"

    try:
        await context.bot.send_message(chat_id=int(CHANNEL_PRIVATE), text=testo, parse_mode="Markdown")
        await update.message.reply_text("✅ Storico pubblicato nel Canale VIP!")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

# -------------------------
# STATISTICHE ADMIN
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
    await update.message.reply_text(
        f"📊 *Statistiche*\n\n"
        f"👥 Totale storici: {tot}\n"
        f"✅ Attivi ora: {attivi}",
        parse_mode="Markdown"
    )

# -------------------------
# PIN MESSAGGI NEI CANALI
# -------------------------
@admin_only
async def pin_pubblico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = (
        "📢 *BENVENUTO NEL CANALE UFFICIALE*\n\n"
        "Qui pubblico una selezione delle mie giocate gratuitamente\.\n\n"
        "*Cosa trovi in questo canale:*\n"
        "⚽ Schedine su Calcio, Basket, Tennis e altri sport\n"
        "🎯 Singola o 🔀 Multipla indicata su ogni giocata\n"
        "⭐ Difficoltà indicata con le stelline\n"
        "✅ Risultati aggiornati in tempo reale\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 *Vuoi accedere a TUTTE le mie giocate?*\n"
        "Nel canale VIP pubblico schedine esclusive che qui non escono mai\.\n\n"
        "👉 Scrivimi [qui](https://t.me/carmine_scommesse_bot) per abbonarti"
    )
    try:
        msg = await context.bot.send_message(chat_id=int(CHANNEL_PUBLIC), text=testo, parse_mode="MarkdownV2", disable_web_page_preview=True)
        await context.bot.pin_chat_message(chat_id=int(CHANNEL_PUBLIC), message_id=msg.message_id, disable_notification=True)
        await update.message.reply_text("✅ Messaggio inviato e fissato nel Canale Pubblico!")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

@admin_only
async def pin_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    testo = (
        "💎 *BENVENUTO NEL CANALE VIP*\n\n"
        "Sei nel posto giusto\. Qui ricevi tutto\.\n\n"
        "✅ Tutte le schedine, nessuna esclusa\n"
        "🎯 Singole e 🔀 Multiple\n"
        "✅ Le giocate più profittevoli\n"
        "✅ Risultati aggiornati in tempo reale\n"
        "✅ Notifica immediata appena pubblico\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *REGOLE:*\n"
        "— Non condividere i contenuti di questo canale\n"
        "— Non screenshottare le schedine\n"
        "— Chi viola le regole viene rimosso\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 *Per rinnovare il tuo abbonamento:*\n"
        "👉 Scrivi [qui](https://t.me/carmine_scommesse_bot) e usa il comando /vip"
    )
    try:
        msg = await context.bot.send_message(chat_id=int(CHANNEL_PRIVATE), text=testo, parse_mode="MarkdownV2", disable_web_page_preview=True)
        await context.bot.pin_chat_message(chat_id=int(CHANNEL_PRIVATE), message_id=msg.message_id, disable_notification=True)
        await update.message.reply_text("✅ Messaggio inviato e fissato nel Canale VIP!")
    except Exception as e:
        await update.message.reply_text(f"❌ Errore: {e}")

# -------------------------
# INVITO WHATSAPP
# -------------------------
@admin_only
async def invito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messaggio = (
        "👋 Ciao\!\n\n"
        "Ti segnalo questo canale Telegram dove vengono pubblicati "
        "pronostici sulle scommesse sportive ⚽🏀🎾\n\n"
        "✅ Calcio, Basket, Tennis e altri sport\n"
        "🎯 Giocate Singole e 🔀 Multiple\n"
        "✅ Risultati aggiornati in tempo reale\n"
        "✅ Difficoltà indicata per ogni giocata\n\n"
        "📢 Il canale è GRATUITO\!\n\n"
        "👉 Entra subito [qui](https://t.me/carminescommesae)\n\n"
        "🔥 Chi vuole di più può accedere al canale VIP con giocate esclusive\!"
    )
    await update.message.reply_text(
        "📋 *Copia e manda questo messaggio ai tuoi amici su WhatsApp:*\n\n"
        f"{messaggio}",
        parse_mode="MarkdownV2",
        disable_web_page_preview=True
    )

# -------------------------
# CONTROLLO SCADENZE ORARIO
# -------------------------
async def controlla_scadenze(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    adesso = datetime.now()

    c.execute("SELECT user_id FROM abbonati WHERE data_scadenza < ?", (adesso.strftime("%Y-%m-%d %H:%M"),))
    for utente in c.fetchall():
        try:
            await context.bot.ban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=utente[0])
            await context.bot.unban_chat_member(chat_id=int(CHANNEL_PRIVATE), user_id=utente[0])
            await context.bot.send_message(chat_id=utente[0], text="⚠️ Il tuo VIP è terminato.\nUsa /vip per rinnovare!")
            c.execute("DELETE FROM abbonati WHERE user_id = ?", (utente[0],))
        except: pass

    tra_tre_giorni = adesso + timedelta(days=3)
    tra_due_giorni = adesso + timedelta(days=2)
    c.execute("""
        SELECT user_id FROM abbonati
        WHERE data_scadenza BETWEEN ? AND ? AND avvisato = 0
    """, (tra_due_giorni.strftime("%Y-%m-%d %H:%M"), tra_tre_giorni.strftime("%Y-%m-%d %H:%M")))
    for utente in c.fetchall():
        try:
            await context.bot.send_message(
                chat_id=utente[0],
                text=(
                    "⏳ *Attenzione!*\n\n"
                    "Il tuo abbonamento VIP scadrà tra *3 giorni*.\n\n"
                    "Per non perdere l'accesso al canale rinnova subito!\n\n"
                    "👉 Scrivi /vip per rinnovare"
                ),
                parse_mode="Markdown"
            )
            c.execute("UPDATE abbonati SET avvisato = 1 WHERE user_id = ?", (utente[0],))
        except: pass

    tra_un_giorno = adesso + timedelta(days=1)
    c.execute("""
        SELECT user_id FROM abbonati
        WHERE data_scadenza BETWEEN ? AND ? AND avvisato = 1
    """, (adesso.strftime("%Y-%m-%d %H:%M"), tra_un_giorno.strftime("%Y-%m-%d %H:%M")))
    for utente in c.fetchall():
        try:
            await context.bot.send_message(
                chat_id=utente[0],
                text=(
                    "🚨 *Ultimo avviso!*\n\n"
                    "Il tuo abbonamento VIP scade *domani*.\n\n"
                    "Dopo la scadenza verrai rimosso automaticamente dal canale.\n\n"
                    "🔥 Rinnova ora prima che sia tardi!\n"
                    "👉 Scrivi /vip"
                ),
                parse_mode="Markdown"
            )
            c.execute("UPDATE abbonati SET avvisato = 2 WHERE user_id = ?", (utente[0],))
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
            F_TIPO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, f_tipo)],
            F_FOTO:  [MessageHandler(filters.PHOTO, f_foto)],
            F_STAKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, f_stake)],
            F_DOVE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, f_dove)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profilo", profilo))
    app.add_handler(CommandHandler("statistiche", statistiche))
    app.add_handler(CommandHandler("storico", storico))
    app.add_handler(CommandHandler("mandastoricoVIP", manda_storico_vip))
    app.add_handler(CommandHandler("vip", vip_command))
    app.add_handler(CommandHandler("risultato", comando_risultato))
    app.add_handler(CommandHandler("eliminaschedina", elimina_schedina))
    app.add_handler(CommandHandler("pinpubblico", pin_pubblico))
    app.add_handler(CommandHandler("pinvip", pin_vip))
    app.add_handler(CommandHandler("invito", invito))

    app.add_handler(CallbackQueryHandler(scelta_piano_callback, pattern="^vip_"))
    app.add_handler(CallbackQueryHandler(gestisci_risultati_callback, pattern="^(sel_ris|esito)_"))
    app.add_handler(CallbackQueryHandler(conferma_elimina_callback, pattern="^(del_ris|del_conf|del_annulla)"))

    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(conv_foto)

    app.job_queue.run_repeating(controlla_scadenze, interval=3600, first=10)

    print("✅ Bot avviato e pronto!")
    app.run_polling()

if __name__ == "__main__":
    main()
