use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;

use serde::Deserialize;
use serde::Serialize;
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemotionSetupStatusDto {
    pub ready: bool,
    pub upgrade_required: bool,
    pub marker_present: bool,
    pub node_ready: bool,
    pub project_ready: bool,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemotionSetupProgressDto {
    pub step: String,
    pub label: String,
    pub percent: u8,
    pub done: bool,
}

static SETUP_LOCK: Mutex<()> = Mutex::new(());

#[derive(Debug, Deserialize)]
struct NodeWinManifest {
    url: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct NodeManifest {
    version: String,
    win_x64: NodeWinManifest,
}

#[derive(Debug, Deserialize)]
struct RemotionManifest {
    install_id: String,
    node: NodeManifest,
}

pub fn node_home(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("node")
}

pub fn remotion_project_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("remotion-project")
}

pub fn browser_dir(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("remotion-browser")
}

fn marker_path(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("remotion_v1.json")
}

fn setup_log_path(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("logs").join("remotion_setup.log")
}

fn append_log(data_dir: &Path, line: &str) {
    let path = setup_log_path(data_dir);
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(file, "{}", line);
    }
}

fn manifest_path(install_dir: &Path) -> Option<PathBuf> {
    for root in [
        install_dir.join("bundle-resources"),
        install_dir.join("resources"),
        install_dir.to_path_buf(),
    ] {
        let candidate = root.join("remotion-runtime-manifest.json");
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn load_manifest(install_dir: &Path) -> Result<RemotionManifest, String> {
    let path = manifest_path(install_dir).ok_or_else(|| "缺少 remotion-runtime-manifest.json".to_string())?;
    let text = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| format!("manifest 解析失败: {e}"))
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    let digest = Sha256::digest(bytes);
    Ok(format!("{:x}", digest))
}

fn bundled_lock_path(app_dir: &Path) -> PathBuf {
    app_dir.join("remotion").join("package-lock.json")
}

fn project_ready(project: &Path) -> bool {
    project.join("package.json").is_file() && project.join("node_modules").is_dir()
}

fn node_ready(node_home: &Path) -> bool {
    node_home.join("node.exe").is_file() && node_home.join("npm.cmd").is_file()
}

fn read_marker(data_dir: &Path) -> Option<serde_json::Value> {
    let path = marker_path(data_dir);
    if !path.is_file() {
        return None;
    }
    let text = fs::read_to_string(&path).map_err(|_| ()).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn upgrade_required(marker: &serde_json::Value, app_version: &str, lock_path: &Path) -> bool {
    if marker.get("install_id").and_then(|v| v.as_str()) != Some("remotion_v1") {
        return true;
    }
    if marker.get("app_version").and_then(|v| v.as_str()) != Some(app_version) {
        return true;
    }
    if !lock_path.is_file() {
        return false;
    }
    let expected = marker
        .get("remotion_lock_sha256")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if expected.is_empty() {
        return false;
    }
    match sha256_file(lock_path) {
        Ok(actual) => actual != expected,
        Err(_) => true,
    }
}

pub fn status(data_dir: &Path, app_dir: &Path, app_version: &str) -> RemotionSetupStatusDto {
    let project = remotion_project_dir(data_dir);
    let node = node_home(data_dir);
    let lock = bundled_lock_path(app_dir);
    let marker_present = marker_path(data_dir).is_file();
    let marker = read_marker(data_dir);
    let upgrade = marker
        .as_ref()
        .map(|m| upgrade_required(m, app_version, &lock))
        .unwrap_or(false);
    let node_ok = node_ready(&node);
    let project_ok = project_ready(&project);
    let ready = marker_present && node_ok && project_ok && !upgrade;
    let reason = if upgrade {
        Some("upgrade_required".into())
    } else if !node_ok {
        Some("node_missing".into())
    } else if !project_ok {
        Some("node_modules_missing".into())
    } else if !marker_present {
        Some("marker_missing".into())
    } else {
        None
    };
    RemotionSetupStatusDto {
        ready,
        upgrade_required: upgrade,
        marker_present,
        node_ready: node_ok,
        project_ready: project_ok,
        reason,
    }
}

fn emit_progress(app: &AppHandle, step: &str, label: &str, percent: u8, done: bool) {
    let _ = app.emit(
        "ainews:remotion-setup-progress",
        RemotionSetupProgressDto {
            step: step.to_string(),
            label: label.to_string(),
            percent,
            done,
        },
    );
}

fn run_hidden(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}

fn download_file(url: &str, dest: &Path) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(600))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client.get(url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("下载失败 HTTP {}", resp.status()));
    }
    let bytes = resp.bytes().map_err(|e| e.to_string())?;
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(dest, &bytes).map_err(|e| e.to_string())?;
    Ok(())
}

