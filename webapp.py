import streamlit as st
import pandas as pd
from datetime import timedelta, date
import itertools
import math

# --- KONFIGURATION ---
st.set_page_config(page_title="mycareernow Planer", page_icon="📅")

MAX_TEILNEHMER_PRO_KLASSE = 20

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

# --- HELPER FUNKTIONEN ---

def get_monday(d):
    """Zwingt ein Datum auf den Montag der Woche (falls Wochenende)."""
    wd = d.weekday()
    if wd > 0: # Alles außer Montag zurück zum Montag
        return d - timedelta(days=wd)
    return d

def get_friday_of_week(monday_date, weeks_duration=1):
    """
    Berechnet den Freitag basierend auf dem Start-Montag und der Dauer in Wochen.
    Beispiel: Start Mo 01.01., Dauer 1 Woche -> Ende Fr 05.01.
    Beispiel: Start Mo 01.01., Dauer 2 Wochen -> Ende Fr 12.01.
    """
    # Wir addieren Wochen, ziehen dann 3 Tage ab (Mo -> So -> Sa -> Fr)
    return monday_date + timedelta(weeks=weeks_duration) - timedelta(days=3)

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    # ab_datum ist der Montag, ab dem wir suchen
    
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
    
    # Der "Zeiger" für den aktuellen Zeitstrahl. MUSS ein Montag sein.
    # Wir nutzen get_monday, falls der User z.B. einen Mittwoch auswählt.
    current_monday = get_monday(pd.to_datetime(start_wunsch))
    
    # --- ONBOARDING (B4.0) ---
    if b40_aktiv:
        # B4.0 findet am Freitag VOR dem Start statt.
        # Da current_monday der Start des ersten Moduls ist, rechnen wir zurück.
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
        # Der Zeiger current_monday bleibt unverändert auf dem Start des ersten Moduls/Lernphase
    
    total_gap_days = 0
    moeglich = True
    fehler_grund = ""
    
    pmpx_im_paket = PRAXIS_MODUL in modul_reihenfolge
    pmpx_bereits_platziert = False

    # Teilzeit-Konto in WOCHEN (float, z.B. 2.0 für 2 Wochen)
    tz_guthaben_wochen = 0.0
    modul_counter = 0 
    
    anzahl_module = len(modul_reihenfolge)

    for i, modul in enumerate(modul_reihenfolge):
        
        # Schleife, um Lücken/Pausen abzuarbeiten, bevor das Modul gesetzt wird
        while True:
            kurs = finde_naechsten_start(df, modul, current_monday)
            
            if kurs is None:
                moeglich = False
                fehler_grund = f"Kein freier Termin für '{modul}' ab {current_monday.strftime('%d.%m.%Y')} gefunden."
                break
            
            start = kurs['Startdatum'] # Excel-Start (ist immer Montag)
            ende = kurs['Enddatum']    # Excel-Ende (ist immer Freitag)
            
            # Berechne Lücke in GANZEN WOCHEN
            # Differenz zwischen Wunsch-Start (current_monday) und Kurs-Start (start)
            # Da beides Montage sind, muss das durch 7 teilbar sein.
            gap_days = (start - current_monday).days
            gap_weeks = gap_days // 7
            
            # ---------------------------------------------------------
            # TEILZEIT LOGIK
            # ---------------------------------------------------------
            if ist_teilzeit:
                
                # A) Lücke füllen (Wartezeit überbrücken)
                # Wir füllen nur, wenn die Lücke mind. 1 Woche ist UND wir Guthaben haben
                if gap_weeks >= 1 and tz_guthaben_wochen >= 1:
                    
                    # Wie viele Wochen können wir füllen?
                    # Max: Die Lücke selbst, das Guthaben, oder das Limit (4 Wochen)
                    weeks_to_take = min(gap_weeks, int(tz_guthaben_wochen), 4)
                    
                    # Nur ausführen, wenn wir mind. 1 Woche füllen können
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
                        
                        # Guthaben abziehen
                        tz_guthaben_wochen -= weeks_to_take
                        
                        if weeks_to_take > 1: modul_counter = 0
                        
                        # Zeiger weiterschieben
                        current_monday = current_monday + timedelta(weeks=weeks_to_take)
                        
                        # Loop neu starten (Gap hat sich verkleinert, prüfen ob Modul jetzt passt)
                        continue

                # B) Zwangspause (nach 2 Modulen)
                # Nur wenn KEINE Lücke da ist (gap_weeks == 0)
                # UND wir Guthaben haben
                elif gap_weeks == 0 and modul_counter >= 2 and tz_guthaben_wochen >= 1:
                    
                    # Wir nehmen max 4 Wochen, oder was da ist
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
                        
                        # Zeiger weiter
                        current_monday = current_monday + timedelta(weeks=weeks_to_take)
                        
                        # Nach Pause müssen wir Kurs neu suchen (Startdatum hat sich verschoben)
                        continue

            # ---------------------------------------------------------
            # VOLLZEIT LOGIK (Lückenfüller)
            # ---------------------------------------------------------
            elif gap_weeks >= 1:
                darf_fuellen = (not pmpx_im_paket) or pmpx_bereits_platziert
                if darf_fuellen:
                    # Max 2 Wochen füllen
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

            # ---------------------------------------------------------
            # MODUL PLATZIEREN
            # ---------------------------------------------------------
            
            # Wenn wir hier sind, wird das Modul gebucht.
            # Eventuelle Rest-Lücke (die nicht gefüllt werden konnte) wird rot markiert.
            total_gap_days += (gap_weeks * 7) # Nur für Statistik
            
            plan.append({
                "Modul": kurs['Modulname'],
                "Kuerzel": modul,
                "Start": start,
                "Ende": ende,
                "Wartetage_davor": gap_days, # Anzeige in Tagen
                "Kategorie": MODUL_ZU_KAT.get(modul, "Sonstiges")
            })
            
            # Guthaben verdienen
            if ist_teilzeit:
                # Dauer in Wochen berechnen
                # (Ende - Start + 3 Tage) / 7
                # Beispiel: Mo bis Fr = 4 Tage Diff + 3 = 7 / 7 = 1 Woche
                modul_dauer_wochen = ((ende - start).days + 3) / 7
                
                # Verdienst: 50% der Dauer
                tz_guthaben_wochen += (modul_dauer_wochen / 2)
                modul_counter += 1
            
            if modul == PRAXIS_MODUL: pmpx_bereits_platziert = True
            
            # Zeiger auf den Montag NACH dem Kurs setzen
            current_monday = get_next_monday(ende + timedelta(days=1))
            
            break # Modul platziert, weiter zum nächsten

        if not moeglich: break

    # --- ENDABRECHNUNG TEILZEIT (RESTGUTHABEN) ---
    if moeglich and ist_teilzeit and tz_guthaben_wochen >= 1:
        # Alles was übrig ist (abgerundet auf ganze Wochen) anhängen
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
                        
                        kuerzel_liste_text = []
                        for item in bester['plan']:
                            if item['Kuerzel'] == "SELBSTLERN": kuerzel_liste_text.append("Selbstlernphase")
                            elif item['Kuerzel'] == "TZ-LERNEN": kuerzel_liste_text.append("TZ-Lernen")
                            else: kuerzel_liste_text.append(item['Kuerzel'])
                        
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