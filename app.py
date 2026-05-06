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

# --- IMPORTIAMO IL NOSTRO MODULO DATABASE ---
from database import supabase, carica_dati_utente

# --- Insegniamo a Python a leggere foto da iPhone e Android ---
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# --- GESTIONE LIBRERIA PDF IN SICUREZZA ---
try:
    from fpdf import FPDF
    import tempfile
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="VN Pro - AI Nutrition", layout="wide", page_icon="🟢")

# --- 1.1 INIZIALIZZAZIONE MEMORIA (IL FIX DELL'ERRORE!) ---
if 'utente_loggato' not in st.session_state: 
    st.session_state.utente_loggato = False
if 'email_utente' not in st.session_state: 
    st.session_state.email_utente = ""
if 'lang' not in st.session_state:
    st.session_state.lang = 'it'

# --- 1.2 SISTEMA MULTILINGUA ---
translations = {
    'it': {
        'nav': "NAVIGAZIONE",
        'dash': "📊 Dashboard",
        'stats': "📈 Statistiche",
        'diet': "📅 Piano Alimentare",
        'shop': "🛒 Lista Spesa",
        'hist': "📜 Storico",
        'chat': "🧠 Chat IA",
        'prof': "⚙️ Profilo",
        'welcome': "Bentornato",
        'summary': "Ecco il tuo riepilogo giornaliero.",
        'target': "TARGET (KCAL)",
        'assunte': "ASSUNTE",
        'residuo': "RESIDUO",
        'nutriscore': "NUTRISCORE",
        'dist_macro': "Distribuzione Macronutrienti",
        'reg_pasto': "Registra Pasto",
        'analizza': "🪄 Analizza Piatto",
        'tip': "Consiglio del giorno",
        'save_cloud': "Salva nel Diario",
        'privacy_msg': "Devi accettare la Privacy Policy.",
        'logout': "Esci",
        'placeholder_chat': "Fai una domanda nutrizionale...",
        'low_data': "Nessun dato sufficiente. Registra i tuoi pasti.",
        'upload_action': "Carica foto",
        'why_score': "Perché questo voto?",
        'estimated_values': "VALORI STIMATI"
    },
    'en': {
        'nav': "NAVIGATION",
        'dash': "📊 Dashboard",
        'stats': "📈 Analytics",
        'diet': "📅 Meal Plan",
        'shop': "🛒 Grocery List",
        'hist': "📜 History",
        'chat': "🧠 AI Coach",
        'prof': "⚙️ Profile",
        'welcome': "Welcome back",
        'summary': "Here is your daily summary.",
        'target': "TARGET (KCAL)",
        'assunte': "CONSUMED",
        'residuo': "REMAINING",
        'nutriscore': "NUTRISCORE",
        'dist_macro': "Macro Distribution",
        'reg_pasto': "Log Meal",
        'analizza': "🪄 Analyze Dish",
        'tip': "Tip of the day",
        'save_cloud': "Save to Cloud",
        'privacy_msg': "You must accept the Privacy Policy.",
        'logout': "Logout",
        'placeholder_chat': "Ask a nutrition question...",
        'low_data': "Not enough data. Start logging your meals.",
        'upload_action': "Upload photo",
        'why_score': "Why this score?",
        'estimated_values': "ESTIMATED VALUES"
    }
}

L = translations[st.session_state.lang]

# --- 2. CONFIGURAZIONE IA E NUOVO RAG (PICKLE COMPRESSO) ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"] # Usa i secrets in modo sicuro!
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

@st.cache_data
def carica_database_rag():
    try:
        cartella_corrente = os.path.dirname(os.path.abspath(__file__))
        percorso_pkl = os.path.join(cartella_corrente, "conoscenza_nutrizionista.pkl.gz")
        if os.path.exists(percorso_pkl):
            return pd.read_pickle(percorso_pkl, compression="gzip")
        return None
    except Exception as e:
        return None

db_rag = carica_database_rag()

def recupera_da_manuali(query_testo, top_k=3):
    if db_rag is None: return ""
    try:
        res = genai.embed_content(model="models/gemini-embedding-001", content=query_testo, task_type="retrieval_query")
        query_vec = np.array(res['embedding'])
        risultati = []
        for item in db_rag:
            doc_vec = np.array(item["vettore"])
            sim = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
            risultati.append((sim, item["testo"], item["fonte"]))
        risultati.sort(key=lambda x: x[0], reverse=True)
        testi_top = [f"(Fonte: {r[2]})\n{r[1]}" for r in risultati[:top_k]]
        return "\n\n---\n\n".join(testi_top)
    except Exception as e: return ""

# --- 3. FUNZIONI UTILI ---
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
        with open(tmp.name, "rb") as f: pdf_bytes = f.read()
    return pdf_bytes

