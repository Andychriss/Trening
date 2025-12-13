import os
import sys
import datetime
from garminconnect import Garmin

# --- 1. KONFIGURASJON ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

if not GARMIN_EMAIL:
    # Prøv å lese fra config.txt hvis miljøvariabler mangler
    try:
        from pathlib import Path
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

def main():
    print("Logger inn på Garmin...")
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
    # Vi henter bare de endepunktene vi vet inneholder dataene dine (basert på JSON-analysen)
    user_profile = client.get_user_profile()
    body_comp = client.get_body_composition(today_str)
    training_status = client.get_training_status(today_str)
    stats = client.get_stats(today_str)
    hrv_data = client.get_hrv_data(today_str)
    activities = client.get_activities_by_date(today_str, today_str, "")

    # --- PARSING (NAKKEKIRURGI PÅ JSON-STRUKTUREN) ---

    # 1. VEKT & FETT (Fra Body Composition -> dateWeightList)
    weight_val = "N/A"
    body_fat = "N/A"
    
    if body_comp and 'dateWeightList' in body_comp and body_comp['dateWeightList']:
        # Hent nyeste måling
        latest_measure = body_comp['dateWeightList'][0]
        
        if 'weight' in latest_measure:
            # Garmin lagrer ofte vekt i gram (80800.0) -> del på 1000
            w = latest_measure['weight']
            weight_val = f"{w / 1000:.1f} kg"
            
        if 'bodyFat' in latest_measure:
            body_fat = f"{latest_measure['bodyFat']}%"
            
    # Fallback for vekt: User Profile
    if weight_val == "N/A" and user_profile:
        w = user_profile.get('userData', {}).get('weight')
        if w: weight_val = f"{w / 1000:.1f} kg"


    # 2. TRAINING LOAD (Fra Training Status -> EnhetsID -> acuteTrainingLoadDTO)
    acute_load = "N/A"
    chronic_load = "N/A"
    load_ratio = "N/A"
    
    if training_status:
        # Vi må grave oss ned: mostRecentTrainingStatus -> latestTrainingStatusData
        recent_status = training_status.get('mostRecentTrainingStatus', {})
        device_data_map = recent_status.get('latestTrainingStatusData', {})
        
        # Siden nøkkelen er en ukjent ID (f.eks "3468074856"), looper vi og tar første treff
        for device_id, data in device_data_map.items():
            if 'acuteTrainingLoadDTO' in data:
                load_dto = data['acuteTrainingLoadDTO']
                acute_load = load_dto.get('dailyTrainingLoadAcute', "N/A")
                chronic_load = load_dto.get('dailyTrainingLoadChronic', "N/A")
                load_ratio = load_dto.get('dailyAcuteChronicWorkloadRatio', "N/A")
                break # Vi fant data, stopp letingen

    # 3. VO2 MAX (Fra User Profile)
    vo2_run = "N/A"
    vo2_cycle = "N/A"
    if user_profile and 'userData' in user_profile:
        u_data = user_profile['userData']
        vo2_run = u_data.get('vo2MaxRunning', "N/A")
        vo2_cycle = u_data.get('vo2MaxCycling', "N/A")

    # 4. HRV & HELSE
    hrv_text = "N/A"
    if hrv_data and 'hrvSummary' in hrv_data:
        s = hrv_data['hrvSummary']
        hrv_text = f"Siste: {s.get('lastNightAvg')} ms | Status: {s.get('status')}"
    
    resting_hr = stats.get('restingHeartRate', "N/A")
    stress = stats.get('averageStressLevel', "N/A")

    # 5. AKTIVITETER
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Aktivitet')
            dur_sec = act.get('duration', 0)
            m, s = divmod(int(dur_sec), 60)
            h, m = divmod(m, 60)
            dur_str = f"{h}t {m}m" if h > 0 else f"{m}m"
            load = act.get('trainingLoad', 'N/A')
            act_text += f"- {name}: {dur_str} (Load: {load})\n"
    else:
        act_text = "Ingen trening i dag."

    # --- GENERER RAPPORT ---
    prompt = f"""
Hei Gemini! Her er dagens tall ({today_str}).

Kropp:
- Vekt: {weight_val}
- Fettprosent: {body_fat}
- Hvilepuls: {resting_hr}
- Stress: {stress}
- HRV: {hrv_text}

Ytelse:
- VO2 Max: Løp {vo2_run} / Sykkel {vo2_cycle}
- FTP: Ikke satt i profil (Autodetect er på)

Belastning (Training Status):
- Akutt Load (7 dager): {acute_load}
- Kronisk Load (4 uker): {chronic_load}
- Load Ratio: {load_ratio}

Dagens Økter:
{act_text}

Gi meg en kort vurdering av belastning vs. restitusjon.
    """

    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt)

    print("-" * 40)
    print(f"✅ SUKSESS! Data funnet:")
    print(f"   Vekt: {weight_val} | Fett: {body_fat}")
    print(f"   Load: {acute_load} / {chronic_load} (Ratio: {load_ratio})")
    print(f"   VO2:  {vo2_run}")
    print("-" * 40)
    print("Filen 'til_chat.txt' er klar.")

if __name__ == "__main__":
    main()
