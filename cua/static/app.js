(() => {
  const $ = (id) => document.getElementById(id);

  let totalSteps = 0;
  let runStarted = false;

  function setStatus(s, label) {
    const el = $("status");
    el.textContent = label ?? s.toUpperCase();
    el.className = `status status-${s}`;
  }

  function fmtSrc(b64) { return `data:image/png;base64,${b64}`; }

  function applyEvent(e) {
    if (e.type === "start") {
      runStarted = true;
      $("task").textContent = e.task ?? "(no task)";
      $("transcript").innerHTML = "";
      $("messages").innerHTML = "";
      $("thumbs").innerHTML = "";
      $("latest").removeAttribute("src");
      $("action").textContent = "starting…";
      setStatus("start", "STARTING");
    }
    else if (e.type === "step") {
      if (e.screenshot_b64) {
        $("latest").src = fmtSrc(e.screenshot_b64);
        const t = document.createElement("img");
        t.src = fmtSrc(e.screenshot_b64);
        t.alt = `step ${e.step}`;
        t.title = `step ${e.step}: ${e.action_label ?? ""}`;
        t.addEventListener("click", () => { $("latest").src = t.src; $("action").textContent = t.title; });
        $("thumbs").appendChild(t);
        $("thumbs").scrollLeft = $("thumbs").scrollWidth;
      }
      $("action").textContent = `[${e.step}] ${e.action_label ?? ""}`;
      const li = document.createElement("li");
      li.textContent = `[${e.step}] ${e.action_label ?? ""}`;
      $("transcript").appendChild(li);
      $("transcript").parentElement.scrollTop = $("transcript").parentElement.scrollHeight;
      totalSteps = e.step;
      setStatus("step", `STEP ${e.step}`);
    }
    else if (e.type === "message") {
      const li = document.createElement("li");
      li.textContent = e.text;
      $("messages").appendChild(li);
      $("messages").parentElement.scrollTop = $("messages").parentElement.scrollHeight;
    }
    else if (e.type === "done") {
      setStatus("done", `DONE (${e.total_steps ?? totalSteps} steps)`);
    }
    else if (e.type === "error") {
      setStatus("error", "ERROR");
      $("action").textContent = `error: ${e.message ?? "unknown"}`;
    }
  }

  function connect() {
    const url = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
    const ws = new WebSocket(url);
    ws.onopen = () => { if (!runStarted) setStatus("idle", "WAITING"); };
    ws.onclose = () => { setTimeout(connect, 1500); };
    ws.onmessage = (evt) => {
      try { applyEvent(JSON.parse(evt.data)); }
      catch (e) { console.error(e); }
    };
  }

  connect();
})();
