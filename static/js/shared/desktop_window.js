/** Legacy no-op: native Windows title bar restored in desktop shell. */
(function () {
    window.DesktopWindow = {
        isDesktop() {
            return Boolean(window.__TAURI__?.core?.invoke);
        },
        mountControls() {},
        initAuthTitlebar() {},
        toggleMaximize() {
            return Promise.resolve();
        },
    };
})();
