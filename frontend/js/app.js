(() => {
  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  const state = {
    layers: [],
    dataset: null,
    date: "2026-01-23",
    layerId: null,
    compare: false,
    dockMode: "strength", // mobile: strength | compare
    swipe: 50,
    opacity: 0.85,
    beforeOverlay: null,
    afterOverlay: null,
    singleOverlay: null,
  };

  const isMobile = () => window.matchMedia("(max-width: 991.98px)").matches;

  const map = L.map("map", { zoomControl: false }).setView([1.38, 104.12], 11);
  L.control.zoom({ position: "topright" }).addTo(map);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19,
  }).addTo(map);
  L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);

  const dock = $("controlDock");
  const sidebar = $("sidebar");
  if (dock) {
    L.DomEvent.disableClickPropagation(dock);
    L.DomEvent.disableScrollPropagation(dock);
  }
  if (sidebar) {
    L.DomEvent.disableClickPropagation(sidebar);
    L.DomEvent.disableScrollPropagation(sidebar);
  }

  function toast(msg, on = true) {
    const el = $("toast");
    el.textContent = msg || "";
    el.classList.toggle("d-none", !on);
  }

  function measureDock() {
    if (!dock || !isMobile()) {
      document.documentElement.style.setProperty("--dock-h", "0px");
      return;
    }
    const h = Math.ceil(dock.getBoundingClientRect().height);
    document.documentElement.style.setProperty("--dock-h", `${Math.max(h, 72)}px`);
    map.invalidateSize({ animate: false });
  }

  function clearOverlays() {
    [state.singleOverlay, state.beforeOverlay, state.afterOverlay].forEach((ly) => {
      if (ly) map.removeLayer(ly);
    });
    state.singleOverlay = state.beforeOverlay = state.afterOverlay = null;
  }

  function boundsOf(raster) {
    const b = raster.bounds;
    return L.latLngBounds([b.south, b.west], [b.north, b.east]);
  }

  function rasterById(id) {
    return state._rasters.find((r) => r.id === id);
  }

  function currentLayerMeta() {
    return state.layers.find((l) => l.layer_id === state.layerId);
  }

  function applySwipe() {
    if (!state.afterOverlay) return;
    const el = state.afterOverlay.getElement && state.afterOverlay.getElement();
    if (!el) return;
    const size = map.getSize();
    const x = (state.swipe / 100) * size.x;
    el.style.clip = `rect(0px, ${size.x}px, ${size.y}px, ${x}px)`;
  }

  map.on("move zoom resize", () => {
    if (state.compare) applySwipe();
  });

  function fitWithPadding(bounds, maxZoom) {
    const padBottom = isMobile()
      ? Math.max(24, parseInt(getComputedStyle(document.documentElement).getPropertyValue("--dock-h"), 10) || 108)
      : 20;
    map.fitBounds(bounds, {
      paddingTopLeft: [20, isMobile() ? 48 : 20],
      paddingBottomRight: [20, padBottom],
      maxZoom: maxZoom || 12,
    });
  }

  function updateExplain(extra) {
    const meta = currentLayerMeta();
    if (!meta) {
      $("explain").textContent = "Choose a layer to see a short explanation.";
      return;
    }
    const compareNote = state.compare
      ? `<p class="mb-0 mt-2 text-secondary">Comparing <strong>23 Jan</strong> (left) with <strong>24 Jan</strong> (right). Visual only — not a fire or damage score.</p>`
      : `<p class="mb-0 mt-2 text-secondary">Showing <strong>${state.date === "2026-01-23" ? "23" : "24"} January 2026</strong>.</p>`;
    $("explain").innerHTML = `<strong>${meta.title}</strong><p class="mb-0 mt-1">${meta.blurb}</p>${compareNote}${extra || ""}`;
  }

  function syncSwipeUI(val) {
    $$(".dock-swipe").forEach((el) => {
      el.value = String(val);
    });
    $$(".swipe-val").forEach((el) => {
      el.textContent = `${val}%`;
    });
  }

  function syncOpacityUI(val) {
    $$(".dock-opacity").forEach((el) => {
      el.value = String(val);
    });
    $$(".opacity-val").forEach((el) => {
      el.textContent = `${val}%`;
    });
  }

  function syncCompareUI(enabled) {
    $$(".dock-compare").forEach((el) => {
      el.checked = enabled;
    });
    $$(".dock-swipe").forEach((el) => {
      // Mobile swipe is always enabled in compare panel; desktop disables until compare on
      if (el.id === "swipeDesktop") el.disabled = !enabled;
      else el.disabled = false;
    });
    document.querySelectorAll('input[name="date"]').forEach((r) => {
      r.disabled = enabled;
    });
  }

  function setDockMode(mode, { applyView = true } = {}) {
    state.dockMode = mode === "compare" ? "compare" : "strength";
    const strength = state.dockMode === "strength";
    const wantCompare = !strength;

    $("panelStrength")?.classList.toggle("d-none", !strength);
    $("panelCompare")?.classList.toggle("d-none", strength);

    if ($("modeStrength") && $("modeCompare")) {
      $("modeStrength").checked = strength;
      $("modeCompare").checked = !strength;
    }

    const flipped = state.compare !== wantCompare;
    state.compare = wantCompare;
    syncCompareUI(wantCompare);

    if (flipped && applyView) showView();
    else measureDock();
  }

  async function showView() {
    const meta = currentLayerMeta();
    if (!meta) return;

    clearOverlays();
    toast("Loading satellite picture…");
    measureDock();

    try {
      if (state.compare) {
        const beforeId = meta.dates["2026-01-23"];
        const afterId = meta.dates["2026-01-24"];
        if (!beforeId || !afterId) {
          toast("This layer is not available on both days.", true);
          setTimeout(() => toast("", false), 2500);
          setDockMode("strength", { applyView: false });
          await showView();
          return;
        }
        const before = rasterById(beforeId);
        const after = rasterById(afterId);
        await fetch("/api/rasters/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ before_id: beforeId, after_id: afterId }),
        }).then((r) => r.json());

        const bb = boundsOf(before);
        const ba = boundsOf(after);
        state.beforeOverlay = L.imageOverlay(before.overlay_url, bb, { opacity: state.opacity }).addTo(map);
        state.afterOverlay = L.imageOverlay(after.overlay_url, ba, { opacity: state.opacity }).addTo(map);
        fitWithPadding(bb.extend(ba), 11);
        state.afterOverlay.on("load", applySwipe);
        setTimeout(applySwipe, 150);
        updateExplain();
      } else {
        const id = meta.dates[state.date];
        if (!id) {
          toast("No picture for this date and layer.", true);
          setTimeout(() => toast("", false), 2500);
          updateExplain(`<p class="mb-0 mt-2 text-warning">Try the other date or another layer.</p>`);
          return;
        }
        const raster = rasterById(id);
        state.singleOverlay = L.imageOverlay(raster.overlay_url, boundsOf(raster), {
          opacity: state.opacity,
        }).addTo(map);
        fitWithPadding(boundsOf(raster), 12);
        updateExplain();
      }
    } catch (e) {
      toast("Could not load the picture. Please try again.", true);
      updateExplain(`<p class="mb-0 mt-2 text-warning">${String(e.message || e)}</p>`);
    } finally {
      setTimeout(() => toast("", false), 400);
      measureDock();
    }
  }

  function fillLayerSelect() {
    const sel = $("layerSelect");
    sel.innerHTML = state.layers.map((l) => `<option value="${l.layer_id}">${l.title}</option>`).join("");
    const prefer = state.layers.find((l) => l.layer_id === "colour") || state.layers[0];
    if (prefer) {
      state.layerId = prefer.layer_id;
      sel.value = prefer.layer_id;
    }
  }

  function openSheet() {
    sidebar.classList.add("open");
    $("sheetBackdrop").hidden = false;
  }

  function closeSheet() {
    sidebar.classList.remove("open");
    $("sheetBackdrop").hidden = true;
  }

  // ---- Events ----
  document.querySelectorAll('input[name="date"]').forEach((el) => {
    el.addEventListener("change", (e) => {
      state.date = e.target.value;
      if (!state.compare) showView();
      else updateExplain();
      if (isMobile()) closeSheet();
    });
  });

  $("layerSelect").addEventListener("change", (e) => {
    state.layerId = e.target.value;
    showView();
    if (isMobile()) closeSheet();
  });

  document.querySelectorAll('input[name="dockMode"]').forEach((el) => {
    el.addEventListener("change", (e) => {
      if (!e.target.checked) return;
      setDockMode(e.target.value);
    });
  });

  // Desktop compare switch
  $("compareToggleDesktop").addEventListener("change", (e) => {
    setDockMode(e.target.checked ? "compare" : "strength");
  });

  function onSwipeInput(e) {
    state.swipe = Number(e.target.value);
    syncSwipeUI(state.swipe);
    applySwipe();
  }

  function onOpacityInput(e) {
    const v = Number(e.target.value);
    state.opacity = v / 100;
    syncOpacityUI(v);
    [state.singleOverlay, state.beforeOverlay, state.afterOverlay].forEach((ly) => {
      if (ly) ly.setOpacity(state.opacity);
    });
  }

  function bindSlider(selector, onInput) {
    $$(selector).forEach((el) => {
      el.addEventListener("input", onInput);
      ["pointerdown", "touchstart", "mousedown"].forEach((evt) => {
        el.addEventListener(evt, (ev) => ev.stopPropagation(), { passive: true });
      });
    });
  }
  bindSlider(".dock-swipe", onSwipeInput);
  bindSlider(".dock-opacity", onOpacityInput);

  $("openSidebar").addEventListener("click", openSheet);
  $("closeSidebar").addEventListener("click", closeSheet);
  $("sheetBackdrop").addEventListener("click", closeSheet);

  window.addEventListener("resize", () => {
    measureDock();
    if (state.compare) applySwipe();
    if (!isMobile()) closeSheet();
  });
  window.addEventListener("orientationchange", () => {
    setTimeout(() => {
      measureDock();
      map.invalidateSize({ animate: false });
      if (state.compare) applySwipe();
    }, 250);
  });

  document.body.addEventListener(
    "touchmove",
    (e) => {
      if (e.target.closest(".sidebar") || e.target.closest(".control-dock")) return;
      if (e.target.closest("#map") || e.target.closest(".map-pane")) {
        if (e.cancelable) e.preventDefault();
      }
    },
    { passive: false }
  );

  async function boot() {
    if (window.lucide) lucide.createIcons();
    toast("Loading…");
    measureDock();
    try {
      const res = await fetch("/api/rasters");
      if (!res.ok) throw new Error("Server unavailable");
      const data = await res.json();
      state.dataset = data.dataset;
      state._rasters = data.rasters || [];
      state.layers = data.dataset.layers || [];

      if (!state.layers.length) {
        $("emptyState").classList.remove("d-none");
        openSheet();
        toast("", false);
        return;
      }

      $("about").innerHTML = `
        <p class="mb-2">${data.dataset.plain_note}</p>
        <p class="mb-1"><strong>Place:</strong> ${data.dataset.place}</p>
        <p class="mb-1"><strong>Dates:</strong> ${(data.dataset.acquisition_dates || []).join(", ")}</p>
        <p class="mb-1"><strong>Source:</strong> ${data.dataset.sensor}</p>
        <p class="mb-0">${data.dataset.count} picture layers loaded.</p>`;
      $("attrib").textContent = data.dataset.attribution;

      fillLayerSelect();
      syncSwipeUI(50);
      syncOpacityUI(85);
      setDockMode("strength", { applyView: false });
      await showView();
    } catch (e) {
      $("emptyState").classList.remove("d-none");
      $("emptyState").textContent = "Could not reach the map server. Start the app with uvicorn on port 8000.";
      openSheet();
      toast("", false);
    }

    requestAnimationFrame(measureDock);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("./sw.js").catch(() => {});
    }
  }

  boot();
})();
