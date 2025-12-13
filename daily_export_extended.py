import os
import sys
import datetime
from datetime import timedelta
from pathlib import Path
from garminconnect import Garmin

# --- 1. KONFIGURASJON ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

if not GARMIN_EMAIL:
    current_dir = Path(__file__).parent
    config_file = current_dir / 'config.txt'
    if config_file.exists():
        config = {}
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip().strip('"').strip("'")
            GARMIN_EMAIL = config.get("GARMIN_EMAIL")
            GARMIN_PASSWORD = config.get("GARMIN_PASSWORD")
        except: pass

if not GARMIN_EMAIL or not GARMIN_PASSWORD:
    print("Mangler Garmin brukernavn/passord.")
    sys.exit(1)

def format_duration(seconds):
    if not seconds: return "0m"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}t {m}m" if h > 0 else f"{m}m"

# --- FORBEDRET SØKEFUNKSJON ---
def find_valid_data(client_func, required_key, max_days=30):
    """
    Søker bakover i tid.
    Returnerer KUN data hvis 'required_key' faktisk har en verdi (ikke None).
    """
    today = datetime.date.today()
    for i in range(max_days):
        check_date = (today - timedelta(days=i)).isoformat()
        try:
            data = client_func(check_date)
            # Sjekk om dataen faktisk inneholder nøkkelen vi trenger
            if data and required_key in data and data[required_key] is not None:
                return data, check_date
        except:
            pass
    return {}, "Ingen funnet"

def main():
    print(f"Logger inn på Garmin...")
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
    except Exception as e:
        print(f"Innlogging feilet: {e}")
        return

    today = datetime.date.today()
    today_str = today.isoformat()
    print(f"Henter data for {today_str} (og historikk)...")

    # --- 1. HENT OG PAKK UT PROFIL (Viktig fix!) ---
    # Dataene ligger i 'userData'-nøkkelen
    full_profile = client.get_user_profile() or {}
    user_profile = full_profile.get('userData', {})
    
    print(f"Profil hentet. Fant brukernavn: {user_profile.get('userName', 'Ukjent')}")

    # --- 2. HENTING MED VALIDERING ---
    
    # Treningsstatus: Vi godtar bare data hvis 'acuteLoad' finnes
    print("Leter etter gyldig Training Status...")
    train_status, train_date = find_valid_data(client.get_training_status, 'acuteLoad', max_days=7)

    # Kroppskomposisjon: Vi godtar bare data hvis 'totalBodyWeight' finnes
    print("Leter etter siste innveiing...")
    body_comp, body_date = find_valid_data(client.get_body_composition, 'totalBodyWeight', max_days=60)

    # Dagens stats (Puls/Stress)
    try: stats = client.get_stats(today_str) or {}
    except: stats = {}
    
    # HRV
    try: hrv_data = client.get_hrv_data(today_str) or {}
    except: hrv_data = {}

    # Aktiviteter
    try: activities = client.get_activities_by_date(today_str, today_str, "") or []
    except: activities = []


    # --- 3. PARSING AV DATA ---

    # -- Vekt --
    weight_val = "N/A"
    body_fat = "N/A"
    
    # Prøver historisk søk
    if body_comp.get('totalBodyWeight'):
        weight_val = f"{body_comp['totalBodyWeight'] / 1000:.1f} kg"
    if body_comp.get('totalBodyFat'):
        body_fat = f"{body_comp['totalBodyFat']:.1f}%"
    
    # Fallback til profil (som nå er riktig utpakket)
    if weight_val == "N/A" and user_profile.get('weight'):
        weight_val = f"{user_profile['weight'] / 1000:.1f} kg"

    # -- Ytelse (VO2 & FTP) --
    # Nå som vi har pakket ut 'userData', bør disse finnes
    vo2_run = user_profile.get('vo2MaxRunning', 'N/A')
    vo2_cycle = user_profile.get('vo2MaxCycling', 'N/A')
    
    # FTP - sjekker også terskelwatt hvis FTP mangler
    ftp_val = user_profile.get('ftp', 'N/A')
    if ftp_val == "N/A":
        ftp_val = user_profile.get('userFTP', 'N/A')
    
    # Hvis VO2 fortsatt mangler, sjekk 'stats'
    if vo2_run == "N/A": vo2_run = stats.get('vo2MaxRunning', 'N/A')

    # -- Training Load --
    acute_load = train_status.get('acuteLoad', 'N/A')
    chronic_load = train_status.get('chronicLoad', 'N/A')
    load_ratio = train_status.get('loadRatio',
