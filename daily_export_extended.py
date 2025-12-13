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

# Fallback til lokal fil hvis vi kjører lokalt
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
    # Oppsett av Gemini (hvis nøkkel finnes)
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
        hrv_data = client.get_hrv_data(today_str) or {}
        sleep_data = client.get_sleep_data(today_str) or {}
        activities = client.get_activities_by_date(today_str, today_str, "") or []
    except:
        stats, hrv_data, sleep_data, activities = {}, {}, {}, []

    # Pakk ut verdier
    resting_hr = stats.get('restingHeartRate', 'N/A')
    avg_stress = stats.get('averageStressLevel', 'N/A')
    
    hrv_val = "N/A"
    if 'hrvSummary' in hrv_data:
        hrv_val = hrv_data['hrvSummary'].get('lastNightAverage', 'N/A')

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

    # --- HER LAGES TEKSTEN DU VIL KOPIERE ---
    prompt_for_chat = f"""
Hei Gemini! Her er dagens tall fra Garmin ({today_str}).
Kan du analysere dette for meg?

Helse:
- Hvilepuls: {resting_hr}
- HRV (siste natt): {hrv_val}
- Stress: {avg_stress}
- Søvn: {sleep_val}

Trening:
{act_text}
    """
    
    # 1. Lagre teksten til en fil du kan kopiere fra
    with open("til_chat.txt", "w", encoding="utf-8") as f:
        f.write(prompt_for_chat)
    print("✅ Lagret 'til_chat.txt' - klar for klipp og lim!")

    # 2. (Valgfritt) Kjør analysen automatisk også, hvis API-nøkkel finnes
    if model:
        try:
            print("Kjører også automatisk analyse...")
            response = model.generate_content(prompt_for_chat + "\nGi en kort oppsummering.")
            with open("min_treningslogg.md", "a", encoding="utf-8") as f:
                f.write(f"\n\n## {today_str}\n{response.text}\n")
            print("✅ Treningslogg oppdatert.")
        except Exception as e:
            print(f"Kunne ikke kjøre auto-analyse: {e}")

if __name__ == "__main__":
    main()

