async function loadIndustrySettings() {
    const currentEl = document.getElementById("industryCurrent");
    const selectEl = document.getElementById("industrySwitchSelect");
    const statusBar = document.getElementById("industryStatusBar");
    if (!currentEl || !selectEl) return;

    function setStatus(msg, isError) {
        if (statusBar) {
            statusBar.textContent = msg || "";
            statusBar.style.color = isError ? "#f87171" : "";
        }
    }

    setStatus("加载中…");
    try {
        const [meRes, taxRes] = await Promise.all([
            fetch("/api/me/industry"),
            fetch("/api/industry/taxonomy"),
        ]);
        if (!meRes.ok || !taxRes.ok) throw new Error("加载失败");
        const me = await meRes.json();
        const tax = await taxRes.json();
        const active = me.active_industry_id || "—";
        const name = me.display_name || active;
        currentEl.innerHTML = `
            <div><strong>当前垂类</strong><br>${name} <code>${active}</code></div>
            <div><strong>Pack 版本</strong><br>${me.pack_version || "—"}</div>
            <div><strong>Onboarding</strong><br>${me.needs_onboarding ? "未完成" : "已完成"}</div>
        `;
        selectEl.innerHTML = "";
        (tax.l1 || []).forEach((group) => {
            (group.l2 || []).forEach((item) => {
                const opt = document.createElement("option");
                opt.value = item.path;
                opt.textContent = `${group.display_name || group.slug} · ${item.display_name}`;
                if (item.path === me.active_industry_id) opt.selected = true;
                selectEl.appendChild(opt);
            });
        });
        setStatus("");
    } catch (err) {
        setStatus(err.message || String(err), true);
    }
}

document.getElementById("industrySwitchBtn")?.addEventListener("click", async () => {
    const selectEl = document.getElementById("industrySwitchSelect");
    const path = selectEl?.value;
    if (!path) return;
    const res = await fetch("/api/me/industry/switch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_industry_id: path }),
    });
    const body = await res.json().catch(() => ({}));
    const statusBar = document.getElementById("industryStatusBar");
    if (!res.ok) {
        if (statusBar) statusBar.textContent = body.detail || "切换失败";
        return;
    }
    if (statusBar) statusBar.textContent = body.message || "已切换";
    loadIndustrySettings();
});

document.getElementById("industrySyncPackBtn")?.addEventListener("click", async () => {
    const statusBar = document.getElementById("industryStatusBar");
    if (statusBar) statusBar.textContent = "同步中…";
    const res = await fetch("/api/me/industry/sync-pack", { method: "POST" });
    if (!res.ok) {
        if (statusBar) statusBar.textContent = "同步失败";
        return;
    }
    if (statusBar) statusBar.textContent = "行业包已同步";
    loadIndustrySettings();
});

window.loadIndustrySettings = loadIndustrySettings;
