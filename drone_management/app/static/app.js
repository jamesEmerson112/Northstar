(() => {
  const $ = (id) => document.getElementById(id);

  const DEFAULT_CENTER = { lat: 37.77927, lng: -122.41924 };
  const DEFAULT_ZOOM = 14;
  const TILT_DEG = 67.5;
  const TRAIL_MAX = 600;
  const DRONE_PATH = "M0,-12 L8,8 L0,4 L-8,8 Z";

  let map = null;
  let marker = null;
  let trail = null;
  const trailPath = [];
  let droneId = null;
  let droneSysId = null;
  let lastHeading = 0;

  function setHint(msg) {
    $("hint").textContent = msg;
  }

  function setOnline(online) {
    const el = $("d-online");
    el.textContent = online ? "online" : "offline";
    el.className = online ? "online" : "offline";
  }

  function fmt(x, digits = 5) {
    return (x === null || x === undefined) ? "—" : Number(x).toFixed(digits);
  }

  function droneIcon(heading) {
    return {
      path: DRONE_PATH,
      fillColor: "#ff7a00",
      fillOpacity: 1,
      strokeColor: "#222",
      strokeWeight: 1.2,
      scale: 1.4,
      rotation: Number.isFinite(heading) ? heading : 0,
      anchor: new google.maps.Point(0, 0),
    };
  }

  function ensureMarker(position) {
    if (!marker) {
      marker = new google.maps.Marker({
        position,
        map,
        icon: droneIcon(lastHeading),
        title: "drone",
      });
      map.panTo(position);
    } else {
      marker.setPosition(position);
    }
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

    if (!map) return;

    if (p.heading_deg != null) {
      lastHeading = p.heading_deg;
      if (marker) marker.setIcon(droneIcon(lastHeading));
    }

    if (p.lat != null && p.lon != null) {
      const ll = { lat: p.lat, lng: p.lon };
      ensureMarker(ll);
      trailPath.push(ll);
      if (trailPath.length > TRAIL_MAX) trailPath.splice(0, trailPath.length - TRAIL_MAX);
      if (trail) trail.setPath(trailPath);
    }
  }

  function applyAck(ack) {
    $("d-ack").textContent = `${ack.command_id ?? "?"} → ${ack.status}`;
  }

  function setupSocket() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws/telemetry`);
    ws.onopen = () => setHint("live");
    ws.onclose = () => {
      setHint("disconnected — retrying…");
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
      setHint("no drone yet — wait for telemetry");
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

  function wirePanelControls() {
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
      if (!map) return;
      map.setOptions({ draggableCursor: e.target.checked ? "crosshair" : null });
    });
  }

  function wireMapControls() {
    const viewButtons = document.querySelectorAll(".view-toggle button[data-view]");
    function setActiveView(name) {
      viewButtons.forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    }
    viewButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const v = btn.dataset.view;
        map.setMapTypeId(v);
        setActiveView(v);
      });
    });
    setActiveView("hybrid");

    $("tilt-toggle").addEventListener("click", () => {
      const cur = map.getTilt() || 0;
      map.setTilt(cur > 0 ? 0 : TILT_DEG);
      $("tilt-toggle").classList.toggle("active", (map.getTilt() || 0) > 0);
    });
  }

  window.initMap = function initMap() {
    const mapOptions = {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      mapTypeId: "hybrid",
      tilt: 0,
      streetViewControl: true,
      fullscreenControl: false,
      mapTypeControl: false,
    };
    if (window.__GMAP_MAP_ID__) mapOptions.mapId = window.__GMAP_MAP_ID__;

    map = new google.maps.Map($("map"), mapOptions);

    trail = new google.maps.Polyline({
      path: trailPath,
      strokeColor: "#36c",
      strokeOpacity: 0.9,
      strokeWeight: 2,
      map,
    });

    map.addListener("click", (e) => {
      if (!$("goto-toggle").checked) return;
      const alt = parseFloat(prompt("Goto altitude (m, AGL):", "20"));
      if (!Number.isFinite(alt) || alt <= 0) return;
      postCommand("goto", { lat: e.latLng.lat(), lon: e.latLng.lng(), alt_m: alt });
    });

    wireMapControls();
    setupSocket();
  };

  async function bootstrap() {
    wirePanelControls();
    setHint("loading map…");
    let cfg;
    try {
      const r = await fetch("/api/config");
      cfg = await r.json();
    } catch (e) {
      setHint("could not load /api/config");
      return;
    }
    if (!cfg.google_maps_api_key) {
      setHint("GOOGLE_MAPS_API_KEY not set on server");
      return;
    }
    if (cfg.google_maps_map_id) window.__GMAP_MAP_ID__ = cfg.google_maps_map_id;

    const s = document.createElement("script");
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(cfg.google_maps_api_key)}&v=weekly&callback=initMap`;
    s.async = true;
    s.defer = true;
    s.onerror = () => setHint("failed to load Google Maps script");
    document.head.appendChild(s);
  }

  bootstrap();
})();
