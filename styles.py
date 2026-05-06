def get_login_css():
    return """
    <style>
    .stApp { background-color: #121212; color: #ffffff; font-family: -apple-system, sans-serif; }
    h1, h2, h3 { color: #ffffff !important; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div { background-color: #1c1c1e !important; color: white !important; border-radius: 12px !important; border: 1px solid #2c2c2e !important; }
    .stButton>button { background-color: #16EC06 !important; color: #000000 !important; border-radius: 20px !important; font-weight: bold !important; border: none !important; transition: all 0.2s; }
    .stButton>button:hover { background-color: #12c005 !important; transform: scale(1.02); }
    </style>
    """

def get_main_css():
    return """
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
    """