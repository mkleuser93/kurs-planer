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

# HIER DEINEN GITHUB RAW LINK EINFÜGEN
GITHUB_RAW_URL = "https://raw.githubusercontent.com/mkleuser93/kurs-planer/refs/heads/main/modul_texte_backup.json"

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
# Tuple = ODER-Logik
ABHAENGIGKEITEN = {
    "PSM2": "PSM1",
    "PSPO1": "PSM1", 
    "PSPO2": "PSPO1", # Änderung: Benötigt PSPO1
    "SPS": "PSM1",
    "PSK": "PSM1",
    "PAL-E": "PSM1",
    "PAL-EBM": "PSM1",
    "AKI-EX": "AKI",
    "2wo_PMPX": ("PSM1", "IPMA") # PSM1 ODER IPMA
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
    if not os.path.exists(TEXT_FILE): return {}
    with open(TEXT_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_text(kuerzel, text):
    data = load_texts()
    data[kuerzel] = text
    with open(TEXT_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

def save_all_texts_from_upload(uploaded_json):
    data = json.load(uploaded_json)
    with open(TEXT_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

def get_next_monday(d):
    wd = d.weekday() 
    if wd == 0: return d
    return d + timedelta(days=(7 - wd))

def get_friday_of_week(monday_date, weeks_duration=1):
    return monday_date + timedelta(weeks=weeks_duration) - timedelta(days=3)

def finde_naechsten_start(df, modul_kuerzel, ab_datum, ignore_capacity=False):
    ab_datum = get_next_monday(pd.to_datetime(ab_datum))
    mask = (df['Kuerzel'] == modul_kuerzel) & (df['Startdatum'] >= ab_datum)
    df_filtered = df[mask].copy()
    
    if not ignore_capacity:
        if 'Teilnehmeranzahl' in df_filtered.columns and 'Klassenanzahl' in df_filtered.columns:
            def is_course_full(row):
                klassen = row['Klassenanzahl']
                teilnehmer = row['Teilnehmeranzahl']
                # Wenn Klassenanzahl 0 oder leer -> Gehe von unbegrenzter Kapazität aus
                if pd.isna(klassen) or klassen == 0: return False 
                limit = klassen * MAX_TEILNEHMER_PRO_KLASSE
                current = 0 if pd.isna(teilnehmer) else teilnehmer
                return current >= limit

            df_filtered['is_full'] = df_filtered.apply(is_course_full, axis=1)
            df_filtered = df_filtered[~df_filtered['is_full']]

    if df_filtered.empty: return None
    return df_filtered.sort_values(by='Startdatum').iloc[0]

def berechne_kategorie_wechsel(plan):
    wechsel = 0
    letzte_kat = None
    for eintrag in plan:
        if eintrag['Kuerzel'] in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]: continue
        kuerzel = eintrag['Kuerzel']
        aktuelle_kat = MODUL_ZU_KAT.get(kuerzel, "Sonstiges")
        # Beim ersten Modul gibt es keinen Wechsel
        if letzte_kat is not None and aktuelle_kat != letzte_kat:
            wechsel += 1
        letzte_kat = aktuelle_kat
    return wechsel

def berechne_plan_fuer_permutation(df, modul_reihenfolge, start_wunsch, b40_aktiv, ist_teilzeit, ignore_capacity):
    plan = []
    current_monday = get_next_monday(pd.to_datetime(start_wunsch))
    
    if b40_aktiv:
        b40_start = current_monday - timedelta(days=3)
        plan.append({
            "Modul": "Bildung 4.0 - Virtual Classroom",
            "Kuerzel": "B4.0",
            "Start": b40_start,
            "Ende": b40_start,
            "Wartetage_davor": 0,
            "Kategorie": "Onboarding"
        })
    
    total_gap_weeks = 0
    gap_events = 0 # Anzahl der Lücken (unabhängig von Dauer)
    tz_guthaben_wochen = 0.0
    modul_counter = 0 
    
    for modul in modul_reihenfolge:
        kurs = finde_naechsten_start(df, modul, current_monday, ignore_capacity)
        
        if kurs is None:
            return False, 0, 0, [], f"Kein Termin für {modul}"
            
        start = kurs['Startdatum']
        ende = kurs['Enddatum']
        gap_days = (start - current_monday).days
        gap_weeks = gap_days // 7
        
        # Lücken behandeln
        if gap_weeks >= 1:
            if ist_teilzeit and tz_guthaben_wochen >= 1:
                weeks_to_take = min(gap_weeks, int(tz_guthaben_wochen))
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
                gap_days -= (weeks_to_take * 7) 
                current_monday += timedelta(weeks=weeks_to_take)
                
            gap_weeks_rest = gap_days // 7
            if gap_weeks_rest >= 1:
                # Hier entsteht eine echte Lücke ("SELBSTLERN")
                gap_events += 1
                total_gap_weeks += gap_weeks_rest
                
                sl_ende = get_friday_of_week(current_monday, gap_weeks_rest)
                plan.append({
                    "Modul": "Indiv. Selbstlernphase",
                    "Kuerzel": "SELBSTLERN",
                    "Start": current_monday,
                    "Ende": sl_ende,
                    "Wartetage_davor": 0,
                    "Kategorie": "Lückenfüller"
                })
                current_monday += timedelta(weeks=gap_weeks_rest)

        # Modul eintragen
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
            
        current_monday = get_next_monday(ende + timedelta(days=1))

    if ist_teilzeit and tz_guthaben_wochen >= 1:
        weeks_left = int(tz_guthaben_wochen)
        tz_ende = get_friday_of_week(current_monday, weeks_left)
        plan.append({
            "Modul": "Teilzeit-Selbstlernphase (Abschluss)",
            "Kuerzel": "TZ-LERNEN",
            "Start": current_monday,
            "Ende": tz_ende,
            "Wartetage_davor": 0,
            "Kategorie": "Teilzeit"
        })

    return True, total_gap_weeks, gap_events, plan, ""

def ist_reihenfolge_gueltig(reihenfolge):
    gesehene_module = set()
    for modul in reihenfolge:
        voraussetzung = ABHAENGIGKEITEN.get(modul)
        if voraussetzung:
            if isinstance(voraussetzung, tuple): # OR
                if not any(v in gesehene_module for v in voraussetzung):
                    return False
            elif isinstance(voraussetzung, str): # AND
                if voraussetzung in reihenfolge and voraussetzung not in gesehene_module:
                    return False
        gesehene_module.add(modul)
    return True

def check_fehlende_voraussetzungen(gewuenschte_module):
    fehler = []
    auswahl = set(gewuenschte_module)
    for m in gewuenschte_module:
        req = ABHAENGIGKEITEN.get(m)
        if req:
            if isinstance(req, tuple):
                if not any(r in auswahl for r in req):
                    fehler.append(f"{m} benötigt eines von: {' / '.join(req)}")
            elif isinstance(req, str):
                if req not in auswahl:
                    fehler.append(f"{m} benötigt {req}")
    return fehler

# --- SCORING SYSTEM ---
def bewertung_sortierung(plan_info):
    """
    Regelwerk:
    1 Wechsel < 1 Lücke < 2 Wechsel
    
    Wir nutzen ein Penalty-System:
    - Penalty pro Switch = 10
    - Penalty pro Gap-Event = 15 (plus kleiner Zuschlag für Dauer)
    
    Beispiele:
    1 Switch (10) vs 1 Gap (15) -> Switch gewinnt (kleinerer Score).
    1 Gap (15) vs 2 Switches (20) -> Gap gewinnt.
    """
    
    # 1. Switches
    switches = plan_info['switches']
    penalty_switches = switches * 10
    
    # 2. Gaps
    gap_events = plan_info['gap_events']
    total_gap_weeks = plan_info['gap_weeks']
    # Basisstrafe 15 pro Lücke + 1 pro Woche Dauer (damit kurze Lücken besser sind als lange)
    penalty_gaps = (gap_events * 15) + total_gap_weeks
    
    # 3. Soft-Skills (PMPX Position etc.)
    # Sollte nur greifen, wenn Score sonst identisch ist.
    # Wir geben hier sehr kleine Strafen (< 1 Punkt), damit die Hauptlogik nicht gestört wird.
    soft_score = 0
    
    plan = plan_info['plan']
    echte_module = [x['Kuerzel'] for x in plan if x['Kuerzel'] not in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]]
    idx = {mod: i for i, mod in enumerate(echte_module)}
    
    # PMPX sollte spät kommen -> Strafe wenn andere PM Module danach kommen
    pm_module_refs = ["PSM1", "PSM2", "PSPO1", "PSPO2", "SPS", "PAL-E", "PAL-EBM", "PSK", "IPMA", "IT-TOOLS"]
    if PRAXIS_MODUL in idx:
        pmpx_pos = idx[PRAXIS_MODUL]
        for pm in pm_module_refs:
            if pm in idx:
                if pmpx_pos < idx[pm]:
                    soft_score += 0.1 # Minimaler Impact
    
    total_score = penalty_switches + penalty_gaps + soft_score
    return total_score

# --- UI ---
st.title("🎓 mycareernow Angebotsplaner")

st.sidebar.header("📝 Texte & Backup")
if "is_admin" not in st.session_state: st.session_state.is_admin = False

if not st.session_state.is_admin:
    st.sidebar.info("🔒 Bearbeitung gesperrt")
    if p := st.sidebar.text_input("Passwort", type="password"):
        if p == ADMIN_PASSWORD:
            st.session_state.is_admin = True
            st.rerun()
else:
    st.sidebar.success("🔓 Admin")
    if "DEIN_USER" in GITHUB_RAW_URL: st.sidebar.warning("⚠️ GitHub-Link fehlt")
    elif st.sidebar.button("🔄 Texte von GitHub laden"):
        if os.path.exists(TEXT_FILE): os.remove(TEXT_FILE)
        init_texts_from_github()
        st.rerun()
        
    cur = load_texts()
    st.sidebar.download_button("⬇️ Backup", json.dumps(cur, indent=4), "backup.json", "application/json")
    if u := st.sidebar.file_uploader("⬆️ Restore", ["json"]): save_all_texts_from_upload(u); st.sidebar.success("OK")
    
    if st.sidebar.button("Logout"): st.session_state.is_admin = False; st.rerun()
    
    st.sidebar.markdown("---")
    all_k = set(ABHAENGIGKEITEN.keys()).union({x for v in KATEGORIEN_MAPPING.values() for x in v})
    all_k.update(["B4.0", "SELBSTLERN", "TZ-LERNEN"])
    sel = st.sidebar.selectbox("Editor", sorted(all_k))
    val = load_texts().get(sel, "")
    nh = st_quill(val, html=True, key=f"q_{sel}")
    if st.sidebar.button("💾"): save_text(sel, nh); st.sidebar.success("Gespeichert")

st.write("Lade die Excel-Liste hoch.")
up = st.file_uploader("Kursdaten", ["xlsx", "csv"])

if up:
    try:
        if up.name.endswith('.csv'): df = pd.read_csv(up, sep=';')
        else: df = pd.read_excel(up)
        
        df.columns = [c.strip() for c in df.columns]
        df['Startdatum'] = pd.to_datetime(df['Startdatum'], dayfirst=True)
        df['Enddatum'] = pd.to_datetime(df['Enddatum'], dayfirst=True)
        df['Kuerzel'] = df['Kuerzel'].astype(str).str.strip()
        
        for c in ['Klassenanzahl', 'Teilnehmeranzahl']:
            if c not in df.columns: df[c] = 0
            df[c] = df[c].fillna(0).astype(int)

        c1, c2 = st.columns(2)
        with c1: start_d = st.date_input("Startdatum", date(2026, 2, 9), format="DD.MM.YYYY")
        with c2: mods = st.multiselect("Module", sorted(df['Kuerzel'].unique()))
        
        st.markdown("---")
        c1, c2, c3, c4 = st.columns(4)
        skip_b40 = c1.checkbox("Ohne B4.0")
        ignore_dep = c2.checkbox("Abhängigkeiten ignorieren")
        is_tz = c3.checkbox("Teilzeit")
        ignore_cap = c4.checkbox("Teilnehmerzahl ignorieren", value=True, help="Bucht auch volle Kurse")

        if st.button("Angebot berechnen"):
            if not mods: st.warning("Keine Module gewählt.")
            else:
                errs = check_fehlende_voraussetzungen(mods)
                if errs and not ignore_dep:
                    st.error("Fehler:"); [st.write(f"- {e}") for e in errs]
                else:
                    if errs: st.warning("Ignoriere Voraussetzungen.")
                    
                    with st.spinner("Simuliere alle Kombinationen..."):
                        plans = []
                        for r in itertools.permutations(mods):
                            if not ignore_dep and not ist_reihenfolge_gueltig(r):
                                continue
                            
                            poss, gap_weeks, gap_events, p, _ = berechne_plan_fuer_permutation(
                                df, r, pd.to_datetime(start_d), not skip_b40, is_tz, ignore_cap
                            )
                            
                            if poss:
                                sw = berechne_kategorie_wechsel(p)
                                plans.append({
                                    "gap_weeks": gap_weeks, 
                                    "gap_events": gap_events,
                                    "switches": sw, 
                                    "plan": p
                                })
                        
                        if not plans: st.error("Kein Plan möglich.")
                        else:
                            plans.sort(key=bewertung_sortierung)
                            best = plans[0]
                            
                            st.success("Angebot erstellt!")
                            
                            if best['gap_events'] == 0: 
                                st.info("✅ Lückenlos!")
                            else: 
                                st.warning(f"Plan enthält {best['gap_events']} Lücke(n) ({best['gap_weeks']} Wochen).")
                                
                            s_date = best['plan'][0]['Start'].strftime('%d.%m.%Y')
                            e_date = best['plan'][-1]['Ende'].strftime('%d.%m.%Y')
                            
                            col1, col2 = st.columns(2)
                            col1.markdown(f"**Start:** {s_date}")
                            col2.markdown(f"**Ende:** {e_date}")
                            
                            k_chain = " -> ".join([x['Kuerzel'] for x in best['plan']])
                            st.info(f"**Ablauf:** {k_chain}")
                            
                            t_data = []
                            for x in best['plan']:
                                n = ""
                                if x['Kuerzel']=="SELBSTLERN": n="🔹 Lücke (Selbstlernzeit)"
                                elif x['Wartetage_davor'] > 3: n=f"⚠️ {x['Wartetage_davor']} Tage Gap"
                                t_data.append({
                                    "Modul": x['Modul'], 
                                    "Von": x['Start'].strftime('%d.%m.%Y'),
                                    "Bis": x['Ende'].strftime('%d.%m.%Y'),
                                    "Info": n
                                })
                            st.table(t_data)
                            
                            txts = load_texts()
                            html = ""
                            for x in best['plan']:
                                t = txts.get(x['Kuerzel'], "")
                                if not t: t = f"<p><strong>{x['Modul']}</strong></p>"
                                html += f"{t}<br>"
                                
                            st.subheader("📋 Copy für HubSpot")
                            components.html(f"""
                            <div id="cb" style="border:1px solid #ddd;padding:10px;height:200px;overflow:auto;">{html}</div>
                            <button onclick="document.getSelection().selectAllChildren(document.getElementById('cb')); document.execCommand('copy'); alert('Kopiert!');" style="margin-top:10px;padding:8px;background:#4CAF50;color:white;border:none;border-radius:4px;cursor:pointer;">Kopieren</button>
                            """, height=300)

    except Exception as e: st.error(f"Fehler: {e}")