@st.cache_data(ttl=86400) 
def get_tip_del_giorno(data_odierna, lang):
    if db_rag is None or len(db_rag) == 0:
        return "Bevi almeno 2 litri d'acqua al giorno e cerca di variare il più possibile le fonti proteiche durante la settimana." if lang == 'it' else "Drink at least 2 liters of water a day and try to vary your protein sources."
    
    random.seed(data_odierna.toordinal())
    frammento = random.choice(db_rag)["testo"]
    lang_name = "ITALIANO" if lang == 'it' else "ENGLISH"
    
    prompt = f"Sei un nutrizionista. Estrai un singolo 'Consiglio del giorno' (massimo 2 righe, tono motivazionale e pratico) basandoti solo su questo estratto di manuale: {frammento}. Non usare asterischi o introduzioni. RISPONDI RIGOROSAMENTE IN {lang_name}."
    try:
        res = model.generate_content(prompt)
        return res.text.strip().replace('**', '')
    except:
        return "Dai priorità ai carboidrati complessi e ricchi di fibre per avere energia costante durante tutta la giornata." if lang == 'it' else "Prioritize complex carbohydrates rich in fiber for constant energy throughout the day."

# --- IL CANCELLO: AUTENTICAZIONE E REGISTRAZIONE ---
if not st.session_state.utente_loggato:
    login_placeholder = st.empty()
    
    with login_placeholder.container():
        st.markdown("""
        <style>
        .stApp { background-color: #121212; color: #ffffff; font-family: -apple-system, sans-serif; }
        h1, h2, h3 { color: #ffffff !important; }
        .stTextInput>div>div>input, .stSelectbox>div>div>div { background-color: #1c1c1e !important; color: white !important; border-radius: 12px !important; border: 1px solid #2c2c2e !important; }
        .stButton>button { background-color: #16EC06 !important; color: #000000 !important; border-radius: 20px !important; font-weight: bold !important; border: none !important; transition: all 0.2s; }
        .stButton>button:hover { background-color: #12c005 !important; transform: scale(1.02); }
        </style>
        """, unsafe_allow_html=True)
        
        try:
            st.image("logo_vn.png", width=100)
        except:
            st.markdown("<h1 style='color:#16EC06;'>VN PRO</h1>", unsafe_allow_html=True)
            
        st.title("Virtual Nutritionist Pro")
        st.write("Accedi o crea un nuovo account sul Cloud.")
        
        tab_login, tab_registrazione = st.tabs(["🔑 Accedi", "📝 Crea Profilo Completo"])
        
        with tab_login:
            with st.form("login_form"):
                email_input = st.text_input("Email").strip()
                password_input = st.text_input("Password", type="password").strip()
                if st.form_submit_button("Accedi"):
                    if supabase is None: st.error("⚠️ Errore connessione Supabase.")
                    else:
                        try:
                            auth_response = supabase.auth.sign_in_with_password({"email": email_input, "password": password_input})
                            if auth_response.user:
                                st.session_state.utente_loggato = True
                                st.session_state.email_utente = auth_response.user.email
                                login_placeholder.empty()
                                st.rerun() 
                        except Exception as e: st.error("❌ Credenziali non valide.")
        
        with tab_registrazione:
            st.subheader("Raccontaci di te")
            with st.form("register_form"):
                c1, c2 = st.columns(2)
                reg_nome = c1.text_input("Nome*").strip()
                reg_cognome = c2.text_input("Cognome*").strip()
                c3, c4 = st.columns(2)
                reg_dob = c3.date_input("Data di Nascita*", min_value=datetime(1920, 1, 1), max_value=datetime.now())
                reg_sesso = c4.selectbox("Sesso*", ["Uomo", "Donna"])
                c4_1, c4_2 = st.columns(2)
                reg_peso = c4_1.number_input("Peso (kg)*", min_value=30.0, max_value=250.0, value=70.0, step=0.1)
                reg_altezza = c4_2.number_input("Altezza (cm)*", min_value=100.0, max_value=250.0, value=170.0, step=1.0)
                st.divider()
                c5, c6 = st.columns(2)
                reg_dieta = c5.selectbox("Preferenza Culinaria*", ["Onnivoro", "Carnivoro", "Vegetariano", "Vegano", "Pescatariano"])
                reg_sport = c6.selectbox("Attività Fisica*", ["Sedentario", "Leggera (1-2 volte/sett)", "Moderata (3-4 volte/sett)", "Intensa (5+ volte/sett)", "Atleta Professionista"])
                reg_obiettivo = st.selectbox("Obiettivo Principale*", ["Dimagrimento", "Definizione Muscolare", "Mantenimento", "Aumento Massa Muscolare", "Ricomposizione Corporea"])
                st.divider()
                reg_email = st.text_input("Email*").strip()
                c7, c8 = st.columns(2)
                reg_password = c7.text_input("Scegli una Password*", type="password").strip()
                reg_password_confirm = c8.text_input("Conferma Password*", type="password").strip()
                
                st.markdown("<span style='font-size: 12px; color: #8e8e93; font-weight:bold; letter-spacing:1px;'>CONSENSI LEGALI (GDPR)</span>", unsafe_allow_html=True)
                cons_privacy = st.checkbox("Accetto la Privacy Policy e i Termini di Servizio (Obbligatorio)*")
                cons_mkt = st.checkbox("Acconsento a ricevere comunicazioni di marketing e offerte (Facoltativo)")
                cons_prof = st.checkbox("Acconsento all'analisi dei miei dati per fini statistici e di profilazione (Facoltativo)")
                
                if st.form_submit_button("Crea Account e Salva Profilo"):
                    if not cons_privacy:
                        st.warning("⚠️ Devi accettare la Privacy Policy per poterti registrare.")
                    elif reg_password != reg_password_confirm: 
                        st.warning("⚠️ Le password non coincidono.")
                    elif len(reg_password) < 6: 
                        st.warning("⚠️ Password troppo corta.")
                    else:
                        try:
                            res = supabase.auth.sign_up({"email": reg_email, "password": reg_password})
                            oggi_data = datetime.now().date()
                            eta = oggi_data.year - reg_dob.year - ((oggi_data.month, oggi_data.day) < (reg_dob.month, reg_dob.day))
                            bmr = (10 * reg_peso) + (6.25 * reg_altezza) - (5 * eta) + (5 if reg_sesso=="Uomo" else -161)
                            moltiplicatori = {"Sedentario": 1.2, "Leggera (1-2 volte/sett)": 1.375, "Moderata (3-4 volte/sett)": 1.55, "Intensa (5+ volte/sett)": 1.725, "Atleta Professionista": 1.9}
                            tdee_calcolato = bmr * moltiplicatori.get(reg_sport, 1.2)
                            if "Dimagrimento" in reg_obiettivo or "Definizione" in reg_obiettivo: tdee_calcolato -= 400 
                            elif "Aumento Massa" in reg_obiettivo: tdee_calcolato += 300 
                            
                            nuovo_id = random.randint(10000000, 99999999) 
                            supabase.table("utenti").insert({
                                "user_id": nuovo_id, "nome": reg_nome, "cognome": reg_cognome, "email": reg_email, 
                                "sesso": reg_sesso, "data_nascita": str(reg_dob), "dieta": reg_dieta, 
                                "sport": reg_sport, "obiettivo": reg_obiettivo, "peso": reg_peso, 
                                "altezza": reg_altezza, "tdee": tdee_calcolato,
                                "consenso_privacy": cons_privacy,
                                "consenso_marketing": cons_mkt,
                                "consenso_profilazione": cons_prof
                            }).execute()
                            st.success(f"✅ Profilo creato! Fabbisogno calcolato: {tdee_calcolato:.0f} kcal. Vai su 'Accedi'.")
                        except Exception as e: st.error(f"Errore registrazione: {e}")
    st.stop() 

