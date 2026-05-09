(() => {
  const $ = (id) => document.getElementById(id);

  const map = L.map("map").setView([37.7749, -122.4194], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19,
  }).addTo(map);

  let marker = null;
  const trail = L.polyline([], { color: "#36c", weight: 2 }).addTo(map);
  let droneId = null; // resolved on first telemetry message
  let droneSysId = null;

  function ensureMarker(latlng) {
    if (!marker) {
      marker = L.marker(latlng).addTo(map);
      map.setView(latlng, map.getZoom());
    } else {
      marker.setLatLng(latlng);
    }
  }

  function setOnline(online) {
    const el = $("d-online");
    el.textContent = online ? "online" : "offline";
    el.className = online ? "online" : "offline";
  }

  function fmt(x, digits = 5) {
    return (x === null || x === undefined) ? "—" : Number(x).toFixed(digits);
  }

  function applyTelemetry(p) {
    if (p.system_id != null) droneSysId = p.system_id;
    if (p.drone_id != null) droneId = p.drone_id;
    $("d-id").textContent = droneId ?? droneSysId ?? "—";
    setOnline(!!p.last_heartbeat_at);
    $("d-mode").textContent = p.mode ?? "—";
    $("d-armed").textContent = p.armed === null || p.armed === undefined ? "—" : (p.armed ? "yes" : "no");
    $("d-lat").textContent = fmt(p.lat);
    $("d-lon").textContent = fmt(p.lon);
    $("d-alt").textContent = (p.rel_alt_m == null ? "—" : Number(p.rel_alt_m).toFixed(1)) + " m";
    $("d-hdg").textContent = (p.heading_deg == null ? "—" : Number(p.heading_deg).toFixed(0)) + " °";
    $("d-batt").textContent = (p.battery_remaining == null ? "—" : p.battery_remaining) + " %";
    $("d-gps").textContent = (p.satellites == null ? "—" : p.satellites) + " sats";

    if (p.lat != null && p.lon != null) {
      const ll = [p.lat, p.lon];
      ensureMarker(ll);
      trail.addLatLng(ll);
      const latlngs = trail.getLatLngs();
      if (latlngs.length > 600) trail.setLatLngs(latlngs.slice(-600));
    }
  }

  function applyAck(ack) {
    $("d-ack").textContent = `${ack.command_id ?? "?"} → ${ack.status}`;
  }

  function setupSocket() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/telemetry`);
    ws.onopen = () => $("hint").textContent = "live";
    ws.onclose = () => {
      $("hint").textContent = "disconnected — retrying…";
      setTimeout(setupSocket, 1500);
    };
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "telemetry" || msg.type === "snapshot") applyTelemetry(msg);
        else if (msg.type === "command_ack") applyAck(msg);
      } catch (e) {
        console.error(e);
      }
    };
  }

  async function postCommand(kind, body) {
    if (droneId == null) {
      $("hint").textContent = "no drone yet — wait for telemetry";
      return;
    }
    const r = await fetch(`/api/drones/${droneId}/commands/${kind}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body == null ? null : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    $("d-ack").textContent = `${kind} → ${data.status ?? r.status}`;
  }

  document.querySelectorAll(".buttons button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.cmd;
      if (kind === "takeoff") postCommand(kind, { alt_m: 20 });
      else if (kind === "goto") return;
      else postCommand(kind);
    });
  });

  $("mode-apply").addEventListener("click", () => {
    postCommand("mode", { mode: $("mode-select").value });
  });

  $("goto-toggle").addEventListener("change", (e) => {
    map.getContainer().style.cursor = e.target.checked ? "crosshair" : "";
  });

  map.on("click", (e) => {
    if (!$("goto-toggle").checked) return;
    const alt = parseFloat(prompt("Goto altitude (m, AGL):", "20"));
    if (!Number.isFinite(alt) || alt <= 0) return;
    postCommand("goto", { lat: e.latlng.lat, lon: e.latlng.lng, alt_m: alt });
  });

  setupSocket();
})();
