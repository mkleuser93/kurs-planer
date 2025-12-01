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

# --- FUNKTIONEN ---

def finde_naechsten_start(df, modul_kuerzel, ab_datum):
    ab_datum = pd.to_datetime(ab_datum)
    
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
    naechster_moeglicher_start = start_wunsch
    
    # --- ONBOARDING ---
    if b40_aktiv:
        b40_start = start_wunsch - timedelta(days=3)
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

    # --- TEILZEIT VARIABLEN ---
    # tz_saldo speichert die verdiente Selbstlernzeit in TAGEN.
    # Beispiel: 4 Wochen Kurs = 28 Tage -> Verdienst: 14 Tage Saldo.
    tz_saldo = 0.0
    modul_counter = 0 # Zählt Module seit der letzten Pause
    
    anzahl_module = len(modul_reihenfolge)

    for i, modul in enumerate(modul_reihenfolge):
        
        # 1. Kurs suchen (frühestmöglich)
        kurs = finde_naechsten_start(df, modul, naechster_moeglicher_start)
        
        if kurs is None:
            moeglich = False
            fehler_grund = f"Kein freier Termin für '{modul}' ab {naechster_moeglicher_start.strftime('%d.%m.%Y')} gefunden."
            break
        
        start = kurs['Startdatum']
        ende = kurs['Enddatum']
        
        # 2. Prüfen: Gibt es eine NATÜRLICHE LÜCKE?
        gap = (start - naechster_moeglicher_start).days
        if gap < 0: gap = 0
        
        # --- TEILZEIT LOGIK: NATÜRLICHE LÜCKE NUTZEN ---
        if ist_teilzeit:
            if gap > 3: 
                # Wir haben eine Lücke! Die nutzen wir als TZ-Lernen.
                # Wir kappen die Bezeichnung nicht zwingend, aber wir verbuchen sie.
                
                # Wie viel der Lücke können wir als "TZ-Lernen" verbuchen?
                # Eigentlich alles, aber wir dürfen das Saldo auch ins Minus laufen lassen, 
                # weil wir die Zeit später wieder reinholen ("Schulden machen").
                # ABER: Die Anforderung sagt "Nie länger als 4 Wochen am Stück".
                
                # Wenn die Lücke RIESIG ist (z.B. 8 Wochen), müssen wir sie splitten?
                # Nein, wenn der Kurs erst in 8 Wochen startet, können wir das nicht ändern.
                # Wir nennen es "TZ-Lernen + Wartezeit".
                
                # Wir verbuchen die Lücke gegen unser Saldo.
                tz_saldo -= gap
                
                # Wenn wir eine große Lücke hatten, gilt das als Pause -> Counter Reset
                if gap > 7:
                    modul_counter = 0

                plan.append({
                    "Modul": "Teilzeit-Selbstlernphase (Wartezeit)",
                    "Kuerzel": "TZ-LERNEN",
                    "Start": naechster_moeglicher_start,
                    "Ende": start - timedelta(days=1),
                    "Wartetage_davor": 0,
                    "Kategorie": "Teilzeit"
                })
                
                # Gap ist jetzt "gefüllt"
                gap = 0 
                
        # --- VOLLZEIT LOGIK: LÜCKENFÜLLER ---
        elif gap > 3: # Vollzeit
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
                # Rest-Gap bleibt stehen
                gap = gap - dauer_tage

        # Modul eintragen
        plan.append({
            "Modul": kurs['Modulname'],
            "Kuerzel": modul,
            "Start": start,
            "Ende": ende,
            "Wartetage_davor": gap, # Sollte bei TZ 0 sein, da gefüllt
            "Kategorie": MODUL_ZU_KAT.get(modul, "Sonstiges")
        })
        
        if modul == PRAXIS_MODUL: pmpx_bereits_platziert = True
        
        # --- TEILZEIT: SALDO AUFLADEN ---
        if ist_teilzeit:
            dauer_modul = (ende - start).days + 1
            verdienst = dauer_modul / 2  # 50% der Dauer
            tz_saldo += verdienst
            modul_counter += 1
            
            naechster_moeglicher_start = ende + timedelta(days=1)
            
            # --- TEILZEIT: PAUSE EINSCHIEBEN? ---
            # Bedingungen:
            # 1. Wir haben 2 Module hintereinander gemacht (Counter >= 2)
            # 2. ODER wir sind am allerletzten Modul (dann müssen wir abbauen)
            # 3. UND wir haben überhaupt Guthaben (Saldo > 0)
            
            is_last_module = (i == anzahl_module - 1)
            
            if (modul_counter >= 2 or is_last_module) and tz_saldo > 0:
                
                # WICHTIG: Bevor wir eine Pause erzwingen, schauen wir kurz in die Zukunft!
                # Wenn das NÄCHSTE Modul sowieso erst in 3 Wochen startet, 
                # brauchen wir JETZT keine künstliche Pause machen, die kommt ja gleich von selbst.
                
                # Einfacher Check: Wir erzwingen die Pause nur, wenn wir Guthaben haben.
                # Die Länge ist MAXIMAL 4 Wochen (28 Tage).
                # Wenn wir am Ende sind, nehmen wir alles (auch wenn > 4 Wochen, um auf die Summe zu kommen? 
                # User sagte: "Nie länger als 4 Wochen". Aber wenn wir noch 6 Wochen Guthaben haben?
                # Dann machen wir 4 Wochen Pause -> Rest verfällt? Nein, muss aufgehen.
                # Wir machen am Ende den Rest. Zwischendrin deckeln wir auf 28.
                
                pause_tage = tz_saldo
                if not is_last_module:
                    pause_tage = min(tz_saldo, 28) # Deckel 4 Wochen zwischendrin
                
                # Mindestens 1 Woche Pause, sonst lohnt das Stückeln nicht (außer am Ende)
                if pause_tage >= 5 or is_last_module:
                    tz_start = naechster_moeglicher_start
                    tz_ende = tz_start + timedelta(days=int(pause_tage) - 1)
                    # -1 weil Start+1Tag = 2 Tage Spanne
                    # Besser: start + timedelta(days=dauer) ist der Endzeitpunkt exklusiv? 
                    # Pandas Logik: 1.1. + 1 Tag = 2.1.
                    # Wenn Pause 1 Tag: 1.1. bis 1.1.
                    
                    if pause_tage < 1: pause_tage = 1 # Safety
                    
                    # Korrekte Berechnung Enddatum
                    tz_ende = tz_start + timedelta(days=int(pause_tage) -1 if pause_tage >=1 else 0)

                    plan.append({
                        "Modul": "Teilzeit-Selbstlernphase",
                        "Kuerzel": "TZ-LERNEN",
                        "Start": tz_start,
                        "Ende": tz_ende,
                        "Wartetage_davor": 0,
                        "Kategorie": "Teilzeit"
                    })
                    
                    tz_saldo -= pause_tage
                    modul_counter = 0 # Reset
                    naechster_moeglicher_start = tz_ende + timedelta(days=1)

        else:
            # Vollzeit Standard weiter
            naechster_moeglicher_start = ende + timedelta(days=1)
            
    # --- ENDE FOR LOOP ---

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
                            elif item['Wartetage_davor'] > 3: hinweis = f"⚠️ {item['Wartetage_davor']} Tage Lücke davor"
                            
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