# --- SEZIONE UTENTE LOGGATO ---
pasti, utente, spesa, target_v, id_utente = carica_dati_utente(st.session_state.email_utente)

st.markdown("""
    <style>
    .stApp { background-color: #000000; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    [data-testid="stSidebar"] { background-color: #0a0a0a; border-right: 1px solid #16EC0633; }
    header { background: transparent !important; }
    footer { display: none !important; }
    h1, h2, h3 { color: #ffffff !important; font-weight: 600 !important; letter-spacing: 0.5px; }
    p, .stMarkdown { color: #e5e5ea; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div { background-color: #1c1c1e !important; color: white !important; border-radius: 12px !important; border: 1px solid #2c2c2e !important; }
    .stButton>button { background-color: #1c1c1e !important; color: #ffffff !important; border-radius: 30px !important; border: 1px solid #16EC06 !important; padding: 6px 20px !important; font-weight: 600 !important; transition: all 0.2s; }
    .stButton>button:hover { background-color: #16EC06 !important; color: #000000 !important; transform: scale(1.02); box-shadow: 0 0 15px #16EC06; }
    [data-testid="baseButton-primary"] { background-color: #16EC06 !important; color: #000000 !important; }
    [data-testid="baseButton-primary"]:hover { background-color: #12c005 !important; }
    
    .metric-card { background-color: #121212; border: 1px solid #16EC0633; border-radius: 20px; padding: 25px 15px; text-align: center; margin-bottom: 10px; transition: 0.3s; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .metric-card:hover { border-color: #16EC06; box-shadow: 0 0 15px #16EC0633; }
    .metric-value { font-size: 36px; font-weight: 800; color: #ffffff; margin-top: 5px; display: block; line-height: 1; }
    .metric-label { font-size: 10px; color: #16EC06; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; }
    
    [data-testid="stForm"] { background-color: #121212; border: 1px solid #2c2c2e; border-radius: 16px; }
    .stTabs [data-baseweb="tab-list"] { background-color: transparent; }
    .stTabs [data-baseweb="tab"] { color: #8e8e93; }
    .stTabs [aria-selected="true"] { color: #16EC06 !important; background-color: transparent !important; border-bottom-color: #16EC06 !important; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    try:
        st.image("logo_vn.png", width=120)
    except:
        st.markdown("<h2 style='color:#16EC06; font-weight:900;'>VN PRO</h2>", unsafe_allow_html=True)
    st.markdown("</div><br>", unsafe_allow_html=True)

    st.markdown(f"<div style='color:#8e8e93; font-size:12px; font-weight:bold; margin-bottom:5px;'>USER</div><div style='color:white; font-size:14px; margin-bottom:15px;'>{st.session_state.email_utente}</div>", unsafe_allow_html=True)
    
    opzioni_lingua = ["Italiano", "English"]
    indice_corrente = 0 if st.session_state.lang == 'it' else 1
    lingua_selezionata = st.selectbox("🌍 LINGUA / LANGUAGE", opzioni_lingua, index=indice_corrente)
    
    if st.button("Conferma / Confirm", use_container_width=True):
        st.session_state.lang = 'it' if lingua_selezionata == "Italiano" else 'en'
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

oggi = datetime.now().date()
lang_str = "ITALIANO" if st.session_state.lang == 'it' else "ENGLISH"

def pulisci_valore(testo):
    if not testo: return 0.0
    solo_numeri = re.sub(r'[^0-9.]', '', str(testo).replace(',', '.'))
    try: return float(solo_numeri)
    except: return 0.0

if menu == L['dash']:
    if utente.empty:
        st.markdown("<h2>Dashboard Personale</h2>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h2>{L['welcome']}, {utente['nome'].values[0]}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:#8e8e93; margin-top:-10px; margin-bottom:20px;'>{L['summary']}</p>", unsafe_allow_html=True)
    
    df_p_v = pd.DataFrame()
    if not pasti.empty:
        p_temp = pasti.copy()
        if pd.api.types.is_datetime64tz_dtype(p_temp['data_ora']):
            p_temp['data_ora'] = p_temp['data_ora'].dt.tz_localize(None)
        df_p_v = p_temp[p_temp['data_ora'].dt.date == oggi]

    assunte = df_p_v['calorie'].sum() if not df_p_v.empty else 0
    residuo = target_v - assunte
    rating_medio = df_p_v['rating'].mean() if not df_p_v.empty and 'rating' in df_p_v.columns else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='metric-card'><span class='metric-label'>🎯 {L['target']}</span><span class='metric-value'>{target_v:.0f}</span></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='metric-card'><span class='metric-label'>🍎 {L['assunte']}</span><span class='metric-value'>{assunte:.0f}</span></div>", unsafe_allow_html=True)
    
    res_col = "#16EC06" if residuo >= 0 else "#e54343"
    k3.markdown(f"<div class='metric-card' style='border-top: 3px solid {res_col};'><span class='metric-label'>🔋 {L['residuo']}</span><span class='metric-value' style='color:{res_col}'>{residuo:.0f}</span></div>", unsafe_allow_html=True)
    
    rat_col = "#16EC06" if rating_medio >= 75 else "#e5a443" if rating_medio >= 50 else "#e54343"
    rat_val = f"{rating_medio:.0f}" if rating_medio > 0 else "--"
    k4.markdown(f"<div class='metric-card'><span class='metric-label'>⭐ {L['nutriscore']}</span><span class='metric-value' style='color:{rat_col}'>{rat_val}</span></div>", unsafe_allow_html=True)

    st.write("")
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown(f"<h4 style='font-size: 16px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>{L['dist_macro']}</h4>", unsafe_allow_html=True)
        if not df_p_v.empty:
            c_carbo = df_p_v['carboidrati'].sum() if 'carboidrati' in df_p_v.columns else 0
            c_prot = df_p_v['proteine'].sum() if 'proteine' in df_p_v.columns else 0
            c_fat = df_p_v['grassi'].sum() if 'grassi' in df_p_v.columns else 0
            fig_p = go.Figure(data=[go.Pie(labels=['Carbo', 'Prot', 'Fat'], values=[c_carbo, c_prot, c_fat], hole=.6, marker=dict(colors=['#58a6ff', '#e54343', '#16EC06']))])
            fig_p.update_layout(paper_bgcolor='rgba(0,0,0,0)', font_color="#e5e5ea", height=280, margin=dict(t=10,b=0,l=0,r=0), showlegend=True)
            st.plotly_chart(fig_p, use_container_width=True)
        else:
            st.info(L['low_data'])

    with col_right:
        st.markdown(f"<h4 style='font-size: 16px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>{L['reg_pasto']}</h4>", unsafe_allow_html=True)
        up_file = st.file_uploader(L['upload_action'], type=['jpg', 'jpeg', 'png', 'heic', 'avif'], key=f"up_{st.session_state.uploader_key}", label_visibility="collapsed")
        
        if up_file:
            try:
                img = Image.open(up_file)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                    
                st.image(img, use_container_width=True)
                
                if st.button(L['analizza'], use_container_width=True):
                    with st.spinner("Elaborazione IA in corso..."):
                        prompt = f"""Analizza la foto del piatto. Restituisci ESATTAMENTE e SOLO una riga con questo formato preciso. Traduci la Descrizione e la Spiegazione rigorosamente in {lang_str}:
                        DATA_BLOCK|Nome Piatto|Kcal|Carbo|Prot|Fat|FatSaturi|Score|Descrizione_max_2_righe|Spiegazione_Score_max_2_righe
                        
                        Esempio:
                        DATA_BLOCK|Avocado Toast|350|30|12|20|4|85|Un delizioso toast con avocado fresco e uovo, ricco di grassi sani.|Punteggio alto grazie all'ottimo bilanciamento di grassi monoinsaturi e proteine."""
                        
                        res = model.generate_content([prompt, img])
                        st.session_state.dati_tecnici = res.text.strip().replace('\n', '')
                        st.session_state.mostra_form = True
                        st.rerun()
                        
            except Exception as e:
                st.error("⚠️ Formato immagine non supportato o file corrotto.")

        if st.session_state.mostra_form:
            m = re.search(r"DATA_BLOCK\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*?)\|(.*)", st.session_state.dati_tecnici)
            
            if m:
                n_i, k_i, c_i, p_i, f_i, sat_i, r_i, desc_i, spiegazione_i = m.groups()
                
                st.markdown(f"<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; margin-bottom:15px; border:1px solid #16EC06;'>", unsafe_allow_html=True)
                st.markdown(f"<h3 style='margin-top:0; color:#16EC06 !important;'>{n_i}</h3>", unsafe_allow_html=True)
                st.write(f"<span style='color:#8e8e93;'>{desc_i}</span>", unsafe_allow_html=True)
                
                st.markdown(f"<br><span style='font-size:11px; color:#8e8e93; font-weight:bold; letter-spacing:1px;'>{L['estimated_values']}</span>", unsafe_allow_html=True)
                st.markdown(f"""
                * **🔥 {k_i}** kcal
                * **🥑 {c_i}g** Carbo | **🥩 {p_i}g** Prot
                * **🧈 {f_i}g** Grassi *(Saturi: {sat_i}g)*
                """)
                
                st.markdown(f"<div style='background-color:#121212; padding:10px; border-radius:8px; margin-top:10px;'><strong style='color:#16EC06;'>Score: {r_i}/100</strong><br><span style='font-size:13px; color:#e5e5ea;'><i>{spiegazione_i}</i></span></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                
                with st.form("save"):
                    u_n = st.text_input("Nome piatto / Dish name", value=n_i)
                    u_c = st.selectbox("Pasto / Meal", ["Colazione", "Pranzo", "Cena", "Spuntino"])
                    
                    if st.form_submit_button(L['save_cloud'], type="primary"):
                        dettagli_extra = f"Grassi saturi: {sat_i}g. Note IA: {spiegazione_i}"
                        supabase.table("pasti").insert({
                            "user_id": int(id_utente), "descrizione": f"{u_n} ({u_c})", "calorie": pulisci_valore(k_i),
                            "carboidrati": pulisci_valore(c_i), "proteine": pulisci_valore(p_i), "grassi": pulisci_valore(f_i),
                            "rating": pulisci_valore(r_i), "dettaglio_json": dettagli_extra
                        }).execute()
                        st.session_state.mostra_form = False
                        st.session_state.uploader_key += 1
                        st.rerun()
            else:
                st.error("Errore nella lettura dell'IA. Riprova.")

    st.markdown("<br><hr style='border-color: #2c2c2e;'>", unsafe_allow_html=True)
    st.markdown(f"<h4 style='font-size: 14px; color: #16EC06; letter-spacing: 1px; text-transform: uppercase;'>💡 {L['tip']}</h4>", unsafe_allow_html=True)
    tip_oggi = get_tip_del_giorno(oggi, st.session_state.lang)
    st.markdown(f"<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; border-left:4px solid #16EC06;'><span style='color:#e5e5ea; font-style:italic;'>\"{tip_oggi}\"</span></div>", unsafe_allow_html=True)


elif menu == L['stats']:
    pasti_stats = pasti.copy()
    if not pasti_stats.empty:
        if pd.api.types.is_datetime64tz_dtype(pasti_stats['data_ora']):
            pasti_stats['data_ora'] = pasti_stats['data_ora'].dt.tz_localize(None)
        pasti_stats['data_solo'] = pasti_stats['data_ora'].dt.date
    
    st.markdown("<h5 style='text-align: center; color: #16EC06; letter-spacing: 2px; font-size:13px;'>TREND VIEW</h5>", unsafe_allow_html=True)
    
    if pasti_stats.empty:
        st.info(L['low_data'])
    else:
        if "trend_period" not in st.session_state: st.session_state.trend_period = "W"
        if "trend_offset" not in st.session_state: st.session_state.trend_offset = 0
        if "trend_metric" not in st.session_state: st.session_state.trend_metric = "🔥 Calorie"
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        c_met, c_per = st.columns([1, 1])
        with c_met:
            metrica = st.selectbox("Seleziona Metrica", ["🔥 Calorie", "⭐ NutriScore", "🥑 Carboidrati", "🥩 Proteine", "🧈 Grassi"], label_visibility="collapsed")
        with c_per:
            periodo = st.radio("Periodo", ["W", "M", "3M", "6M"], horizontal=True, label_visibility="collapsed")
            
        if periodo != st.session_state.trend_period:
            st.session_state.trend_period = periodo
            st.session_state.trend_offset = 0
            st.rerun()
        if metrica != st.session_state.trend_metric:
            st.session_state.trend_metric = metrica
            
        oggi_dt = datetime.now().date()
        if periodo == "W": days_in_period = 7
        elif periodo == "M": days_in_period = 28
        elif periodo == "3M": days_in_period = 90
        else: days_in_period = 180
        
        end_date = oggi_dt + timedelta(days=st.session_state.trend_offset * days_in_period)
        start_date = end_date - timedelta(days=days_in_period - 1)
        
        prior_end = start_date - timedelta(days=1)
        prior_start = prior_end - timedelta(days=days_in_period - 1)
        
        mask_current = (pasti_stats['data_solo'] >= start_date) & (pasti_stats['data_solo'] <= end_date)
        mask_prior = (pasti_stats['data_solo'] >= prior_start) & (pasti_stats['data_solo'] <= prior_end)
        
        df_curr = pasti_stats[mask_current]
        df_prior = pasti_stats[mask_prior]
        
        col_map = {"🔥 Calorie": "calorie", "⭐ NutriScore": "rating", "🥑 Carboidrati": "carboidrati", "🥩 Proteine": "proteine", "🧈 Grassi": "grassi"}
        target_col = col_map[metrica]
        
        def calcola_media(df, col):
            if df.empty: return 0
            df_g = df.groupby('data_solo')[col].sum() if col != "rating" else df.groupby('data_solo')[col].mean()
            return df_g.mean()
            
        avg_curr = calcola_media(df_curr, target_col)
        avg_prior = calcola_media(df_prior, target_col)
        
        diff_pct = 0
        if avg_prior > 0:
            diff_pct = ((avg_curr - avg_prior) / avg_prior) * 100
            
        color_hex_bg = "#16EC0633" if diff_pct >= 0 else "#e5434333"
        color_hex_fg = "#16EC06" if diff_pct >= 0 else "#e54343"
        arrow = "▲" if diff_pct >= 0 else "▼"
        
        st.markdown(f"""
        <div style="padding: 20px 0;">
            <div style="font-size: 11px; color: #8e8e93; font-weight: 700; letter-spacing: 1px; margin-bottom: 2px;">AVERAGE</div>
            <div style="font-size: 56px; font-weight: bold; color: #ffffff; line-height: 1; margin: 0 0 12px 0;">{avg_curr:,.0f}</div>
            <span style="background-color: {color_hex_bg}; color: {color_hex_fg}; padding: 6px 12px; border-radius: 8px; font-size: 13px; font-weight: bold;">{arrow} {abs(diff_pct):.0f}% vs. prior period</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("")
        c_nav_l, c_nav_d, c_nav_r = st.columns([1, 4, 1])
        with c_nav_l:
            if st.button("❮", use_container_width=True): 
                st.session_state.trend_offset -= 1
                st.rerun()
        with c_nav_d:
            st.markdown(f"<div style='text-align: center; padding-top: 5px; font-weight: bold; font-size: 14px; color: #ffffff; letter-spacing:1px;'>{start_date.strftime('%b %d').upper()} - {end_date.strftime('%b %d, %y').upper()}</div>", unsafe_allow_html=True)
        with c_nav_r:
            if st.button("❯", disabled=(st.session_state.trend_offset >= 0), use_container_width=True):
                st.session_state.trend_offset += 1
                st.rerun()
                
        if not df_curr.empty:
            df_curr_agg = df_curr.copy()
            df_curr_agg['data_dt'] = pd.to_datetime(df_curr_agg['data_solo'])
            
            if periodo == "W":
                df_g = df_curr_agg.groupby('data_dt')[target_col].sum() if target_col != 'rating' else df_curr_agg.groupby('data_dt')[target_col].mean()
                df_group = df_g.reset_index()
                df_group['x_axis'] = df_group['data_dt'].dt.strftime('%a %d')
            elif periodo == "M":
                df_curr_agg['week'] = df_curr_agg['data_dt'] - pd.to_timedelta(df_curr_agg['data_dt'].dt.dayofweek, unit='D')
                df_g = df_curr_agg.groupby('week')[target_col].sum() if target_col != 'rating' else df_curr_agg.groupby('week')[target_col].mean()
                df_group = df_g.reset_index()
                df_group['x_axis'] = "W. " + df_group['week'].dt.strftime('%d %b')
                df_group = df_group.rename(columns={'week': 'data_dt'})
            else:
                df_curr_agg['month'] = df_curr_agg['data_dt'].dt.to_period('M').dt.to_timestamp()
                df_g = df_curr_agg.groupby('month')[target_col].sum() if target_col != 'rating' else df_curr_agg.groupby('month')[target_col].mean()
                df_group = df_g.reset_index()
                df_group['x_axis'] = df_group['month'].dt.strftime('%b %y')
                df_group = df_group.rename(columns={'month': 'data_dt'})
                
            df_group = df_group.sort_values('data_dt')
            
            fig = px.bar(df_group, x='x_axis', y=target_col)
            fig.update_traces(marker_color='#16EC06', marker_line_width=0, opacity=0.9)
            fig.update_layout(
                xaxis_title="", yaxis_title="",
                xaxis=dict(type='category', showgrid=False, color='#8e8e93'),
                yaxis=dict(showgrid=True, gridcolor='#2c2c2e', color='#8e8e93'),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(t=20,b=10,l=0,r=0), height=250, dragmode=False
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

elif menu == L['diet']:
    st.markdown(f"<h2>{L['diet']}</h2>", unsafe_allow_html=True)
    if utente.empty:
        st.warning("Completa il profilo per usare questa funzione.")
        st.stop()
        
    profilo = utente.iloc[0]
    st.info(f"📌 Obiettivo: **{profilo.get('obiettivo', '')}** (Dieta: **{profilo.get('dieta', '')}**). Target: **{target_v:.0f} Kcal**.")
    
    with st.container():
        c1, c2 = st.columns(2)
        num_pasti = c1.selectbox("Pasti Giornalieri", ["3 Pasti", "4 Pasti", "5 Pasti"])
        allergie = c2.multiselect("Allergie/Esclusioni", ["Nessuna", "Frutta secca", "Lattosio", "Glutine", "Agrumi", "Crostacei"])

    if st.button("✨ Genera Piano con IA", type="primary"):
        with st.spinner("Generazione in corso..."):
            query_rag = f"Principi nutrizionali per una dieta {profilo['dieta']} con l'obiettivo di {profilo['obiettivo']}."
            conoscenza_rag = recupera_da_manuali(query_rag)
            
            instr = f"""Crea un piano alimentare da {target_v} kcal in base ai dati dell'utente.
            REGOLE ESTRATTE DAI MANUALI:
            {conoscenza_rag}
            
            Profilo: Dieta {profilo['dieta']}. Obiettivo: {profilo['obiettivo']}. Allergie: {', '.join(allergie)}.
            
            ⚠️ ATTENZIONE: DEVI generare rigorosamente {num_pasti} al giorno. Usa la struttura puntata standard e RISPONDI RIGOROSAMENTE IN {lang_str}.
            """
            
            res = model.generate_content(instr)
            st.session_state.piano_testo = res.text
            
            res_s = model.generate_content(f"Estrai solo una lista della spesa a punti da questo testo. Rimuovi asterischi e introduzioni. RISPONDI RIGOROSAMENTE IN {lang_str}: {res.text}")
            items = [re.sub(r'^\* |^- ', '', i).strip() for i in res_s.text.split('\n') if len(i)>2]
            
            oggi_str = datetime.now().strftime("%Y-%m-%d") 
            supabase.table("spesa").delete().eq("user_id", int(id_utente)).execute()
            for i in items:
                supabase.table("spesa").insert({"user_id": int(id_utente), "item": i, "completato": False, "data_inserimento": oggi_str}).execute()
            st.success("Piano Generato e Salvato!")

    if "piano_testo" in st.session_state:
        st.markdown(f"<div style='background-color:#1c1c1e; padding:20px; border-radius:16px;'>{st.session_state.piano_testo}</div>", unsafe_allow_html=True)
        if FPDF_AVAILABLE:
            pdf_bytes = genera_pdf_dieta(st.session_state.piano_testo)
            st.download_button("📥 Scarica in PDF", data=pdf_bytes, file_name=f"Dieta_{profilo['nome']}.pdf", mime="application/pdf")

elif menu == L['shop']:
    st.markdown(f"<h2>{L['shop']}</h2>", unsafe_allow_html=True)
    if spesa.empty:
        st.info("La tua lista della spesa è vuota.")
    else:
        st.markdown("<div style='background-color:#1c1c1e; padding:20px; border-radius:16px;'>", unsafe_allow_html=True)
        for _, row in spesa.iterrows():
            c = st.checkbox(row['item'], value=row['completato'], key=f"s_{row['id']}")
            if c != row['completato']:
                supabase.table("spesa").update({"completato": c}).eq("id", row['id']).execute()
                st.rerun()
        st.markdown("</div><br>", unsafe_allow_html=True)
        if st.button("Svuota Lista", type="primary"):
            supabase.table("spesa").delete().eq("user_id", int(id_utente)).execute()
            st.rerun()

elif menu == L['hist']:
    st.markdown(f"<h2>{L['hist']}</h2>", unsafe_allow_html=True)
    if pasti.empty:
        st.info(L['low_data'])
    else:
        p_ord = pasti.sort_values('data_ora', ascending=False)
        for _, r in p_ord.iterrows():
            st.markdown("<div style='background-color:#1c1c1e; padding:15px; border-radius:12px; margin-bottom:10px; border-left: 4px solid #16EC06;'>", unsafe_allow_html=True)
            c1, c2 = st.columns([5, 1])
            score_txt = f" (Score: {r['rating']:.0f})" if 'rating' in r and pd.notna(r['rating']) else ""
            c1.markdown(f"<strong style='color:white;'>{r['data_ora'].strftime('%d/%m/%Y %H:%M')}</strong> - <span style='color:#e5e5ea;'>{r['descrizione']}</span> | <strong style='color:#58a6ff;'>{r['calorie']:.0f} kcal</strong><span style='color:#16EC06;'>{score_txt}</span>", unsafe_allow_html=True)
            if c2.button("Elimina", key=f"del_{r['id']}"):
                supabase.table("pasti").delete().eq("id", r['id']).execute()
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

elif menu == L['chat']:
    st.markdown(f"<h2>{L['chat']}</h2>", unsafe_allow_html=True)
    if "messages" not in st.session_state: st.session_state.messages = []
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
        
    if p := st.chat_input(L['placeholder_chat']):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        conoscenza = recupera_da_manuali(p)
        prompt_rag = f"""Sei un nutrizionista AI. RISPONDI RIGOROSAMENTE IN {lang_str}. Usa in via prioritaria queste nozioni:
        ---
        {conoscenza}
        ---
        Domanda: {p}"""
        res = model.generate_content(prompt_rag)
        st.session_state.messages.append({"role": "assistant", "content": res.text})
        with st.chat_message("assistant"): st.markdown(res.text)

elif menu == L['prof']:
    st.markdown(f"<h2>{L['prof']}</h2>", unsafe_allow_html=True)
    
    is_utente_limbo = utente.empty
    profilo = {} if is_utente_limbo else utente.iloc[0]
    
    tab_dati, tab_sicurezza, tab_privacy = st.tabs(["📝 Dati", "🔒 Password", "🛡️ Privacy"])
    
    with tab_dati:
        with st.form("update_profile"):
            c1, c2 = st.columns(2)
            up_nome = c1.text_input("Nome", value=profilo.get('nome', ''))
            up_cognome = c2.text_input("Cognome", value=profilo.get('cognome', ''))
            c3, c4, c5 = st.columns(3)
            up_sesso = c3.selectbox("Sesso", ["Uomo", "Donna"], index=0 if profilo.get('sesso')=="Uomo" else 1)
            up_peso = c4.number_input("Peso (kg)", value=float(profilo.get('peso', 70.0)))
            up_altezza = c5.number_input("Altezza (cm)", value=float(profilo.get('altezza', 170.0)))
            c6, c7 = st.columns(2)
            diete = ["Onnivoro", "Carnivoro", "Vegetariano", "Vegano", "Pescatariano"]
            up_dieta = c6.selectbox("Dieta", diete, index=diete.index(profilo.get('dieta')) if profilo.get('dieta') in diete else 0)
            sport = ["Sedentario", "Leggera (1-2 volte/sett)", "Moderata (3-4 volte/sett)", "Intensa (5+ volte/sett)", "Atleta Professionista"]
            up_sport = c7.selectbox("Sport", sport, index=sport.index(profilo.get('sport')) if profilo.get('sport') in sport else 0)
            ob = ["Dimagrimento", "Mantenimento", "Aumento Massa Muscolare", "Definizione Muscolare", "Ricomposizione Corporea"]
            up_obiettivo = st.selectbox("Obiettivo", ob, index=ob.index(profilo.get('obiettivo')) if profilo.get('obiettivo') in ob else 0)
            
            if st.form_submit_button("Salva Modifiche e Ricalcola TDEE", type="primary"):
                eta = 30 
                bmr = (10 * up_peso) + (6.25 * up_altezza) - (5 * eta) + (5 if up_sesso=="Uomo" else -161)
                molts = {"Sedentario": 1.2, "Leggera (1-2 volte/sett)": 1.375, "Moderata (3-4 volte/sett)": 1.55, "Intensa (5+ volte/sett)": 1.725, "Atleta Professionista": 1.9}
                ntdee = bmr * molts.get(up_sport, 1.2)
                if "Dimagrimento" in up_obiettivo: ntdee -= 400
                elif "Aumento" in up_obiettivo: ntdee += 300
                
                if is_utente_limbo:
                    supabase.table("utenti").insert({
                        "user_id": random.randint(10000000, 99999999), "email": st.session_state.email_utente,
                        "nome": up_nome, "cognome": up_cognome, "sesso": up_sesso, "peso": up_peso, "altezza": up_altezza, 
                        "dieta": up_dieta, "sport": up_sport, "obiettivo": up_obiettivo, "tdee": ntdee
                    }).execute()
                    st.success("✅ Profilo salvato!")
                else:
                    supabase.table("utenti").update({
                        "nome": up_nome, "cognome": up_cognome, "sesso": up_sesso, "peso": up_peso, "altezza": up_altezza, 
                        "dieta": up_dieta, "sport": up_sport, "obiettivo": up_obiettivo, "tdee": ntdee
                    }).eq("user_id", int(id_utente)).execute()
                    st.success("✅ Profilo aggiornato!")
                    
    with tab_sicurezza:
        with st.form("pwd"):
            n_pwd = st.text_input("Nuova Password", type="password")
            if st.form_submit_button("Aggiorna Password", type="primary"): 
                supabase.auth.update_user({'password': n_pwd})
                st.success("Password modificata.")
                
    with tab_privacy:
        with st.form("privacy_form"):
            st.markdown("<p style='color:#e5e5ea; margin-bottom:20px;'>Gestisci i tuoi consensi sulla privacy. Puoi modificarli in qualsiasi momento.</p>", unsafe_allow_html=True)
            up_mkt = st.checkbox("Acconsento a ricevere comunicazioni di marketing e offerte", value=bool(profilo.get('consenso_marketing', False)))
            up_prof = st.checkbox("Acconsento all'analisi dei miei dati per fini statistici e di profilazione", value=bool(profilo.get('consenso_profilazione', False)))
            
            if st.form_submit_button("Aggiorna Consensi GDPR", type="primary"):
                if not is_utente_limbo:
                    supabase.table("utenti").update({
                        "consenso_marketing": up_mkt,
                        "consenso_profilazione": up_prof
                    }).eq("user_id", int(id_utente)).execute()
                    st.success("✅ Preferenze privacy aggiornate!")