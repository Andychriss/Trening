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

# --- 2. HJELPEFUNKSJONER ---
def format_duration(seconds):
    if not seconds: return "0m"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}t {m}m" if h > 0 else f"{m}m"

# Ny funksjon: Søk bakover i tid etter data
def find_latest_data(client_func, max_days=30):
    today = datetime.date.today()
    for i in range(max_days):
        check_date = (today - timedelta(days=i)).isoformat()
        try:
            data = client_func(check_date)
            # Sjekk om dataen faktisk inneholder noe nyttig (ikke bare tomme strukturer)
            if data:
                return data, check_date
        except:
            pass
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
    print(f"Henter data (Søker bakover hvis dagens data mangler)...")

    # --- HENT DATA (SMARTERE SØK) ---

    # 1. Grunnleggende (Må være i dag)
    try: stats = client.get_stats(today_str) or {}
    except: stats = {}
    
    try: hrv_data = client.get_hrv_data(today_str) or {}
    except: hrv_data = {}

    # 2. Vekt & Kropp (Søk bakover 30 dager)
    # Mange veier seg ikke hver dag. Vi finner siste registrering.
    body_comp, body_date = find_latest_data(client.get_body_composition, max_days=30)
    print(f"Fant kroppsdata fra: {body_date}")

    # 3. Training Status (Søk bakover 3 dager)
    # Load beregnes ofte natten over. Hvis dagens er tom, sjekk i går.
    train_status, train_date = find_latest_data(client.get_training_status, max_days=3)
    print(f"Fant treningsstatus fra: {train_date}")

    # 4. User Profile (Statisk info som VO2/FTP ligger ofte her)
    try: user_profile = client.get_user_profile() or {}
    except: user_profile = {}

    # 5. Aktiviteter (Kun i dag)
    try: activities = client.get_activities_by_date(today_str, today_str, "") or []
    except: activities = []


    # --- PARSING ---

    # -- Vekt --
    weight_val = "N/A"
    body_fat = "N/A"
    
    # Sjekk historisk søk først
    if 'totalBodyWeight' in body_comp and body_comp['totalBodyWeight']:
        weight_val = f"{body_comp['totalBodyWeight'] / 1000:.1f} kg"
    if 'totalBodyFat' in body_comp and body_comp['totalBodyFat']:
        body_fat = f"{body_comp['totalBodyFat']:.1f}%"
    
    # Fallback til profil hvis historisk søk feilet
    if weight_val == "N/A" and 'weight' in user_profile:
        weight_val = f"{user_profile['weight'] / 1000:.1f} kg"

    # -- Helse --
    resting_hr = stats.get('restingHeartRate', 'N/A')
    avg_stress = stats.get('averageStressLevel', 'N/A')

    # -- HRV --
    hrv_details = "N/A"
    hrv_summary = hrv_data.get('hrvSummary', {})
    if hrv_summary:
        last_night = hrv_summary.get('lastNightAvg', 'N/A')
        weekly_avg = hrv_summary.get('weeklyAvg', 'N/A')
        status = hrv_summary.get('status', 'N/A')
        hrv_details = f"Siste natt: {last_night} ms\n- Ukesnitt: {weekly_avg} ms\n- Status: {status}"
    else:
        # Fallback til enkel verdi fra stats
        if 'hrvStatus' in user_profile:
             hrv_details = user_profile['hrvStatus']

    # -- Training Load & Status --
    acute_load = "N/A"
    chronic_load = "N/A"
    load_ratio = "N/A"
    endurance_score = "N/A"
    
    if train_status:
        acute_load = train_status.get('acuteLoad', 'N/A')
        chronic_load = train_status.get('chronicLoad', 'N/A')
        load_ratio = train_status.get('loadRatio', 'N/A')
        endurance_score = train_status.get('enduranceScore', 'N/A')
        
        # Beregn ratio manuelt hvis mangler
        if load_ratio == "N/A" and isinstance(acute_load, (int, float)) and isinstance(chronic_load, (int, float)):
            if chronic_load > 0: load_ratio = round(acute_load / chronic_load, 2)

    # -- VO2 Max & FTP --
    # VO2 ligger ofte i User Profile ELLER stats for en gitt dag
    vo2_run = user_profile.get('vo2MaxRunning', 'N/A')
    vo2_cycle = user_profile.get('vo2MaxCycling', 'N/A')
    
    # FTP - Ligger ofte dypt i profilen eller settings. 
    # Vi sjekker user_profile for 'userFTP' eller 'ftp'
    ftp_val = user_profile.get('userFTP', user_profile.get('ftp', 'N/A'))

    # Hvis VO2 fortsatt er N/A, sjekk 'stats' fra i dag
    if vo2_run == "N/A": vo2_run = stats.get('vo2MaxRunning', 'N/A')
    if vo2_cycle == "N/A": vo2_cycle = stats.get('vo2MaxCycling', 'N/A')

    # -- Aktiviteter --
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

    # --- GENERER TEKSTFIL ---
    prompt_for_chat = f"""
Hei Gemini! Her er en statusrapport fra Garmin ({today_str}).
Merk: Noen data kan være hentet fra siste registrerte måling (opptil 30 dager tilbake).

Fysiometri & Helse:
- Vekt: {weight_val}
- Fettprosent: {body_fat}
- Hvilepuls: {resting_hr}
- Stressnivå: {avg_stress}
- HRV Status:
{hrv_details}

Ytelse & Kapasitet:
- VO2 Max (Løp): {vo2_run}
- VO2 Max (Sykkel): {vo2_cycle}
- Cycling FTP: {ftp_val} W
- Endurance Score: {endurance_score}

Training Load (Fra {train_date}):
- Akutt Load: {acute_load}
- Kronisk Load: {chronic_load}
- Load Ratio: {load_ratio}

Dagens Økter:
{act_text}
    """
    
    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt_for_chat)
    
    print("-" * 40)
    print(f"✅ Rapport generert!")
    print(f"Vekt funnet: {weight_val} (Dato: {body_date})")
    print(f"Load funnet: {acute_load} (Dato: {train_date})")
    print(f"VO2 Max: Løp {vo2_run} / Sykkel {vo2_cycle}")
    print("-" * 40)
    
    # DEBUG: Hvis du fortsatt får N/A, vil dette vise hva User Profile faktisk inneholder
    if vo2_run == "N/A" and vo2_cycle == "N/A":
        print("\n[DEBUG] Innhold i User Profile (nøkler):")
        print(list(user_profile.keys()))

if __name__ == "__main__":
    main()
