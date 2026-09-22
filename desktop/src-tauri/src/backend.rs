use std::fs::{File, OpenOptions};
use std::io::{ErrorKind, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub struct BackendProcess {
    /// `None` when reusing an already-listening embedded API from a prior session.
    child: Option<Child>,
    log_path: PathBuf,
}

impl BackendProcess {
    pub fn adopted(log_path: PathBuf) -> Self {
        Self {
            child: None,
            log_path,
        }
    }
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

pub fn python_venv_root(python_exe: &Path) -> Option<PathBuf> {
    let scripts = python_exe.parent()?;
    if scripts.file_name().and_then(|n| n.to_str()) != Some("Scripts") {
        return None;
    }
    scripts.parent().map(|p| p.to_path_buf())
}

#[derive(Debug, Clone)]
pub struct PythonLaunch {
    pub executable: PathBuf,
    pub pythonhome: Option<PathBuf>,
    pub pythonpath: Option<PathBuf>,
}

pub(crate) enum PyvenvRepairOutcome {
    Ok,
    Repaired,
    ReadOnlyUseEnv(PathBuf),
}

fn canonical_path(path: &Path) -> PathBuf {
    path.canonicalize().unwrap_or_else(|_| path.to_path_buf())
}

fn strip_pyvenv_value(mut value: &str) -> &str {
    value = value.trim();
    while value.starts_with('=') {
        value = value[1..].trim_start();
    }
    if value.len() >= 2 && value.starts_with('"') && value.ends_with('"') {
        &value[1..value.len() - 1]
    } else {
        value
    }
}

fn pyvenv_home_matches_venv(text: &str, venv_root: &Path) -> bool {
    let desired = canonical_path(venv_root);
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("home") {
            let value = strip_pyvenv_value(rest.trim_start_matches('=').trim());
            if value.is_empty() || value == "." {
                return false;
            }
            let home_path = PathBuf::from(value);
            if home_path.is_absolute() {
                return canonical_path(&home_path) == desired;
            }
            return false;
        }
    }
    false
}

fn bundled_has_stdlib_zip(venv_root: &Path) -> bool {
    let Ok(entries) = std::fs::read_dir(venv_root) else {
        return false;
    };
    entries.filter_map(Result::ok).any(|entry| {
        entry
            .file_name()
            .to_str()
            .is_some_and(|name| name.starts_with("python") && name.ends_with(".zip"))
    })
}

fn bundled_stdlib_ok(venv_root: &Path) -> bool {
    venv_root.join("Lib").join("encodings").is_dir() || bundled_has_stdlib_zip(venv_root)
}

/// Launch with PYTHONHOME so prefix is the bundled venv, not the app install dir.
fn bundled_portable_launch(venv_root: &Path) -> Option<PythonLaunch> {
    let root = canonical_path(venv_root);
    let direct = root.join("python.exe");
    if !direct.is_file() || !bundled_stdlib_ok(&root) {
        return None;
    }
    let site_packages = root.join("Lib").join("site-packages");
    Some(PythonLaunch {
        executable: direct,
        pythonhome: Some(root),
        pythonpath: site_packages.is_dir().then_some(site_packages),
    })
}

fn pythonpath_sep() -> char {
    if cfg!(windows) {
        ';'
    } else {
        ':'
    }
}

fn path_list_append(existing: Option<&Path>, segment: &Path) -> PathBuf {
    let seg = segment.to_string_lossy();
    match existing {
        Some(base) => PathBuf::from(format!(
            "{}{}{}",
            base.to_string_lossy(),
            pythonpath_sep(),
            seg
        )),
        None => segment.to_path_buf(),
    }
}

/// Bundled venvs disable user site (`ENABLE_USER_SITE` false); `pip install --user` still targets Roaming.
fn query_user_site_packages(exe: &Path) -> Option<PathBuf> {
    #[cfg(windows)]
    let mut cmd = {
        let mut c = Command::new(exe);
        c.arg("-c")
            .arg("import site; print(site.getusersitepackages())")
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        c.creation_flags(CREATE_NO_WINDOW);
        c
    };
    #[cfg(not(windows))]
    let mut cmd = {
        let mut c = Command::new(exe);
        c.arg("-c")
            .arg("import site; print(site.getusersitepackages())")
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        c
    };
    let out = cmd.output().ok()?;
    if !out.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&out.stdout);
    let line = stdout.trim();
    if line.is_empty() {
        None
    } else {
        Some(PathBuf::from(line))
    }
}

