use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub struct BackendProcess {
    child: Child,
}

pub fn install_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn resource_roots(install_dir: &Path) -> Vec<PathBuf> {
    [
        install_dir.join("bundle-resources"),
        install_dir.join("resources"),
    ]
    .into_iter()
    .filter(|root| root.is_dir())
    .collect()
}

pub fn resolve_app_dir(install_dir: &Path) -> PathBuf {
    for root in resource_roots(install_dir) {
        let bundled = root.join("app");
        if bundled.join("web_server.py").exists() {
            return bundled;
        }
    }
    install_dir.to_path_buf()
}

pub fn resolve_python_exe(install_dir: &Path) -> PathBuf {
    let mut candidates = Vec::new();
    for root in resource_roots(install_dir) {
        candidates.push(root.join("python/Scripts/python.exe"));
        candidates.push(root.join("python/python.exe"));
    }
    candidates.push(install_dir.join("python/Scripts/python.exe"));
    for candidate in candidates {
        if candidate.exists() {
            return candidate;
        }
    }
    if cfg!(windows) {
        PathBuf::from("python")
    } else {
        PathBuf::from("python3")
    }
}

pub fn spawn_backend(
    python: &Path,
    app_dir: &Path,
    install_dir: &Path,
    data_dir: &Path,
    port: u16,
) -> std::io::Result<BackendProcess> {
    let mut cmd = Command::new(python);
    cmd.arg("web_server.py")
        .current_dir(app_dir)
        .env("AINEWS_DATA_DIR", data_dir)
        .env("AINEWS_RESOURCE_DIR", app_dir)
        .env("PORT", port.to_string());

    if cfg!(debug_assertions) {
        cmd.env("AINES_DEV_MODE", "1");
        cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    } else {
        // Packaged builds must not pipe stdout/stderr without draining them;
        // otherwise loguru/uvicorn eventually block when the pipe buffer fills.
        cmd.env("AINEWS_NO_CONSOLE_LOG", "1");
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
    }

    for root in resource_roots(install_dir) {
        let playwright_browsers = root.join("playwright-browsers");
        if playwright_browsers.is_dir() {
            cmd.env(
                "PLAYWRIGHT_BROWSERS_PATH",
                playwright_browsers.to_string_lossy().to_string(),
            );
            break;
        }
    }

    let mut ffmpeg = None;
    for root in resource_roots(install_dir) {
        let candidate = root.join("ffmpeg").join("ffmpeg.exe");
        if candidate.is_file() {
            ffmpeg = Some(candidate);
            break;
        }
    }
    if let Some(ffmpeg) = ffmpeg {
        cmd.env(
            "AINEWS_FFMPEG_PATH",
            ffmpeg.to_string_lossy().to_string(),
        );
    }

    #[cfg(windows)]
    if !cfg!(debug_assertions) {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd.spawn()?;
    Ok(BackendProcess { child })
}

pub fn wait_for_health(port: u16, timeout: Duration) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;
    let url = format!("http://127.0.0.1:{port}/api/health");
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err("backend health check timeout".into())
}

impl BackendProcess {
    pub fn shutdown(mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
