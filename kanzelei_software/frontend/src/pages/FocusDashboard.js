/**
 * Fokus-Dashboard — Kritisch, Blockiert, Automatisch heute, Top-Nervfaktoren
 */
import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  getBlockierung,
  getAutopilotStats,
  getHeuteOps,
  getKpis,
  getOnboardingStatus,
  getDashboardRoi,
} from "../api";
import { PRODUCT_SUBLINE } from "../navAccess";
import { useContentLayoutWidth } from "../useContentLayoutWidth";
import OnboardingWizard from "../components/OnboardingWizard";

const AMPEL = {
  gruen: { bg: "color-mix(in srgb, var(--green) 14%, var(--bg3))", border: "var(--green)", label: "Grün" },
  gelb: { bg: "color-mix(in srgb, var(--orange) 14%, var(--bg3))", border: "var(--orange)", label: "Gelb" },
  rot: { bg: "color-mix(in srgb, var(--red) 14%, var(--bg3))", border: "var(--red)", label: "Rot" },
};

function Section({ title, subtitle, children, accent = "var(--accent)" }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <div style={{ marginBottom: 14 }}>
        <h2 style={{
          margin: 0, fontFamily: "var(--font-head)", fontSize: 18, color: "var(--text)",
          borderLeft: `3px solid ${accent}`, paddingLeft: 12,
        }}>
          {title}
        </h2>
        {subtitle ? (
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--text3)", paddingLeft: 15 }}>
            {subtitle}
          </p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function StatCard({ label, value, sub, color = "var(--text)" }) {
  return (
    <div style={{
      background: "var(--bg2)", border: "1px solid var(--border2)", borderRadius: 12,
      padding: "16px 18px", minWidth: 0,
    }}>
      <div style={{ fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontFamily: "var(--font-head)", color, marginTop: 6, lineHeight: 1 }}>
        {value}
      </div>
      {sub ? <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 6 }}>{sub}</div> : null}
    </div>
  );
}