fn enrich_with_user_site_packages(launch: PythonLaunch) -> PythonLaunch {
    let user_site = query_user_site_packages(&launch.executable);
    let Some(user_site) = user_site.filter(|p| p.is_dir()) else {
        return launch;
    };
    PythonLaunch {
        pythonpath: Some(path_list_append(launch.pythonpath.as_deref(), &user_site)),
        ..launch
    }
}

fn apply_python_env(cmd: &mut Command, launch: &PythonLaunch) {
    if let Some(home) = launch.pythonhome.as_deref() {
        cmd.env("PYTHONHOME", home);
    }
    if let Some(path) = launch.pythonpath.as_deref() {
        cmd.env("PYTHONPATH", path);
    }
}

pub fn apply_launch_env(cmd: &mut Command, launch: &PythonLaunch) {
    apply_python_env(cmd, launch);
}

pub fn resolve_playwright_browsers_path(install_dir: &Path, data_dir: &Path) -> Option<PathBuf> {
    let user = data_dir.join("playwright-browsers");
    if playwright_chromium_ready(&user) {
        return Some(user);
    }
    for root in resource_roots(install_dir) {
        let bundled = root.join("playwright-browsers");
        if playwright_chromium_ready(&bundled) {
            return Some(bundled);
        }
    }
    if user.exists() || data_dir.exists() {
        return Some(user);
    }
    None
}

fn playwright_chromium_ready(browsers_dir: &Path) -> bool {
    if !browsers_dir.is_dir() {
        return false;
    }
    let Ok(entries) = std::fs::read_dir(browsers_dir) else {
        return false;
    };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.starts_with("chromium") {
            let p = entry.path();
            if p.join("chrome-win").join("chrome.exe").is_file()
                || p.join("chrome-win64").join("chrome.exe").is_file()
            {
                return true;
            }
        }
    }
    false
}

/// Windows venv launchers need `home` pointing at the venv directory (absolute path).
/// `home = .` breaks; builder-machine paths break on other PCs.
/// When install dir is not writable (Program Files), skip the write and use PYTHONHOME.
pub fn ensure_bundled_python_config(venv_root: &Path) -> Result<PyvenvRepairOutcome, String> {
    let cfg_path = venv_root.join("pyvenv.cfg");
    if !cfg_path.is_file() {
        return Ok(PyvenvRepairOutcome::Ok);
    }

    let home = canonical_path(venv_root);
    let home_display = home.to_string_lossy();

    let text = std::fs::read_to_string(&cfg_path).map_err(|e| e.to_string())?;
    if pyvenv_home_matches_venv(&text, venv_root) {
        return Ok(PyvenvRepairOutcome::Ok);
    }

    let mut version = String::from("3.11.0");
    let mut include_system = String::from("false");
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("version") {
            version = strip_pyvenv_value(rest).to_string();
        }
        if let Some(rest) = trimmed.strip_prefix("include-system-site-packages") {
            include_system = strip_pyvenv_value(rest).to_string();
        }
    }

    let interpreter = home.join("python.exe");
    if !interpreter.is_file() {
        return Err(format!(
            "内置 Python 缺少 python.exe（{}）。请重新安装完整安装包。",
            interpreter.display()
        ));
    }

    let new_cfg = format!(
        "home = {home}\ninclude-system-site-packages = {include_system}\nversion = {version}\n",
        home = home_display,
        include_system = include_system,
        version = version,
    );

    match std::fs::write(&cfg_path, new_cfg) {
        Ok(()) => Ok(PyvenvRepairOutcome::Repaired),
        Err(e) if e.kind() == ErrorKind::PermissionDenied => {
            Ok(PyvenvRepairOutcome::ReadOnlyUseEnv(home))
        }
        Err(e) => Err(e.to_string()),
    }
}

pub fn repair_bundled_python(venv_root: &Path) -> Result<(), String> {
    ensure_bundled_python_config(venv_root).map(|_| ())
}

