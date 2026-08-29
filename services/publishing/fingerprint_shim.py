"""Browser fingerprint shims aligned with persona / real Chrome signals."""
from __future__ import annotations

import json
from typing import Any

from services.publishing.human_interaction import STEALTH_INIT_SCRIPT

DEFAULT_FINGERPRINT: dict[str, Any] = {
    "languages": ["zh-CN", "zh", "en"],
    "hardware_concurrency": 8,
    "device_memory": 8,
    "webgl_vendor": "Google Inc. (Intel)",
    "webgl_renderer": "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
}


def fingerprint_values_from_persona(persona: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(DEFAULT_FINGERPRINT)
    if not persona:
        return data
    if persona.get("languages"):
        data["languages"] = list(persona["languages"])
    if persona.get("hardware_concurrency") is not None:
        data["hardware_concurrency"] = int(persona["hardware_concurrency"])
    if persona.get("device_memory") is not None:
        data["device_memory"] = int(persona["device_memory"])
    if persona.get("webgl_vendor"):
        data["webgl_vendor"] = str(persona["webgl_vendor"])
    if persona.get("webgl_renderer"):
        data["webgl_renderer"] = str(persona["webgl_renderer"])
    return data


def build_fingerprint_init_script(persona: dict[str, Any] | None = None) -> str:
    """Return init script that patches shallow automation/fingerprint signals."""
    values = fingerprint_values_from_persona(persona)
    payload = json.dumps(values, ensure_ascii=False)
    return f"""
(() => {{
  const cfg = {payload};
  try {{
    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
  }} catch (e) {{}}
  try {{
    Object.defineProperty(navigator, 'languages', {{ get: () => cfg.languages.slice() }});
    Object.defineProperty(navigator, 'language', {{ get: () => cfg.languages[0] || 'zh-CN' }});
  }} catch (e) {{}}
  try {{
    Object.defineProperty(navigator, 'hardwareConcurrency', {{
      get: () => cfg.hardware_concurrency,
    }});
  }} catch (e) {{}}
  try {{
    if ('deviceMemory' in navigator) {{
      Object.defineProperty(navigator, 'deviceMemory', {{ get: () => cfg.device_memory }});
    }}
  }} catch (e) {{}}
  try {{
    window.chrome = window.chrome || {{}};
    window.chrome.runtime = window.chrome.runtime || {{}};
    if (!window.chrome.csi) window.chrome.csi = () => ({{}});
    if (!window.chrome.loadTimes) window.chrome.loadTimes = () => ({{}});
  }} catch (e) {{}}
  try {{
    const pluginData = [
      {{ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }},
      {{ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }},
      {{ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }},
    ];
    const pluginArray = {{
      length: pluginData.length,
      item: (index) => pluginData[index] || null,
      namedItem: (name) => pluginData.find((p) => p.name === name) || null,
      refresh: () => undefined,
    }};
    pluginData.forEach((plugin, index) => {{
      pluginArray[index] = plugin;
    }});
    Object.defineProperty(navigator, 'plugins', {{ get: () => pluginArray }});
  }} catch (e) {{}}
  try {{
    const vendor = cfg.webgl_vendor;
    const renderer = cfg.webgl_renderer;
    const patchWebGL = (contextPrototype) => {{
      if (!contextPrototype || contextPrototype.__ainewsPatched) return;
      const originalGetParameter = contextPrototype.getParameter;
      contextPrototype.getParameter = function getParameter(parameter) {{
        const ext = this.getExtension('WEBGL_debug_renderer_info');
        if (ext) {{
          if (parameter === ext.UNMASKED_VENDOR_WEBGL) return vendor;
          if (parameter === ext.UNMASKED_RENDERER_WEBGL) return renderer;
        }}
        return originalGetParameter.call(this, parameter);
      }};
      contextPrototype.__ainewsPatched = true;
    }};
    patchWebGL(WebGLRenderingContext && WebGLRenderingContext.prototype);
    patchWebGL(WebGL2RenderingContext && WebGL2RenderingContext.prototype);
  }} catch (e) {{}}
  try {{
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
      parameters && parameters.name === 'notifications'
        ? Promise.resolve({{ state: Notification.permission }})
        : originalQuery(parameters)
    );
  }} catch (e) {{}}
}})();
"""


def build_combined_stealth_init_script(persona: dict[str, Any] | None = None) -> str:
    """Base stealth script plus persona-aware fingerprint shim."""
    return STEALTH_INIT_SCRIPT.strip() + "\n" + build_fingerprint_init_script(persona)
