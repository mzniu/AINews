use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter};

use crate::backend;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeSetupStatusDto {
    pub ready: bool,
    pub torch_ready: bool,
    pub playwright_ready: bool,
    pub playwright_path: String,
    pub extras_marker: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeSetupProgressDto {
    pub step: String,
    pub label: String,
    pub percent: u8,
    pub done: bool,
}

static SETUP_LOCK: Mutex<()> = Mutex::new(());

pub fn playwright_browsers_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("playwright-browsers")
}

fn extras_requirements_path(app_dir: &Path) -> PathBuf {
    app_dir.join("requirements-desktop-extras.txt")
}

fn setup_marker_path(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("setup_v1.json")
}

fn chromium_installed(browsers_dir: &Path) -> bool {
    if !browsers_dir.is_dir() {
        return false;
    }
    let Ok(entries) = std::fs::read_dir(browsers_dir) else {
        return false;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.starts_with("chromium") {
            let chrome = entry.path().join("chrome-win").join("chrome.exe");
            if chrome.is_file() {
                return true;
            }
            let chrome2 = entry.path().join("chrome-win64").join("chrome.exe");
            if chrome2.is_file() {
                return true;
            }
        }
    }
    false
}

fn bundled_playwright_dir(install_dir: &Path) -> Option<PathBuf> {
    for root in [
        install_dir.join("bundle-resources"),
        install_dir.join("resources"),
    ] {
        let p = root.join("playwright-browsers");
        if chromium_installed(&p) {
            return Some(p);
        }
    }
    None
}

fn python_check_import(python: &Path, module: &str) -> bool {
    let launch = match backend::prepare_python_runtime(python) {
        Ok(l) => l,
        Err(_) => return false,
    };
    let mut cmd = Command::new(&launch.executable);
    backend::apply_launch_env(&mut cmd, &launch);
    cmd.arg("-c")
        .arg(format!("import {module}"))
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd.status().map(|s| s.success()).unwrap_or(false)
}

pub fn status(python: &Path, install_dir: &Path, data_dir: &Path, _app_dir: &Path) -> RuntimeSetupStatusDto {
    let user_pw = playwright_browsers_dir(data_dir);
    let pw_path = if chromium_installed(&user_pw) {
        user_pw
    } else if let Some(b) = bundled_playwright_dir(install_dir) {
        b
    } else {
        user_pw
    };

    let torch_ready = python_check_import(python, "torch");
    let playwright_ready = chromium_installed(&pw_path);
    let extras_marker = setup_marker_path(data_dir).is_file();
    let ready = torch_ready && playwright_ready && extras_marker;

    RuntimeSetupStatusDto {
        ready,
        torch_ready,
        playwright_ready,
        playwright_path: pw_path.to_string_lossy().to_string(),
        extras_marker,
    }
}

fn emit_progress(app: &AppHandle, step: &str, label: &str, percent: u8, done: bool) {
    let _ = app.emit(
        "ainews:setup-progress",
        RuntimeSetupProgressDto {
            step: step.to_string(),
            label: label.to_string(),
            percent,
            done,
        },
    );
}

