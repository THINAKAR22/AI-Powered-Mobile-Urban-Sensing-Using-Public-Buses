import React, { useEffect, useState } from "react";
import { getHealth, createIncident, createBus, getIncidents, getBuses } from "../services/api";
import {
  IconActivity,
  IconDatabase,
  IconVolume,
  IconVolumeX,
  IconCheckCircle,
  IconRefresh,
  IconDownload,
  IconSend,
  IconPlus,
} from "../components/icons";
import { playAlertChime } from "../utils/audio";
import { downloadJSON } from "../utils/export";

const CITIES = [
  { name: "Chennai, TN", lat: 13.0827, lng: 80.2707 },
  { name: "Bengaluru, KA", lat: 12.9716, lng: 77.5946 },
  { name: "Mumbai, MH", lat: 19.076, lng: 72.8777 },
  { name: "New Delhi, DL", lat: 28.6139, lng: 77.209 },
  { name: "Hyderabad, TS", lat: 17.385, lng: 78.4867 },
];

export default function Settings({
  audioEnabled = true,
  onToggleAudio,
  onTriggerWsAlert,
}) {
  const [healthStatus, setHealthStatus] = useState(null);
  const [latency, setLatency] = useState(null);
  const [checking, setChecking] = useState(false);
  const [seedBusy, setSeedBusy] = useState(false);
  const [seedMessage, setSeedMessage] = useState(null);

  // Settings in localStorage
  const [defaultCity, setDefaultCity] = useState(
    localStorage.getItem("urban_sensing_city") || "Chennai, TN"
  );
  const [toastDuration, setToastDuration] = useState(
    Number(localStorage.getItem("urban_sensing_toast_duration")) || 6
  );

  const runHealthCheck = async () => {
    setChecking(true);
    const start = performance.now();
    try {
      const data = await getHealth();
      const end = performance.now();
      setLatency(Math.round(end - start));
      setHealthStatus({ ok: true, data });
    } catch (err) {
      setLatency(null);
      setHealthStatus({ ok: false, error: err.message || "Failed to reach server" });
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    runHealthCheck();
  }, []);

  const handleCityChange = (cityName) => {
    setDefaultCity(cityName);
    localStorage.setItem("urban_sensing_city", cityName);
  };

  const handleToastDurationChange = (seconds) => {
    setToastDuration(seconds);
    localStorage.setItem("urban_sensing_toast_duration", String(seconds));
  };

  const handleTriggerTestIncident = async () => {
    setSeedBusy(true);
    setSeedMessage(null);
    try {
      const cityObj = CITIES.find((c) => c.name === defaultCity) || CITIES[0];
      const offsetLat = (Math.random() - 0.5) * 0.04;
      const offsetLng = (Math.random() - 0.5) * 0.04;

      const types = ["pothole", "crack", "surface_damage", "waterlogging"];
      const chosenType = types[Math.floor(Math.random() * types.length)];
      const severities = ["critical", "high", "medium"];
      const chosenSeverity = severities[Math.floor(Math.random() * severities.length)];
      const busNum = `TN-${String(Math.floor(Math.random() * 89) + 10).padStart(2, "0")}-SB-${Math.floor(Math.random() * 9000) + 1000}`;

      const testPayload = {
        incident_type: chosenType,
        severity: chosenSeverity,
        confidence: Number((0.85 + Math.random() * 0.14).toFixed(2)),
        latitude: Number((cityObj.lat + offsetLat).toFixed(6)),
        longitude: Number((cityObj.lng + offsetLng).toFixed(6)),
        bus_number: busNum,
        description: `Simulated ${chosenType} defect captured by Dashcam Camera #02 along ${cityObj.name.split(",")[0]} transit corridor.`,
        status: "pending",
        verified: false,
      };

      const result = await createIncident(testPayload);
      setSeedMessage({
        type: "success",
        text: `Created simulated incident #${result.id} (${chosenType}) via WebSocket & Database!`,
      });

      if (audioEnabled) {
        playAlertChime();
      }
    } catch (err) {
      setSeedMessage({
        type: "error",
        text: `Failed to trigger incident: ${err.message}`,
      });
    } finally {
      setSeedBusy(false);
    }
  };

  const handleGenerateTestBus = async () => {
    setSeedBusy(true);
    setSeedMessage(null);
    try {
      const cityObj = CITIES.find((c) => c.name === defaultCity) || CITIES[0];
      const busNum = `TN-01-BUS-${Math.floor(Math.random() * 9000) + 1000}`;
      await createBus({
        bus_number: busNum,
        route: `Express Route ${Math.floor(Math.random() * 80) + 10}`,
        status: "active",
        last_latitude: cityObj.lat,
        last_longitude: cityObj.lng,
      });
      setSeedMessage({
        type: "success",
        text: `Registered test bus ${busNum} with live dashcam sensing status!`,
      });
    } catch (err) {
      setSeedMessage({
        type: "error",
        text: `Failed to register bus: ${err.message}`,
      });
    } finally {
      setSeedBusy(false);
    }
  };

  const handleBackupExport = async () => {
    try {
      const [incidents, buses] = await Promise.all([
        getIncidents().catch(() => []),
        getBuses().catch(() => []),
      ]);
      downloadJSON(
        {
          timestamp: new Date().toISOString(),
          system: "AI-Powered Mobile Urban Sensing Platform",
          incidents,
          buses,
        },
        `urban_sensing_full_backup_${Date.now()}.json`
      );
    } catch (err) {
      alert("Failed to export backup: " + err.message);
    }
  };

  return (
    <div className="dashboard-page settings-page">
      <div className="page-header-row">
        <div>
          <p className="eyebrow">Platform Control</p>
          <h1 className="page-title">System Settings & Diagnostics</h1>
        </div>
      </div>

      <div className="settings-grid">
        {/* System Diagnostics Card */}
        <section className="panel settings-card">
          <div className="panel__header">
            <div className="panel__title">
              <IconActivity size={18} />
              <div>
                <h2>Backend Health & API Status</h2>
                <span className="panel__subtitle">FastAPI REST & WebSocket diagnostics</span>
              </div>
            </div>
            <button
              type="button"
              className="retry-button"
              onClick={runHealthCheck}
              disabled={checking}
            >
              <IconRefresh size={13} /> {checking ? "Pinging…" : "Check Health"}
            </button>
          </div>

          <div className="health-metrics">
            <div className="health-metric">
              <span className="health-metric__label">API Server Status</span>
              <div className="health-metric__val">
                <span
                  className={`status-dot${healthStatus?.ok ? "" : " status-dot--offline"}`}
                />
                <strong>{healthStatus?.ok ? "Online & Healthy" : "Offline / Unreachable"}</strong>
              </div>
            </div>

            <div className="health-metric">
              <span className="health-metric__label">Round-Trip Latency</span>
              <div className="health-metric__val">
                <strong>{latency != null ? `${latency} ms` : "—"}</strong>
                {latency != null && (
                  <span
                    className="health-badge"
                    style={{
                      background: latency < 100 ? "var(--green-light)" : "var(--orange-light)",
                      color: latency < 100 ? "var(--green)" : "var(--orange)",
                    }}
                  >
                    {latency < 100 ? "Optimal" : "Moderate"}
                  </span>
                )}
              </div>
            </div>

            <div className="health-metric">
              <span className="health-metric__label">Database Engine</span>
              <div className="health-metric__val">
                <IconDatabase size={15} />
                <strong>
                  {healthStatus?.data?.database === "connected"
                    ? "MongoDB Connected"
                    : "Connecting…"}
                </strong>
              </div>
            </div>

            <div className="health-metric">
              <span className="health-metric__label">WebSocket Broadcast Feed</span>
              <div className="health-metric__val">
                <span className="live-badge">
                  <span className="live-badge__dot" />
                  ws://127.0.0.1:8000/ws/incidents
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Live Simulation & Test Pipeline */}
        <section className="panel settings-card">
          <div className="panel__header">
            <div className="panel__title">
              <IconSend size={18} />
              <div>
                <h2>Live Simulation & Testing</h2>
                <span className="panel__subtitle">Inject synthetic events to test realtime pipeline</span>
              </div>
            </div>
          </div>

          <p className="settings-desc">
            Use these controls to test end-to-end incident ingestion, M4/M6 WebSocket
            propagation, sound notifications, and map auto-panning.
          </p>

          {seedMessage && (
            <div
              className={`action-${seedMessage.type === "success" ? "ok" : "error"}`}
              style={{ marginBottom: "14px" }}
            >
              {seedMessage.type === "success" && <IconCheckCircle size={15} />}
              {seedMessage.text}
            </div>
          )}

          <div className="simulation-actions">
            <button
              type="button"
              className="action-button action-button--primary"
              onClick={handleTriggerTestIncident}
              disabled={seedBusy}
            >
              <IconSend size={14} /> Trigger Random Incident Alert
            </button>

            <button
              type="button"
              className="action-button"
              onClick={handleGenerateTestBus}
              disabled={seedBusy}
            >
              <IconPlus size={14} /> Add Active Sensing Bus
            </button>
          </div>
        </section>

        {/* UI & Sensing Preferences */}
        <section className="panel settings-card">
          <div className="panel__header">
            <div className="panel__title">
              <IconVolume size={18} />
              <div>
                <h2>Notification & Audio Preferences</h2>
                <span className="panel__subtitle">Alert sound and toast display rules</span>
              </div>
            </div>
          </div>

          <div className="preferences-list">
            <div className="preference-item">
              <div>
                <strong>Audio Alert Chime</strong>
                <p>Play a pleasant sound effect when a new road defect is detected.</p>
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button
                  type="button"
                  className="secondary-button secondary-button--outline"
                  onClick={playAlertChime}
                  title="Test Sound"
                >
                  <IconVolume size={13} /> Test Chime
                </button>
                <button
                  type="button"
                  className={`toggle-switch${audioEnabled ? " toggle-switch--active" : ""}`}
                  onClick={onToggleAudio}
                  aria-label="Toggle Audio Chime"
                >
                  <span className="toggle-switch__handle" />
                </button>
              </div>
            </div>

            <div className="preference-item">
              <div>
                <strong>Alert Popup Duration</strong>
                <p>How long real-time alerts remain visible on screen.</p>
              </div>
              <select
                className="setting-select"
                value={toastDuration}
                onChange={(e) => handleToastDurationChange(Number(e.target.value))}
              >
                <option value={3}>3 Seconds</option>
                <option value={6}>6 Seconds (Default)</option>
                <option value={10}>10 Seconds</option>
                <option value={20}>20 Seconds</option>
              </select>
            </div>

            <div className="preference-item">
              <div>
                <strong>Default Sensing Region</strong>
                <p>Default center coordinates for spatial map initialization.</p>
              </div>
              <select
                className="setting-select"
                value={defaultCity}
                onChange={(e) => handleCityChange(e.target.value)}
              >
                {CITIES.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Backup & Export */}
        <section className="panel settings-card">
          <div className="panel__header">
            <div className="panel__title">
              <IconDatabase size={18} />
              <div>
                <h2>Data Export & Backup</h2>
                <span className="panel__subtitle">Export complete database records</span>
              </div>
            </div>
          </div>

          <p className="settings-desc">
            Download a full JSON archive containing all incident reports, bus fleet records,
            and coordinates for archiving or civil work reporting.
          </p>

          <button
            type="button"
            className="secondary-button secondary-button--outline"
            onClick={handleBackupExport}
          >
            <IconDownload size={14} /> Download System Snapshot (JSON)
          </button>
        </section>
      </div>
    </div>
  );
}
