import streamlit as st
from supabase import create_client, Client
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import google.generativeai as genai
from PIL import Image
import re
import os
import random

# --- GESTIONE LIBRERIA PDF IN SICUREZZA ---
try:
    from fpdf import FPDF
    import tempfile
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Virtual Nutritionist Pro", layout="wide")

# --- 1.5 CONFIGURAZIONE SUPABASE E LOGIN ---
# INSERISCI QUI IL TUO URL PULITO E LA TUA KEY
SUPABASE_URL = "https://xzxzwwexjikfhnplnmns.supabase.co"
SUPABASE_KEY = "sb_publishable_igxY0k0M8HQMst2h3NdrrQ_vQhtBr9r"

supabase = None
try:
    if "INSERISCI" not in SUPABASE_URL:
        supabase = create_client(SUPABASE_URL.strip().rstrip("/"), SUPABASE_KEY.strip())
except Exception as e:
    st.error(f"Errore di connessione a Supabase: {e}")

if 'utente_loggato' not in st.session_state:
    st.session_state.utente_loggato = False
if 'email_utente' not in st.session_state:
    st.session_state.email_utente = ""

# --- 4. FUNZIONI DATABASE ---
def get_db_connection():
    conn = sqlite3.connect('nutrizionista.db')
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spesa (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item TEXT, completato INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            user_id INTEGER PRIMARY KEY, tdee REAL, nome TEXT
        )
    """)
    nuove_colonne = ['cognome', 'email', 'sesso', 'data_nascita', 'dieta', 'sport', 'obiettivo', 'peso', 'altezza']
    for col in nuove_colonne:
        try:
            tipo_dato = "REAL" if col in ['peso', 'altezza'] else "TEXT"
            conn.execute(f"ALTER TABLE utenti ADD COLUMN {col} {tipo_dato}")
        except:
            pass 
            
    try:
        conn.execute("ALTER TABLE pasti ADD COLUMN rating REAL DEFAULT 0")
    except:
        pass
    return conn

def genera_pdf_dieta(testo_markdown):
    testo_pulito = testo_markdown.replace('**', '').replace('* ', '- ')
    testo_pulito = testo_pulito.encode('latin-1', 'replace').decode('latin-1')
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Il tuo Piano Alimentare", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=12)
    for riga in testo_pulito.split('\n'):
        pdf.multi_cell(0, 8, txt=riga)
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            pdf_bytes = f.read()
    return pdf_bytes

# IL CANCELLO: Logica di Autenticazione e Registrazione
if not st.session_state.utente_loggato:
    st.title("🔐 Virtual Nutritionist Pro")
    st.write("Accedi o crea un nuovo account per gestire il tuo percorso nutrizionale.")
    
    tab_login, tab_registrazione = st.tabs(["🔑 Accedi", "📝 Crea Profilo Completo"])
    
    with tab_login:
        with st.form("login_form"):
            email_input = st.text_input("Email").strip()
            password_input = st.text_input("Password", type="password").strip()
            submit_login = st.form_submit_button("Accedi")
            
            if submit_login:
                if supabase is None:
                    st.error("⚠️ Inserisci URL e KEY di Supabase nel codice.")
                else:
                    try:
                        auth_response = supabase.auth.sign_in_with_password({"email": email_input, "password": password_input})
                        if auth_response.user:
                            st.session_state.utente_loggato = True
                            st.session_state.email_utente = auth_response.user.email
                            st.rerun() 
                    except Exception as e:
                        st.error("❌ Credenziali non valide o utente non confermato.")
                        st.warning(f"Dettaglio tecnico: {str(e)}")

    with tab_registrazione:
        st.subheader("Raccontaci di te")
        with st.form("register_form"):
            st.markdown("**Dati Personali e Fisici**")
            c1, c2 = st.columns(2)
            reg_nome = c1.text_input("Nome*").strip()
            reg_cognome = c2.text_input("Cognome").strip()
            
            c3, c4 = st.columns(2)
            reg_dob = c3.date_input("Data di Nascita*", min_value=datetime(1920, 1, 1), max_value=datetime.now())
            reg_sesso = c4.selectbox("Sesso*", ["Uomo", "Donna"])
            
            c4_1, c4_2 = st.columns(2)
            reg_peso = c4_1.number_input("Peso (kg)*", min_value=30.0, max_value=250.0, value=70.0, step=0.1)
            reg_altezza = c4_2.number_input("Altezza (cm)*", min_value=100.0, max_value=250.0, value=170.0, step=1.0)
            
            st.divider()
            st.markdown("**Profilo Nutrizionale e Sportivo**")
            c5, c6 = st.columns(2)
            reg_dieta = c5.selectbox("Preferenza Culinaria*", ["Onnivoro", "Carnivoro (Prevalenza Carne)", "Vegetariano", "Vegano", "Pescatariano", "Flessitariano"])
            reg_sport = c6.selectbox("Attività Fisica*", ["Sedentario", "Leggera (1-2 volte/settimana)", "Moderata (3-4 volte/settimana)", "Intensa (5+ volte/settimana)", "Atleta Professionista"])
            
            reg_obiettivo = st.selectbox("Obiettivo Principale*", ["Dimagrimento", "Definizione Muscolare", "Mantenimento", "Aumento Massa Muscolare", "Ricomposizione Corporea"])
            
            st.divider()
            st.markdown("**Credenziali di Accesso**")
            reg_email = st.text_input("Email*").strip()
            c7, c8 = st.columns(2)
            reg_password = c7.text_input("Scegli una Password*", type="password").strip()
            reg_password_confirm = c8.text_input("Conferma Password*", type="password").strip()
            
            submit_register = st.form_submit_button("Crea Account e Salva Profilo")
            
            if submit_register:
                if supabase is None:
                    st.error("⚠️ Connessione a Supabase mancante.")
                elif not reg_nome or not reg_email or not reg_password:
                    st.warning("Compila tutti i campi obbligatori contrassegnati con l'asterisco (*).")
                elif reg_password != reg_password_confirm:
                    st.warning("Le password non coincidono. Riprova.")
                elif len(reg_password) < 6:
                    st.warning("La password deve contenere almeno 6 caratteri.")
                else:
                    try:
                        res = supabase.auth.sign_up({"email": reg_email, "password": reg_password})
                        
                        oggi_data = datetime.now().date()
                        eta = oggi_data.year - reg_dob.year - ((oggi_data.month, oggi_data.day) < (reg_dob.month, reg_dob.day))
                        
                        if reg_sesso == "Uomo":
                            bmr = (10 * reg_peso) + (6.25 * reg_altezza) - (5 * eta) + 5
                        else:
                            bmr = (10 * reg_peso) + (6.25 * reg_altezza) - (5 * eta) - 161
                            
                        moltiplicatori = {"Sedentario": 1.2, "Leggera (1-2 volte/settimana)": 1.375, "Moderata (3-4 volte/settimana)": 1.55, "Intensa (5+ volte/settimana)": 1.725, "Atleta Professionista": 1.9}
                        tdee_calcolato = bmr * moltiplicatori.get(reg_sport, 1.2)
                        
                        if "Dimagrimento" in reg_obiettivo or "Definizione" in reg_obiettivo:
                            tdee_calcolato -= 400 
                        elif "Aumento Massa" in reg_obiettivo:
                            tdee_calcolato += 300 
                        
                        conn = get_db_connection()
                        nuovo_id = random.randint(10000000, 99999999) 
                        
                        conn.execute("""
                            INSERT INTO utenti (user_id, nome, cognome, email, sesso, data_nascita, dieta, sport, obiettivo, peso, altezza, tdee)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (nuovo_id, reg_nome, reg_cognome, reg_email, reg_sesso, str(reg_dob), reg_dieta, reg_sport, reg_obiettivo, reg_peso, reg_altezza, tdee_calcolato))
                        conn.commit()
                        conn.close()
                        
                        st.success(f"✅ Profilo creato! Il tuo Fabbisogno calcolato è di {tdee_calcolato:.0f} kcal. Vai alla scheda 'Accedi'.")
                    except Exception as e:
                        st.error("❌ Errore durante la registrazione.")
                        st.warning(f"Dettaglio tecnico: {str(e)}")
                    
    st.stop() 

