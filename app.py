import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import google.generativeai as genai
from PIL import Image
import re
import os
import random

# --- IMPORTIAMO DATABASE E STILI ---
from database import supabase, carica_dati_utente
from styles import get_login_css, get_main_css

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError: pass

try:
    from fpdf import FPDF
    import tempfile
    FPDF_AVAILABLE = True
except ImportError: FPDF_AVAILABLE = False

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="VN Pro - AI Nutrition", layout="wide", page_icon="🟢")

# --- 1.1 INIZIALIZZAZIONE MEMORIA ---
if 'utente_loggato' not in st.session_state: 
    st.session_state.utente_loggato = False
if 'email_utente' not in st.session_state: 
    st.session_state.email_utente = ""
if 'lang' not in st.session_state:
    st.session_state.lang = 'it'

# --- 1.2 FUNZIONE CENTRALE CALCOLO TDEE (COERENZA 100%) ---
def calcola_tdee_professionale(peso, altezza, dob, sesso, sport, obiettivo):
    oggi_data = datetime.now().date()
    eta = oggi_data.year - dob.year - ((oggi_data.month, oggi_data.day) < (dob.month, dob.day))
    
    bmr = (10 * peso) + (6.25 * altezza) - (5 * eta) + (5 if sesso == "Uomo" else -161)
    
    moltiplicatori = {
        "Sedentario": 1.2,
        "Leggera": 1.375,
        "Moderata": 1.55,
        "Intensa": 1.725,
        "Atleta": 1.9
    }
    chiave_sport = sport.split(" ")[0]
    tdee = bmr * moltiplicatori.get(chiave_sport, 1.2)
    
    if "Dimagrimento" in obiettivo: tdee -= 400
    elif "Aumento" in obiettivo: tdee += 300
    elif "Definizione" in obiettivo: tdee -= 250
    
    return tdee

translations = {
    'it': {
        'nav': "NAVIGAZIONE", 'dash': "📊 Dashboard", 'stats': "📈 Statistiche", 'diet': "📅 Piano Alimentare",
        'shop': "🛒 Lista Spesa", 'hist': "📜 Storico", 'chat': "🧠 Chat IA", 'prof': "⚙️ Profilo",
        'welcome': "Bentornato", 'summary': "Ecco il tuo riepilogo giornaliero.", 'target': "TARGET (KCAL)",
        'assunte': "ASSUNTE", 'residuo': "RESIDUO", 'nutriscore': "NUTRISCORE", 'dist_macro': "Distribuzione Macronutrienti",
        'reg_pasto': "Registra Pasto", 'analizza': "🪄 Analizza Piatto", 'tip': "Consiglio del giorno",
        'save_cloud': "Salva nel Diario", 'privacy_msg': "Devi accettare la Privacy Policy.", 'logout': "Esci",
        'placeholder_chat': "Fai una domanda nutrizionale...", 'low_data': "Nessun dato sufficiente. Registra i tuoi pasti.",
        'upload_action': "Carica foto", 'why_score': "Perché questo voto?", 'estimated_values': "VALORI STIMATI",
        'empty_list_warn': "Sei sicuro di voler svuotare tutta la lista?", 'yes_empty': "Sì, svuota", 'cancel': "Annulla"
    },
    'en': {
        'nav': "NAVIGATION", 'dash': "📊 Dashboard", 'stats': "📈 Analytics", 'diet': "📅 Meal Plan",
        'shop': "🛒 Grocery List", 'hist': "📜 History", 'chat': "🧠 AI Coach", 'prof': "⚙️ Profile",
        'welcome': "Welcome back", 'summary': "Here is your daily summary.", 'target': "TARGET (KCAL)",
        'assunte': "CONSUMED", 'residuo': "REMAINING", 'nutriscore': "NUTRISCORE", 'dist_macro': "Macro Distribution",
        'reg_pasto': "Log Meal", 'analizza': "🪄 Analyze Dish", 'tip': "Tip of the day",
        'save_cloud': "Save to Cloud", 'privacy_msg': "You must accept the Privacy Policy.", 'logout': "Logout",
        'placeholder_chat': "Ask a nutrition question...", 'low_data': "Not enough data. Start logging your meals.",
        'upload_action': "Upload photo", 'why_score': "Why this score?", 'estimated_values': "ESTIMATED VALUES",
        'empty_list_warn': "Are you sure you want to empty the list?", 'yes_empty': "Yes, empty it", 'cancel': "Cancel"
    }
}
L = translations[st.session_state.lang]

