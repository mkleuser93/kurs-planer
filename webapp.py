import streamlit as st
import pandas as pd
from datetime import timedelta, date
import itertools

# --- KONFIGURATION ---
st.set_page_config(page_title="mycareernow Planer", page_icon="📅")

MAX_TEILNEHMER_PRO_KLASSE = 20

# Abhängigkeiten definieren
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
    "Lückenfüller": ["SELBSTLERN"]
}

MODUL_ZU_KAT = {}
for kat, module in KATEGORIEN_MAPPING.items():
    for mod in module:
        MODUL_ZU_KAT[mod] = kat

PRAXIS_MODUL = "2wo_PMPX"
ONBOARDING_MODUL = "B4.0"

# --- FUNKTIONEN ---

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    ab_datum = pd.to_datetime(ab_datum)
    
    # Check ob Spalten existieren (Fallback falls alte Excel)
    if 'Teilnehmeranzahl' in df.columns and 'Klassenanzahl' in df.columns:
        moegliche_termine = df[
            (df['Kuerzel'] == modul_kuerzel) & 
            (df['Startdatum'] >= ab_datum) &
            (df['Teilnehmeranzahl'] < (df['Klassenanzahl'] * MAX_TEILNEHMER_PRO_KLASSE))
        ].sort_values(by='Startdatum')
    else:
        # Fallback ohne Kapazitätsprüfung
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
        if eintrag['Kuerzel'] in ["SELBSTLERN", "B4.0"]: continue
        kuerzel = eintrag['Kuerzel']
        aktuelle_kat = MODUL_ZU_KAT.get(kuerzel, "Sonstiges")
        if letzte_kat is not None and aktuelle_kat != letzte_kat:
            wechsel += 1
        letzte_kat = aktuelle_kat
    return wechsel

def berechne_plan(df, modul_reihenfolge, start_wunsch, b40_aktiv):
    plan = []
    
    # Datum konvertieren
    start_wunsch = pd.to_datetime(start_wunsch)
    naechster_moeglicher_start = start_wunsch
    
    # --- LOGIK FÜR B4.0 (ONBOARDING) ---
    if b40_aktiv:
        # B4.0 findet 3 Tage VOR dem eigentlichen ersten Modul statt
        # Dauer: 1 Tag
        b40_start = start_wunsch - timedelta(days=3)
        b40_ende = b40_start # Endet am gleichen Tag (1 Tag Dauer)
        
        plan.append({
            "Modul": "Bildung 4.0 - Virtual Classroom",
            "Kuerzel": "B4.0",
            "Start": b40_start,
            "Ende": b40_ende,
            "Wartetage_davor": 0,
            "Kategorie": "Onboarding"
        })
        
        # Der "Gap" zwischen B4.0 (Ende -3 Tage) und Start (Tag 0) sind automatisch 2 Tage Pause
        # Wir setzen den Zähler für Gap aber nicht hoch, da das gewollt ist.
    
    total_gap_days = 0
    moeglich = True
    fehler_grund = ""
    
    pmpx_im_paket = PRAXIS_MODUL in modul_reihenfolge
    pmpx_bereits_platziert = False

    for modul in modul_reihenfolge:
        kurs = finde_naechsten_start(df, modul, naechster_moeglicher_start)
        
        if kurs is None:
            moeglich = False
            fehler_grund = f"Kein freier Termin für '{modul}' ab {naechster_moeglicher_start.strftime('%d.%m.%Y')} gefunden."
            break
        
        start = kurs['Startdatum']
        ende = kurs['Enddatum']
        
        gap = (start - naechster_moeglicher_start).days
        if gap < 0: gap = 0
        
        # Lückenfüller Logik
        if gap > 3:
            darf_fuellen = (not pmpx_im_paket) or pmpx_bereits_platziert
            if darf_fuellen:
                dauer_tage = min(gap, 14)
                sl_start = naechster_moeglicher_start
                sl_ende = sl_start + timedelta(days=dauer_tage)
                plan.append({
                    "Modul": "Indiv. Selbstlernphase",
                    "Kuerzel": "SELBSTLERN",
                    "Start": sl_start,
                    "Ende": sl_ende,
                    "Wartetage_davor": 0,
                    "Kategorie": "Lückenfüller"
                })
                gap = gap - dauer_tage 
        
        total_gap_days += gap
        
        plan.append({
            "Modul": kurs['Modulname'],
            "Kuerzel": modul,
            "Start": start,
            "Ende": ende,
            "Wartetage_davor": gap,
            "Kategorie": MODUL_ZU_KAT.get(modul, "Sonstiges")
        })
        
        naechster_moeglicher_start = ende + timedelta(days=1)
        if modul == PRAXIS_MODUL: pmpx_bereits_platziert = True

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
    echte_module = [x['Kuerzel'] for x in plan_info['plan'] if x['Kuerzel'] not in ["SELBSTLERN", "B4.0"]]
    try:
        pmpx_index = echte_module.index(PRAXIS_MODUL)
    except ValueError:
        pmpx_index = -1 
    return (plan_info['gaps'], plan_info['switches'], -pmpx_index)

# --- UI LOGIK ---

