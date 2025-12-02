import streamlit as st
import pandas as pd
from datetime import timedelta, date
import itertools

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

# --- HELPER FUNKTIONEN (DATUM) ---

def get_next_monday(d):
    """Schiebt ein Datum auf den nächsten Montag, falls es Sa/So ist."""
    # weekday(): Mon=0, Sun=6
    wd = d.weekday()
    if wd == 5: # Samstag
        return d + timedelta(days=2)
    elif wd == 6: # Sonntag
        return d + timedelta(days=1)
    return d

def get_previous_friday(d):
    """Schiebt ein Datum auf den vorherigen Freitag zurück, falls es Sa/So/Mon ist (für Enddaten)."""
    wd = d.weekday()
    if wd == 5: # Samstag -> Freitag
        return d - timedelta(days=1)
    elif wd == 6: # Sonntag -> Freitag
        return d - timedelta(days=2)
    elif wd == 0: # Montag -> Freitag (der Vorwoche)
        return d - timedelta(days=3)
    return d

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    # Wir stellen sicher, dass wir ab einem Montag suchen, falls ab_datum am Wochenende liegt
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
    start_wunsch = pd.to_datetime(start_wunsch)
    naechster_moeglicher_start = get_next_monday(start_wunsch)
    
    # --- ONBOARDING (B4.0) ---
    if b40_aktiv:
        # B4.0 findet Fr/Sa/So/Mo statt? Nein, 1 Tag.
        # Regel: 3 Tage VOR Start. 
        # Wenn Start = Montag 09.02., dann B4.0 = Freitag 06.02.
        # Rechnung: Montag - 3 Tage = Freitag. Perfekt.
        
        b40_start = naechster_moeglicher_start - timedelta(days=3)
        # Wenn b40_start auf Sa/So fällt (unwahrscheinlich bei Mo-Start), anpassen?
        # Wir lassen die -3 Tage Regel fix, da sie meistens Fr trifft.
        
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

    tz_saldo = 0.0
    modul_counter = 0 
    
    anzahl_module = len(modul_reihenfolge)

    for i, modul in enumerate(modul_reihenfolge):
        
        while True:
            # Stelle sicher, dass wir ab einem Montag suchen
            naechster_moeglicher_start = get_next_monday(naechster_moeglicher_start)
            
            kurs = finde_naechsten_start(df, modul, naechster_moeglicher_start)
            
            if kurs is None:
                moeglich = False
                fehler_grund = f"Kein freier Termin für '{modul}' ab {naechster_moeglicher_start.strftime('%d.%m.%Y')} gefunden."
                break
            
            start = kurs['Startdatum'] # Ist in Excel hoffentlich immer Montag
            ende = kurs['Enddatum']    # Ist in Excel hoffentlich immer Freitag
            
            gap = (start - naechster_moeglicher_start).days
            if gap < 0: gap = 0
            
            # ---------------------------------------------------------
            # LOGIK: TEILZEIT
            # ---------------------------------------------------------
            if ist_teilzeit:
                
                # A) NATÜRLICHE LÜCKE (Wartezeit)
                if gap > 3 and tz_saldo >= 1:
                    # Wir nutzen Guthaben. 
                    # Max 28 Tage, Max Saldo, Max Gap.
                    fill_duration = min(gap, tz_saldo, 28)
                    
                    if fill_duration >= 4: # Mindestens fast eine Woche
                        # Berechne Ende: Start + Dauer.
                        # Aber das Ende muss ein Freitag sein.
                        
                        tz_start = naechster_moeglicher_start # Ist Montag
                        
                        # Ziel-Ende berechnen
                        target_end = tz_start + timedelta(days=int(fill_duration))
                        # Einrasten auf vorherigen Freitag
                        tz_ende_fixed = get_previous_friday(target_end)
                        
                        # Sicherstellen, dass wir nicht vor dem Start enden (Min. Mo-Fr)
                        if tz_ende_fixed < tz_start:
                             tz_ende_fixed = tz_start + timedelta(days=4) # Zwinge 1 Woche
                        
                        # Check: Kollidiert das mit dem Kursstart?
                        if tz_ende_fixed >= start:
                            # Pause ist zu lang für die Lücke durch das Einrasten.
                            # Wir verkürzen auf den Freitag VOR dem Kursstart.
                            tz_ende_fixed = start - timedelta(days=3)
                        
                        plan.append({
                            "Modul": "Teilzeit-Selbstlernphase (Wartezeit)",
                            "Kuerzel": "TZ-LERNEN",
                            "Start": tz_start,
                            "Ende": tz_ende_fixed,
                            "Wartetage_davor": 0,
                            "Kategorie": "Teilzeit"
                        })
                        
                        # Tatsächlich verbrauchte Tage (Kalendertage für Saldo)
                        # Wir berechnen Saldo einfach: Neue Startposition - Alte Startposition
                        used_days = (tz_ende_fixed - tz_start).days + 3 # +3 um bis zum nächsten Montag zu kommen
                        
                        tz_saldo -= used_days
                        if tz_saldo < 0: tz_saldo = 0
                        
                        if used_days > 7: modul_counter = 0
                            
                        # Weiter am nächsten Montag
                        naechster_moeglicher_start = tz_ende_fixed + timedelta(days=3)
                        continue 

                # B) ZWANGSPAUSE
                elif gap <= 3 and modul_counter >= 2 and tz_saldo >= 7:
                    
                    # Wir wollen ca. 4 Wochen (28 Tage) oder Saldo
                    target_days = min(tz_saldo, 28)
                    
                    tz_start = naechster_moeglicher_start # Ist Montag
                    target_end = tz_start + timedelta(days=int(target_days))
                    
                    # Auf Freitag einrasten
                    tz_ende_fixed = get_previous_friday(target_end)
                    
                    # Min 1 Woche
                    if tz_ende_fixed < tz_start:
                         tz_ende_fixed = tz_start + timedelta(days=4)

                    plan.append({
                        "Modul": "Teilzeit-Selbstlernphase",
                        "Kuerzel": "TZ-LERNEN",
                        "Start": tz_start,
                        "Ende": tz_ende_fixed,
                        "Wartetage_davor": 0,
                        "Kategorie": "Teilzeit"
                    })
                    
                    used_days = (tz_ende_fixed - tz_start).days + 3
                    tz_saldo -= used_days
                    if tz_saldo < 0: tz_saldo = 0
                    
                    modul_counter = 0
                    naechster_moeglicher_start = tz_ende_fixed + timedelta(days=3)
                    continue

            # ---------------------------------------------------------
            # LOGIK: VOLLZEIT
            # ---------------------------------------------------------
            elif gap > 3: 
                darf_fuellen = (not pmpx_im_paket) or pmpx_bereits_platziert
                if darf_fuellen:
                    # Vollzeit Lückenfüller: Immer Mo-Fr
                    # Wir füllen max 2 Wochen (14 Tage)
                    # Gap = Tage bis Start (z.B. 14 Tage).
                    
                    sl_start = naechster_moeglicher_start
                    
                    # Ziel: Lücke füllen, aber am Freitag enden
                    # Max Fülldauer = Lücke - 3 Tage (damit wir Freitag enden vor Montag Start)
                    max_fill = gap - 3 
                    if max_fill > 14: max_fill = 11 # Max 2 Wochen (Mo-Fr nächste Woche)
                    
                    if max_fill >= 4: # Lohnt sich nur für >= 1 Woche
                        sl_ende = sl_start + timedelta(days=max_fill)
                        # Sicherstellen dass es Freitag ist
                        sl_ende = get_previous_friday(sl_ende)
                        
                        plan.append({
                            "Modul": "Indiv. Selbstlernphase",
                            "Kuerzel": "SELBSTLERN",
                            "Start": sl_start,
                            "Ende": sl_ende,
                            "Wartetage_davor": 0,
                            "Kategorie": "Lückenfüller"
                        })
                        naechster_moeglicher_start = sl_ende + timedelta(days=3)
                        continue

            # ---------------------------------------------------------
            # MODUL PLATZIEREN
            # ---------------------------------------------------------
            total_gap_days += gap
            
            plan.append({
                "Modul": kurs['Modulname'],
                "Kuerzel": modul,
                "Start": start,
                "Ende": ende,
                "Wartetage_davor": gap,
                "Kategorie": MODUL_ZU_KAT.get(modul, "Sonstiges")
            })
            
            if ist_teilzeit:
                dauer_modul = (ende - start).days + 1
                verdienst = dauer_modul / 2
                tz_saldo += verdienst
                modul_counter += 1
            
            if modul == PRAXIS_MODUL: pmpx_bereits_platziert = True
            
            # Nächster Start: Montag nach Ende
            naechster_moeglicher_start = get_next_monday(ende + timedelta(days=1))
            break 

        if not moeglich: break

    # --- ENDABRECHNUNG TEILZEIT (REST) ---
    if moeglich and ist_teilzeit and tz_saldo >= 4: # Nur wenn >= 1 Woche (Mo-Fr sind 5 Tage, wir brauchen ca 7 Tage Saldo für 1 Woche Pause)
        
        tz_start = naechster_moeglicher_start
        target_end = tz_start + timedelta(days=int(tz_saldo))
        tz_ende_fixed = get_previous_friday(target_end)
        
        if tz_ende_fixed >= tz_start:
            plan.append({
                "Modul": "Teilzeit-Selbstlernphase (Abschluss)",
                "Kuerzel": "TZ-LERNEN",
                "Start": tz_start,
                "Ende": tz_ende_fixed,
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
                            elif item['Wartetage_davor'] > 3: hinweis = f"⚠️ {item['Wartetage_davor']} Tage Rest-Lücke (Guthaben leer)"
                            
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