# Kanzlei AI — Produktpositionierung

## Was wir sind

**Mandanten-Orchestrierung + Portal + proaktiver Bot + Aufgaben.**  
DATEV (oder andere Fibu) bleibt **System of Record** für Buchführung.

## Was wir nicht sind

- Kein DATEV-Ersatz
- Kein vollständiges Lohn-/Fibu-System
- Keine zertifizierte GoBD-Fibu (Exporte sind Übergabe, nicht Haftungsersatz)

## Killer-Loop (Pilot)

1. Mandant hat fehlende Belege / keine Antwort / überfällige Aufgaben  
2. **Automation → Proaktiver Bot → Analyse**  
3. Fragen im **Mandanten-Portal**  
4. Mandant antwortet → Statistik steigt, `letzte_antwort` aktualisiert  
5. Kanzlei sieht weniger Telefonate im Dashboard  

## Technisch produktiv

- DATEV Export EXTF v700  
- ELSTER XML  
- Bank CSV Import (`POST /bank/import`)  
- Portal Chat, Upload, Unterschrift  

## Bewusst deaktiviert (Roadmap)

- DATEV Live-Import  
- FinTS/EBICS live  
- ELSTER ERiC Direktversand  
- Shopify, Amazon, Personio, Lexoffice  

Diese Toggles sind in `settings_manager.ROADMAP_SETTINGS_MUST_BE_FALSE` gesperrt.

## Navigation

Standard **Produktfokus** (`produkt_fokus_aktiv`): nur Kern-Tabs.  
Erweiterte Module (Steuer-Autopilot, Scanner, …) über Einstellungen → Rollen/Navigation freischaltbar.