pub fn prepare_python_runtime(python: &Path) -> Result<PythonLaunch, String> {
    if let Some(root) = python_venv_root(python) {
        match ensure_bundled_python_config(&root)? {
            PyvenvRepairOutcome::Ok | PyvenvRepairOutcome::Repaired => {
                let launch = PythonLaunch {
                    executable: python.to_path_buf(),
                    pythonhome: None,
                    pythonpath: None,
                };
                validate_python_launch(&launch)?;
                return Ok(enrich_with_user_site_packages(launch));
            }
            PyvenvRepairOutcome::ReadOnlyUseEnv(_) => {
                let launch = bundled_portable_launch(&root).ok_or_else(|| {
                    format!(
                        "内置 Python 不完整（缺少 Lib\\encodings，{}）。请重新安装最新完整安装包。",
                        root.display()
                    )
                })?;
                validate_python_launch(&launch)?;
                return Ok(enrich_with_user_site_packages(launch));
            }
        }
    }

    let launch = PythonLaunch {
        executable: python.to_path_buf(),
        pythonhome: None,
        pythonpath: None,
    };
    validate_python_launch(&launch)?;
    Ok(enrich_with_user_site_packages(launch))
}

fn read_pyvenv_home(python: &Path) -> Option<String> {
    let venv_root = python.parent().and_then(|scripts| {
        if scripts.file_name().and_then(|n| n.to_str()) == Some("Scripts") {
            scripts.parent()
        } else {
            None
        }
    });
    let cfg_path = venv_root?.join("pyvenv.cfg");
    let text = std::fs::read_to_string(cfg_path).ok()?;
    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(rest) = trimmed.strip_prefix("home") {
            let value = strip_pyvenv_value(rest.trim_start_matches('=').trim());
            if !value.is_empty() {
                return Some(value.to_string());
            }
        }
    }
    None
}

/// Ensure bundled venv does not point at a missing interpreter on another machine.
pub fn validate_python_exe(python: &Path) -> Result<(), String> {
    prepare_python_runtime(python).map(|_| ())
}

fn validate_python_launch(launch: &PythonLaunch) -> Result<(), String> {
    if launch.pythonhome.is_none() {
        if let Some(home) = read_pyvenv_home(&launch.executable) {
            if home != "." {
                let home_path = PathBuf::from(&home);
                if home_path.is_absolute() && !home_path.exists() {
                    return Err(format!(
                        "内置 Python 环境仍指向构建机路径（不存在）：{home}\n\
请重新安装最新版 AINews 安装包；若已是最新，请联系支持并提供诊断信息。"
                    ));
                }
            }
        }
    }

    #[cfg(windows)]
    let mut cmd = {
        let mut c = Command::new(&launch.executable);
        c.arg("-c").arg("import dotenv");
        c.creation_flags(CREATE_NO_WINDOW);
        c
    };
    #[cfg(not(windows))]
    let mut cmd = {
        let mut c = Command::new(&launch.executable);
        c.arg("-c").arg("import dotenv");
        c
    };
    apply_python_env(&mut cmd, launch);

    let output = cmd
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| format!("无法执行 Python ({}): {e}", launch.executable.display()))?;

    if output.status.success() {
        return Ok(());
    }

    let stderr = String::from_utf8_lossy(&output.stderr);
    let mut msg = format!("内置 Python 无法启动: {}", launch.executable.display());
    if !stderr.trim().is_empty() {
        msg.push_str(&format!("\n{stderr}"));
    }
    msg.push_str(
        "\n请重新安装最新版 AINews；若问题仍在，请复制诊断信息发给开发人员。",
    );
    Err(msg.trim_end().to_string())
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

pub fn read_log_tail(path: &Path, max_lines: usize) -> String {
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
    cloud_access_token: Option<&str>,
) -> std::io::Result<BackendProcess> {
    let launch = prepare_python_runtime(python)
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
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
            launch.executable.display(),
            app_dir.display()
        ),
    );

    let mut cmd = Command::new(&launch.executable);
    apply_python_env(&mut cmd, &launch);
    cmd.arg("web_server.py")
        .current_dir(app_dir)
        .env("AINEWS_DATA_DIR", data_dir)
        .env("AINEWS_RESOURCE_DIR", app_dir)
        .env("PORT", port.to_string());

    if let Some(token) = cloud_access_token.filter(|t| !t.is_empty()) {
        cmd.env("AINEWS_CLOUD_ACCESS_TOKEN", token);
    }

    if cfg!(debug_assertions) {
        cmd.env("AINES_DEV_MODE", "1");
        cmd.stdout(Stdio::piped()).stderr(Stdio::from(log_file));
    } else {
        cmd.env("AINEWS_NO_CONSOLE_LOG", "1");
        cmd.stdout(Stdio::null()).stderr(Stdio::from(log_file));
    }

    if let Some(playwright_browsers) =
        resolve_playwright_browsers_path(install_dir, data_dir)
    {
        cmd.env(
            "PLAYWRIGHT_BROWSERS_PATH",
            playwright_browsers.to_string_lossy().to_string(),
        );
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
        child: Some(child),
        log_path,
    })
}