fn verify_sha256(path: &Path, expected: &str) -> Result<(), String> {
    if expected.trim().is_empty() {
        return Ok(());
    }
    let actual = sha256_file(path)?;
    if actual.eq_ignore_ascii_case(expected.trim()) {
        Ok(())
    } else {
        Err("Node 安装包校验失败 (sha256)".into())
    }
}

fn extract_node_zip(zip_path: &Path, node_home: &Path) -> Result<(), String> {
    fs::create_dir_all(node_home).map_err(|e| e.to_string())?;
    let temp = node_home.parent().unwrap().join("node_zip_extract");
    if temp.exists() {
        fs::remove_dir_all(&temp).ok();
    }
    fs::create_dir_all(&temp).map_err(|e| e.to_string())?;
    let mut cmd = Command::new("tar");
    cmd.args(["-xf"])
        .arg(zip_path)
        .arg("-C")
        .arg(&temp);
    run_hidden(&mut cmd);
    let status = cmd.status().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("解压 Node 失败 (tar)".into());
    }
    let mut inner: Option<PathBuf> = None;
    for entry in fs::read_dir(&temp).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.is_dir() {
            inner = Some(path);
            break;
        }
    }
    let inner = inner.ok_or_else(|| "Node zip 结构异常".to_string())?;
    for entry in fs::read_dir(&inner).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let src = entry.path();
        let dst = node_home.join(entry.file_name());
        if src.is_dir() {
            copy_dir_filtered(&src, &dst, false)?;
        } else {
            if dst.exists() {
                fs::remove_file(&dst).ok();
            }
            fs::copy(&src, &dst).map_err(|e| e.to_string())?;
        }
    }
    fs::remove_dir_all(&temp).ok();
    Ok(())
}

