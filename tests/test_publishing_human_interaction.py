from services.publishing.human_interaction import (
    DEFAULT_PUBLISH_USER_AGENT,
    STEALTH_CHROMIUM_ARGS,
    STEALTH_INIT_SCRIPT,
)


def test_stealth_launch_args_disable_automation_control():
    assert any("AutomationControlled" in arg for arg in STEALTH_CHROMIUM_ARGS)


def test_stealth_init_script_masks_webdriver():
    assert "webdriver" in STEALTH_INIT_SCRIPT
    assert "undefined" in STEALTH_INIT_SCRIPT


def test_default_user_agent_looks_like_desktop_chrome():
    assert "Chrome" in DEFAULT_PUBLISH_USER_AGENT
    assert "Windows" in DEFAULT_PUBLISH_USER_AGENT