# --- 2. CONFIGURAZIONE IA ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

@st.cache_data
def carica_database_rag():
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conoscenza_nutrizionista.pkl.gz")
        if os.path.exists(p): return pd.read_pickle(p, compression="gzip")
        return None
    except: return None

db_rag = carica_database_rag()

def recupera_da_manuali(query_testo, top_k=3):
    if db_rag is None: return ""
    try:
        res = genai.embed_content(model="models/gemini-embedding-001", content=query_testo, task_type="retrieval_query")
        q_v = np.array(res['embedding'])
        results = []
        for item in db_rag:
            d_v = np.array(item["vettore"])
            sim = np.dot(q_v, d_v) / (np.linalg.norm(q_v) * np.linalg.norm(d_v))
            results.append((sim, item["testo"], item["fonte"]))
        results.sort(key=lambda x: x[0], reverse=True)
        return "\n\n---\n\n".join([f"(Fonte: {r[2]})\n{r[1]}" for r in results[:top_k]])
    except: return ""

def genera_pdf_dieta(testo_markdown):
    testo_pulito = testo_markdown.replace('**', '').replace('* ', '- ').encode('latin-1', 'replace').decode('latin-1')
    pdf = FPDF()
    pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.set_font("Arial", 'B', 16); pdf.cell(200, 10, txt="Il tuo Piano Alimentare", ln=True, align='C')
    pdf.ln(10); pdf.set_font("Arial", size=12)
    for riga in testo_pulito.split('\n'): pdf.multi_cell(0, 8, txt=riga)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f: pdf_bytes = f.read()
    return pdf_bytes

@st.cache_data(ttl=86400, show_spinner=False) 
def get_tip_del_giorno(data_odierna, lang):
    if db_rag is None or len(db_rag) == 0:
        return "Bevi almeno 2 litri d'acqua al giorno e varia le fonti proteiche." if lang == 'it' else "Drink at least 2 liters of water a day and vary protein sources."
    random.seed(data_odierna.toordinal())
    frammento = random.choice(db_rag)["testo"]
    lang_name = "ITALIANO" if lang == 'it' else "ENGLISH"
    prompt = f"Sei un nutrizionista. Estrai un 'Consiglio del giorno' (max 2 righe, motivazionale) basandoti solo su questo testo: {frammento}. RISPONDI IN {lang_name}."
    try: return model.generate_content(prompt).text.strip().replace('**', '')
    except: return "Scegli carboidrati complessi per energia costante." if lang == 'it' else "Choose complex carbs for steady energy."