/// Returns true when the local API already answers on this port.
pub fn probe_backend_health(port: u16) -> bool {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build();
    let client = match client {
        Ok(c) => c,
        Err(_) => return false,
    };
    let url = format!("http://127.0.0.1:{port}/api/health");
    match client.get(&url).send() {
        Ok(resp) => resp.status().is_success(),
        Err(_) => false,
    }
}

fn local_port_in_use(port: u16) -> bool {
    std::net::TcpListener::bind(("0.0.0.0", port)).is_err()
}

#[cfg(windows)]
fn pids_listening_on_port(port: u16) -> Vec<u32> {
    let output = Command::new("netstat")
        .args(["-ano"])
        .output()
        .ok()
        .map(|o| o.stdout);
    let stdout = match output {
        Some(s) => String::from_utf8_lossy(&s).to_string(),
        None => return Vec::new(),
    };
    let needle = format!(":{port}");
    let mut pids = Vec::new();
    for line in stdout.lines() {
        if !line.contains("LISTENING") || !line.contains(&needle) {
            continue;
        }
        let parts: Vec<&str> = line.split_whitespace().collect();
        if let Some(pid_str) = parts.last() {
            if let Ok(pid) = pid_str.parse::<u32>() {
                if pid > 0 {
                    pids.push(pid);
                }
            }
        }
    }
    pids.sort_unstable();
    pids.dedup();
    pids
}

#[cfg(not(windows))]
fn pids_listening_on_port(_port: u16) -> Vec<u32> {
    Vec::new()
}

#[cfg(windows)]
fn process_command_line(pid: u32) -> Option<String> {
    let script = format!(
        "(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"
    );
    let output = Command::new("powershell")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            &script,
        ])
        .creation_flags(CREATE_NO_WINDOW)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let line = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if line.is_empty() {
        None
    } else {
        Some(line)
    }
}

#[cfg(not(windows))]
fn process_command_line(_pid: u32) -> Option<String> {
    None
}

/// If the port is held by a dead/stuck `web_server.py` (not healthy), stop it so a new backend can bind.
pub fn reclaim_stale_backend_port(port: u16) {
    if probe_backend_health(port) {
        return;
    }
    if !local_port_in_use(port) {
        return;
    }
    for pid in pids_listening_on_port(port) {
        let cmdline = process_command_line(pid);
        let is_ainews = cmdline
            .as_deref()
            .map(|c| c.contains("web_server.py"))
            .unwrap_or(false);
        if !is_ainews {
            continue;
        }
        let pid_arg = pid.to_string();
        let _ = Command::new("taskkill")
            .args(["/PID", &pid_arg, "/F", "/T"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    for _ in 0..20 {
        if !local_port_in_use(port) {
            break;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
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
        if let Some(child) = backend.child.as_mut() {
            if let Ok(Some(status)) = child.try_wait() {
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

/// After health succeeds, ask the local API whether industry onboarding is required.
pub fn fetch_needs_industry_onboarding(port: u16) -> bool {
    let client = match reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    let url = format!("http://127.0.0.1:{port}/api/me/industry");
    match client.get(&url).send() {
        Ok(resp) if resp.status().is_success() => resp
            .json::<serde_json::Value>()
            .ok()
            .and_then(|body| {
                body.get("needs_onboarding")
                    .and_then(|v| v.as_bool())
            })
            .unwrap_or(false),
        _ => false,
    }
}

impl BackendProcess {
    pub fn log_path(&self) -> &Path {
        &self.log_path
    }

    pub fn shutdown(mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
