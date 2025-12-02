import streamlit as st
import pandas as pd
from datetime import timedelta, date
import itertools
import json
import os

# --- KONFIGURATION ---
st.set_page_config(page_title="mycareernow Planer", page_icon="📅", layout="wide")

MAX_TEILNEHMER_PRO_KLASSE = 20
TEXT_FILE = "modul_texte.json"

ABHAENGIGKEITEN = {
    "PSM2": "PSM1",
    "PSPO1": "PSM1",
    "PSPO2": "PSM1",
    "SPS": "PSM1",
    "PSK": "PSM1",
    "PAL-E": "PSM1",
    "PAL-EBM": "PSM1",
    "AKI-EX": "AKI",
    "IT-TOOLS": "PMPX",
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

# --- HELPER FUNKTIONEN (TEXTE LADEN/SPEICHERN) ---

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

# --- HELPER FUNKTIONEN (LOGIK) ---

def get_next_monday(d):
    wd = d.weekday() 
    if wd == 0: return d
    return d + timedelta(days=(7 - wd))

def get_friday_of_week(monday_date, weeks_duration=1):
    return monday_date + timedelta(weeks=weeks_duration) - timedelta(days=3)

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    ab_datum = get_next_monday(pd.to_datetime(ab_datum))
    
    if 'Teilnehmeranzahl' in df.columns and 'Klassenanzahl' in df.columns:
        moegliche_termine = df[
            (df['Kuerzel'] == modul_kuerzel) & 
            (df['Startdatum'] >= ab_datum) &
            (df['Teilnehmeranzahl'] < (df['Klassenanzahl'] * MAX_TEILNEHMER_PRO_KLASSE))
        ].sort_values(by='Startdatum')
    else:
        moegliche_termine = df[
            (df['Kuerzel'] == modul_kuerzel) & 
            (df['Startdatum'] >= ab_datum)
        ].sort_values(by='Startdatum')
    
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

def berechne_plan(df, modul_reihenfolge, start_wunsch, b40_aktiv, ist_teilzeit):
    plan = []
    current_monday = get_next_monday(pd.to_datetime(start_wunsch))
    
    # --- ONBOARDING (B4.0) ---
    if b40_aktiv:
        b40_start = current_monday - timedelta(days=3) # Freitag
        b40_ende = b40_start # 1 Tag
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
            kurs = finde_naechsten_start(df, modul, current_monday)
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
            if voraussetzung not in auswahl_set:
                fehler_liste.append(f"Modul '{modul}' benötigt '{voraussetzung}'")
    return fehler_liste

def bewertung_sortierung(plan_info):
    echte_module = [x['Kuerzel'] for x in plan_info['plan'] if x['Kuerzel'] not in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]]
    try:
        pmpx_index = echte_module.index(PRAXIS_MODUL)
    except ValueError:
        pmpx_index = -1 
    return (plan_info['gaps'], plan_info['switches'], -pmpx_index)

# --- UI LOGIK ---

st.title("🎓 mycareernow Angebotsplaner")

# --- SIDEBAR: TEXT EDITOR ---
st.sidebar.header("📝 Texte verwalten")
st.sidebar.info("Hier kannst du die Snippets aus HubSpot einfügen. Sie werden automatisch gespeichert.")

# Liste aller bekannten Kürzel (Standard + was schon in der Datei ist)
all_known_kuerzel = set(ABHAENGIGKEITEN.keys())
for k_list in KATEGORIEN_MAPPING.values():
    for k in k_list:
        all_known_kuerzel.add(k)
all_known_kuerzel.add("B4.0")
all_known_kuerzel.add("SELBSTLERN")
all_known_kuerzel.add("TZ-LERNEN")

# Sortierte Liste für Dropdown
sorted_kuerzel = sorted(list(all_known_kuerzel))

# Editor Logik
selected_modul = st.sidebar.selectbox("Modul wählen:", sorted_kuerzel)
current_texts = load_texts()
current_text_value = current_texts.get(selected_modul, "")

new_text = st.sidebar.text_area(f"Text für {selected_modul} (Markdown/Text):", value=current_text_value, height=300)

if st.sidebar.button("💾 Text Speichern"):
    save_text(selected_modul, new_text)
    st.sidebar.success(f"Text für {selected_modul} gespeichert!")
    st.rerun() # Neuladen damit die Änderungen sofort wirksam sind

# --- HAUPTBEREICH ---

st.write("Lade die Excel-Liste hoch (Nur für Termine). Texte werden links verwaltet.")
uploaded_file = st.file_uploader("Kursdaten (Excel) hochladen", type=["xlsx", "csv"])