# --- 3. AUTENTICAZIONE ---
if not st.session_state.utente_loggato:
    st.markdown(get_login_css(), unsafe_allow_html=True)
    try: st.image("logo_vn.png", width=100)
    except: st.markdown("<h1 style='color:#16EC06;'>VN PRO</h1>", unsafe_allow_html=True)
    
    st.title("Virtual Nutritionist Pro")
    t_log, t_reg = st.tabs(["🔑 Accedi", "📝 Crea Profilo Completo"])
    
    with t_log:
        with st.form("login"):
            e_in = st.text_input("Email").strip()
            p_in = st.text_input("Password", type="password").strip()
            if st.form_submit_button("Entra"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": e_in, "password": p_in})
                    if res.user:
                        st.session_state.utente_loggato = True
                        st.session_state.email_utente = res.user.email
                        st.rerun() 
                except Exception as e: st.error("❌ Credenziali errate.")
    
    with t_reg:
        st.subheader("Raccontaci di te")
        with st.form("register"):
            c1, c2 = st.columns(2)
            r_n = c1.text_input("Nome*").strip()
            r_c = c2.text_input("Cognome*").strip()
            
            c3, c4 = st.columns(2)
            r_dob = c3.date_input("Data Nascita*", min_value=datetime(1920,1,1), max_value=datetime.now())
            r_sex = c4.selectbox("Sesso*", ["Uomo", "Donna"])
            
            c5, c6 = st.columns(2)
            r_w = c5.number_input("Peso (kg)*", min_value=30.0, max_value=250.0, value=70.0, step=0.1)
            r_h = c6.number_input("Altezza (cm)*", min_value=100.0, max_value=250.0, value=170.0, step=1.0)
            
            st.divider()
            r_diet = st.selectbox("Preferenza Culinaria*", ["Onnivoro", "Carnivoro", "Vegetariano", "Vegano", "Pescatariano"])
            r_sport = st.selectbox("Attività Fisica*", ["Sedentario", "Leggera (1-2 volte/sett)", "Moderata (3-4 volte/sett)", "Intensa (5+ volte/sett)", "Atleta Professionista"])
            r_obj = st.selectbox("Obiettivo Principale*", ["Dimagrimento", "Definizione Muscolare", "Mantenimento", "Aumento Massa Muscolare", "Ricomposizione Corporea"])
            
            st.divider()
            r_e = st.text_input("Email*").strip()
            
            c7, c8 = st.columns(2)
            r_p = c7.text_input("Scegli una Password*", type="password").strip()
            r_p_conf = c8.text_input("Conferma Password*", type="password").strip()
            
            st.markdown("<span style='font-size: 12px; color: #8e8e93; font-weight:bold; letter-spacing:1px;'>CONSENSI LEGALI (GDPR)</span>", unsafe_allow_html=True)
            cons_privacy = st.checkbox("Accetto la Privacy Policy e i Termini di Servizio (Obbligatorio)*")
            cons_mkt = st.checkbox("Acconsento a ricevere comunicazioni di marketing e offerte (Facoltativo)")
            cons_prof = st.checkbox("Acconsento all'analisi dei miei dati per fini statistici e di profilazione (Facoltativo)")
            
            if st.form_submit_button("Crea Account e Salva Profilo"):
                if not cons_privacy: 
                    st.warning("⚠️ Devi accettare la Privacy Policy per poterti registrare.")
                elif r_p != r_p_conf: 
                    st.warning("⚠️ Le password non coincidono.")
                elif len(r_p) < 6: 
                    st.warning("⚠️ Password troppo corta.")
                else:
                    try:
                        auth_res = supabase.auth.sign_up({"email": r_e, "password": r_p})
                        nuovo_id_uuid = str(auth_res.user.id)
                        u_tdee = calcola_tdee_professionale(r_w, r_h, r_dob, r_sex, r_sport, r_obj)
                        
                        supabase.table("utenti").insert({
                            "user_id": nuovo_id_uuid, "nome": r_n, "cognome": r_c, "email": r_e,
                            "sesso": r_sex, "data_nascita": str(r_dob), "peso": r_w, "altezza": r_h,
                            "dieta": r_diet, "sport": r_sport, "obiettivo": r_obj, "tdee": u_tdee,
                            "consenso_privacy": cons_privacy,
                            "consenso_marketing": cons_mkt,
                            "consenso_profilazione": cons_prof
                        }).execute()
                        st.success("✅ Account creato! Effettua il login.")
                    except Exception as e: st.error(f"Errore registrazione: {e}")
    st.stop()

# --- 4. CARICAMENTO DATI ---
pasti, utente, spesa, target_v, id_utente = carica_dati_utente(st.session_state.email_utente)

if target_v is None: target_v = 2000
id_utente = str(id_utente) if id_utente else "0"

st.markdown(get_main_css(), unsafe_allow_html=True)

# --- 5. SIDEBAR ---
with st.sidebar:
    st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
    try: st.image("logo_vn.png", width=120)
    except: st.markdown("<h2 style='color:#16EC06;'>VN PRO</h2>", unsafe_allow_html=True)
    st.markdown("</div><br>", unsafe_allow_html=True)
    
    st.markdown(f"<small style='color:#8e8e93;'>UTENTE</small><br><b>{st.session_state.email_utente}</b>", unsafe_allow_html=True)
    sel_lang = st.selectbox("🌍 LINGUA / LANGUAGE", ["Italiano", "English"], index=0 if st.session_state.lang == 'it' else 1)
    if st.button("OK / Confirm"):
        st.session_state.lang = 'it' if sel_lang == "Italiano" else 'en'
        st.rerun()
    st.divider()
    
if "uploader_key" not in st.session_state: st.session_state.uploader_key = 0
if "mostra_form" not in st.session_state: st.session_state.mostra_form = False

menu = st.sidebar.radio(L['nav'], [L['dash'], L['stats'], L['diet'], L['shop'], L['hist'], L['chat'], L['prof']], label_visibility="collapsed")

with st.sidebar:
    st.write("")
    if st.button(L['logout'], use_container_width=True):
        if supabase is not None: supabase.auth.sign_out()
        st.session_state.utente_loggato = False
        st.session_state.email_utente = ""
        st.rerun()

# --- 6. LOGICA PAGINE ---
oggi = datetime.now().date()
lang_str = "ITALIANO" if st.session_state.lang == 'it' else "ENGLISH"

def pulisci_valore(testo):
    if not testo: return 0.0
    try: return float(re.sub(r'[^0-9.]', '', str(testo).replace(',', '.')))
    except: return 0.0

if menu == L['dash']:
    prof = utente.iloc[0] if not utente.empty else {}
    st.markdown(f"<h2>{L['welcome']}, {prof.get('nome', 'User')} 🟢</h2>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#8e8e93; margin-top:-10px; margin-bottom:20px;'>{L['summary']}</p>", unsafe_allow_html=True)
    
    df_p_v = pd.DataFrame()
    if not pasti.empty:
        p_temp = pasti.copy()
        if pd.api.types.is_datetime64tz_dtype(p_temp['data_ora']): p_temp['data_ora'] = p_temp['data_ora'].dt.tz_localize(None)
        df_p_v = p_temp[p_temp['data_ora'].dt.date == oggi]

    assunte = df_p_v['calorie'].sum() if not df_p_v.empty else 0
    residuo = target_v - assunte
    rating_medio = df_p_v['rating'].mean() if not df_p_v.empty and 'rating' in df_p_v.columns else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-card'><span class='metric-label'>🎯 {L['target']}</span><span class='metric-value'>{target_v:.0f}</span></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-card'><span class='metric-label'>🍎 {L['assunte']}</span><span class='metric-value'>{assunte:.0f}</span></div>", unsafe_allow_html=True)
    res_col = "#16EC06" if residuo >= 0 else "#e54343"
    k3.markdown(f"<div class='metric-card' style='border-top:2px solid {res_col}'><span class='metric-label'>🔋 {L['residuo']}</span><span class='metric-value' style='color:{res_col}'>{residuo:.0f}</span></div>", unsafe_allow_html=True)
    rat_col = "#16EC06" if rating_medio >= 75 else "#e5a443" if rating_medio >= 50 else "#e54343"
    rat_val = f"{rating_medio:.0f}" if rating_medio > 0 else "--"
    k4.markdown(f"<div class='metric-card'><span class='metric-label'>⭐ {L['nutriscore']}</span><span class='metric-value' style='color:{rat_col}'>{rat_val}</span></div>", unsafe_allow_html=True)

    c_l, c_r = st.columns([2, 1])
    with c_l:
        st.markdown(f"<h4 style='font-size: 16px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>{L['dist_macro']}</h4>", unsafe_allow_html=True)
        if not df_p_v.empty:
            c_carbo, c_prot, c_fat = df_p_v['carboidrati'].sum(), df_p_v['proteine'].sum(), df_p_v['grassi'].sum()
            fig_p = go.Figure(data=[go.Pie(labels=['Carbo', 'Prot', 'Fat'], values=[c_carbo, c_prot, c_fat], hole=.6, marker=dict(colors=['#58a6ff', '#e54343', '#16EC06']))])
            fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#e5e5ea", height=280, margin=dict(t=10,b=0,l=0,r=0), showlegend=True)
            st.plotly_chart(fig_p, use_container_width=True)
        else: st.info(L['low_data'])

    with c_r:
        st.markdown(f"<h4 style='font-size: 16px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>{L['reg_pasto']}</h4>", unsafe_allow_html=True)
        up = st.file_uploader(L['upload_action'], type=['jpg','jpeg','png','heic','avif'], key=f"up_{st.session_state.uploader_key}", label_visibility="collapsed")
        if up:
            try:
                img = Image.open(up).convert('RGB'); st.image(img, use_container_width=True)
                if st.button(L['analizza'], use_container_width=True):
                    with st.spinner("IA..."):
                        p = f"Analizza foto. Formato ESATTO. Traduci Descrizione e Spiegazione in {lang_str}: DATA_BLOCK|Nome Piatto|Kcal|Carbo|Prot|Fat|FatSaturi|Score|Desc_2righe|Spiegazione_2righe"
                        st.session_state.dati_tecnici = model.generate_content([p, img]).text.strip().replace('\n', '')
                        st.session_state.mostra_form = True; st.rerun()
            except Exception: st.error("⚠️ Errore file.")
        
        if st.session_state.get('mostra_form'):
            m = re.search(r"DATA_BLOCK\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*)", st.session_state.dati_tecnici)
            if m:
                n_i, k_i, c_i, p_i, f_i, sat_i, r_i, d_i, s_i = m.groups()
                st.markdown(f"<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; margin-bottom:15px; border:1px solid #16EC06;'><h3 style='margin-top:0; color:#16EC06 !important;'>{n_i}</h3><span style='color:#8e8e93;'>{d_i}</span><br><br><span style='font-size:11px; color:#8e8e93; font-weight:bold;'>{L['estimated_values']}</span><br>🔥 {k_i} kcal | 🥑 {c_i}g C | 🥩 {p_i}g P | 🧈 {f_i}g F (Sat: {sat_i}g)<div style='background-color:#121212; padding:10px; border-radius:8px; margin-top:10px;'><strong style='color:#16EC06;'>Score: {r_i}/100</strong><br><span style='font-size:13px; color:#e5e5ea;'><i>{s_i}</i></span></div></div>", unsafe_allow_html=True)
                with st.form("save"):
                    u_n = st.text_input("Dish name", value=n_i)
                    u_c = st.selectbox("Meal", ["Colazione", "Pranzo", "Cena", "Spuntino"])
                    if st.form_submit_button(L['save_cloud'], type="primary"):
                        dettagli_extra = f"Grassi saturi: {sat_i}g. Note: {s_i}"
                        supabase.table("pasti").insert({"user_id": id_utente, "descrizione": f"{u_n} ({u_c})", "calorie": pulisci_valore(k_i), "carboidrati": pulisci_valore(c_i), "proteine": pulisci_valore(p_i), "grassi": pulisci_valore(f_i), "rating": pulisci_valore(r_i), "dettaglio_json": dettagli_extra}).execute()
                        st.session_state.mostra_form = False; st.session_state.uploader_key += 1; st.rerun()

    st.markdown("<br><hr style='border-color: #2c2c2e;'>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='font-size: 14px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>💡 {L['tip']}</h4>", unsafe_allow_html=True)
    msg_spinner = "A breve il tuo consiglio giornaliero personalizzato..." if st.session_state.lang == 'it' else "Preparing your personalized daily tip..."
    with st.spinner(msg_spinner):
        tip = get_tip_del_giorno(oggi, st.session_state.lang)
    st.markdown(f"<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; border-left:4px solid #16EC06;'><span style='color:#e5e5ea; font-style:italic;'>\"{tip}\"</span></div>", unsafe_allow_html=True)

elif menu == L['stats']:
    pasti_stats = pasti.copy()
    if not pasti_stats.empty:
        if pd.api.types.is_datetime64tz_dtype(pasti_stats['data_ora']): pasti_stats['data_ora'] = pasti_stats['data_ora'].dt.tz_localize(None)
        pasti_stats['data_solo'] = pasti_stats['data_ora'].dt.date
    
    st.markdown("<h5 style='text-align: center; color: #16EC06; letter-spacing: 2px; font-size:13px;'>TREND VIEW</h5>", unsafe_allow_html=True)
    if pasti_stats.empty: st.info(L['low_data'])
    else:
        if "trend_period" not in st.session_state: st.session_state.trend_period = "W"
        if "trend_offset" not in st.session_state: st.session_state.trend_offset = 0
        if "trend_metric" not in st.session_state: st.session_state.trend_metric = "🔥 Calorie"
        
        c_met, c_per = st.columns([1, 1])
        with c_met: metrica = st.selectbox("Seleziona Metrica", ["🔥 Calorie", "⭐ NutriScore", "🥑 Carboidrati", "🥩 Proteine", "🧈 Grassi"], label_visibility="collapsed")
        with c_per: periodo = st.radio("Periodo", ["W", "M", "3M", "6M"], horizontal=True, label_visibility="collapsed")
            
        if periodo != st.session_state.trend_period: st.session_state.trend_period = periodo; st.session_state.trend_offset = 0; st.rerun()
        if metrica != st.session_state.trend_metric: st.session_state.trend_metric = metrica
            
        days_in_p = 7 if periodo == "W" else 28 if periodo == "M" else 90 if periodo == "3M" else 180
        end_date = oggi + timedelta(days=st.session_state.trend_offset * days_in_p)
        start_date = end_date - timedelta(days=days_in_p - 1)
        prior_end = start_date - timedelta(days=1); prior_start = prior_end - timedelta(days=days_in_p - 1)
        
        df_curr = pasti_stats[(pasti_stats['data_solo'] >= start_date) & (pasti_stats['data_solo'] <= end_date)]
        df_prior = pasti_stats[(pasti_stats['data_solo'] >= prior_start) & (pasti_stats['data_solo'] <= prior_end)]
        target_col = {"🔥 Calorie": "calorie", "⭐ NutriScore": "rating", "🥑 Carboidrati": "carboidrati", "🥩 Proteine": "proteine", "🧈 Grassi": "grassi"}[metrica]
        
        def calcola_media(df, col): return 0 if df.empty else (df.groupby('data_solo')[col].sum().mean() if col != "rating" else df.groupby('data_solo')[col].mean().mean())
        avg_curr, avg_prior = calcola_media(df_curr, target_col), calcola_media(df_prior, target_col)
        diff_pct = ((avg_curr - avg_prior) / avg_prior * 100) if avg_prior > 0 else 0
        color_bg, color_fg, arrow = ("#16EC0633", "#16EC06", "▲") if diff_pct >= 0 else ("#e5434333", "#e54343", "▼")
        
        st.markdown(f"<div style='padding: 20px 0;'><div style='font-size:11px; color:#8e8e93; font-weight:700;'>AVERAGE</div><div style='font-size:56px; font-weight:bold; color:#ffffff;'>{avg_curr:,.0f}</div><span style='background-color:{color_bg}; color:{color_fg}; padding:6px 12px; border-radius:8px; font-weight:bold;'>{arrow} {abs(diff_pct):.0f}% vs prior</span></div>", unsafe_allow_html=True)
        
        c_nav_l, c_nav_d, c_nav_r = st.columns([1, 4, 1])
        with c_nav_l:
            if st.button("❮", use_container_width=True): st.session_state.trend_offset -= 1; st.rerun()
        with c_nav_d: st.markdown(f"<div style='text-align:center; padding-top:5px; font-weight:bold; font-size:14px;'>{start_date.strftime('%b %d').upper()} - {end_date.strftime('%b %d, %y').upper()}</div>", unsafe_allow_html=True)
        with c_nav_r:
            if st.button("❯", disabled=(st.session_state.trend_offset >= 0), use_container_width=True): st.session_state.trend_offset += 1; st.rerun()
                
        if not df_curr.empty:
            df_agg = df_curr.copy(); df_agg['data_dt'] = pd.to_datetime(df_agg['data_solo'])
            if periodo == "W":
                df_g = df_agg.groupby('data_dt')[target_col].sum() if target_col != 'rating' else df_agg.groupby('data_dt')[target_col].mean()
                df_group = df_g.reset_index(); df_group['x_axis'] = df_group['data_dt'].dt.strftime('%a %d')
            elif periodo == "M":
                df_agg['week'] = df_agg['data_dt'] - pd.to_timedelta(df_agg['data_dt'].dt.dayofweek, unit='D')
                df_g = df_agg.groupby('week')[target_col].sum() if target_col != 'rating' else df_agg.groupby('week')[target_col].mean()
                df_group = df_g.reset_index(); df_group['x_axis'] = "W. " + df_group['week'].dt.strftime('%d %b'); df_group.rename(columns={'week': 'data_dt'}, inplace=True)
            else:
                df_agg['month'] = df_agg['data_dt'].dt.to_period('M').dt.to_timestamp()
                df_g = df_agg.groupby('month')[target_col].sum() if target_col != 'rating' else df_agg.groupby('month')[target_col].mean()
                df_group = df_g.reset_index(); df_group['x_axis'] = df_group['month'].dt.strftime('%b %y'); df_group.rename(columns={'month': 'data_dt'}, inplace=True)
                
            fig = px.bar(df_group.sort_values('data_dt'), x='x_axis', y=target_col)
            fig.update_traces(marker_color='#16EC06', marker_line_width=0, opacity=0.9)
            fig.update_layout(xaxis_title="", yaxis_title="", xaxis=dict(type='category', showgrid=False, color='#8e8e93'), yaxis=dict(showgrid=True, gridcolor='#2c2c2e', color='#8e8e93'), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=20,b=10,l=0,r=0), height=250)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

