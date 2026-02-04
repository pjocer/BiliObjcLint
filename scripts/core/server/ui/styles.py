"""Shared CSS styles for BiliObjCLint server UI."""
from __future__ import annotations

STYLE = """
<style>
:root {
  --bg-1: #fff5f7;
  --bg-2: #ffeef2;
  --ink: #1e1e1e;
  --muted: #6b6b6b;
  --accent: #fb7299;
  --accent-dark: #f25d8e;
  --accent-2: #d97706;
  --card: #ffffff;
  --border: #fcd5df;
  --shadow: 0 18px 50px rgba(251,114,153,0.08);
  --radius: 16px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: "Space Grotesk", "IBM Plex Sans", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
  color: var(--ink);
  background: radial-gradient(1200px 600px at 10% 10%, #fff0f3 0%, transparent 60%),
              radial-gradient(900px 500px at 90% 0%, #ffe8ee 0%, transparent 60%),
              linear-gradient(180deg, var(--bg-1) 0%, var(--bg-2) 100%);
  min-height: 100vh;
}

.container {
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.brand {
  display: flex;
  flex-direction: column;
}

.brand h1 {
  margin: 0;
  font-size: 32px;
  letter-spacing: -0.02em;
}

.brand p {
  margin: 6px 0 0 0;
  color: var(--muted);
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #ffeef2;
  font-size: 12px;
}

.nav a {
  color: var(--ink);
  text-decoration: none;
  margin-right: 12px;
  font-weight: 600;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 22px;
  margin: 18px 0;
  box-shadow: var(--shadow);
  animation: floatIn 0.6s ease both;
}

@keyframes floatIn {
  from { transform: translateY(8px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.form-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
}

input, select {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 14px;
  min-width: 160px;
  background: #fff;
}

button {
  padding: 10px 16px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

button:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(251, 114, 153, 0.35);
}

.table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
}

.table th, .table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  font-size: 14px;
}

.table th {
  background: #ffeef2;
  color: #3d3d3d;
}

.table tr:nth-child(even) td {
  background: #fff5f7;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}

.stat {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  background: #fff;
}

.stat .label { color: var(--muted); font-size: 12px; }
.stat .value { font-size: 22px; font-weight: 700; }

.muted { color: var(--muted); font-size: 12px; }

.chart { display: flex; flex-direction: column; gap: 10px; }
.legend { display: flex; gap: 12px; font-size: 12px; color: var(--muted); }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-item i { display: inline-block; width: 12px; height: 12px; border-radius: 999px; }

.error { color: #b00020; }
.warn { color: #b26a00; }

.login-wrapper {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(300px, 420px);
  gap: 32px;
  align-items: center;
}

.login-panel {
  background: #fff;
  border-radius: 20px;
  padding: 24px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}

.hero {
  padding: 24px;
}

.hero h2 {
  margin: 0 0 10px;
  font-size: 30px;
}

.hero p {
  color: var(--muted);
}

/* iOS-style toggle switch */
.ios-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 26px;
  vertical-align: middle;
}

.ios-switch .slider {
  position: absolute;
  cursor: default;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #e9e9eb;
  transition: 0.3s;
  border-radius: 26px;
}

.ios-switch .slider:before {
  position: absolute;
  content: "";
  height: 22px;
  width: 22px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: 0.3s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.ios-switch.on .slider {
  background-color: #fb7299;
}

.ios-switch.on .slider:before {
  transform: translateX(18px);
}

/* Rule name with tooltip */
.rule-name {
  cursor: help;
  border-bottom: 1px dashed var(--muted);
}

@media (max-width: 800px) {
  .login-wrapper { grid-template-columns: 1fr; }
  header { flex-direction: column; align-items: flex-start; }
}
</style>
"""
