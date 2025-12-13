import os
import sys
import datetime
from pathlib import Path
from garminconnect import Garmin

# --- 1. KONFIGURASJON ---
GARMIN_EMAIL = os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

# Fallback til lokal fil (config.txt)
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

    # Hent data
    try:
        stats = client.get_stats(today_str) or {}
        try: hrv_data = client.get_hrv_data(today_str) or {}
        except: hrv_data = {}
        
        sleep_data = client.get_sleep_data(today_str) or {}
        user_summary = client.get_user_summary(today_str) or {}
        activities = client.get_activities_by_date(today_str, today_str, "") or []
    except Exception as e:
        print(f"Feil ved henting av data: {e}")
        stats, hrv_data, sleep_data, activities, user_summary = {}, {}, {}, [], {}
    
    # Pakk ut verdier
    resting_hr = stats.get('restingHeartRate', 'N/A')
    avg_stress = stats.get('averageStressLevel', 'N/A')
    
    # --- HRV LOGIKK ---
    hrv_details = "N/A"
    hrv_summary = hrv_data.get('hrvSummary', {})
    
    if hrv_summary:
        last_night = hrv_summary.get('lastNightAvg', 'N/A')
        weekly_avg = hrv_summary.get('weeklyAvg', 'N/A')
        max_5min = hrv_summary.get('lastNight5MinHigh', 'N/A')
        status = hrv_summary.get('status', 'N/A')
        
        baseline = hrv_summary.get('baseline', {})
        baseline_low = baseline.get('balancedLow', '?')
        baseline_high = baseline.get('balancedUpper', '?')
        
        hrv_details = (
            f"Siste natt: {last_night} ms\n"
            f"- Ukesnitt (7 dager): {weekly_avg} ms\n"
            f"- Baseline: {baseline_low}-{baseline_high} ms\n"
            f"- 5 min maks: {max_5min} ms\n"
            f"- Status: {status}"
        )
    else:
        # Fallback
        val = user_summary.get('hrvStatus') or user_summary.get('totalAverageHRV')
        if val:
            hrv_details = f"Siste natt: {val} (Mangler detaljer)"

    # Søvn
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
- Stressnivå: {avg_stress}
- Søvnvarighet: {sleep_val}

HRV Data:
{hrv_details}

Trening:
{act_text}
    """
    
    # Lagre til fil
    file_name = "til_chat.txt"
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(prompt_for_chat)
    
    print("-" * 30)
    print(f"✅ Suksess! Data er lagret i '{file_name}'")
    print("Du kan nå åpne filen, kopiere alt, og lime det inn i Gemini.")
    print("-" * 30)

if __name__ == "__main__":
    main()