elif menu == L['diet']:
    st.markdown(f"<h2>{L['diet']}</h2>", unsafe_allow_html=True)
    if utente.empty: st.warning("Completa il profilo."); st.stop()
    prof = utente.iloc[0]
    st.info(f"📌 Obiettivo: **{prof.get('obiettivo', '')}** (Dieta: **{prof.get('dieta', '')}**). Target: **{target_v:.0f} Kcal**.")
    
    c1, c2 = st.columns(2)
    num_pasti = c1.selectbox("Pasti Giornalieri", ["3 Pasti", "4 Pasti", "5 Pasti"])
    allergie = c2.multiselect("Allergie", ["Nessuna", "Frutta secca", "Lattosio", "Glutine", "Agrumi", "Crostacei"])

    if st.button("✨ Genera Piano con IA", type="primary"):
        with st.spinner("IA..."):
            instr = f"Crea piano {target_v} kcal. REGOLE: {recupera_da_manuali(f'Principi per dieta {prof['dieta']}')}. Profilo: Dieta {prof['dieta']}. Allergie: {','.join(allergie)}. FAI ESATTAMENTE {num_pasti}. RISPONDI IN {lang_str}."
            st.session_state.piano_testo = model.generate_content(instr).text
            res_s = model.generate_content(f"Estrai lista spesa a punti. RISPONDI IN {lang_str}: {st.session_state.piano_testo}")
            items = [re.sub(r'^\* |^- ', '', i).strip() for i in res_s.text.split('\n') if len(i)>2]
            supabase.table("spesa").delete().eq("user_id", id_utente).execute()
            for i in items: supabase.table("spesa").insert({"user_id": id_utente, "item": i, "completato": False, "data_inserimento": oggi.strftime("%Y-%m-%d")}).execute()
            st.success("Piano Generato!")

    if "piano_testo" in st.session_state:
        st.markdown(f"<div style='background-color:#1c1c1e; padding:20px; border-radius:16px;'>{st.session_state.piano_testo}</div>", unsafe_allow_html=True)
        if FPDF_AVAILABLE: st.download_button("📥 PDF", data=genera_pdf_dieta(st.session_state.piano_testo), file_name="Dieta.pdf", mime="application/pdf")

