import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import timedelta, date
import itertools
import json
import os
import locale
import requests
from streamlit_quill import st_quill

# --- KONFIGURATION ---
st.set_page_config(page_title="mycareernow Planer", page_icon="📅", layout="wide")

# HIER DEINEN GITHUB RAW LINK EINFÜGEN (Optional)
GITHUB_RAW_URL = "https://raw.githubusercontent.com/DEIN_USER/DEIN_REPO/main/modul_texte_backup.json"

MAX_TEILNEHMER_PRO_KLASSE = 20
TEXT_FILE = "modul_texte.json"
ADMIN_PASSWORD = "mycarrEer.admin!186"

# Locale setzen
try:
    locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'de_DE')
    except:
        pass

# --- INIT TEXTE ---
def init_texts_from_github():
    if not os.path.exists(TEXT_FILE):
        try:
            if "DEIN_USER" not in GITHUB_RAW_URL:
                response = requests.get(GITHUB_RAW_URL)
                if response.status_code == 200:
                    with open(TEXT_FILE, "w", encoding="utf-8") as f:
                        f.write(response.text)
        except Exception as e:
            print(f"GitHub Error: {e}")

init_texts_from_github()

# --- ABHÄNGIGKEITEN ---
# Tuple = ODER-Verknüpfung (Eines davon reicht)
ABHAENGIGKEITEN = {
    "PSM2": "PSM1",
    "PSPO1": "PSM1", 
    "PSPO2": "PSPO1", 
    "SPS": "PSM1",
    "PSK": "PSM1",
    "PAL-E": "PSM1",
    "PAL-EBM": "PSM1",
    "AKI-EX": "AKI",
    "2wo_PMPX": ("PSM1", "IPMA") 
}

KATEGORIEN_MAPPING = {
    "Onboarding": ["B4.0"],
    "Projektmanagement": ["PSM1", "PSM2", "PSPO1", "PSPO2", "SPS", "PAL-E", "PAL-EBM", "PSK", "IPMA", "2wo_PMPX", "IT-TOOLS"],
    "Künstliche Intelligenz": ["AKI", "AKI-EX"],
    "Qualitätsmanagement": ["SQM", "PQM"],
    "Human Resources": ["PeMa", "PeEin", "ARSR", "PeFü", "KKP"],
    "Marketing": ["SEO", "SEA", "SoMe"],
    "Lückenfüller": ["SELBSTLERN"],
    "Teilzeit": ["TZ-LERNEN"]
}

MODUL_ZU_KAT = {}
for kat, module in KATEGORIEN_MAPPING.items():
    for mod in module:
        MODUL_ZU_KAT[mod] = kat

PRAXIS_MODUL = "2wo_PMPX"

# --- HELPER FUNKTIONEN ---

