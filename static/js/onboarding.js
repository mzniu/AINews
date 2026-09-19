(function () {
    const l1Tabs = document.getElementById("l1Tabs");
    const l2Grid = document.getElementById("l2Grid");
    const confirmBtn = document.getElementById("confirmBtn");
    const statusBar = document.getElementById("statusBar");
    const selectionHint = document.getElementById("selectionHint");

    let taxonomy = [];
    let activeL1 = "";
    let selectedPath = "";

    function setStatus(message, isError) {
        statusBar.textContent = message || "";
        statusBar.style.color = isError ? "#f87171" : "";
    }

    async function checkAlreadyOnboarded() {
        const res = await fetch("/api/me/industry");
        if (!res.ok) return;
        const body = await res.json();
        if (!body.needs_onboarding) {
            window.location.href = "/";
        }
    }

    async function loadTaxonomy() {
        const res = await fetch("/api/industry/taxonomy");
        if (!res.ok) throw new Error("无法加载垂类列表");
        const body = await res.json();
        taxonomy = body.l1 || [];
        if (!taxonomy.length) throw new Error("垂类列表为空");
        activeL1 = taxonomy[0].slug;
        renderL1();
        renderL2();
    }

    function renderL1() {
        l1Tabs.innerHTML = "";
        taxonomy.forEach((group) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = group.display_name || group.slug;
            btn.className = group.slug === activeL1 ? "active" : "";
            btn.addEventListener("click", () => {
                activeL1 = group.slug;
                selectedPath = "";
                confirmBtn.disabled = true;
                selectionHint.textContent = "请选择一个垂类卡片";
                renderL1();
                renderL2();
            });
            l1Tabs.appendChild(btn);
        });
    }

    function renderL2() {
        l2Grid.innerHTML = "";
        const group = taxonomy.find((g) => g.slug === activeL1);
        (group?.l2 || []).forEach((item) => {
            const card = document.createElement("button");
            card.type = "button";
            card.className =
                "onboarding-card" + (item.path === selectedPath ? " selected" : "");
            const title = document.createElement("strong");
            title.textContent = item.display_name || item.path;
            card.appendChild(title);
            if (item.status && item.status !== "active") {
                const badge = document.createElement("span");
                badge.className = "badge";
                badge.textContent = item.status;
                card.appendChild(badge);
            }
            const meta = document.createElement("div");
            meta.className = "hint";
            meta.textContent = item.path;
            card.appendChild(meta);
            card.addEventListener("click", () => {
                selectedPath = item.path;
                confirmBtn.disabled = false;
                selectionHint.textContent = `已选：${item.display_name}（${item.path}）`;
                renderL2();
            });
            l2Grid.appendChild(card);
        });
    }

    async function confirmSelection() {
        if (!selectedPath) return;
        confirmBtn.disabled = true;
        setStatus("正在保存垂类并同步行业包…");
        try {
            const putRes = await fetch("/api/me/industry", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ active_industry_id: selectedPath }),
            });
            if (!putRes.ok) {
                const err = await putRes.json().catch(() => ({}));
                throw new Error(err.detail || "保存失败");
            }
            const syncRes = await fetch("/api/me/industry/sync-pack", { method: "POST" });
            if (!syncRes.ok) throw new Error("行业包同步失败");
            setStatus("完成，正在进入工作台…");
            window.location.href = "/";
        } catch (err) {
            setStatus(err.message || String(err), true);
            confirmBtn.disabled = false;
        }
    }

    confirmBtn.addEventListener("click", confirmSelection);
    checkAlreadyOnboarded()
        .then(loadTaxonomy)
        .catch((err) => setStatus(err.message || String(err), true));
})();