elif menu == L['shop']:
    st.markdown(f"<h2>{L['shop']}</h2>", unsafe_allow_html=True)
    if spesa.empty: st.info("Lista vuota.")
    else:
        st.markdown("<div style='background-color:#1c1c1e; padding:20px; border-radius:16px;'>", unsafe_allow_html=True)
        for _, row in spesa.iterrows():
            c = st.checkbox(row['item'], value=row['completato'], key=f"s_{row['id']}")
            if c != row['completato']: supabase.table("spesa").update({"completato": c}).eq("id", row['id']).execute(); st.rerun()
        st.markdown("</div><br>", unsafe_allow_html=True)
        
        if st.button("Svuota Lista", type="primary"): st.session_state.conferma_svuota = True
        if st.session_state.get('conferma_svuota', False):
            st.warning(f"⚠️ {L['empty_list_warn']}")
            c_yes, c_no = st.columns(2)
            if c_yes.button(L['yes_empty']):
                supabase.table("spesa").delete().eq("user_id", id_utente).execute()
                st.session_state.conferma_svuota = False
                st.rerun()
            if c_no.button(L['cancel']):
                st.session_state.conferma_svuota = False
                st.rerun()

elif menu == L['hist']:
    st.markdown(f"<h2>{L['hist']}</h2>", unsafe_allow_html=True)
    if pasti.empty: st.info(L['low_data'])
    else:
        for _, r in pasti.sort_values('data_ora', ascending=False).iterrows():
            st.markdown("<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; margin-bottom:10px; border-left: 4px solid #16EC06;'>", unsafe_allow_html=True)
            c1, c2 = st.columns([5, 1])
            sc = f" (Score: {r['rating']:.0f})" if 'rating' in r and pd.notna(r['rating']) else ""
            c1.markdown(f"<strong style='color:white;'>{r['data_ora'].strftime('%d/%m/%Y %H:%M')}</strong> - <span style='color:#e5e5ea;'>{r['descrizione']}</span> | <strong style='color:#58a6ff;'>{r['calorie']:.0f} kcal</strong><span style='color:#16EC06;'>{sc}</span>", unsafe_allow_html=True)
            if c2.button("Elimina", key=f"del_{r['id']}"): supabase.table("pasti").delete().eq("id", r['id']).execute(); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

