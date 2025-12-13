import os
import sys
import datetime
from pathlib import Path
from garminconnect import Garmin
import google.generativeai as genai

# --- 1. KONFIGURASJON (Sky + Lokal) ---
# Prøver først å hente fra Miljøvariabler (GitHub/Sky)
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Hvis vi IKKE fant passord i miljøet, sjekk lokal config.txt
if not GARMIN_EMAIL:
    current_dir = Path(__file__).parent
    config_file = current_dir / 'config.txt'
    if config_file.exists():
        print(f"Laster konfigurasjon fra lokal fil: {config_file}")
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
        except Exception as e:
            print(f"Kunne ikke lese config.txt: {e}")

if not GARMIN_EMAIL or not GARMIN_PASSWORD or not GEMINI_API_KEY:
    print("FEIL: Mangler passord/API-nøkkel. Sjekk GitHub Secrets eller config.txt.")
    sys.exit(1)

# --- 2. HJELPEFUNKSJONER ---
def format_duration(seconds):
    if not seconds: return "0m"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}t {m}m" if h > 0 else f"{m}m"

def main():
    # Oppsett av Gemini (Bruker Flash 2.5/siste versjon)
    genai.configure(api_key=GEMINI_API_KEY)
    # Bruker en modell som er rask og gratis i skyen
    model = genai.GenerativeModel('gemini-1.5-flash') 

    print(f"Logger inn på Garmin...")
    try:
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.login()
        print("✅ Logget inn!")
    except Exception as e:
        print(f"❌ Innlogging feilet: {e}")
        return # Avslutter hvis vi ikke kommer inn

    today = datetime.date.today()
    # today = datetime.date(2025, 12, 12) # For testing av spesifikk dato
    today_str = today.isoformat()
    print(f"Henter data for {today_str}...")

    # Hent data (med feilhåndtering for manglende data)
    try:
        stats = client.get_stats(today_str) or {}
        hrv_data = client.get_hrv_data(today_str) or {}
        sleep_data = client.get_sleep_data(today_str) or {}
        user_summary = client.get_user_summary(today_str) or {}
        activities = client.get_activities_by_date(today_str, today_str, "") or []
    except Exception as e:
        print(f"Advarsel ved henting av data: {e}")
        return

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

    # Bygg aktivitetsliste
    act_text = ""
    if activities:
        for act in activities:
            name = act.get('activityName', 'Ukjent')
            dur = format_duration(act.get('duration', 0))
            avg_hr = act.get('averageHR', 'N/A')
            
            # Hent soner
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

    # Send til Gemini
    prompt = f"""
    Analyser min dag (Garmin data) for {today_str}.
    Fokus: Restitusjon, Stress og Trening (spesielt tid i soner).
    
    Helse:
    - Hvilepuls: {resting_hr}
    - HRV (siste natt): {hrv_val}
    - Stress (snitt): {avg_stress}
    - Søvn: {sleep_val}
    
    Trening:
    {act_text}
    
    Gi en kort oppsummering på norsk.
    """
    
    print("Spør Gemini...")
    try:
        response = model.generate_content(prompt)
        content = response.text
        
        # Lagre til fil
        with open("min_treningslogg.md", "a", encoding="utf-8") as f:
            f.write(f"\n\n## {today_str}\n{content}\n")
        print("✅ Ferdig! Logg oppdatert.")
        
    except Exception as e:
        print(f"Gemini feilet: {e}")

if __name__ == "__main__":
    main()