fn run_pip_install_with_progress(
    app: &AppHandle,
    launch: &backend::PythonLaunch,
    req: &Path,
    use_user_site: bool,
    step: &str,
    percent_start: u8,
    percent_end: u8,
) -> Result<(), String> {
    let mut cmd = Command::new(&launch.executable);
    backend::apply_launch_env(&mut cmd, launch);
    cmd.arg("-m").arg("pip").arg("install");
    if use_user_site {
        cmd.arg("--user");
    }
    cmd.arg("-r")
        .arg(req)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(|e| format!("无法运行 pip: {e}"))?;
    let stderr = child.stderr.take();
    let mut last_emit = percent_start;
    if let Some(err) = stderr {
        let reader = BufReader::new(err);
        for line in reader.lines().map_while(Result::ok) {
            if line.contains("Downloading") || line.contains("Installing") {
                if last_emit + 2 < percent_end {
                    last_emit += 1;
                    emit_progress(app, step, &line, last_emit, false);
                }
            }
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err("pip failed".into())
    }
}

fn run_pip_extras(
    app: &AppHandle,
    launch: &backend::PythonLaunch,
    app_dir: &Path,
    step: &str,
    label: &str,
    percent_start: u8,
    percent_end: u8,
) -> Result<(), String> {
    emit_progress(app, step, label, percent_start, false);
    let req = extras_requirements_path(app_dir);
    if !req.is_file() {
        return Err(format!("缺少依赖清单: {}", req.display()));
    }

    if run_pip_install_with_progress(app, launch, &req, false, step, percent_start, percent_end)
        .is_err()
        && run_pip_install_with_progress(app, launch, &req, true, step, percent_start, percent_end)
            .is_err()
    {
        return Err("安装 AI 组件失败（pip）。请检查网络后重试。".into());
    }
    emit_progress(app, step, "AI 组件安装完成", percent_end, false);
    Ok(())
}

fn run_playwright_install(
    app: &AppHandle,
    launch: &backend::PythonLaunch,
    browsers_dir: &Path,
    step: &str,
    label: &str,
    percent_start: u8,
    percent_end: u8,
) -> Result<(), String> {
    std::fs::create_dir_all(browsers_dir).map_err(|e| e.to_string())?;
    emit_progress(app, step, label, percent_start, false);

    let mut cmd = Command::new(&launch.executable);
    backend::apply_launch_env(&mut cmd, &launch);
    cmd.arg("-m")
        .arg("playwright")
        .arg("install")
        .arg("chromium")
        .env(
            "PLAYWRIGHT_BROWSERS_PATH",
            browsers_dir.to_string_lossy().to_string(),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn().map_err(|e| format!("无法运行 playwright: {e}"))?;
    let stderr = child.stderr.take();
    let mut last_emit = percent_start;
    if let Some(err) = stderr {
        let reader = BufReader::new(err);
        for line in reader.lines().map_while(Result::ok) {
            if last_emit + 3 < percent_end {
                last_emit += 1;
                emit_progress(app, step, &line, last_emit, false);
            }
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("下载 Playwright 浏览器失败。请检查网络后重试。".into());
    }
    if !chromium_installed(browsers_dir) {
        return Err("Playwright 安装完成但未找到 Chromium。".into());
    }
    emit_progress(app, step, "浏览器组件就绪", percent_end, false);
    Ok(())
}

fn write_marker(data_dir: &Path) -> Result<(), String> {
    let dir = data_dir.join("runtime");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let body = r#"{"version":1}"#;
    std::fs::write(setup_marker_path(data_dir), body).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn run(
    app: &AppHandle,
    python: &Path,
    install_dir: &Path,
    data_dir: &Path,
    app_dir: &Path,
) -> Result<(), String> {
    let _guard = SETUP_LOCK.lock().unwrap();
    let current = status(python, install_dir, data_dir, app_dir);
    if current.ready {
        emit_progress(app, "done", "运行环境已就绪", 100, true);
        return Ok(());
    }

    emit_progress(app, "check", "正在检查运行环境…", 5, false);
    let launch = backend::prepare_python_runtime(python)?;

    if !current.torch_ready {
        run_pip_extras(
            app,
            &launch,
            app_dir,
            "ml",
            "正在下载 AI 组件（首次约 1–2GB，请保持网络畅通）…",
            10,
            70,
        )?;
        if !python_check_import(python, "torch") {
            return Err("AI 组件安装后仍无法加载 torch。".into());
        }
    } else {
        emit_progress(app, "ml", "AI 组件已安装", 70, false);
    }

    let browsers_dir = playwright_browsers_dir(data_dir);
    if !current.playwright_ready {
        run_playwright_install(
            app,
            &launch,
            &browsers_dir,
            "playwright",
            "正在下载发布用浏览器（Chromium）…",
            72,
            95,
        )?;
    } else {
        emit_progress(app, "playwright", "浏览器组件已安装", 95, false);
    }

    write_marker(data_dir)?;
    emit_progress(app, "done", "初始化完成", 100, true);
    Ok(())
}
