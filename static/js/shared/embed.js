(function () {
    const params = new URLSearchParams(window.location.search);
    if (params.get('embed') !== '1') return;
    document.body.classList.add('is-embedded');
})();
