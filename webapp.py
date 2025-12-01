import streamlit as st
import pandas as pd
from datetime import timedelta, date
import itertools

# --- KONFIGURATION ---
st.set_page_config(page_title="MyCareer Planer", page_icon="📅")

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

# --- FUNKTIONEN ---

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    ab_datum = pd.to_datetime(ab_datum)
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
        if eintrag['Kuerzel'] == "SELBSTLERN": continue
        kuerzel = eintrag['Kuerzel']
        aktuelle_kat = MODUL_ZU_KAT.get(kuerzel, "Sonstiges")
        if letzte_kat is not None and aktuelle_kat != letzte_kat:
            wechsel += 1
        letzte_kat = aktuelle_kat
    return wechsel

def berechne_plan(df, modul_reihenfolge, start_wunsch):
    plan = []
    naechster_moeglicher_start = pd.to_datetime(start_wunsch)
    total_gap_days = 0
    moeglich = True
    fehler_grund = ""
    
    pmpx_im_paket = PRAXIS_MODUL in modul_reihenfolge
    pmpx_bereits_platziert = False

    for modul in modul_reihenfolge:
        kurs = finde_naechsten_start(df, modul, naechster_moeglicher_start)
        
        if kurs is None:
            moeglich = False
            fehler_grund = f"Kein Termin für '{modul}' gefunden ab {naechster_moeglicher_start.strftime('%d.%m.%Y')}"
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
    """
    Prüft die zeitliche Logik.
    Erlaubt fehlende Voraussetzungen (das wird separat geprüft),
    aber WENN beide da sind, muss die Reihenfolge stimmen.
    """
    gesehene_module = set()
    for modul in reihenfolge:
        voraussetzung = ABHAENGIGKEITEN.get(modul)
        if voraussetzung:
            # Nur prüfen, wenn die Voraussetzung auch im aktuellen Plan ist
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
                fehler_liste.append(f"Modul '{modul}' benötigt normalerweise '{voraussetzung}'")
    return fehler_liste

def bewertung_sortierung(plan_info):
    echte_module = [x['Kuerzel'] for x in plan_info['plan'] if x['Kuerzel'] != "SELBSTLERN"]
    try:
        pmpx_index = echte_module.index(PRAXIS_MODUL)
    except ValueError:
        pmpx_index = -1 
    return (plan_info['gaps'], plan_info['switches'], -pmpx_index)

# --- UI LOGIK ---

st.title("🎓 MyCareer Angebots-Generator")
st.write("Lade die Excel-Liste hoch und wähle die Module aus.")

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
        
        verfuegbare_module = sorted(df['Kuerzel'].unique())
        
        col1, col2 = st.columns(2)
        with col1:
            start_datum = st.date_input("Startdatum", date(2026, 2, 9))
        
        with col2:
            gewuenschte_module = st.multiselect("Wähle die Module aus:", verfuegbare_module)

        st.markdown("---")
        
        # Die neue Checkbox für Sonderfälle
        ignore_deps = st.checkbox("⚠️ Abhängigkeiten ignorieren (z.B. bei bestandenem Einstufungstest)")

        if st.button("Angebot berechnen"):
            if not gewuenschte_module:
                st.warning("Bitte wähle mindestens ein Modul aus.")
            else:
                # 1. Check auf fehlende Voraussetzungen
                fehlende_voraussetzungen = check_fehlende_voraussetzungen(gewuenschte_module)
                
                # ABBRUCHBEDINGUNG: Fehler gefunden UND Checkbox NICHT gesetzt
                if fehlende_voraussetzungen and not ignore_deps:
                    st.error("❌ Berechnung gestoppt: Fehlende Voraussetzungen!")
                    for fehler in fehlende_voraussetzungen:
                        st.write(f"- {fehler}")
                    st.warning("👉 Wenn der Teilnehmer einen Test bestanden hat, setze bitte den Haken bei 'Abhängigkeiten ignorieren' (oberhalb dieses Buttons).")
                    st.stop()
                
                # WARNUNG: Fehler gefunden ABER Checkbox gesetzt -> Wir machen weiter
                if fehlende_voraussetzungen and ignore_deps:
                    st.warning(f"Achtung: Folgende Abhängigkeiten werden ignoriert: {', '.join(fehlende_voraussetzungen)}")

                # 2. Berechnung
                with st.spinner("Berechne beste Kombination..."):
                    gueltige_plaene = []
                    letzter_fehler = ""
                    
                    for reihenfolge in itertools.permutations(gewuenschte_module):
                        if not ist_reihenfolge_gueltig(reihenfolge): continue
                        
                        moeglich, gaps, plan, fehler = berechne_plan(df, reihenfolge, pd.to_datetime(start_datum))
                        
                        if moeglich:
                            switches = berechne_kategorie_wechsel(plan)
                            gueltige_plaene.append({"gaps": gaps, "switches": switches, "plan": plan})
                        else:
                            letzter_fehler = fehler
                    
                    if not gueltige_plaene:
                        st.error("Kein zeitlich passender Plan möglich!")
                        st.info(f"Häufigster Grund: {letzter_fehler}")
                    else:
                        gueltige_plaene.sort(key=bewertung_sortierung)
                        bester = gueltige_plaene[0]
                        
                        st.success(f"Bestes Angebot gefunden! (Ungedeckte Lückentage: {bester['gaps']})")
                        
                        display_data = []
                        for item in bester['plan']:
                            start_str = item['Start'].strftime('%d.%m.%Y')
                            ende_str = item['Ende'].strftime('%d.%m.%Y')
                            hinweis = ""
                            if item['Kuerzel'] == "SELBSTLERN":
                                hinweis = "🔹 Lückenfüller"
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
                        
                        kuerzel_only = [x['Kuerzel'] for x in bester['plan'] if x['Kuerzel'] != "SELBSTLERN"]
                        st.text_area("Kompakte Reihenfolge (für E-Mail/Word):", " -> ".join(kuerzel_only))

    except Exception as e:
        st.error(f"Fehler beim Lesen der Datei: {e}")

else:
    st.info("Bitte lade zuerst die kursdaten.xlsx hoch.")