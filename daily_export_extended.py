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

# Funksjon for å finne data bakover i tid (maks 5 dager)
def get_latest_data(client_func, max_days=5):
    today = datetime.date.today()
    for i in range(max_days):
        date_str = (today - timedelta(days=i)).isoformat()
        try:
            data = client_func(date_str)
            if data: return data, date_str
        except: pass
    return {}, "Ingen data"

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
    print(f"Henter data for {today_str}...")

    # --- 1. HENT BRUKERPROFIL (VIKTIGSTE KILDE FOR VEKT/FETT/VO2) ---
    try:
        full_profile = client.get_user_profile()
        # Dataene ligger nesten alltid i 'userData'-nøkkelen
        user_profile = full_profile.get('userData', {})
    except:
        user_profile = {}

    # --- 2. HENT DAGLIG SAMMENDRAG (FALLBACK FOR LOAD) ---
    # Vi sjekker i dag, så i går hvis i dag er tom
    user_summary, summary_date = get_latest_data(client.get_user_summary, 2)
    
    # --- 3. HENT TRENINGSSTATUS ---
    training_status, status_date = get_latest_data(client.get_training_status, 2)

    # --- 4. HENT HELSEDATA (HRV/PULS) ---
    try: hrv_data = client.get_hrv_data(today_str) or {}
    except: hrv_data = {}
    
    try: stats = client.get_stats(today_str) or {}
    except: stats = {}

    # --- 5. HENT AKTIVITETER ---
    try: activities = client.get_activities_by_date(today_str, today_str, "") or []
    except: activities = []


    # --- PARSING (LOGIKK FOR Å FINNE TALLENE) ---

    # A. VEKT & FETTPROSENT
    weight_val = "N/A"
    body_fat = "N/A"

    # Sjekk 1: Brukerprofilen (Der VO2 max lå)
    if 'weight' in user_profile and user_profile['weight']:
        weight_val = f"{user_profile['weight'] / 1000:.1f} kg"
    
    if 'bodyFat' in user_profile and user_profile['bodyFat']:
        body_fat = f"{user_profile['bodyFat']:.1f}%"

    # Sjekk 2: User Summary (Hvis du har veid deg i dag/igår)
    if weight_val == "N/A" and 'weight' in user_summary:
        weight_val = f"{user_summary['weight'] / 1000:.1f} kg"
    
    if body_fat == "N/A" and 'bodyFat' in user_summary:
         body_fat = f"{user_summary['bodyFat']:.1f}%"

    # B. VO2 MAX & FTP
    vo2_run = user_profile.get('vo2MaxRunning', 'N/A')
    vo2_cycle = user_profile.get('vo2MaxCycling', 'N/A')
    
    # FTP: Sjekker flere mulige nøkler i profilen
    ftp_val = user_profile.get('ftp', user_profile.get('userFTP', user_profile.get('thresholdPower', 'N/A')))

    # C. TRAINING LOAD
    acute_load = "N/A"
    chronic_load = "N/A"
    load_ratio = "N/A"
    endurance_score = "N/A"

    # Kilde 1: Training Status (Mest detaljert)
    if training_status:
        acute_load = training_status.get('acuteLoad') or training_status.get('sevenDayLoad')
        chronic_load = training_status.get('chronicLoad') or training_status.get('longTermLoad')
        load_ratio = training_status.get('loadRatio')
        endurance_score = training_status.get('enduranceScore', 'N/A')

    # Kilde 2: User Summary (Backup hvis status feilet)
    if acute_load in [None, "N/A"] and user_summary:
        # User Summary har ofte 'sevenDayTrainingLoad' selv om Training Status mangler
        acute_load = user_summary.get('sevenDayTrainingLoad', user_summary.get('mostRecentActivityTrainingLoad', 'N/A'))

    # Fiks formatering
    if acute_load is None: acute_load = "N/A"
    if chronic_load is None: chronic_load = "N/A"
    
    # Regn ut ratio hvis vi har tallene men mangler ratioen
    if load_ratio in [None, "N/A"] and acute_load != "N/A" and chronic_load != "N/A":
        try:
            load_ratio = round(float(acute_load) / float(chronic_load), 2)
        except: pass

    # D. HELSE (HRV / PULS)
    resting_hr = stats.get('restingHeartRate', user_profile.get('restingHeartRate', 'N/A'))
    avg_stress = stats.get('averageStressLevel', 'N/A')

    hrv_details = "N/A"
    hrv_summary = hrv_data.get('hrvSummary', {})
    if hrv_summary:
        hrv_details = (f"Siste natt: {hrv_summary.get('lastNightAvg')} ms | "
                       f"Ukesnitt: {hrv_summary.get('weeklyAvg')} ms | "
                       f"Status: {hrv_summary.get('status')}")

    # E. AKTIVITETER
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Ukjent')
            dur = format_duration(act.get('duration', 0))
            avg_hr = act.get('averageHR', 'N/A')
            load = act.get('trainingLoad', 'N/A')
            act_text += f"- {name}: {dur} | Puls: {avg_hr} | Load: {load}\n"
    else:
        act_text = "Ingen trening registrert i dag."

    # --- GENERER FIL ---
    prompt = f"""
Hei Gemini! Data fra Garmin ({today_str}).

Kropp:
- Vekt: {weight_val}
- Fettprosent: {body_fat}
- Hvilepuls: {resting_hr}
- Stress: {avg_stress}
- HRV: {hrv_details}

Ytelse:
- VO2 Max Løp: {vo2_run}
- VO2 Max Sykkel: {vo2_cycle}
- FTP: {ftp_val} W
- Endurance Score: {endurance_score}

Belastning (Load):
- Akutt (7-dager): {acute_load}
- Kronisk (4-uker): {chronic_load}
- Load Ratio: {load_ratio}

Dagens Økter:
{act_text}
    """
    
    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt)
    
    print("-" * 40)
    print(f"✅ Ferdig!")
    print(f"Vekt: {weight_val} | Fett: {body_fat}")
    print(f"VO2: {vo2_run} | FTP: {ftp_val}")
    print(f"Load: {acute_load}")
    print("-" * 40)

    # --- DEBUG HJELP ---
    # Hvis fettprosent fortsatt er N/A, printer vi alle nøklene i profilen din
    if body_fat == "N/A":
        print("\n[DEBUG] Fettprosent mangler. Her er nøklene i din profil (sjekk om bodyFat heter noe annet):")
        print(list(user_profile.keys()))
    
    if acute_load == "N/A":
        print("\n[DEBUG] Load mangler. Her er nøklene i User Summary:")
        keys_with_load = [k for k in user_summary.keys() if 'load' in k.lower()]
        print(keys_with_load)

if __name__ == "__main__":
    main()
