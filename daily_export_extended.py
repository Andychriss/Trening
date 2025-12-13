import os
import sys
import datetime
from pathlib import Path
from garminconnect import Garmin

# --- 1. KONFIGURASJON ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

if not GARMIN_EMAIL:
    try:
        current_dir = Path(__file__).parent
        config_file = current_dir / 'config.txt'
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        k, v = line.split('=', 1)
                        if k.strip() == "GARMIN_EMAIL": GARMIN_EMAIL = v.strip().strip('"\'')
                        if k.strip() == "GARMIN_PASSWORD": GARMIN_PASSWORD = v.strip().strip('"\'')
    except: pass

if not GARMIN_EMAIL or not GARMIN_PASSWORD:
    print("Mangler brukernavn/passord.")
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

    # --- HENT DATA ---
    try: user_profile = client.get_user_profile()
    except: user_profile = {}
    
    try: body_comp = client.get_body_composition(today_str)
    except: body_comp = {}
    
    try: training_status = client.get_training_status(today_str)
    except: training_status = {}
    
    try: stats = client.get_stats(today_str)
    except: stats = {}
    
    try: hrv_data = client.get_hrv_data(today_str)
    except: hrv_data = {}
    
    try: activities = client.get_activities_by_date(today_str, today_str, "")
    except: activities = []

    # --- PARSING ---

    # 1. VEKT & FETT (Fra Body Composition -> dateWeightList)
    weight_val = "N/A"
    body_fat = "N/A"
    
    # Sjekk dagens innveiing (med fettprosent)
    if body_comp and 'dateWeightList' in body_comp and body_comp['dateWeightList']:
        latest = body_comp['dateWeightList'][0]
        if 'weight' in latest:
            weight_val = f"{latest['weight'] / 1000:.1f} kg"
        if 'bodyFat' in latest:
            body_fat = f"{latest['bodyFat']:.1f}%"
            
    # Fallback vekt fra profil (hvis ingen veiing i dag)
    if weight_val == "N/A" and user_profile:
        w = user_profile.get('userData', {}).get('weight')
        if w: weight_val = f"{w / 1000:.1f} kg"

    # 2. TRAINING LOAD (Fra Training Status -> Device ID -> acuteTrainingLoadDTO)
    acute_load = "N/A"
    chronic_load = "N/A"
    load_ratio = "N/A"
    
    if training_status:
        recent_status = training_status.get('mostRecentTrainingStatus', {})
        device_data_map = recent_status.get('latestTrainingStatusData', {})
        
        # Finn data uavhengig av klokkens ID
        for device_id, data in device_data_map.items():
            if 'acuteTrainingLoadDTO' in data:
                load_dto = data['acuteTrainingLoadDTO']
                acute_load = load_dto.get('dailyTrainingLoadAcute', "N/A")
                chronic_load = load_dto.get('dailyTrainingLoadChronic', "N/A")
                load_ratio = load_dto.get('dailyAcuteChronicWorkloadRatio', "N/A")
                break

    # 3. VO2 MAX
    vo2_run = "N/A"
    vo2_cycle = "N/A"
    if user_profile and 'userData' in user_profile:
        u_data = user_profile['userData']
        vo2_run = u_data.get('vo2MaxRunning', "N/A")
        vo2_cycle = u_data.get('vo2MaxCycling', "N/A")

    # 4. HELSE (HRV / PULS)
    hrv_text = "N/A"
    if hrv_data and 'hrvSummary' in hrv_data:
        s = hrv_data['hrvSummary']
        hrv_text = (f"Siste natt: {s.get('lastNightAvg')} ms | "
                    f"Ukesnitt: {s.get('weeklyAvg')} ms | "
                    f"Status: {s.get('status')}")
    
    resting_hr = stats.get('restingHeartRate', "N/A")
    stress = stats.get('averageStressLevel', "N/A")

    # 5. AKTIVITETER
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Aktivitet')
            dur = format_duration(act.get('duration', 0))
            load = act.get('trainingLoad', 'N/A')
            act_text += f"- {name}: {dur} | Load: {load}\n"
    else:
        act_text = "Ingen trening i dag."

    # --- GENERER FIL ---
    prompt = f"""
Hei Gemini! Her er dagens tall ({today_str}).

Kropp & Helse:
- Vekt: {weight_val}
- Fettprosent: {body_fat}
- Hvilepuls: {resting_hr}
- Stress: {stress}
- HRV: {hrv_text}

Ytelse (VO2 Max):
- Løp: {vo2_run}
- Sykkel: {vo2_cycle}

Belastning (Training Status):
- Akutt Load (7 dager): {acute_load}
- Kronisk Load (4 uker): {chronic_load}
- Load Ratio: {load_ratio}

Dagens Økter:
{act_text}

Gi en kort analyse av dagens status.
    """

    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    print("-" * 40)
    print(f"✅ SUKSESS!")
    print(f"   Vekt: {weight_val} | Fett: {body_fat}")
    print(f"   Load: {acute_load} / {chronic_load} (Ratio: {load_ratio})")
    print(f"   VO2:  {vo2_run}")
    print("-" * 40)
    print("Filen 'til_chat.txt' er oppdatert.")

if __name__ == "__main__":
    main()