def load_texts():
    if not os.path.exists(TEXT_FILE):
        return {}
    with open(TEXT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_text(kuerzel, text):
    data = load_texts()
    data[kuerzel] = text
    with open(TEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return data

def save_all_texts_from_upload(uploaded_json):
    data = json.load(uploaded_json)
    with open(TEXT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return data

def get_next_monday(d):
    wd = d.weekday() 
    if wd == 0: return d
    return d + timedelta(days=(7 - wd))

def get_friday_of_week(monday_date, weeks_duration=1):
    return monday_date + timedelta(weeks=weeks_duration) - timedelta(days=3)

def finde_naechsten_start(df, modul_kuerzel, ab_datum, ignore_capacity=False):
    # Ab Datum auf nächsten Montag normalisieren
    ab_datum = get_next_monday(pd.to_datetime(ab_datum))
    
    # Basis-Filter: Modul und Datum
    mask = (df['Kuerzel'] == modul_kuerzel) & (df['Startdatum'] >= ab_datum)
    
    # Optional: Kapazitäts-Filter
    if not ignore_capacity:
        if 'Teilnehmeranzahl' in df.columns and 'Klassenanzahl' in df.columns:
            # Nur Kurse, die nicht voll sind
            mask = mask & (df['Teilnehmeranzahl'] < (df['Klassenanzahl'] * MAX_TEILNEHMER_PRO_KLASSE))
    
    moegliche_termine = df[mask].sort_values(by='Startdatum')
    
    if moegliche_termine.empty:
        return None
    return moegliche_termine.iloc[0]

def berechne_kategorie_wechsel(plan):
    wechsel = 0
    letzte_kat = None
    for eintrag in plan:
        if eintrag['Kuerzel'] in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]: continue
        kuerzel = eintrag['Kuerzel']
        aktuelle_kat = MODUL_ZU_KAT.get(kuerzel, "Sonstiges")
        if letzte_kat is not None and aktuelle_kat != letzte_kat:
            wechsel += 1
        letzte_kat = aktuelle_kat
    return wechsel

def berechne_plan(df, modul_reihenfolge, start_wunsch, b40_aktiv, ist_teilzeit, ignore_capacity):
    plan = []
    current_monday = get_next_monday(pd.to_datetime(start_wunsch))
    
    # --- ONBOARDING ---
    if b40_aktiv:
        b40_start = current_monday - timedelta(days=3)
        b40_ende = b40_start
        plan.append({
            "Modul": "Bildung 4.0 - Virtual Classroom",
            "Kuerzel": "B4.0",
            "Start": b40_start,
            "Ende": b40_ende,
            "Wartetage_davor": 0,
            "Kategorie": "Onboarding"
        })
    
    total_gap_days = 0
    moeglich = True
    fehler_grund = ""
    pmpx_im_paket = PRAXIS_MODUL in modul_reihenfolge
    pmpx_bereits_platziert = False
    tz_guthaben_wochen = 0.0
    modul_counter = 0 
    
    for i, modul in enumerate(modul_reihenfolge):
        while True:
            kurs = finde_naechsten_start(df, modul, current_monday, ignore_capacity)
            if kurs is None:
                moeglich = False
                fehler_grund = f"Kein freier Termin für '{modul}' ab {current_monday.strftime('%d.%m.%Y')} gefunden."
                break
            
            start = kurs['Startdatum']
            ende = kurs['Enddatum']
            gap_days = (start - current_monday).days
            gap_weeks = gap_days // 7
            
            # --- TEILZEIT LOGIK ---
            if ist_teilzeit:
                if gap_weeks >= 1 and tz_guthaben_wochen >= 1:
                    weeks_to_take = min(gap_weeks, int(tz_guthaben_wochen), 4)
                    if weeks_to_take >= 1:
                        tz_ende = get_friday_of_week(current_monday, weeks_to_take)
                        plan.append({
                            "Modul": "Teilzeit-Selbstlernphase (Wartezeit)",
                            "Kuerzel": "TZ-LERNEN",
                            "Start": current_monday,
                            "Ende": tz_ende,
                            "Wartetage_davor": 0,
                            "Kategorie": "Teilzeit"
                        })
                        tz_guthaben_wochen -= weeks_to_take
                        if weeks_to_take > 1: modul_counter = 0
                        current_monday = current_monday + timedelta(weeks=weeks_to_take)
                        continue
                elif gap_weeks == 0 and modul_counter >= 2 and tz_guthaben_wochen >= 1:
                    weeks_to_take = min(int(tz_guthaben_wochen), 4)
                    if weeks_to_take >= 1:
                        tz_ende = get_friday_of_week(current_monday, weeks_to_take)
                        plan.append({
                            "Modul": "Teilzeit-Selbstlernphase",
                            "Kuerzel": "TZ-LERNEN",
                            "Start": current_monday,
                            "Ende": tz_ende,
                            "Wartetage_davor": 0,
                            "Kategorie": "Teilzeit"
                        })
                        tz_guthaben_wochen -= weeks_to_take
                        modul_counter = 0
                        current_monday = current_monday + timedelta(weeks=weeks_to_take)
                        continue

            # --- VOLLZEIT LOGIK ---
            elif gap_weeks >= 1:
                darf_fuellen = (not pmpx_im_paket) or pmpx_bereits_platziert
                if darf_fuellen:
                    weeks_to_take = min(gap_weeks, 2)
                    sl_ende = get_friday_of_week(current_monday, weeks_to_take)
                    plan.append({
                        "Modul": "Indiv. Selbstlernphase",
                        "Kuerzel": "SELBSTLERN",
                        "Start": current_monday,
                        "Ende": sl_ende,
                        "Wartetage_davor": 0,
                        "Kategorie": "Lückenfüller"
                    })
                    current_monday = current_monday + timedelta(weeks=weeks_to_take)
                    continue

            # --- MODUL ---
            total_gap_days += gap_days
            plan.append({
                "Modul": kurs['Modulname'],
                "Kuerzel": modul,
                "Start": start,
                "Ende": ende,
                "Wartetage_davor": gap_days,
                "Kategorie": MODUL_ZU_KAT.get(modul, "Sonstiges")
            })
            
            if ist_teilzeit:
                modul_dauer_wochen = ((ende - start).days + 3) // 7
                tz_guthaben_wochen += (modul_dauer_wochen / 2)
                modul_counter += 1
            
            if modul == PRAXIS_MODUL: pmpx_bereits_platziert = True
            current_monday = get_next_monday(ende + timedelta(days=1))
            break 

        if not moeglich: break

    # --- ENDABRECHNUNG TEILZEIT ---
    if moeglich and ist_teilzeit and tz_guthaben_wochen >= 1:
        weeks_left = int(tz_guthaben_wochen)
        if weeks_left >= 1:
            tz_ende = get_friday_of_week(current_monday, weeks_left)
            plan.append({
                "Modul": "Teilzeit-Selbstlernphase (Abschluss)",
                "Kuerzel": "TZ-LERNEN",
                "Start": current_monday,
                "Ende": tz_ende,
                "Wartetage_davor": 0,
                "Kategorie": "Teilzeit"
            })

    return moeglich, total_gap_days, plan, fehler_grund

def ist_reihenfolge_gueltig(reihenfolge):
    gesehene_module = set()
    for modul in reihenfolge:
        voraussetzung = ABHAENGIGKEITEN.get(modul)
        if voraussetzung:
            if isinstance(voraussetzung, tuple):
                erfuellt = any(v in gesehene_module for v in voraussetzung)
                if not erfuellt: return False
            elif isinstance(voraussetzung, str):
                if voraussetzung in reihenfolge and voraussetzung not in gesehene_module:
                    return False
        gesehene_module.add(modul)
    return True

def check_fehlende_voraussetzungen(gewuenschte_module):
    fehler_liste = []
    auswahl_set = set(gewuenschte_module)
    for modul in gewuenschte_module:
        voraussetzung = ABHAENGIGKEITEN.get(modul)
        if voraussetzung:
            if isinstance(voraussetzung, tuple):
                erfuellt = any(v in auswahl_set for v in voraussetzung)
                if not erfuellt:
                    optionen_str = " oder ".join(voraussetzung)
                    fehler_liste.append(f"Modul '{modul}' benötigt zwingend eines dieser Module: {optionen_str}")
            elif isinstance(voraussetzung, str):
                if voraussetzung not in auswahl_set:
                    fehler_liste.append(f"Modul '{modul}' benötigt '{voraussetzung}'")
    return fehler_liste

# --- SCORE LOGIK ---
def bewertung_sortierung(plan_info):
    echte_module = [x['Kuerzel'] for x in plan_info['plan'] if x['Kuerzel'] not in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]]
    idx = {mod: i for i, mod in enumerate(echte_module)}
    
    soft_score = 0
    
    # PAL sollte möglichst spät kommen (nach PMPX) -> PMPX Index < PAL Index ist gut.
    # Wenn PAL < PMPX -> Schlecht (Punkte)
    pals = ["PAL-E", "PAL-EBM"]
    refs = ["2wo_PMPX", "PSPO1"]
    
    for pal in pals:
        if pal in idx:
            for ref in refs:
                if ref in idx:
                    if idx[pal] < idx[ref]: soft_score += 50
    
    # Late Bloomers
    late = ["IT-TOOLS", "PAL-E", "PAL-EBM"]
    for l in late:
        if l in idx: soft_score -= idx[l] # Je höher Index, desto besser

    # PSM1 vor PSPO1
    if "PSM1" in idx and "PSPO1" in idx:
        if idx["PSM1"] > idx["PSPO1"]: soft_score += 20

    return (plan_info['gaps'], soft_score, plan_info['switches'])

# --- UI ---
st.title("🎓 mycareernow Angebotsplaner")

# --- SIDEBAR ---
st.sidebar.header("📝 Texte & Backup")
if "is_admin" not in st.session_state: st.session_state.is_admin = False

if not st.session_state.is_admin:
    st.sidebar.info("🔒 Bearbeitung gesperrt")
    if pwd := st.sidebar.text_input("Admin-Passwort", type="password"):
        if pwd == ADMIN_PASSWORD:
            st.session_state.is_admin = True
            st.rerun()
        else:
            st.sidebar.error("Falsch")
else:
    st.sidebar.success("🔓 Admin-Modus")
    
    if "DEIN_USER" in GITHUB_RAW_URL: st.sidebar.warning("⚠️ GitHub-Link prüfen!")
    else:
        if st.sidebar.button("🔄 GitHub neu laden"):
            try:
                if os.path.exists(TEXT_FILE): os.remove(TEXT_FILE)
                init_texts_from_github()
                st.sidebar.success("Geladen!")
                st.rerun()
            except Exception as e: st.sidebar.error(f"{e}")

    current = load_texts()
    st.sidebar.download_button("⬇️ Backup (.json)", json.dumps(current, indent=4), "backup.json", "application/json")
    
    if up := st.sidebar.file_uploader("⬆️ Restore", ["json"]):
        save_all_texts_from_upload(up)
        st.sidebar.success("Wiederhergestellt!")

    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state.is_admin = False
        st.rerun()

    st.sidebar.markdown("---")
    all_k = set(ABHAENGIGKEITEN.keys())
    for v in KATEGORIEN_MAPPING.values(): all_k.update(v)
    all_k.update(["B4.0", "SELBSTLERN", "TZ-LERNEN"])
    
    sel = st.sidebar.selectbox("Modul wählen:", sorted(all_k))
    val = load_texts().get(sel, "")
    new_html = st_quill(val, html=True, key=f"q_{sel}")
    if st.sidebar.button("💾 Speichern"):
        save_text(sel, new_html)
        st.sidebar.success("Gespeichert")

# --- MAIN ---
st.write("Lade die Excel-Liste hoch.")
up_file = st.file_uploader("Kursdaten (Excel)", ["xlsx", "csv"])

if up_file:
    try:
        if up_file.name.endswith('.csv'): df = pd.read_csv(up_file, sep=';')
        else: df = pd.read_excel(up_file)
        
        df.columns = [c.strip() for c in df.columns]
        df['Startdatum'] = pd.to_datetime(df['Startdatum'], dayfirst=True)
        df['Enddatum'] = pd.to_datetime(df['Enddatum'], dayfirst=True)
        df['Kuerzel'] = df['Kuerzel'].astype(str).str.strip()
        
        for c in ['Klassenanzahl', 'Teilnehmeranzahl']:
            if c not in df.columns: df[c] = 0
            df[c] = df[c].fillna(0).astype(int)
            
        c1, c2 = st.columns(2)
        with c1: start_d = st.date_input("Startdatum (Fachmodul)", date(2026, 2, 9), format="DD.MM.YYYY")
        with c2: mods = st.multiselect("Module:", sorted(df['Kuerzel'].unique()))
        
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        skip_b40 = c1.checkbox("Ohne B4.0")
        ignore_dep = c2.checkbox("Abhängigkeiten ignorieren")
        is_tz = c3.checkbox("Teilzeit")
        ignore_cap = c4.checkbox("Teilnehmerzahl ignorieren", value=True, help="Bucht auch volle Kurse. Wichtig für lückenlose Planung!")

        if st.button("Angebot berechnen"):
            if not mods: st.warning("Keine Module gewählt.")
            else:
                errs = check_fehlende_voraussetzungen(mods)
                if errs and not ignore_dep:
                    st.error("Fehlende Voraussetzungen:")
                    for e in errs: st.write(f"- {e}")
                else:
                    if errs: st.warning("Ignoriere Voraussetzungen.")
                    
                    with st.spinner("Rechne..."):
                        plans = []
                        for r in itertools.permutations(mods):
                            if not ist_reihenfolge_gueltig(r): continue
                            possible, gaps, p, _ = berechne_plan(df, r, pd.to_datetime(start_d), not skip_b40, is_tz, ignore_cap)
                            if possible:
                                sw = berechne_kategorie_wechsel(p)
                                plans.append({"gaps": gaps, "switches": sw, "plan": p})
                        
                        if not plans: st.error("Kein Plan möglich.")
                        else:
                            plans.sort(key=bewertung_sortierung)
                            best = plans[0]
                            st.success("Angebot erstellt!")
                            
                            if best['gaps'] > 0: st.warning(f"{best['gaps']} Lückentage.")
                            else: st.info("✅ Lückenlos.")
                            
                            st.subheader("Übersicht")
                            col1, col2 = st.columns(2)
                            col1.markdown(f"**Start:** {best['plan'][0]['Start'].strftime('%d.%m.%Y')}")
                            col2.markdown(f"**Ende:** {best['plan'][-1]['Ende'].strftime('%d.%m.%Y')}")
                            st.info(" -> ".join([x['Kuerzel'] for x in best['plan']]))
                            
                            # TABLE
                            data = []
                            for x in best['plan']:
                                info = ""
                                if x['Kuerzel'] == "SELBSTLERN": info = "🔹 Lücke"
                                elif x['Wartetage_davor'] > 3: info = f"⚠️ {x['Wartetage_davor']} Tage Gap"
                                data.append({"Modul": x['Modul'], "Von": x['Start'].strftime('%d.%m.%Y'), "Bis": x['Ende'].strftime('%d.%m.%Y'), "Info": info})
                            st.table(data)
                            
                            # COPY
                            txts = load_texts()
                            html_clip = ""
                            for x in best['plan']:
                                t = txts.get(x['Kuerzel'], "")
                                if not t: t = f"<p><strong>{x['Modul']}</strong></p>"
                                html_clip += f"{t}<br>"
                            
                            st.subheader("📋 Copy für HubSpot")
                            components.html(f"""
                            <div id="copy_box" style="border:1px solid #ddd; padding:10px; height:200px; overflow:auto;">{html_clip}</div>
                            <button onclick="copyIt()" style="margin-top:10px; padding:10px; background:#4CAF50; color:white; border:none; border-radius:4px; cursor:pointer;">Kopieren</button>
                            <script>
                            function copyIt() {{
                                var r = document.createRange();
                                r.selectNode(document.getElementById("copy_box"));
                                window.getSelection().removeAllRanges();
                                window.getSelection().addRange(r);
                                document.execCommand('copy');
                                window.getSelection().removeAllRanges();
                                alert('Kopiert!');
                            }}
                            </script>
                            """, height=300)

    except Exception as e: st.error(f"Fehler: {e}")