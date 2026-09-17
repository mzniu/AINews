use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub struct BackendProcess {
    child: Child,
    log_path: PathBuf,
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

pub fn backend_log_path(data_dir: &Path) -> PathBuf {
    data_dir.join("logs").join("backend.log")
}

fn read_log_tail(path: &Path, max_lines: usize) -> String {
    let Ok(mut file) = File::open(path) else {
        return String::new();
    };
    let Ok(len) = file.metadata().map(|m| m.len()) else {
        return String::new();
    };
    let read_from = len.saturating_sub(16_384);
    let _ = file.seek(SeekFrom::Start(read_from));
    let mut buf = String::new();
    let _ = file.read_to_string(&mut buf);
    let lines: Vec<&str> = buf.lines().collect();
    if lines.len() <= max_lines {
        buf.trim_end().to_string()
    } else {
        lines[lines.len() - max_lines..].join("\n")
    }
}

pub fn spawn_backend(
    python: &Path,
    app_dir: &Path,
    install_dir: &Path,
    data_dir: &Path,
    port: u16,
) -> std::io::Result<BackendProcess> {
    let log_path = backend_log_path(data_dir);
    if let Some(parent) = log_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let log_file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)?;
    let started_at = chrono_lite_now();
    let _ = writeln_log(
        &log_path,
        format!(
            "\n--- backend start {started_at} python={} app_dir={} port={port} ---",
            python.display(),
            app_dir.display()
        ),
    );

    let mut cmd = Command::new(python);
    cmd.arg("web_server.py")
        .current_dir(app_dir)
        .env("AINEWS_DATA_DIR", data_dir)
        .env("AINEWS_RESOURCE_DIR", app_dir)
        .env("PORT", port.to_string());

    if cfg!(debug_assertions) {
        cmd.env("AINES_DEV_MODE", "1");
        cmd.stdout(Stdio::piped()).stderr(Stdio::from(log_file));
    } else {
        cmd.env("AINEWS_NO_CONSOLE_LOG", "1");
        cmd.stdout(Stdio::null()).stderr(Stdio::from(log_file));
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
    Ok(BackendProcess {
        child,
        log_path,
    })
}

fn chrono_lite_now() -> String {
    use std::time::SystemTime;
    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("unix={now}")
}

fn writeln_log(path: &Path, line: String) -> std::io::Result<()> {
    use std::io::Write;
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(file, "{line}")?;
    Ok(())
}

pub fn wait_for_health(
    port: u16,
    timeout: Duration,
    backend: &mut BackendProcess,
) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;
    let url = format!("http://127.0.0.1:{port}/api/health");
    let log_path = backend.log_path.clone();
    let start = Instant::now();
    while start.elapsed() < timeout {
        if let Ok(Some(status)) = backend.child.try_wait() {
            let tail = read_log_tail(&log_path, 12);
            let mut msg = format!(
                "Python 后端进程已退出 (code={})",
                status.code().unwrap_or(-1)
            );
            msg.push_str(&format!("\n日志文件: {}", log_path.display()));
            if !tail.is_empty() {
                msg.push_str(&format!("\n最近日志:\n{tail}"));
            }
            return Err(msg);
        }
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    let tail = read_log_tail(&log_path, 12);
    let mut msg = format!(
        "等待后端就绪超时（{} 秒），请检查防火墙/端口占用或查看日志",
        timeout.as_secs()
    );
    msg.push_str(&format!("\n健康检查: {}", url));
    msg.push_str(&format!("\n日志文件: {}", log_path.display()));
    if !tail.is_empty() {
        msg.push_str(&format!("\n最近日志:\n{tail}"));
    }
    Err(msg)
}

impl BackendProcess {
    pub fn log_path(&self) -> &Path {
        &self.log_path
    }

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
