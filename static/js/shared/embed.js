(function () {
    const params = new URLSearchParams(window.location.search);
    if (params.get('embed') !== '1') return;
    document.documentElement.setAttribute('data-embed', '1');
})();
