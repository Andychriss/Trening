import os
import sys
import datetime
from pathlib import Path
from garminconnect import Garmin
import google.generativeai as genai

# --- 1. KONFIGURASJON ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Fallback til lokal fil
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
            GEMINI_API_KEY = config.get("GEMINI_API_KEY")
        except: pass

if not GARMIN_EMAIL or not GARMIN_PASSWORD:
    print("Mangler passord.")
    sys.exit(1)

# --- 2. HJELPEFUNKSJONER ---
def format_duration(seconds):
    if not seconds: return "0m"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}t {m}m" if h > 0 else f"{m}m"

def main():
    # Oppsett av Gemini
    model = None
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')

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

    # Hent data
    try:
        stats = client.get_stats(today_str) or {}
        # Vi henter HRV, men ignorerer feil midlertidig for å unngå kræsj
        try: hrv_data = client.get_hrv_data(today_str) or {}
        except: hrv_data = {}
        
        sleep_data = client.get_sleep_data(today_str) or {}
        user_summary = client.get_user_summary(today_str) or {}
        activities = client.get_activities_by_date(today_str, today_str, "") or []
    except Exception as e:
        print(f"Feil ved henting av data: {e}")
        stats, hrv_data, sleep_data, activities, user_summary = {}, {}, {}, [], {}

    # --- DEBUG UTKRIFT (Vises i GitHub Logs) ---
    print(f"DEBUG - HRV Raw: {hrv_data}") 
    
    # Pakk ut verdier
    resting_hr = stats.get('restingHeartRate', 'N/A')
    avg_stress = stats.get('averageStressLevel', 'N/A')
    
    # --- NY HRV LOGIKK ---
    hrv_val = "N/A"
    
    # Forsøk 1: Hent fra hrvSummary
    if 'hrvSummary' in hrv_data and hrv_data['hrvSummary']:
        hrv_val = hrv_data['hrvSummary'].get('lastNightAverage', 'N/A')
    
    # Forsøk 2: Hvis N/A, sjekk om det ligger i User Summary (ofte mer stabilt)
    if hrv_val == "N/A" or hrv_val is None:
        print("Fant ikke HRV i standard-feltet, sjekker reserveløsning...")
        if 'hrvStatus' in user_summary:
            hrv_val = user_summary['hrvStatus']
        elif 'totalAverageHRV' in user_summary:
             hrv_val = user_summary['totalAverageHRV']

    # Fiks format hvis det er None
    if hrv_val is None: hrv_val = "N/A"

    sleep_val = "N/A"
    if 'dailySleepDTO' in sleep_data:
        sec = sleep_data['dailySleepDTO'].get('sleepTimeSeconds', 0)
        sleep_val = format_duration(sec)

    # Aktiviteter
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Ukjent')
            dur = format_duration(act.get('duration', 0))
            avg_hr = act.get('averageHR', 'N/A')
            zones_txt = ""
            try:
                zones = client.get_activity_hr_in_timezones(act.get('activityId'))
                if zones:
                    z_list = [f"S{z['zoneNumber']}: {format_duration(z['secsInZone'])}" for z in zones if z.get('secsInZone')]
                    zones_txt = ", ".join(z_list)
            except: pass
            act_text += f"- {name}: {dur}, Puls snitt {avg_hr}. Soner: {zones_txt}\n"
    else:
        act_text = "Ingen trening registrert."

    # --- GENERER TEKST ---
    prompt_for_chat = f"""
Hei Gemini! Her er dagens tall fra Garmin ({today_str}).

Helse:
- Hvilepuls: {resting_hr}
- HRV (siste natt): {hrv_val}
- Stress: {avg_stress}
- Søvn: {sleep_val}

Trening:
{act_text}
    """
    
    # Lagre til fil
    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt_for_chat)
    print("✅ Lagret 'til_chat.txt'")

    # Send til Gemini (hvis nøkkel finnes)
    if model:
        try:
            print("Kjører Gemini analyse...")
            response = model.generate_content(prompt_for_chat + "\nGi en kort analyse.")
            with open("min_treningslogg.md", "a", encoding="utf-8") as f:
                f.write(f"\n\n## {today_str}\n{response.text}\n")
            print("✅ Treningslogg oppdatert.")
        except Exception as e:
            print(f"Gemini feilet: {e}")

if __name__ == "__main__":
    main()

