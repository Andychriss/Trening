import os
import sys
import datetime
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

    # --- INITIALISER VARIABLER ---
    stats = {}
    user_summary = {}
    hrv_data = {}
    sleep_data = {}
    user_profile = {}
    training_status = {}
    body_comp = {}
    activities = []

    # --- HENT DATA (Hver for seg for å unngå krasj) ---
    
    # 1. Stats og Summary
    try: stats = client.get_stats(today_str) or {}
    except: pass
    
    try: user_summary = client.get_user_summary(today_str) or {}
    except: pass

    # 2. Helse
    try: hrv_data = client.get_hrv_data(today_str) or {}
    except: pass
    
    try: sleep_data = client.get_sleep_data(today_str) or {}
    except: pass

    # 3. Profil (Viktig for Vekt/VO2 fallback)
    try: user_profile = client.get_user_profile() or {}
    except: pass

    # 4. Kroppssammensetning
    try: body_comp = client.get_body_composition(today_str) or {}
    except: pass

    # 5. Training Status
    try: training_status = client.get_training_status(today_str) or {}
    except: pass

    # 6. Aktiviteter
    try: activities = client.get_activities_by_date(today_str, today_str, "") or []
    except: pass


    # --- PARSING AV DATA ---

    # -- Vekt & Kropp --
    weight_val = "N/A"
    body_fat = "N/A"
    
    # Prioritet 1: Body Composition (hvis veid i dag)
    if 'totalBodyWeight' in body_comp and body_comp['totalBodyWeight']:
        weight_val = f"{body_comp['totalBodyWeight'] / 1000:.1f} kg"
    if 'totalBodyFat' in body_comp and body_comp['totalBodyFat']:
        body_fat = f"{body_comp['totalBodyFat']:.1f}%"
        
    # Prioritet 2: User Summary (hvis veid i dag)
    if weight_val == "N/A" and 'weight' in user_summary and user_summary['weight']:
         weight_val = f"{user_summary['weight'] / 1000:.1f} kg"
    
    # Prioritet 3: User Profile (siste kjente)
    if weight_val == "N/A" and 'weight' in user_profile and user_profile['weight']:
        weight_val = f"{user_profile['weight'] / 1000:.1f} kg"
        
    # Fallback fettprosent
    if body_fat == "N/A" and 'bodyFat' in user_profile and user_profile['bodyFat']:
        body_fat = f"{user_profile['bodyFat']:.1f}%"


    # -- Helse --
    resting_hr = stats.get('restingHeartRate', 'N/A')
    avg_stress = stats.get('averageStressLevel', 'N/A')

    # -- HRV --
    hrv_details = "N/A"
    hrv_summary = hrv_data.get('hrvSummary', {})
    if hrv_summary:
        last_night = hrv_summary.get('lastNightAvg', 'N/A')
        weekly_avg = hrv_summary.get('weeklyAvg', 'N/A')
        max_5min = hrv_summary.get('lastNight5MinHigh', 'N/A')
        status = hrv_summary.get('status', 'N/A')
        baseline = hrv_summary.get('baseline', {})
        b_low = baseline.get('balancedLow', '?')
        b_high = baseline.get('balancedUpper', '?')
        hrv_details = (
            f"Siste natt: {last_night} ms\n"
            f"- Ukesnitt: {weekly_avg} ms (Baseline: {b_low}-{b_high})\n"
            f"- 5 min maks: {max_5min} ms\n"
            f"- Status: {status}"
        )
    else:
        val = user_summary.get('hrvStatus')
        if val: hrv_details = f"{val}"

    # -- Ytelse (VO2, FTP) --
    vo2_run = "N/A"
    vo2_cycle = "N/A"

    # Sjekk User Profile først (mest pålitelig for "nåværende form")
    if 'vo2MaxRunning' in user_profile: vo2_run = user_profile['vo2MaxRunning']
    if 'vo2MaxCycling' in user_profile: vo2_cycle = user_profile['vo2MaxCycling']

    # FTP
    ftp_val = "N/A"
    if 'userFTP' in user_profile:
        ftp_val = user_profile['userFTP']
    elif 'ftp' in user_summary:
        ftp_val = user_summary['ftp']
    
    # Endurance Score
    endurance_score = "N/A"
    if training_status and 'enduranceScore' in training_status:
        endurance_score = training_status['enduranceScore']

    # -- Training Load --
    acute_load = "N/A"
    chronic_load = "N/A"
    load_ratio = "N/A"
    
    if training_status:
        acute_load = training_status.get('acuteLoad', 'N/A')
        chronic_load = training_status.get('chronicLoad', 'N/A')
        load_ratio = training_status.get('loadRatio', 'N/A')
        
        # Beregn ratio manuelt hvis den mangler
        if load_ratio == "N/A" and isinstance(acute_load, (int, float)) and isinstance(chronic_load, (int, float)):
             if chronic_load > 0:
                 load_ratio = round(acute_load / chronic_load, 2)

    # -- Aktiviteter --
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Ukjent')
            dur = format_duration(act.get('duration', 0))
            avg_hr = act.get('averageHR', 'N/A')
            session_load = act.get('trainingLoad', 'N/A')
            
            # Prøv å hente soner
            zones_txt = ""
            try:
                # Sone-kall kan også feile, så vi wrapper det
                zones = client.get_activity_hr_in_timezones(act.get('activityId'))
                if zones:
                    z_list = [f"S{z['zoneNumber']}: {format_duration(z['secsInZone'])}" for z in zones if z.get('secsInZone')]
                    zones_txt = ", ".join(z_list)
            except: pass
            
            act_text += f"- {name}: {dur} | Puls: {avg_hr} | Load: {session_load}\n  Soner: {zones_txt}\n"
    else:
        act_text = "Ingen trening registrert i dag."

    # --- GENERER TEKSTFIL ---
    prompt_for_chat = f"""
Hei Gemini! Her er en fullstendig statusrapport fra Garmin ({today_str}).

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

Training Load (Belastning):
- Akutt Load (7 dager): {acute_load}
- Kronisk Load (4 uker): {chronic_load}
- Load Ratio: {load_ratio}

Dagens Økter:
{act_text}

Ta hensyn til acute/chronic load ratio og HRV når du analyserer totalbelastningen.
    """
    
    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt_for_chat)
    
    print("-" * 40)
    print(f"✅ Data hentet og lagret i 'til_chat.txt'")
    print(f"Vekt: {weight_val}, VO2: {vo2_run}/{vo2_cycle}, Load: {acute_load}")
    print("-" * 40)

if __name__ == "__main__":
    main()
