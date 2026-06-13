/* Polla access tracking: report active time-on-page.
   Identity is chosen on the home page / nav; here we just record visits and the
   number of *active* seconds (counted only while the tab is visible). */
(function () {
  let visitId = null;
  let activeSeconds = 0;

  setInterval(() => { if (!document.hidden) activeSeconds += 1; }, 1000);

  fetch("/track/visit/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: location.pathname }),
  }).then(r => r.json()).then(d => { visitId = d.visit_id; }).catch(() => {});

  function flush() {
    if (visitId == null) return;
    const body = JSON.stringify({ visit_id: visitId, seconds: activeSeconds });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/track/visit/ping", new Blob([body], { type: "application/json" }));
    } else {
      fetch("/track/visit/ping", {
        method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true,
      }).catch(() => {});
    }
  }

  setInterval(flush, 15000);
  document.addEventListener("visibilitychange", () => { if (document.hidden) flush(); });
  window.addEventListener("pagehide", flush);
})();