export default function FocusDashboard({ onTab, onEmail, onRefresh, isMobile = false }) {
  const lw = useContentLayoutWidth();
  const pad = isMobile || lw < 960 ? "16px max(12px, env(safe-area-inset-left))" : "24px 36px";
  const grid2 = lw < 640 ? "1fr" : "repeat(2, minmax(0, 1fr))";
  const grid4 = lw < 520 ? "1fr" : lw < 900 ? "repeat(2, 1fr)" : "repeat(4, 1fr)";

  const [loading, setLoading] = useState(true);
  const [block, setBlock] = useState(null);
  const [auto, setAuto] = useState(null);
  const [ops, setOps] = useState(null);
  const [kpis, setKpis] = useState([]);
  const [onboarding, setOnboarding] = useState(null);
  const [roi, setRoi] = useState(null);
  const [erweitert, setErweitert] = useState(false);

  const laden = useCallback(async () => {
    setLoading(true);
    try {
      const [b, a, o, k, ob, r] = await Promise.all([
        getBlockierung().catch(() => null),
        getAutopilotStats().catch(() => null),
        getHeuteOps().catch(() => null),
        getKpis().catch(() => []),
        getOnboardingStatus().catch(() => null),
        getDashboardRoi().catch(() => null),
      ]);
      setBlock(b);
      setAuto(a);
      setOps(o);
      setOnboarding(ob);
      setRoi(r);
      const rows = Array.isArray(k?.eintraege) ? k.eintraege : (Array.isArray(k) ? k : []);
      setKpis(rows);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { laden(); }, [laden]);

  const kritisch = kpis.filter((x) => x.status === "KRITISCH" || x.health_ampel === "rot");
  const blockiert = (block?.eintraege || []).slice(0, 12);
  const offeneAntworten = kpis
    .filter((x) => (x.tage_ohne_antwort || 0) >= 7)
    .sort((a, b) => (b.tage_ohne_antwort || 0) - (a.tage_ohne_antwort || 0))
    .slice(0, 8);
  const heute = auto?.heute || {};
  const nerv = block?.nervfaktoren || {};

  return (
    <div style={{ background: "var(--bg)", minHeight: "100%", padding: `${pad} 32px` }}>
      <header style={{ marginBottom: 28, paddingBottom: 20, borderBottom: "1px solid var(--border)" }}>
        <div style={{ fontFamily: "var(--font-head)", fontSize: lw < 520 ? 22 : 28, color: "var(--text)", marginBottom: 6 }}>
          Was brennt heute?
        </div>
        <div style={{ fontSize: 14, color: "var(--text3)", lineHeight: 1.5, maxWidth: 640 }}>
          {PRODUCT_SUBLINE}
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: "var(--text3)", display: "flex", gap: 12, flexWrap: "wrap" }}>
          <span>{new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}</span>
          <button type="button" onClick={() => onTab?.("aufgaben")} style={{
            border: "none", background: "transparent", color: "var(--accent)", cursor: "pointer", fontSize: 12, padding: 0,
          }}>
            Aufgaben →
          </button>
        </div>
      </header>

      {!loading && onboarding && !onboarding.bereit ? (
        <OnboardingWizard status={onboarding} onTab={onTab} onRefresh={laden} />
      ) : null}

      {loading ? (
        <div style={{ color: "var(--text3)", padding: 40, textAlign: "center" }}>Lade Übersicht…</div>
      ) : (
        <>
          <Section title="Kritisch" subtitle="Fristen und blockierte Fälle" accent="var(--red)">
            <div style={{ display: "grid", gridTemplateColumns: grid4, gap: 12, marginBottom: 16 }}>
              <StatCard label="Kritische Mandanten" value={kritisch.length} color="var(--red)" sub="sofort prüfen" />
              <StatCard label="Überfällige Aufgaben" value={ops?.aufgaben_ueberfaellig ?? "—"} color="var(--orange)" />
              <StatCard label="Heute fällig" value={ops?.aufgaben_heute ?? "—"} />
              <StatCard label="Fehlende Unterlagen" value={ops?.fehlende_belege ?? "—"} color="var(--orange)" />
            </div>
            {kritisch.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--green)", padding: 12, background: "var(--bg2)", borderRadius: 10 }}>
                Keine kritischen Fälle — gut so.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {kritisch.slice(0, 6).map((k) => (
                  <div key={k.mandant} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12,
                    padding: "12px 14px", background: "var(--bg2)", borderRadius: 10,
                    border: "1px solid color-mix(in srgb, var(--red) 25%, var(--border))",
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <Link to={`/mandant/${encodeURIComponent(k.mandant)}`} style={{ color: "var(--text)", fontWeight: 600, textDecoration: "none" }}>
                        {k.mandant}
                      </Link>
                      <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 4 }}>
                        {(k.health_gruende || []).slice(0, 2).join(" · ") || k.status}
                      </div>
                    </div>
                    <button type="button" onClick={() => onEmail?.(k.mandant)} style={{
                      flexShrink: 0, padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border2)",
                      background: "var(--bg3)", cursor: "pointer", fontSize: 12,
                    }}>
                      Erinnern
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Blockierungszentrum" subtitle={nerv.headline || "Was hält die Kanzlei auf?"} accent="var(--orange)">
            {blockiert.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--text3)" }}>Keine offenen Blockierungen.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {blockiert.map((row, i) => {
                  const a = AMPEL[row.health_ampel] || AMPEL.gelb;
                  return (
                    <div key={`${row.mandant}-${row.typ}-${i}`} style={{
                      padding: "12px 14px", background: a.bg, borderRadius: 10,
                      borderLeft: `3px solid ${a.border}`,
                      display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12,
                    }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)" }}>{row.titel}</div>
                        <div style={{ fontSize: 12, color: "var(--text2)", marginTop: 4 }}>
                          <strong>{row.mandant}</strong> — {row.detail}
                        </div>
                      </div>
                      <button type="button" onClick={() => onEmail?.(row.mandant)} style={{
                        flexShrink: 0, padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border2)",
                        background: "var(--bg3)", cursor: "pointer", fontSize: 12,
                      }}>
                        Erinnern
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            <button type="button" onClick={() => onTab?.("mandanten")} style={{
              marginTop: 12, padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "transparent", color: "var(--accent)", cursor: "pointer", fontSize: 13,
            }}>
              Alle Mandanten →
            </button>
          </Section>

          {offeneAntworten.length > 0 ? (
            <Section title="Offene Antworten" subtitle="Mandanten ohne Rückmeldung" accent="var(--blue)">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {offeneAntworten.map((k) => (
                  <div key={k.mandant} style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12,
                    padding: "12px 14px", background: "var(--bg2)", borderRadius: 10, border: "1px solid var(--border2)",
                  }}>
                    <div>
                      <Link to={`/mandant/${encodeURIComponent(k.mandant)}`} style={{ fontWeight: 600, color: "var(--text)", textDecoration: "none" }}>
                        {k.mandant}
                      </Link>
                      <div style={{ fontSize: 12, color: "var(--orange)", marginTop: 4 }}>
                        {k.tage_ohne_antwort} Tage ohne Antwort
                        {(k.health_gruende || [])[0] ? ` · ${k.health_gruende[0]}` : ""}
                      </div>
                    </div>
                    <button type="button" onClick={() => onEmail?.(k.mandant)} style={{
                      padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border2)",
                      background: "var(--bg3)", cursor: "pointer", fontSize: 12,
                    }}>
                      Erinnern
                    </button>
                  </div>
                ))}
              </div>
            </Section>
          ) : null}

          <Section title="Autopilot heute" subtitle={auto?.roi_hinweis} accent="var(--green)">
            <div style={{ display: "grid", gridTemplateColumns: grid2, gap: 12 }}>
              <StatCard label="Erinnerungen" value={heute.erinnerungen_gesendet ?? 0} sub="E-Mail & Bot" color="var(--green)" />
              <StatCard label="Dokumente eingesammelt" value={heute.dokumente_eingesammelt ?? 0} color="var(--green)" />
              <StatCard label="Automationen" value={heute.automationen_ausgefuehrt ?? 0} />
              <StatCard label="Geschätzte Std. gespart" value={heute.geschaetzte_stunden_gespart ?? "0"} sub="heute" color="var(--accent)" />
            </div>
            <button type="button" onClick={() => onTab?.("automation")} style={{
              marginTop: 14, padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "var(--bg2)", cursor: "pointer", fontSize: 13,
            }}>
              Automationen verwalten →
            </button>
          </Section>

          <div style={{ marginBottom: 20 }}>
            <button type="button" onClick={() => setErweitert((v) => !v)} style={{
              padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
              background: "var(--bg2)", cursor: "pointer", fontSize: 13, color: "var(--text2)",
            }}>
              {erweitert ? "▾ Weniger anzeigen" : "▸ Integrationen, ROI & Top-Blocker"}
            </button>
          </div>

          {erweitert ? (
            <>
          {ops?.m365?.aktiv ? (
            <Section title="Outlook heute" subtitle={ops.m365.connected_email ? `Verbunden: ${ops.m365.connected_email}` : "Microsoft 365 Kalender"} accent="var(--blue)">
              <div style={{ display: "grid", gridTemplateColumns: grid2, gap: 12, marginBottom: 12 }}>
                <StatCard label="Termine heute" value={ops.m365.termine_heute ?? 0} color="var(--blue)" />
                <StatCard label="Termine (14 Tage)" value={ops.m365.termine_14t ?? 0} sub="Pilot-Sync" />
              </div>
              {(ops.m365.preview_heute || []).length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--text3)" }}>Keine Termine heute im verbundenen Kalender.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {ops.m365.preview_heute.map((ev, i) => (
                    <div key={i} style={{
                      padding: "10px 14px", background: "var(--bg2)", borderRadius: 10, border: "1px solid var(--border2)",
                    }}>
                      <div style={{ fontWeight: 600, fontSize: 14 }}>{ev.subject}</div>
                      <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 4 }}>
                        {String(ev.start || "").slice(11, 16) || "—"}
                        {ev.location ? ` · ${ev.location}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <button type="button" onClick={() => onTab?.("settings")} style={{
                marginTop: 12, padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
                background: "transparent", color: "var(--accent)", cursor: "pointer", fontSize: 13,
              }}>
                M365 in Einstellungen →
              </button>
            </Section>
          ) : ops?.m365?.verbunden && !ops?.m365?.sync_aktiv ? (
            <Section title="Microsoft 365" subtitle="Kalender-Sync ist deaktiviert — unter Integrationen aktivieren" accent="var(--text3)">
              <button type="button" onClick={() => onTab?.("settings")} style={{
                padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)",
                background: "var(--bg2)", cursor: "pointer", fontSize: 13,
              }}>
                Integrationen öffnen →
              </button>
            </Section>
          ) : null}

          {ops?.m365_mail?.aktiv ? (
            <Section title="Posteingang (M365)" subtitle={ops.m365_mail.hinweis || "Mandanten-Mails zuordnen"} accent="var(--blue)">
              <div style={{ display: "grid", gridTemplateColumns: grid2, gap: 12, marginBottom: 12 }}>
                <StatCard label="Ungelesen (Vorschau)" value={ops.m365_mail.ungelesen ?? 0} color="var(--blue)" />
                <StatCard label="Mandanten-Treffer" value={ops.m365_mail.mandanten_treffer ?? 0} sub="Pilot read-only" />
              </div>
              {(ops.m365_mail.preview || []).length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--text3)" }}>Keine passenden Mails in der Vorschau.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {ops.m365_mail.preview.map((msg, i) => (
                    <div key={i} style={{
                      padding: "10px 14px", background: "var(--bg2)", borderRadius: 10, border: "1px solid var(--border2)",
                    }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>{msg.subject}</div>
                      <div style={{ fontSize: 12, color: "var(--text3)", marginTop: 4 }}>
                        {msg.from || "—"}
                        {msg.mandant_vorschlag ? (
                          <> · Mandant: <strong>{msg.mandant_vorschlag}</strong></>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          ) : null}

          {roi ? (
            <Section title="ROI-Center" subtitle={roi.text} accent="var(--brand, var(--accent))">
              <div style={{ display: "grid", gridTemplateColumns: grid4, gap: 12 }}>
                <StatCard label="Erinnerungen" value={roi.erinnerungen ?? 0} color="var(--blue)" />
                <StatCard label="Dokumente" value={roi.dokumente_eingesammelt ?? 0} />
                <StatCard label="Automationen" value={roi.automationen ?? 0} />
                <StatCard
                  label="Std. gespart (geschätzt)"
                  value={roi.geschaetzte_stunden_gespart ?? 0}
                  sub={roi.monat || ""}
                  color="var(--accent)"
                />
              </div>
            </Section>
          ) : null}

          {(nerv.top || []).length > 0 ? (
            <Section title="Top-Nervfaktoren" subtitle={nerv.headline}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(nerv.top || []).map((t) => (
                  <div key={t.mandant} style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                    background: "var(--bg2)", borderRadius: 10, border: "1px solid var(--border2)",
                  }}>
                    <span style={{
                      width: 10, height: 10, borderRadius: "50%", flexShrink: 0,
                      background: t.health_ampel === "rot" ? "var(--red)" : t.health_ampel === "gelb" ? "var(--orange)" : "var(--green)",
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{t.mandant}</div>
                      <div style={{ fontSize: 11, color: "var(--text3)" }}>
                        Gesundheit {t.health_score}/100 · {(t.health_gruende || [])[0] || ""}
                      </div>
                    </div>
                    <span style={{ fontSize: 12, color: "var(--text3)" }}>{t.gewicht}</span>
                  </div>
                ))}
              </div>
            </Section>
          ) : null}

            </>
          ) : null}
        </>
      )}

      <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => { laden(); onRefresh?.(); }} style={{
          padding: "8px 14px", borderRadius: 8, border: "1px solid var(--border2)", background: "var(--bg2)", cursor: "pointer",
        }}>
          Aktualisieren
        </button>
      </div>
    </div>
  );
}