elif menu == L['chat']:
    st.markdown(f"<h2>{L['chat']}</h2>", unsafe_allow_html=True)
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if p := st.chat_input(L['placeholder_chat']):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        res = model.generate_content(f"Sei un nutrizionista AI. RISPONDI IN {lang_str}. Manuali: {recupera_da_manuali(p)}. Domanda: {p}")
        st.session_state.messages.append({"role": "assistant", "content": res.text})
        with st.chat_message("assistant"): st.markdown(res.text)

elif menu == L['prof']:
    st.markdown(f"<h2>{L['prof']} ⚙️</h2>", unsafe_allow_html=True)
    if utente.empty: 
        st.error("Errore: Profilo non trovato. Contatta il supporto.")
        st.stop()
    
    prof = utente.iloc[0]
    t1, t2, t3 = st.tabs(["📝 Dati", "🔒 Password", "🛡️ Privacy"])
    
    with t1:
        with st.form("edit_profile"):
            c1, c2 = st.columns(2); u_n = c1.text_input("Nome", value=prof.get('nome', '')); u_c = c2.text_input("Cognome", value=prof.get('cognome', ''))
            c3, c4, c5 = st.columns(3); u_sex = c3.selectbox("Sesso", ["Uomo", "Donna"], index=0 if prof.get('sesso')=="Uomo" else 1); u_w = c4.number_input("Peso (kg)", value=float(prof.get('peso', 70.0))); u_h = c5.number_input("Altezza (cm)", value=float(prof.get('altezza', 170.0)))
            
            curr_dob = datetime.strptime(prof['data_nascita'], '%Y-%m-%d').date() if prof.get('data_nascita') else datetime(1990,1,1).date()
            u_dob = st.date_input("Data di Nascita", value=curr_dob)
            
            c6, c7 = st.columns(2)
            diete_list = ["Onnivoro", "Vegetariano", "Vegano", "Pescatariano", "Chetogenica"]
            try: u_diet_index = diete_list.index(prof.get('dieta', "Onnivoro"))
            except: u_diet_index = 0
            u_diet = c6.selectbox("Dieta", diete_list, index=u_diet_index)
            
            sport_list = ["Sedentario", "Leggera (1-2 volte/sett)", "Moderata (3-4 volte/sett)", "Intensa (5+ volte/sett)", "Atleta Professionista"]
            try: u_sp_index = sport_list.index(prof.get('sport', "Sedentario"))
            except: u_sp_index = 0
            u_sport = c7.selectbox("Attività Fisica", sport_list, index=u_sp_index)
            
            obj_list = ["Dimagrimento", "Definizione Muscolare", "Mantenimento", "Aumento Massa Muscolare", "Ricomposizione Corporea"]
            try: u_ob_index = obj_list.index(prof.get('obiettivo', "Mantenimento"))
            except: u_ob_index = 2
            u_obj = st.selectbox("Obiettivo", obj_list, index=u_ob_index)
            
            if st.form_submit_button("💾 Salva Modifiche e Ricalcola TDEE", type="primary"):
                nuovo_tdee = calcola_tdee_professionale(u_w, u_h, u_dob, u_sex, u_sport, u_obj)
                try:
                    supabase.table("utenti").update({
                        "nome": u_n, "cognome": u_c, "sesso": u_sex, "peso": u_w, "altezza": u_h, 
                        "data_nascita": str(u_dob), "dieta": u_diet, "sport": u_sport, "obiettivo": u_obj, "tdee": nuovo_tdee
                    }).eq("user_id", str(id_utente)).execute()
                    st.success(f"✅ Profilo aggiornato! Nuovo Target: {nuovo_tdee:.0f} kcal.")
                    st.rerun()
                except Exception as e: st.error(f"Errore nel salvataggio: {e}")

    with t2:
        with st.form("pwd"):
            new_p = st.text_input("Nuova Password", type="password")
            if st.form_submit_button("Aggiorna Password", type="primary"):
                if len(new_p) >= 6:
                    supabase.auth.update_user({"password": new_p}); st.success("Password aggiornata.")
                else: st.warning("Minimo 6 caratteri.")
                
    with t3:
        with st.form("priv"):
            u_mkt = st.checkbox("Acconsento a ricevere comunicazioni di marketing e offerte", value=bool(prof.get('consenso_marketing', False)))
            u_prof = st.checkbox("Acconsento all'analisi dei miei dati per fini statistici e di profilazione", value=bool(prof.get('consenso_profilazione', False)))
            if st.form_submit_button("Salva Privacy", type="primary"):
                supabase.table("utenti").update({"consenso_marketing": u_mkt, "consenso_profilazione": u_prof}).eq("user_id", str(id_utente)).execute()
                st.success("Privacy aggiornata.")