# --- SE ARRIVIAMO QUI, L'UTENTE È LOGGATO ---
with st.sidebar:
    email_loggata = st.session_state.email_utente
    st.success(f"👤 Connesso: {email_loggata}")
    
    if st.button("🚪 Esci dal sistema"):
        if supabase is not None:
            supabase.auth.sign_out()
        st.session_state.utente_loggato = False
        st.session_state.email_utente = ""
        st.rerun()

# =====================================================================
# DA QUI IN POI INIZIA IL TUO CODICE ORIGINALE E INCONTAMINATO
# =====================================================================

GEMINI_API_KEY = "AIzaSyB50kktl5Dg3dBjgDn1ND34cJjomI3StZ4"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
    }
    [data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.8);
        border-right: 1px solid #30363d;
    }
    .metric-card {
        background-color: #1c2128;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
    }
    h1, h2, h3 { color: #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

def carica_dati():
    conn = get_db_connection()
    pasti = pd.read_sql_query("SELECT * FROM pasti", conn)
    utenti = pd.read_sql_query("SELECT * FROM utenti", conn)
    sport = pd.read_sql_query("SELECT * FROM sport", conn)
    conn.close()
    
    pasti['data_ora'] = pd.to_datetime(pasti['data_ora'], errors='coerce')
    return pasti, utenti, sport

def elimina_pasto(pasto_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM pasti WHERE id = ?", (pasto_id,))
    conn.commit()
    conn.close()

def pulisci_valore(testo):
    if not testo: return 0.0
    solo_numeri = re.sub(r'[^0-9.]', '', str(testo).replace(',', '.'))
    try: return float(solo_numeri)
    except: return 0.0

try:
    pasti, utenti, sport = carica_dati()
except Exception as e:
    st.error(f"⚠️ Impossibile caricare il database locale: {e}")
    st.stop()

if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
if "mostra_form" not in st.session_state: st.session_state.mostra_form = False

# --- LOGICA DI ISOLAMENTO UTENTE ---
st.sidebar.title("🥑 Menu Pro")

utente_corrente = utenti[utenti['email'] == email_loggata]

if not utente_corrente.empty:
    id_utente = utente_corrente['user_id'].values[0]
    nome_utente = utente_corrente['nome'].values[0]
else:
    if email_loggata == "tirinatomarco@gmail.com":
        id_utente = 113069242
        nome_utente = "Marco"
    else:
        id_utente = 12345678
        nome_utente = "Ospite"

st.sidebar.markdown(f"### Bentornato, {nome_utente}! 👋")

vista_temporale = st.sidebar.radio("Orizzonte Temporale Dashboard:", ["Oggi", "Settimana", "Mese"])

# --- AGGIORNAMENTO VOCI DEL MENU ---
menu = st.sidebar.radio("Naviga:", [
    "📊 Dashboard", 
    "📅 Piano Alimentare", 
    "🛒 Lista Spesa", 
    "📜 Storico", 
    "🤖 Chat IA",
    "⚙️ Impostazioni Profilo"  # Nuova sezione
])

oggi = datetime.now().date()
inizio_settimana = oggi - timedelta(days=7)
inizio_mese = oggi - timedelta(days=30)

if menu == "📊 Dashboard":
    st.title(f"Dashboard Personale 🚀")
    
    if vista_temporale == "Oggi":
        df_p_v = pasti[(pasti['user_id'] == id_utente) & (pasti['data_ora'].dt.date == oggi)]
        df_s_v = sport[(sport['user_id'] == id_utente) & (pd.to_datetime(sport['data_ora']).dt.date == oggi)]
        if id_utente in utenti['user_id'].values:
            target_v = utenti[utenti['user_id'] == id_utente]['tdee'].values[0]
        else:
            target_v = 2000.0
    elif vista_temporale == "Settimana":
        df_p_v = pasti[(pasti['user_id'] == id_utente) & (pasti['data_ora'].dt.date > inizio_settimana)]
        df_s_v = sport[(sport['user_id'] == id_utente) & (pd.to_datetime(sport['data_ora']).dt.date > inizio_settimana)]
        target_v = (utenti[utenti['user_id'] == id_utente]['tdee'].values[0] * 7) if id_utente in utenti['user_id'].values else (2000.0 * 7)
    else: 
        df_p_v = pasti[(pasti['user_id'] == id_utente) & (pasti['data_ora'].dt.date > inizio_mese)]
        df_s_v = sport[(sport['user_id'] == id_utente) & (pd.to_datetime(sport['data_ora']).dt.date > inizio_mese)]
        target_v = (utenti[utenti['user_id'] == id_utente]['tdee'].values[0] * 30) if id_utente in utenti['user_id'].values else (2000.0 * 30)

    assunte = df_p_v['calorie'].sum()
    bruciate = pd.to_numeric(df_s_v['calorie_bruciate']).sum()
    residuo = target_v - assunte + bruciate
    rating_medio = df_p_v['rating'].mean() if not df_p_v.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.markdown(f"<div class='metric-card'>🎯 Target<br><span class='metric-value'>{target_v:.0f}</span></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-card'>🍎 Assunte<br><span class='metric-value'>{assunte:.0f}</span></div>", unsafe_allow_html=True)
    res_col = "#3fb950" if residuo >= 0 else "#f85149"
    k3.markdown(f"<div class='metric-card' style='border-color:{res_col}'>🔋 Residuo<br><span class='metric-value' style='color:{res_col}'>{residuo:.0f}</span></div>", unsafe_allow_html=True)
    k4.markdown(f"<div class='metric-card'>🏃 Sport<br><span class='metric-value'>+{bruciate:.0f}</span></div>", unsafe_allow_html=True)
    rat_col = "#3fb950" if rating_medio > 75 else "#e3b341" if rating_medio > 50 else "#f85149"
    k5.markdown(f"<div class='metric-card' style='border-color:{rat_col}'>⭐ Rating<br><span class='metric-value' style='color:{rat_col}'>{rating_medio:.0f}%</span></div>", unsafe_allow_html=True)

    st.divider()
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("📈 Trend Calorie (Ultimi 7 Giorni)")
        p_7 = pasti[(pasti['user_id'] == id_utente) & (pasti['data_ora'].dt.date > inizio_settimana)].copy()
        if not p_7.empty:
            p_7['giorno'] = p_7['data_ora'].dt.strftime('%a')
            t_data = p_7.groupby('giorno')['calorie'].sum().reindex(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']).fillna(0).reset_index()
            t_giorno = target_v / (7 if vista_temporale == "Settimana" else (30 if vista_temporale == "Mese" else 1))
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(x=t_data['giorno'], y=t_data['calorie'], name='Calorie', line=dict(color='#58a6ff', width=4), mode='lines+markers'))
            fig_t.add_shape(type="line", x0=0, y0=t_giorno, x1=6, y1=t_giorno, line=dict(color="red", width=2, dash="dash"))
            fig_t.add_annotation(x=0, y=t_giorno, text="Target", showarrow=False, yshift=10, font=dict(color="red"))
            fig_t.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", height=250, margin=dict(t=30,b=20,l=0,r=0))
            st.plotly_chart(fig_t, use_container_width=True)

        st.divider()
        st.subheader(f"📊 Analisi Dettagliata ({vista_temporale})")
        c1, c2 = st.columns(2)
        with c1:
            if not df_p_v.empty:
                st.write("**Distribuzione Macro**")
                fig_p = go.Figure(data=[go.Pie(labels=['Carbo', 'Prot', 'Fat'], values=[df_p_v['carboidrati'].sum(), df_p_v['proteine'].sum(), df_p_v['grassi'].sum()], hole=.5, marker=dict(colors=['#3b82f6', '#f85149', '#3fb950']))])
                fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="white", height=300, margin=dict(t=0,b=0,l=0,r=0))
                st.plotly_chart(fig_p, use_container_width=True)
            else:
                st.info(f"Nessun dato alimentare trovato per il periodo: {vista_temporale}")
        with c2:
            if not df_p_v.empty:
                st.write("**Calorie per Categoria**")
                df_bar = df_p_v.copy()
                df_bar['cat'] = df_bar['descrizione'].apply(lambda x: re.search(r'\((.*?)\)', x).group(1) if '(' in x else 'Altro')
                c_sum = df_bar.groupby('cat')['calorie'].sum().reset_index()
                fig_b = px.bar(c_sum, x='calorie', y='cat', orientation='h', color_discrete_sequence=['#58a6ff'], text_auto='.0f')
                fig_b.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white", height=300, margin=dict(t=0,b=0,l=0,r=0))
                st.plotly_chart(fig_b, use_container_width=True)
            else:
                st.info("Nessuna categoria registrata in questo periodo.")

    with col_right:
        st.subheader("📸 Registra Pasto")
        up_file = st.file_uploader("Carica foto", type=['jpg', 'jpeg', 'png'], key=f"up_{st.session_state.uploader_key}")
        if up_file:
            img = Image.open(up_file)
            st.image(img, use_container_width=True)
            if st.button("🪄 Analizza"):
                with st.spinner("L'IA sta valutando il piatto..."):
                    prompt = "Analizza la foto. Descrivi benefici. Voto 0-100. DATA_BLOCK|Nome|Kcal|Carbo|Prot|Fat|Rating|Dettagli"
                    res = model.generate_content([prompt, img])
                    st.session_state.analisi_testuale = res.text.split("DATA_BLOCK")[0].strip()
                    st.session_state.dati_tecnici = res.text
                    st.session_state.mostra_form = True
                    st.rerun()

        if st.session_state.mostra_form:
            st.info(st.session_state.analisi_testuale)
            m = re.search(r"DATA_BLOCK\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*)", st.session_state.dati_tecnici)
            if m:
                n_i, k_i, c_i, p_i, f_i, r_i, d_i = m.groups()
                with st.form("save"):
                    u_n = st.text_input("Nome", value=n_i)
                    u_c = st.selectbox("Momento", ["Colazione", "Pranzo", "Cena", "Spuntino"])
                    if st.form_submit_button("✅ Salva"):
                        conn = get_db_connection()
                        conn.execute("INSERT INTO pasti (user_id, data_ora, descrizione, calorie, carboidrati, proteine, grassi, rating, dettaglio_json) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (int(id_utente), datetime.now().strftime("%Y-%m-%d %H:%M"), f"{u_n} ({u_c})", pulisci_valore(k_i), pulisci_valore(c_i), pulisci_valore(p_i), pulisci_valore(f_i), pulisci_valore(r_i), d_i))
                        conn.commit(); conn.close()
                        st.session_state.mostra_form = False
                        st.session_state.uploader_key += 1
                        st.rerun()

# --- PIANO ALIMENTARE (SEMPLIFICATO) ---
elif menu == "📅 Piano Alimentare":
    st.title("📅 Il tuo Piano Alimentare")
    
    profilo = utenti[utenti['user_id'] == id_utente].iloc[0] if id_utente in utenti['user_id'].values else None
    
    if profilo is None:
        st.warning("Per favore, aggiorna il tuo Profilo nella sezione Impostazioni per permettere all'IA di calcolare la tua dieta.")
        st.stop()
        
    st.success(f"📌 Stiamo personalizzando la dieta per il tuo obiettivo: **{profilo.get('obiettivo', 'Non specificato')}** (Dieta: **{profilo.get('dieta', 'Non specificata')}**). Target: **{profilo['tdee']:.0f} Kcal**.")
    
    with st.container():
        st.markdown("### 🛠 Personalizza la Giornata")
        c1, c2 = st.columns(2)
        # Nuova selezione dei pasti, molto più semplice per l'utente!
        num_pasti = c1.selectbox("Quanti pasti desideri fare?", ["3 Pasti (Colazione, Pranzo, Cena)", "4 Pasti (+ 1 Spuntino)", "5 Pasti (+ 2 Spuntini)"])
        allergie = c2.multiselect("Allergie/Intolleranze", ["Nessuna", "Frutta secca", "Lattosio", "Glutine", "Agrumi", "Crostacei"])

    if st.button("✨ Genera Piano Adattivo con IA"):
        with st.spinner("L'IA sta elaborando la tua dieta analizzando il tuo andamento..."):
            t_kcal = profilo['tdee']
            
            p_7 = pasti[(pasti['user_id'] == id_utente) & (pasti['data_ora'].dt.date > inizio_settimana)]
            if not p_7.empty:
                assunte_7g = p_7['calorie'].sum()
                giorni_registrati = len(p_7['data_ora'].dt.date.unique())
                media_kcal = assunte_7g / giorni_registrati if giorni_registrati > 0 else 0
                feedback_ia = f"CONTESTO ADATTIVO: La settimana scorsa l'utente ha consumato in media {media_kcal:.0f} kcal al giorno (il suo Target era {t_kcal:.0f} kcal). Aggiusta le porzioni per aiutarlo a tornare in carreggiata se si è discostato troppo."
            else:
                feedback_ia = "CONTESTO ADATTIVO: Questa è la prima settimana o non ci sono dati recenti. Crea un piano standard."

            # Passiamo l'obiettivo, la dieta e il numero di pasti letti dal DB
            instr = f"""Crea un piano alimentare per un utente con target di {t_kcal} kcal.
            {feedback_ia}
            Stile: {profilo['dieta']}. Obiettivo: {profilo['obiettivo']}. Allergie da evitare: {', '.join(allergie)}.
            Numero di pasti richiesto: {num_pasti}.
            Indica ingredienti e calorie stimati per ogni pasto richiesto."""
            
            res = model.generate_content(instr)
            st.session_state.piano_testo = res.text
            
            res_s = model.generate_content(f"Estrai solo la lista della spesa puntata (no commenti) da: {res.text}")
            items = [re.sub(r'^\* |^- ', '', i).strip() for i in res_s.text.split('\n') if i.strip() and len(i) > 2]
            conn = get_db_connection()
            conn.execute("DELETE FROM spesa WHERE user_id = ?", (int(id_utente),))
            for i in items: conn.execute("INSERT INTO spesa (user_id, item) VALUES (?, ?)", (int(id_utente), i))
            conn.commit(); conn.close()
            st.success("Piano Generato!")

    if "piano_testo" in st.session_state:
        st.markdown("---")
        st.markdown(st.session_state.piano_testo)
        
        st.markdown("---")
        if FPDF_AVAILABLE:
            pdf_bytes = genera_pdf_dieta(st.session_state.piano_testo)
            st.download_button(
                label="📥 Scarica Piano in PDF",
                data=pdf_bytes,
                file_name=f"Piano_Alimentare_{nome_utente}.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("💡 Il tuo sistema non ha ancora la libreria per i PDF. Apri il terminale e scrivi: pip install fpdf")

# --- NUOVA SEZIONE: IMPOSTAZIONI PROFILO ---
elif menu == "⚙️ Impostazioni Profilo":
    st.title("⚙️ Gestione Profilo")
    
    profilo = utenti[utenti['user_id'] == id_utente].iloc[0] if id_utente in utenti['user_id'].values else None
    
    if profilo is None:
        st.error("Dati del profilo non trovati.")
    else:
        tab_dati, tab_sicurezza = st.tabs(["📝 Modifica Dati e Obiettivi", "🔒 Cambia Password"])
        
        with tab_dati:
            with st.form("update_profile_form"):
                st.markdown("Aggiorna il tuo peso o il tuo obiettivo. Il sistema ricalcolerà il tuo fabbisogno calorico in automatico!")
                
                # Pre-compiliamo i campi con i dati esistenti per comodità dell'utente
                c1, c2 = st.columns(2)
                up_nome = c1.text_input("Nome", value=profilo.get('nome', '')).strip()
                up_sesso = c2.selectbox("Sesso", ["Uomo", "Donna"], index=0 if profilo.get('sesso') == "Uomo" else 1)
                
                c3, c4 = st.columns(2)
                # Estraiamo il peso in modo sicuro in caso di valori assenti
                peso_attuale = float(profilo['peso']) if pd.notna(profilo.get('peso')) else 70.0
                altezza_attuale = float(profilo['altezza']) if pd.notna(profilo.get('altezza')) else 170.0
                
                up_peso = c3.number_input("Peso (kg)", min_value=30.0, max_value=250.0, value=peso_attuale, step=0.1)
                up_altezza = c4.number_input("Altezza (cm)", min_value=100.0, max_value=250.0, value=altezza_attuale, step=1.0)
                
                st.divider()
                c5, c6 = st.columns(2)
                diete_disp = ["Onnivoro", "Carnivoro (Prevalenza Carne)", "Vegetariano", "Vegano", "Pescatariano", "Flessitariano"]
                idx_dieta = diete_disp.index(profilo.get('dieta')) if profilo.get('dieta') in diete_disp else 0
                up_dieta = c5.selectbox("Preferenza Culinaria", diete_disp, index=idx_dieta)
                
                sport_disp = ["Sedentario", "Leggera (1-2 volte/settimana)", "Moderata (3-4 volte/settimana)", "Intensa (5+ volte/settimana)", "Atleta Professionista"]
                idx_sport = sport_disp.index(profilo.get('sport')) if profilo.get('sport') in sport_disp else 0
                up_sport = c6.selectbox("Attività Fisica", sport_disp, index=idx_sport)
                
                ob_disp = ["Dimagrimento", "Definizione Muscolare", "Mantenimento", "Aumento Massa Muscolare", "Ricomposizione Corporea"]
                idx_ob = ob_disp.index(profilo.get('obiettivo')) if profilo.get('obiettivo') in ob_disp else 0
                up_obiettivo = st.selectbox("Obiettivo Principale", ob_disp, index=idx_ob)
                
                if st.form_submit_button("💾 Salva Modifiche"):
                    # Ricalcolo intelligente del nuovo TDEE
                    try:
                        data_nascita = pd.to_datetime(profilo['data_nascita']).date()
                        oggi_data = datetime.now().date()
                        eta = oggi_data.year - data_nascita.year - ((oggi_data.month, oggi_data.day) < (data_nascita.month, data_nascita.day))
                    except:
                        eta = 30 # Default di sicurezza se la data è assente
                        
                    if up_sesso == "Uomo":
                        bmr = (10 * up_peso) + (6.25 * up_altezza) - (5 * eta) + 5
                    else:
                        bmr = (10 * up_peso) + (6.25 * up_altezza) - (5 * eta) - 161
                        
                    moltiplicatori = {"Sedentario": 1.2, "Leggera (1-2 volte/settimana)": 1.375, "Moderata (3-4 volte/settimana)": 1.55, "Intensa (5+ volte/settimana)": 1.725, "Atleta Professionista": 1.9}
                    nuovo_tdee = bmr * moltiplicatori.get(up_sport, 1.2)
                    
                    if "Dimagrimento" in up_obiettivo or "Definizione" in up_obiettivo:
                        nuovo_tdee -= 400 
                    elif "Aumento Massa" in up_obiettivo:
                        nuovo_tdee += 300 
                        
                    # Sovrascriviamo i dati nel database SQLite (Comando UPDATE)
                    conn = get_db_connection()
                    conn.execute("""
                        UPDATE utenti 
                        SET nome=?, sesso=?, peso=?, altezza=?, dieta=?, sport=?, obiettivo=?, tdee=?
                        WHERE user_id=?
                    """, (up_nome, up_sesso, up_peso, up_altezza, up_dieta, up_sport, up_obiettivo, nuovo_tdee, int(id_utente)))
                    conn.commit()
                    conn.close()
                    st.success("✅ Dati aggiornati! Ricarica la pagina per vedere le modifiche sul tuo Fabbisogno Calorico.")
                    
        with tab_sicurezza:
            with st.form("password_form"):
                st.markdown("Digita una nuova password. Scegli qualcosa di sicuro ma che puoi ricordare facilmente.")
                new_pass = st.text_input("Nuova Password", type="password")
                new_pass_confirm = st.text_input("Conferma Nuova Password", type="password")
                
                if st.form_submit_button("🔒 Aggiorna Password"):
                    if new_pass != new_pass_confirm:
                        st.error("❌ Le due password non coincidono.")
                    elif len(new_pass) < 6:
                        st.error("❌ La password deve contenere almeno 6 caratteri.")
                    else:
                        try:
                            # Invia la nuova password cifrata ai server di Supabase
                            supabase.auth.update_user({'password': new_pass})
                            st.success("✅ Password aggiornata con successo!")
                        except Exception as e:
                            st.error(f"Impossibile aggiornare la password. Dettaglio: {str(e)}")

elif menu == "🛒 Lista Spesa":
    st.title("🛒 Lista della Spesa")
    conn = get_db_connection()
    items_db = pd.read_sql_query(f"SELECT * FROM spesa WHERE user_id = {id_utente}", conn)
    if items_db.empty:
        st.info("Genera un piano alimentare per vedere la lista della spesa.")
    else:
        for _, row in items_db.iterrows():
            c = st.checkbox(row['item'], value=row['completato'] == 1, key=f"s_{row['id']}")
            if c != (row['completato'] == 1):
                conn.execute("UPDATE spesa SET completato = ? WHERE id = ?", (1 if c else 0, row['id']))
                conn.commit()
    if st.button("🗑️ Svuota Lista"):
        conn.execute("DELETE FROM spesa WHERE user_id = ?", (int(id_utente),))
        conn.commit(); conn.close(); st.rerun()
    conn.close()

elif menu == "📜 Storico":
    st.title("📜 Storico")
    p_u = pasti[pasti['user_id'] == id_utente].sort_values('data_ora', ascending=False)
    for _, r in p_u.iterrows():
        c1, c2, c3 = st.columns([4, 1, 0.5])
        c1.write(f"**{r['data_ora']}** - {r['descrizione']} ({r['calorie']:.0f} kcal) ⭐ {r['rating']:.0f}")
        if c3.button("🗑️", key=f"del_{r['id']}"):
            elimina_pasto(r['id'])
            st.rerun()

elif menu == "🤖 Chat IA":
    st.title("🤖 Chat")
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if p := st.chat_input("Chiedi..."):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        res = model.generate_content(p)
        st.session_state.messages.append({"role": "assistant", "content": res.text})
        with st.chat_message("assistant"): st.markdown(res.text)