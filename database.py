import streamlit as st
from supabase import create_client
import pandas as pd

# --- 1.5 CONFIGURAZIONE SUPABASE E LOGIN ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def get_supabase_client():
    try:
        if "INSERISCI" not in SUPABASE_URL:
            return create_client(SUPABASE_URL.strip().rstrip("/"), SUPABASE_KEY.strip())
    except Exception as e:
        st.error(f"Errore connessione Supabase: {e}")
    return None

supabase = get_supabase_client()

def carica_dati_utente(email):
    email_pulita = email.strip()
    
    # Se per qualche motivo l'email è vuota, blocchiamo subito per sicurezza
    if not email_pulita:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 2000.0, 0
        
    try:
        # Grazie alla RLS, Supabase filtrerà già i dati a livello di server
        res_u = supabase.table("utenti").select("*").eq("email", email_pulita).execute()
        utente = pd.DataFrame(res_u.data)
        
        if utente.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 2000.0, 0
            
        u_id = utente['user_id'].values[0]
        target = utente['tdee'].values[0]
        
        # Carichiamo solo i pasti che ci appartengono
        res_p = supabase.table("pasti").select("*").eq("user_id", str(u_id)).execute()
        pasti = pd.DataFrame(res_p.data)
        if not pasti.empty:
            pasti['data_ora'] = pd.to_datetime(pasti['data_ora'])
            
        res_s = supabase.table("spesa").select("*").eq("user_id", str(u_id)).execute()
        spesa = pd.DataFrame(res_s.data)
        
        return pasti, utente, spesa, target, u_id
    except Exception as e:
        st.error(f"Errore di sicurezza o connessione: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), 2000.0, 0