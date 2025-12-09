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

# --- HELPER FUNKTIONEN (Allgemein) ---

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

# --- PERFORMANCE HELPER (NEU) ---

def create_course_index(df):
    """
    Wandelt den DataFrame in ein Dictionary um.
    Struktur: { 'PSK': [ {Start:..., Ende:..., IsFull:...}, ...sortiert... ], ... }
    Das beschleunigt den Zugriff von O(N) auf O(1).
    """
    index = {}
    
    # Vorab-Berechnung der Auslastung für jede Zeile
    def check_full(row):
        k = row.get('Klassenanzahl', 0)
        t = row.get('Teilnehmeranzahl', 0)
        if pd.isna(k) or k == 0: return False
        limit = k * MAX_TEILNEHMER_PRO_KLASSE
        curr = 0 if pd.isna(t) else t
        return curr >= limit

    # Konvertierung zu Dict records
    records = df.to_dict('records')
    
    for row in records:
        k = str(row['Kuerzel']).strip()
        if k not in index:
            index[k] = []
        
        # Datensatz bereinigen und hinzufügen
        entry = {
            'Startdatum': row['Startdatum'],
            'Enddatum': row['Enddatum'],
            'Modulname': row['Modulname'],
            'is_full': check_full(row)
        }
        index[k].append(entry)
        
    # Sortieren pro Modul nach Datum
    for k in index:
        index[k].sort(key=lambda x: x['Startdatum'])
        
    return index

def find_next_course_fast(course_index, modul_kuerzel, ab_datum, ignore_capacity=False):
    """
    Sucht im Index statt im DataFrame. Extrem schnell.
    """
    target_date = get_next_monday(pd.to_datetime(ab_datum))
    
    candidates = course_index.get(modul_kuerzel, [])
    
    for course in candidates:
        # 1. Datums-Check
        if course['Startdatum'] >= target_date:
            # 2. Kapazitäts-Check
            if ignore_capacity or not course['is_full']:
                return course
                
    return None

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

def berechne_plan_fuer_permutation_fast(course_index, modul_reihenfolge, start_wunsch, b40_aktiv, ist_teilzeit, ignore_capacity):
    """
    Nutzt den schnellen Index statt DataFrame.
    """
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
    gap_events = 0
    tz_guthaben_wochen = 0.0
    modul_counter = 0 
    
    for modul in modul_reihenfolge:
        # HIER IST DER UNTERSCHIED: Fast Lookup
        kurs = find_next_course_fast(course_index, modul, current_monday, ignore_capacity)
        
        if kurs is None:
            return False, 0, 0, [], f"Kein Termin für {modul}"
            
        start = kurs['Startdatum']
        ende = kurs['Enddatum']
        gap_days = (start - current_monday).days
        gap_weeks = gap_days // 7
        
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
            if isinstance(voraussetzung, tuple):
                if not any(v in gesehene_module for v in voraussetzung):
                    return False
            elif isinstance(voraussetzung, str):
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
    total_score = 0
    
    # 0. Startmodul Check
    wunsch_start = plan_info.get('wunsch_start')
    plan = plan_info['plan']
    erstes_echtes_modul = None
    for item in plan:
        if item['Kuerzel'] not in ["B4.0", "SELBSTLERN", "TZ-LERNEN"]:
            erstes_echtes_modul = item['Kuerzel']
            break
            
    if wunsch_start and erstes_echtes_modul:
        if erstes_echtes_modul != wunsch_start:
            total_score += 2000 
    
    # 1. Switches
    switches = plan_info['switches']
    total_score += (switches * 10)
    
    # 2. Gaps
    gap_events = plan_info['gap_events']
    total_gap_weeks = plan_info['gap_weeks']
    total_score += (gap_events * 15) + total_gap_weeks
    
    # 3. Soft-Skills
    echte_module = [x['Kuerzel'] for x in plan if x['Kuerzel'] not in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]]
    idx = {mod: i for i, mod in enumerate(echte_module)}
    
    pm_module_refs = ["PSM1", "PSM2", "PSPO1", "PSPO2", "SPS", "PAL-E", "PAL-EBM", "PSK", "IPMA", "IT-TOOLS"]
    if PRAXIS_MODUL in idx:
        pmpx_pos = idx[PRAXIS_MODUL]
        for pm in pm_module_refs:
            if pm in idx:
                if pmpx_pos < idx[pm]:
                    total_score += 0.1 
    
    if "SQM" in idx and "PQM" in idx:
        if idx["PQM"] < idx["SQM"]:
            total_score += 2.0

    return total_score

# --- UI ---
st.title("🎓 mycareernow Angebotsplaner (High Speed)")

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

        # INDEX ERSTELLEN (DAS IST DER TURBO)
        course_index = create_course_index(df)

        c1, c2 = st.columns(2)
        with c1: start_d = st.date_input("Startdatum", date(2026, 2, 9), format="DD.MM.YYYY")
        with c2: mods = st.multiselect("Module", sorted(df['Kuerzel'].unique()))
        
        st.markdown("---")
        
        wunsch_start_modul = None
        use_start_modul = st.checkbox("🏁 Startmodul festlegen (Priorisiert)")
        if use_start_modul:
            if mods:
                wunsch_start_modul = st.selectbox("Wähle das Startmodul:", mods)
            else:
                st.warning("Bitte erst Module oben auswählen.")

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
                    
                    with st.spinner("Simuliere (Turbo-Modus)..."):
                        plans = []
                        # Wir nutzen den Index für die Suche
                        for r in itertools.permutations(mods):
                            if not ignore_dep and not ist_reihenfolge_gueltig(r):
                                continue
                            
                            poss, gap_weeks, gap_events, p, _ = berechne_plan_fuer_permutation_fast(
                                course_index, r, pd.to_datetime(start_d), not skip_b40, is_tz, ignore_cap
                            )
                            
                            if poss:
                                sw = berechne_kategorie_wechsel(p)
                                plans.append({
                                    "gap_weeks": gap_weeks, 
                                    "gap_events": gap_events,
                                    "switches": sw, 
                                    "plan": p,
                                    "wunsch_start": wunsch_start_modul
                                })
                        
                        if not plans: st.error("Kein Plan möglich.")
                        else:
                            plans.sort(key=bewertung_sortierung)
                            best = plans[0]
                            
                            st.success("Angebot erstellt!")
                            
                            if best['gap_events'] == 0: 
                                st.info("✅ Lückenlos!")
                            else: 
                                st.warning(f"Plan enthält {best['gap_events']} Lücke(n).")
                                
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