if uploaded_file:
    try:
        # Kursdaten laden
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=';')
        else:
            xls = pd.ExcelFile(uploaded_file)
            df = pd.read_excel(xls, sheet_name=0) 

        # Bereinigung
        df.columns = [c.strip() for c in df.columns]
        df['Startdatum'] = pd.to_datetime(df['Startdatum'], dayfirst=True)
        df['Enddatum'] = pd.to_datetime(df['Enddatum'], dayfirst=True)
        df['Kuerzel'] = df['Kuerzel'].astype(str).str.strip()
        
        if "Klassenanzahl" not in df.columns: df['Klassenanzahl'] = 1
        else: df['Klassenanzahl'] = df['Klassenanzahl'].fillna(1).astype(int)
            
        if "Teilnehmeranzahl" not in df.columns: df['Teilnehmeranzahl'] = 0
        else: df['Teilnehmeranzahl'] = df['Teilnehmeranzahl'].fillna(0).astype(int)

        verfuegbare_module = sorted(df['Kuerzel'].unique())
        
        col1, col2 = st.columns(2)
        with col1:
            st.info("ℹ️ Datum ist Start des ERSTEN Fachmoduls.")
            start_datum = st.date_input("Gewünschter Start Fachmodul", date(2026, 2, 9))
        
        with col2:
            gewuenschte_module = st.multiselect("Fachmodule auswählen:", verfuegbare_module)

        st.markdown("---")
        
        c1, c2, c3 = st.columns(3)
        with c1: skip_b40 = st.checkbox("B4.0 überspringen")
        with c2: ignore_deps = st.checkbox("Abhängigkeiten ignorieren")
        with c3: is_teilzeit = st.checkbox("Teilzeit-Modell (50% mehr Zeit)")

        if st.button("Angebot berechnen"):
            if not gewuenschte_module:
                st.warning("Bitte wähle mindestens ein Fachmodul aus.")
            else:
                fehlende_voraussetzungen = check_fehlende_voraussetzungen(gewuenschte_module)
                
                if fehlende_voraussetzungen and not ignore_deps:
                    st.error("❌ Berechnung gestoppt: Fehlende Voraussetzungen!")
                    for fehler in fehlende_voraussetzungen: st.write(f"- {fehler}")
                    st.stop()
                
                if fehlende_voraussetzungen and ignore_deps:
                    st.warning(f"Ignoriere Abhängigkeiten: {', '.join(fehlende_voraussetzungen)}")

                with st.spinner("Berechne beste Kombination..."):
                    gueltige_plaene = []
                    letzter_fehler = ""
                    
                    for reihenfolge in itertools.permutations(gewuenschte_module):
                        if not ist_reihenfolge_gueltig(reihenfolge): continue
                        
                        b40_aktiv = not skip_b40
                        moeglich, gaps, plan, fehler = berechne_plan(df, reihenfolge, pd.to_datetime(start_datum), b40_aktiv, is_teilzeit)
                        
                        if moeglich:
                            switches = berechne_kategorie_wechsel(plan)
                            gueltige_plaene.append({"gaps": gaps, "switches": switches, "plan": plan})
                        else:
                            letzter_fehler = fehler
                    
                    if not gueltige_plaene:
                        st.error("Kein Plan möglich!")
                        st.info(f"Grund: {letzter_fehler}")
                    else:
                        gueltige_plaene.sort(key=bewertung_sortierung)
                        bester = gueltige_plaene[0]
                        
                        gesamt_start = bester['plan'][0]['Start']
                        gesamt_ende = bester['plan'][-1]['Ende']
                        
                        st.success(f"Angebot erstellt! (Teilzeit: {'JA' if is_teilzeit else 'NEIN'})")
                        
                        # --- TABELLE ANZEIGEN ---
                        display_data = []
                        for item in bester['plan']:
                            start_str = item['Start'].strftime('%d.%m.%Y')
                            ende_str = item['Ende'].strftime('%d.%m.%Y')
                            hinweis = ""
                            if item['Kuerzel'] == "SELBSTLERN": hinweis = "🔹 Lückenfüller"
                            elif item['Kuerzel'] == "TZ-LERNEN": hinweis = "⏱️ Teilzeit-Lernen"
                            elif item['Kuerzel'] == "B4.0": hinweis = "🚀 Onboarding"
                            elif item['Wartetage_davor'] > 3: hinweis = f"⚠️ {item['Wartetage_davor']} Tage Rest-Lücke"
                            
                            display_data.append({
                                "Kategorie": item['Kategorie'],
                                "Von": start_str,
                                "Bis": ende_str,
                                "Modul": item['Modul'],
                                "Info": hinweis
                            })
                        st.table(display_data)

                        # --- HUBSPOT VORSCHAU ---
                        st.subheader("📋 Vorschau für HubSpot (Markieren & Kopieren)")
                        st.info("👇 Markiere den Text im Kasten unten einfach mit der Maus (so wie auf einer Webseite) und kopiere ihn. HubSpot versteht diese Formatierung.")
                        
                        TEXT_MAPPING = load_texts()

                        with st.container(border=True):
                            # Header
                            st.markdown(f"**Gesamtzeitraum:** {gesamt_start.strftime('%d.%m.%Y')} - {gesamt_ende.strftime('%d.%m.%Y')}")
                            if is_teilzeit:
                                st.markdown("*(Teilzeit-Modell)*")
                            st.markdown("---")
                            
                            # Module
                            for item in bester['plan']:
                                k = item['Kuerzel']
                                start_s = item['Start'].strftime('%d.%m.%Y')
                                ende_s = item['Ende'].strftime('%d.%m.%Y')
                                modul_name = item['Modul']
                                
                                # Text laden
                                beschreibung = TEXT_MAPPING.get(k, "")
                                if not beschreibung:
                                    # Standardtexte falls leer
                                    if k == "B4.0": beschreibung = "Einführung in den virtuellen Klassenraum."
                                    elif k == "SELBSTLERN": beschreibung = "Individuelle Selbstlernphase."
                                    elif k == "TZ-LERNEN": beschreibung = "Teilzeit-Selbstlernphase."
                                    else: beschreibung = "_Keine Beschreibung hinterlegt._"

                                # RENDER BLOCK
                                # Wir nutzen HTML/Markdown Mix für beste Optik
                                st.markdown(f"#### 🗓️ {start_s} - {ende_s} | {modul_name} ({k})")
                                st.markdown(beschreibung)
                                st.markdown("---")

    except Exception as e:
        st.error(f"Fehler beim Lesen der Datei: {e}")

else:
    st.info("Bitte lade zuerst die kursdaten.xlsx hoch.")