fn copy_dir_filtered(src: &Path, dst: &Path, skip_node_modules: bool) -> Result<(), String> {
    fs::create_dir_all(dst).map_err(|e| e.to_string())?;
    for entry in fs::read_dir(src).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name();
        if skip_node_modules && name == "node_modules" {
            continue;
        }
        let from = entry.path();
        let to = dst.join(name);
        if from.is_dir() {
            copy_dir_filtered(&from, &to, skip_node_modules)?;
        } else {
            if let Some(parent) = to.parent() {
                fs::create_dir_all(parent).ok();
            }
            fs::copy(&from, &to).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn sync_remotion_sources(app_dir: &Path, project: &Path) -> Result<(), String> {
    let src = app_dir.join("remotion");
    if !src.join("package.json").is_file() {
        return Err(format!("应用包缺少 remotion 目录: {}", src.display()));
    }
    if project.exists() {
        fs::remove_dir_all(project).map_err(|e| e.to_string())?;
    }
    copy_dir_filtered(&src, project, true)?;
    Ok(())
}

fn path_with_node(node_home: &Path) -> String {
    let path = std::env::var("PATH").unwrap_or_default();
    let node = node_home.to_string_lossy().to_string();
    if path.is_empty() {
        node
    } else {
        format!("{};{}", node, path)
    }
}

fn run_npm_ci(
    app: &AppHandle,
    data_dir: &Path,
    node_home: &Path,
    project: &Path,
    percent_start: u8,
    percent_end: u8,
) -> Result<(), String> {
    emit_progress(app, "npm", "正在安装 Remotion 依赖 (npm ci)…", percent_start, false);
    let npm = node_home.join("npm.cmd");
    let mut cmd = Command::new(&npm);
    cmd.arg("ci")
        .arg("--omit=dev")
        .current_dir(project)
        .env("PATH", path_with_node(node_home))
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    run_hidden(&mut cmd);
    append_log(data_dir, "npm ci --omit=dev");
    let status = cmd.status().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("npm ci 失败，请查看 remotion_setup.log".into());
    }
    emit_progress(app, "npm", "依赖安装完成", percent_end, false);
    Ok(())
}

fn run_browser_ensure(
    app: &AppHandle,
    data_dir: &Path,
    node_home: &Path,
    project: &Path,
    browser: &Path,
) -> Result<(), String> {
    emit_progress(app, "browser", "正在准备 Remotion 浏览器…", 88, false);
    fs::create_dir_all(browser).map_err(|e| e.to_string())?;
    let npx = node_home.join("npx.cmd");
    let mut cmd = Command::new(&npx);
    cmd.args(["remotion", "browser", "ensure"])
        .current_dir(project)
        .env("PATH", path_with_node(node_home))
        .env(
            "REMOTION_BROWSER_DOWNLOAD_DIR",
            browser.to_string_lossy().to_string(),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    run_hidden(&mut cmd);
    append_log(data_dir, "npx remotion browser ensure");
    let status = cmd.status().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("Remotion browser ensure 失败".into());
    }
    emit_progress(app, "browser", "浏览器组件就绪", 95, false);
    Ok(())
}

fn write_marker(
    data_dir: &Path,
    app_version: &str,
    lock_sha: &str,
    node_version: &str,
) -> Result<(), String> {
    let body = serde_json::json!({
        "install_id": "remotion_v1",
        "app_version": app_version,
        "remotion_lock_sha256": lock_sha,
        "node_version": node_version,
        "completed_at": chrono::Utc::now().to_rfc3339(),
    });
    let path = marker_path(data_dir);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(&path, serde_json::to_string_pretty(&body).unwrap()).map_err(|e| e.to_string())?;
    Ok(())
}

pub fn run(
    app: &AppHandle,
    install_dir: &Path,
    data_dir: &Path,
    app_dir: &Path,
    app_version: &str,
) -> Result<(), String> {
    let _guard = SETUP_LOCK.lock().unwrap();
    let current = status(data_dir, app_dir, app_version);
    if current.ready {
        emit_progress(app, "done", "Remotion 运行环境已就绪", 100, true);
        return Ok(());
    }

    append_log(data_dir, "=== remotion setup start ===");
    emit_progress(app, "check", "正在准备 Remotion 运行环境…", 5, false);

    let manifest = load_manifest(install_dir)?;
    let node_home = node_home(data_dir);
    let project = remotion_project_dir(data_dir);
    let browser = browser_dir(data_dir);

    if !node_ready(&node_home) {
        emit_progress(app, "node", "正在下载 Node.js…", 15, false);
        let zip_path = data_dir.join("runtime").join("node-download.zip");
        download_file(&manifest.node.win_x64.url, &zip_path)?;
        verify_sha256(&zip_path, &manifest.node.win_x64.sha256)?;
        extract_node_zip(&zip_path, &node_home)?;
        fs::remove_file(&zip_path).ok();
        if !node_ready(&node_home) {
            return Err("Node 安装后仍不可用".into());
        }
        emit_progress(app, "node", "Node.js 已安装", 40, false);
    }

    sync_remotion_sources(app_dir, &project)?;
    emit_progress(app, "sync", "已同步 Remotion 项目", 50, false);

    run_npm_ci(app, data_dir, &node_home, &project, 55, 85)?;
    if !project_ready(&project) {
        return Err("npm ci 后未找到 node_modules".into());
    }

    run_browser_ensure(app, data_dir, &node_home, &project, &browser)?;

    let lock_sha = sha256_file(&bundled_lock_path(app_dir))?;
    let node_version = manifest.node.version.clone();
    write_marker(data_dir, app_version, &lock_sha, &node_version)?;

    append_log(data_dir, "=== remotion setup done ===");
    emit_progress(app, "done", "Remotion 运行环境安装完成", 100, true);
    Ok(())
}
