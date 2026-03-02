mandanten = { "Müller GmbH" : { 
    "status": "Warten auf Mandant",
    "fehlende_dokumente": 3,
    "tage_ohne-antwort" : 6,
    "warnung_gesendet": False
}}

einstellungen = {
    "warnstufe_gelb" : 3,
    "warnstufe_rot" : 7
}

for name, daten in mandanten.items():
    tage = daten["tage_ohne_antwort"]

    print ("Mandant:", name)

    if tage >= einstellungen["warnstufe_rot"] and not daten["warnung_gesendet"]:
        print ("🔴 Dringend reagieren!")
        daten["warnung_gesendet"] = True

    elif tage >= einstellungen["warnstufe_gelb"] and not daten["warnung_gesendet"]:
        print (" 🟡 Bald nachfassen")
        daten ["warnung_gesendet"] = True

    else: 
        print (" 🟢 Alles okay ")