st.title("🎓 mycareernow Angebotsplaner")
st.write("Lade die Excel-Liste hoch (inkl. Spalten 'Klassenanzahl' und 'Teilnehmeranzahl').")

uploaded_file = st.file_uploader("Kursdaten (Excel) hochladen", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, sep=';')
        else:
            df = pd.read_excel(uploaded_file)
            
        df.columns = [c.strip() for c in df.columns]
        df['Startdatum'] = pd.to_datetime(df['Startdatum'], dayfirst=True)
        df['Enddatum'] = pd.to_datetime(df['Enddatum'], dayfirst=True)
        df['Kuerzel'] = df['Kuerzel'].astype(str).str.strip()
        
        # Spalten vorbereiten (Kapazität)
        if "Klassenanzahl" not in df.columns:
            df['Klassenanzahl'] = 1
        else:
            df['Klassenanzahl'] = df['Klassenanzahl'].fillna(1).astype(int)
            
        if "Teilnehmeranzahl" not in df.columns:
            df['Teilnehmeranzahl'] = 0
        else:
            df['Teilnehmeranzahl'] = df['Teilnehmeranzahl'].fillna(0).astype(int)

        verfuegbare_module = sorted(df['Kuerzel'].unique())
        
        col1, col2 = st.columns(2)
        with col1:
            # Hinweis für den User
            st.info("ℹ️ Das Datum unten ist der Start des ERSTEN Fachmoduls. B4.0 startet automatisch 3 Tage früher.")
            start_datum = st.date_input("Gewünschter Start Fachmodul", date(2026, 2, 9))
        
        with col2:
            gewuenschte_module = st.multiselect("Wähle die Fachmodule aus:", verfuegbare_module)

        st.markdown("---")
        
        # Checkboxen nebeneinander
        c1, c2 = st.columns(2)
        with c1:
            skip_b40 = st.checkbox("B4.0 überspringen (Wiederkehrer)")
        with c2:
            ignore_deps = st.checkbox("⚠️ Abhängigkeiten ignorieren (Test bestanden)")

        if st.button("Angebot berechnen"):
            if not gewuenschte_module:
                st.warning("Bitte wähle mindestens ein Fachmodul aus.")
            else:
                # Voraussetzungs-Check
                fehlende_voraussetzungen = check_fehlende_voraussetzungen(gewuenschte_module)
                
                if fehlende_voraussetzungen and not ignore_deps:
                    st.error("❌ Berechnung gestoppt: Fehlende Voraussetzungen!")
                    for fehler in fehlende_voraussetzungen:
                        st.write(f"- {fehler}")
                    st.stop()
                
                if fehlende_voraussetzungen and ignore_deps:
                    st.warning(f"Ignoriere Abhängigkeiten: {', '.join(fehlende_voraussetzungen)}")

                with st.spinner("Berechne beste Kombination..."):
                    gueltige_plaene = []
                    letzter_fehler = ""
                    
                    # Permutationen berechnen
                    for reihenfolge in itertools.permutations(gewuenschte_module):
                        if not ist_reihenfolge_gueltig(reihenfolge): continue
                        
                        # Hier übergeben wir, ob B4.0 aktiv sein soll (True wenn NICHT übersprungen)
                        b40_aktiv = not skip_b40
                        
                        moeglich, gaps, plan, fehler = berechne_plan(df, reihenfolge, pd.to_datetime(start_datum), b40_aktiv)
                        
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
                        
                        st.success(f"Angebot erstellt! (Starttermin B4.0: {gesamt_start.strftime('%d.%m.%Y')})")
                        
                        display_data = []
                        for item in bester['plan']:
                            start_str = item['Start'].strftime('%d.%m.%Y')
                            ende_str = item['Ende'].strftime('%d.%m.%Y')
                            hinweis = ""
                            if item['Kuerzel'] == "SELBSTLERN":
                                hinweis = "🔹 Lückenfüller"
                            elif item['Kuerzel'] == "B4.0":
                                hinweis = "🚀 Onboarding (3 Tage vor Start)"
                            elif item['Wartetage_davor'] > 3:
                                hinweis = f"⚠️ {item['Wartetage_davor']} Tage Lücke davor"
                            
                            display_data.append({
                                "Kategorie": item['Kategorie'],
                                "Von": start_str,
                                "Bis": ende_str,
                                "Modul": item['Modul'],
                                "Info": hinweis
                            })
                        
                        st.table(display_data)
                        
                        # Text Output
                        kuerzel_liste_text = []
                        for item in bester['plan']:
                            if item['Kuerzel'] == "SELBSTLERN":
                                kuerzel_liste_text.append("Selbstlernphase")
                            else:
                                kuerzel_liste_text.append(item['Kuerzel'])
                        
                        final_text = (
                            f"Gesamtzeitraum: {gesamt_start.strftime('%d.%m.%Y')} - {gesamt_ende.strftime('%d.%m.%Y')}\n\n"
                            f"Modul-Abfolge:\n"
                            f"{' -> '.join(kuerzel_liste_text)}"
                        )
                        
                        st.text_area("Kompakte Daten (für E-Mail/Word):", final_text, height=150)

    except Exception as e:
        st.error(f"Fehler beim Lesen der Datei: {e}")

else:
    st.info("Bitte lade zuerst die kursdaten.xlsx hoch.")