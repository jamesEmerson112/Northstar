(() => {
  const $ = (id) => document.getElementById(id);

  const DEFAULT_CENTER = { lat: 37.7749, lng: -122.4194 };
  const DEFAULT_ZOOM = 14;
  const TILT_DEG = 67.5;
  const TRAIL_MAX = 600;
  const DRONE_PATH = "M0,-12 L8,8 L0,4 L-8,8 Z";
  const ARRIVAL_TOL_M = 8;
  const NAV_ALT_M = 3;
  const ROUTE_THIN_M = 12;
  const ROUTE_MAX_WAYPOINTS = 250;

  let map = null;
  let marker = null;
  let trail = null;
  const trailPath = [];
  let droneId = null;
  let droneSysId = null;
  let lastHeading = 0;
  let lastDronePos = null;

  let directionsService = null;
  let plannedPolyline = null;
  let routeQueue = [];
  let currentWaypoint = null;
  let navFromPlace = null;
  let navToPlace = null;

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

  function haversineM(a, b) {
    const R = 6371000;
    const toRad = (d) => d * Math.PI / 180;
    const dLat = toRad(b.lat - a.lat);
    const dLng = toRad(b.lng - a.lng);
    const lat1 = toRad(a.lat);
    const lat2 = toRad(b.lat);
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
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
      lastDronePos = ll;
      ensureMarker(ll);
      trailPath.push(ll);
      if (trailPath.length > TRAIL_MAX) trailPath.splice(0, trailPath.length - TRAIL_MAX);
      if (trail) trail.setPath(trailPath);

      if (currentWaypoint) {
        const dist = haversineM(ll, currentWaypoint);
        if (dist < ARRIVAL_TOL_M) dispatchNextWaypoint();
      }
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
      return null;
    }
    const r = await fetch(`/api/drones/${droneId}/commands/${kind}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body == null ? null : JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    $("d-ack").textContent = `${kind} → ${data.status ?? r.status}`;
    return data;
  }

  function clearPlannedPolyline() {
    if (plannedPolyline) {
      plannedPolyline.setMap(null);
      plannedPolyline = null;
    }
  }

  function cancelNavigation(reason) {
    routeQueue = [];
    currentWaypoint = null;
    clearPlannedPolyline();
    if (reason) setHint(reason);
  }

  function dispatchNextWaypoint() {
    if (routeQueue.length === 0) {
      currentWaypoint = null;
      clearPlannedPolyline();
      setHint("arrived");
      return;
    }
    currentWaypoint = routeQueue.shift();
    postCommand("goto", { lat: currentWaypoint.lat, lon: currentWaypoint.lng, alt_m: NAV_ALT_M });
  }

  function thinPath(latLngs) {
    if (latLngs.length === 0) return [];
    const result = [{ lat: latLngs[0].lat(), lng: latLngs[0].lng() }];
    for (let i = 1; i < latLngs.length; i++) {
      const next = { lat: latLngs[i].lat(), lng: latLngs[i].lng() };
      const last = result[result.length - 1];
      if (haversineM(last, next) >= ROUTE_THIN_M) result.push(next);
    }
    if (result.length > ROUTE_MAX_WAYPOINTS) {
      const stride = Math.ceil(result.length / ROUTE_MAX_WAYPOINTS);
      const sampled = result.filter((_, i) => i % stride === 0);
      if (sampled[sampled.length - 1] !== result[result.length - 1]) sampled.push(result[result.length - 1]);
      return sampled;
    }
    return result;
  }

  async function startJourney() {
    const fromLoc = navFromPlace?.geometry?.location;
    const toLoc = navToPlace?.geometry?.location;
    if (!fromLoc && !toLoc) { setHint("Pick a From and a To"); return; }
    if (!fromLoc) { setHint("Pick a From"); return; }
    if (!toLoc) { setHint("Pick a To"); return; }

    cancelNavigation();

    setHint("teleporting to From…");
    const teleportResult = await postCommand("teleport", {
      lat: fromLoc.lat(),
      lon: fromLoc.lng(),
    });
    if (!teleportResult || teleportResult.status !== "ACCEPTED") {
      setHint(`teleport failed: ${teleportResult?.status ?? "no response"}`);
      return;
    }

    setHint("computing route…");
    let result;
    try {
      result = await directionsService.route({
        origin: fromLoc,
        destination: toLoc,
        travelMode: google.maps.TravelMode.DRIVING,
      });
    } catch (e) {
      setHint(`no route: ${e?.message ?? e}`);
      return;
    }
    const route = result?.routes?.[0];
    if (!route) {
      setHint("no route found");
      return;
    }

    // Use the denser per-step path so the drone follows actual road curvature.
    // overview_path is too sparse — chords between widely spaced points cut through buildings.
    const stepLatLngs = [];
    for (const leg of route.legs ?? []) {
      for (const step of leg.steps ?? []) {
        const stepPath = step.path ?? [];
        for (const p of stepPath) stepLatLngs.push(p);
      }
    }
    const sourceLatLngs = stepLatLngs.length ? stepLatLngs : (route.overview_path ?? []);
    if (sourceLatLngs.length === 0) { setHint("empty route"); return; }

    const path = thinPath(sourceLatLngs);
    if (path.length === 0) { setHint("empty route"); return; }

    plannedPolyline = new google.maps.Polyline({
      path,
      strokeColor: "#3399ff",
      strokeOpacity: 0.85,
      strokeWeight: 4,
      map,
    });

    routeQueue = path.slice();
    setHint(`navigating ${path.length} waypoints`);
    dispatchNextWaypoint();
  }

  function wirePanelControls() {
    document.querySelectorAll(".buttons button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.dataset.cmd;
        if (kind === "disarm" || kind === "land") cancelNavigation();
        if (kind === "takeoff") postCommand(kind, { alt_m: 20 });
        else if (kind === "goto") return;
        else postCommand(kind);
      });
    });

    $("mode-apply").addEventListener("click", () => {
      const mode = $("mode-select").value;
      if (mode === "MANUAL" || mode === "RTL") cancelNavigation();
      postCommand("mode", { mode });
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
    setActiveView("roadmap");

    $("tilt-toggle").addEventListener("click", () => {
      const cur = map.getTilt() || 0;
      map.setTilt(cur > 0 ? 0 : TILT_DEG);
      $("tilt-toggle").classList.toggle("active", (map.getTilt() || 0) > 0);
    });
    $("tilt-toggle").classList.add("active");
  }

  function wireNavControls() {
    const opts = { fields: ["geometry", "formatted_address"] };
    const acFrom = new google.maps.places.Autocomplete($("nav-from"), opts);
    acFrom.addListener("place_changed", () => { navFromPlace = acFrom.getPlace(); });
    const acTo = new google.maps.places.Autocomplete($("nav-to"), opts);
    acTo.addListener("place_changed", () => { navToPlace = acTo.getPlace(); });

    $("nav-go").addEventListener("click", startJourney);
    $("nav-cancel").addEventListener("click", () => cancelNavigation("navigation cancelled"));

    [$("nav-from"), $("nav-to")].forEach((el) => {
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter") e.preventDefault();
      });
    });
  }

  window.initMap = function initMap() {
    const mapOptions = {
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      mapTypeId: "roadmap",
      tilt: TILT_DEG,
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

    directionsService = new google.maps.DirectionsService();

    map.addListener("click", (e) => {
      if (!$("goto-toggle").checked) return;
      cancelNavigation();
      postCommand("goto", { lat: e.latLng.lat(), lon: e.latLng.lng(), alt_m: NAV_ALT_M });
    });

    wireMapControls();
    wireNavControls();
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
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(cfg.google_maps_api_key)}&v=weekly&libraries=places&callback=initMap`;
    s.async = true;
    s.defer = true;
    s.onerror = () => setHint("failed to load Google Maps script");
    document.head.appendChild(s);
  }

  bootstrap();
})();
