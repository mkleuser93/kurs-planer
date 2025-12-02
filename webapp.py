import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import timedelta, date
import itertools
import json
import os
import locale
from streamlit_quill import st_quill

# --- KONFIGURATION ---
st.set_page_config(page_title="mycareernow Planer", page_icon="📅", layout="wide")

# Locale setzen (Versuch auf Deutsch für Wochentage)
try:
    locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'de_DE')
    except:
        pass

MAX_TEILNEHMER_PRO_KLASSE = 20
TEXT_FILE = "modul_texte.json"
ADMIN_PASSWORD = "mycarrEer.admin!186"

# --- ABHÄNGIGKEITEN ---
# WICHTIG: 2wo_PMPX akzeptiert jetzt PSM1 ODER IPMA
ABHAENGIGKEITEN = {
    "PSM2": "PSM1",
    "PSPO1": "PSM1", 
    "PSPO2": "PSPO1", 
    "SPS": "PSM1",
    "PSK": "PSM1",
    "PAL-E": "PSM1",
    "PAL-EBM": "PSM1",
    "AKI-EX": "AKI",
    "2wo_PMPX": ("PSM1", "IPMA") # Tuple bedeutet: Eines von beiden reicht
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

# --- HELPER FUNKTIONEN (TEXTE) ---

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
    # Sicherstellen, dass wir ab einem Montag suchen
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
        # B4.0 findet am Freitag VOR dem Start statt
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
            # Fall 1: OR-Logik (Tuple) - z.B. 2wo_PMPX braucht (PSM1, IPMA)
            if isinstance(voraussetzung, tuple):
                # Es muss MINDESTENS EINES der Voraussetzungs-Module schon gesehen worden sein
                erfuellt = any(v in gesehene_module for v in voraussetzung)
                if not erfuellt:
                    return False
            
            # Fall 2: Single-Logik (String) - z.B. PSPO1 braucht PSM1
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
            # Fall 1: OR-Logik (Tuple)
            if isinstance(voraussetzung, tuple):
                # Prüfen, ob MINDESTENS EINES der benötigten Module ausgewählt wurde
                erfuellt = any(v in auswahl_set for v in voraussetzung)
                if not erfuellt:
                    optionen_str = " oder ".join(voraussetzung)
                    fehler_liste.append(f"Modul '{modul}' benötigt zwingend eines dieser Module: {optionen_str}")
            
            # Fall 2: Single-Logik (String)
            elif isinstance(voraussetzung, str):
                if voraussetzung not in auswahl_set:
                    fehler_liste.append(f"Modul '{modul}' benötigt '{voraussetzung}'")
                    
    return fehler_liste

# --- SCORE LOGIK (PRIO 1: KEINE LÜCKEN) ---
def bewertung_sortierung(plan_info):
    echte_module = [x['Kuerzel'] for x in plan_info['plan'] if x['Kuerzel'] not in ["SELBSTLERN", "B4.0", "TZ-LERNEN"]]
    idx = {mod: i for i, mod in enumerate(echte_module)}
    
    soft_score = 0
    
    # PAL Logik
    pals = ["PAL-E", "PAL-EBM"]
    referenz_module_fuer_vorne = ["PSPO1", "2wo_PMPX"]
    for pal in pals:
        if pal in idx:
            for ref in referenz_module_fuer_vorne:
                if ref in idx:
                    if idx[pal] < idx[ref]: soft_score += 50
    
    # Late Bloomers
    late_bloomers = ["IT-TOOLS", "PAL-E", "PAL-EBM"]
    for l in late_bloomers:
        if l in idx: soft_score -= idx[l]

    # PSM1 vor PSPO1
    if "PSM1" in idx and "PSPO1" in idx:
        if idx["PSM1"] > idx["PSPO1"]: soft_score += 20

    # SORTIERSCHLÜSSEL: (Gaps, Soft-Score, Switches)
    return (plan_info['gaps'], soft_score, plan_info['switches'])

# --- UI LOGIK ---

st.title("🎓 mycareernow Angebotsplaner")

# --- SIDEBAR: LOGIN & EDITOR ---
st.sidebar.header("📝 Texte verwalten")

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if not st.session_state.is_admin:
    st.sidebar.info("🔒 Bearbeitung gesperrt")
    password = st.sidebar.text_input("Admin-Passwort", type="password")
    
    if password:
        if password == ADMIN_PASSWORD:
            st.session_state.is_admin = True
            st.rerun()
        elif password != "":
            st.sidebar.error("Falsches Passwort")
else:
    st.sidebar.success("🔓 Admin-Modus aktiv")
    if st.sidebar.button("Logout"):
        st.session_state.is_admin = False
        st.rerun()

    st.sidebar.markdown("---")
    
    all_known_kuerzel = set(ABHAENGIGKEITEN.keys())
    for k_list in KATEGORIEN_MAPPING.values():
        for k in k_list: all_known_kuerzel.add(k)
    all_known_kuerzel.add("B4.0")
    all_known_kuerzel.add("SELBSTLERN")
    all_known_kuerzel.add("TZ-LERNEN")

    sorted_kuerzel = sorted(list(all_known_kuerzel))

    selected_modul = st.sidebar.selectbox("Modul wählen:", sorted_kuerzel)
    current_texts = load_texts()
    current_text_value = current_texts.get(selected_modul, "")

    new_text_html = st_quill(value=current_text_value, html=True, key=f"quill_{selected_modul}", placeholder="Hier formatierten Text aus HubSpot einfügen...")

    if st.sidebar.button("💾 Text Speichern"):
        save_text(selected_modul, new_text_html)
        st.sidebar.success(f"Gespeichert: {selected_modul}")

# --- HAUPTBEREICH ---

st.write("Lade die Excel-Liste hoch.")
uploaded_file = st.file_uploader("Kursdaten (Excel) hochladen", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=';')
        else:
            xls = pd.ExcelFile(uploaded_file)
            df = pd.read_excel(xls, sheet_name=0) 

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
            start_datum = st.date_input(
                "Gewünschter Start Fachmodul", 
                value=date(2026, 2, 9),
                format="DD.MM.YYYY"
            )
        
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
                    st.error("❌ Fehlende Voraussetzungen!")
                    for fehler in fehlende_voraussetzungen: st.write(f"- {fehler}")
                    st.stop()
                
                if fehlende_voraussetzungen and ignore_deps:
                    st.warning(f"Ignoriere Abhängigkeiten: {', '.join(fehlende_voraussetzungen)}")

                with st.spinner("Berechne beste Kombination (Priorität: Lückenlosigkeit)..."):
                    gueltige_plaene = []
                    
                    for reihenfolge in itertools.permutations(gewuenschte_module):
                        if not ist_reihenfolge_gueltig(reihenfolge): continue
                        
                        b40_aktiv = not skip_b40
                        moeglich, gaps, plan, fehler = berechne_plan(df, reihenfolge, pd.to_datetime(start_datum), b40_aktiv, is_teilzeit)
                        
                        if moeglich:
                            switches = berechne_kategorie_wechsel(plan)
                            gueltige_plaene.append({"gaps": gaps, "switches": switches, "plan": plan})
                    
                    if not gueltige_plaene:
                        st.error("Kein Plan möglich!")
                    else:
                        gueltige_plaene.sort(key=bewertung_sortierung)
                        bester = gueltige_plaene[0]
                        
                        gesamt_start = bester['plan'][0]['Start']
                        gesamt_ende = bester['plan'][-1]['Ende']
                        
                        st.success(f"Angebot erstellt! (Gesamt: {gesamt_start.strftime('%d.%m.%Y')} - {gesamt_ende.strftime('%d.%m.%Y')})")
                        
                        if bester['gaps'] > 0:
                            st.warning(f"Achtung: Dieser Plan enthält insgesamt {bester['gaps']} Tage Lücke. (Bestes verfügbares Ergebnis)")
                        else:
                            st.info("✅ Dieser Plan ist vollständig lückenlos.")

                        # --- TABELLE ZUR KONTROLLE ---
                        display_data = []
                        for item in bester['plan']:
                            start_str = item['Start'].strftime('%d.%m.%Y')
                            ende_str = item['Ende'].strftime('%d.%m.%Y')
                            hinweis = ""
                            if item['Kuerzel'] == "SELBSTLERN": hinweis = "🔹 Lückenfüller"
                            elif item['Kuerzel'] == "TZ-LERNEN": hinweis = "⏱️ Teilzeit-Lernen"
                            elif item['Kuerzel'] == "B4.0": hinweis = "🚀 Onboarding"
                            elif item['Wartetage_davor'] > 3: hinweis = f"⚠️ {item['Wartetage_davor']} Tage Gap"
                            
                            display_data.append({
                                "Kategorie": item['Kategorie'],
                                "Von": start_str,
                                "Bis": ende_str,
                                "Modul": item['Modul'],
                                "Info": hinweis
                            })
                        st.table(display_data)

                        # --- GENERIERUNG DES HTML-STRINGS FÜR DIE ZWISCHENABLAGE ---
                        TEXT_MAPPING = load_texts()
                        html_content_for_clipboard = ""

                        for item in bester['plan']:
                            k = item['Kuerzel']
                            beschreibung_html = TEXT_MAPPING.get(k, "")
                            
                            if not beschreibung_html:
                                # Standard-Texte falls nicht definiert
                                if k == "B4.0": beschreibung_html = "<p><strong>Bildung 4.0</strong><br>Einführung in den virtuellen Klassenraum.</p>"
                                elif k == "SELBSTLERN": beschreibung_html = "<p><strong>Individuelle Selbstlernphase</strong></p>"
                                elif k == "TZ-LERNEN": beschreibung_html = "<p><strong>Teilzeit-Selbstlernphase</strong></p>"
                                else: beschreibung_html = f"<p><em>Text für {k} fehlt.</em></p>"
                            
                            html_content_for_clipboard += f"{beschreibung_html}<br>"

                        # --- COPY BUTTON KOMPONENTE ---
                        st.subheader("📋 Angebot kopieren")
                        st.info("Klicke auf den Button, um die Textbausteine (mit Formatierung) in die Zwischenablage zu kopieren.")
                        
                        js_code = f"""
                        <div id="content-to-copy" style="border:1px solid #ddd; padding:10px; background:#f9f9f9; max-height: 200px; overflow-y: auto; margin-bottom: 10px;">
                            {html_content_for_clipboard}
                        </div>
                        <button onclick="copyToClipboard()" style="background-color:#4CAF50; color:white; padding:10px 20px; border:none; border-radius:5px; cursor:pointer; font-size:16px;">
                           📋 In Zwischenablage kopieren
                        </button>
                        <script>
                        function copyToClipboard() {{
                            const node = document.getElementById('content-to-copy');
                            const selection = window.getSelection();
                            const range = document.createRange();
                            range.selectNodeContents(node);
                            selection.removeAllRanges();
                            selection.addRange(range);
                            
                            try {{
                                document.execCommand('copy');
                                alert('Erfolgreich kopiert! Du kannst es jetzt in HubSpot einfügen (Strg+V).');
                            }} catch (err) {{
                                alert('Fehler beim Kopieren: ' + err);
                            }}
                            
                            selection.removeAllRanges();
                        }}
                        </script>
                        """
                        components.html(js_code, height=400, scrolling=True)

    except Exception as e:
        st.error(f"Fehler: {e}")

else:
    st.info("Bitte lade zuerst die kursdaten.xlsx hoch.")