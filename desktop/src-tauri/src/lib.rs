mod auth;
mod backend;
mod commands;

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use auth::AuthService;
use backend::BackendProcess;
use tauri::{
    image::Image,
    include_image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconEvent, TrayIconBuilder},
    Emitter, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder,
};

const DEFAULT_PORT: u16 = 8088;

fn app_icon() -> Image<'static> {
    include_image!("icons/128x128@2x.png")
}

pub struct AppState {
    backend: Mutex<Option<BackendProcess>>,
    port: u16,
    python: PathBuf,
    app_dir: PathBuf,
    install_dir: PathBuf,
    user_data: PathBuf,
}

impl AppState {
    /// Start the embedded Python API if needed and block until `/api/health` succeeds.
    ///
    /// Concurrent callers (e.g. login handler + `auth://status-changed`) share the same
    /// mutex so only one spawn/health-wait runs and late callers wait for readiness
    /// instead of navigating to 127.0.0.1 before the port is listening.
    pub fn ensure_backend_running(&self) -> Result<String, String> {
        let mut guard = self.backend.lock().unwrap();
        if guard.is_none() {
            let backend = backend::spawn_backend(
                &self.python,
                &self.app_dir,
                &self.install_dir,
                &self.user_data,
                self.port,
            )
            .map_err(|e| format!("启动 Python 后端失败: {e}"))?;
            backend::wait_for_health(self.port, Duration::from_secs(90))
                .map_err(|e| format!("后端健康检查失败: {e}"))?;
            *guard = Some(backend);
        }
        Ok(format!("http://127.0.0.1:{}", self.port))
    }

    pub fn shutdown_backend(&self) {
        if let Ok(mut guard) = self.backend.lock() {
            if let Some(proc) = guard.take() {
                proc.shutdown();
            }
        }
    }
}

fn ensure_single_instance() -> Result<(), String> {
    let instance = single_instance::SingleInstance::new("AINews.SingleInstance")
        .map_err(|e| format!("无法创建单实例锁: {e}"))?;
    if !instance.is_single() {
        return Err("AINews 已在运行".into());
    }
    Box::leak(Box::new(instance));
    Ok(())
}

fn repo_root() -> PathBuf {
    if let Ok(dir) = std::env::var("AINEWS_REPO_ROOT") {
        return PathBuf::from(dir);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn data_dir() -> PathBuf {
    dirs::data_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("AINews")
}

fn dev_mode_enabled() -> bool {
    std::env::var("AINES_DEV_MODE")
        .ok()
        .is_some_and(|v| matches!(v.trim(), "1" | "true" | "yes" | "on"))
}

fn navigate_main_window(app: &tauri::AppHandle, url: &str) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "主窗口不存在".to_string())?;
    window
        .navigate(url.parse().map_err(|e| format!("无效 URL: {e}"))?)
        .map_err(|e| e.to_string())?;
    let _ = window.show();
    let _ = window.set_focus();
    Ok(())
}

fn navigate_main_window_app(app: &tauri::AppHandle, path: &str) -> Result<(), String> {
    navigate_main_window(app, &format!("http://tauri.localhost/{}", path.trim_start_matches('/')))
}

fn show_auth_page(app: &tauri::AppHandle) -> Result<(), String> {
    navigate_main_window_app(app, "auth.html")
}

fn finish_authorized_startup(app: &tauri::AppHandle, state: &AppState, auth: &AuthService) {
    if let Err(err) = auth.start_post_auth_services(app) {
        eprintln!("授权后启动后台服务失败: {err:#}");
    }
    match state.ensure_backend_running() {
        Ok(url) => {
            if let Err(err) = navigate_main_window(app, &url) {
                eprintln!("打开主界面失败: {err}");
            }
            let _ = app.emit("ainews:backend-ready", url);
        }
        Err(err) => {
            eprintln!("后端启动失败: {err}");
            let _ = show_auth_page(app);
        }
    }
}

#[tauri::command]
fn auth_start_app(
    auth: State<'_, AuthService>,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<String, String> {
    if !auth.is_authorized() {
        return Err("未授权".to_string());
    }
    auth.start_post_auth_services(&app)
        .map_err(|e| e.to_string())?;
    let url = state.ensure_backend_running()?;
    navigate_main_window(&app, &url)?;
    let _ = app.emit("ainews:backend-ready", &url);
    Ok(url)
}

#[tauri::command]
fn ainews_show_login(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<(), String> {
    state.shutdown_backend();
    show_auth_page(&app)
}

pub fn run() {
    if let Err(msg) = ensure_single_instance() {
        eprintln!("{msg}");
        std::process::exit(1);
    }

    let install_dir = backend::install_dir();
    let mut app_dir = backend::resolve_app_dir(&install_dir);
    if !app_dir.join("web_server.py").exists() {
        if cfg!(debug_assertions) {
            app_dir = repo_root();
        }
        if !app_dir.join("web_server.py").exists() {
            eprintln!(
                "找不到 web_server.py（安装目录: {}）",
                install_dir.display()
            );
            std::process::exit(1);
        }
    }
    let user_data = data_dir();
    std::fs::create_dir_all(&user_data).ok();

    let python = backend::resolve_python_exe(&install_dir);
    let port = DEFAULT_PORT;
    let skip_auth = dev_mode_enabled();

    let app_state = AppState {
        backend: Mutex::new(None),
        port,
        python,
        app_dir,
        install_dir,
        user_data: user_data.clone(),
    };

    let initial_url = if skip_auth {
        match app_state.ensure_backend_running() {
            Ok(url) => WebviewUrl::External(url.parse().expect("backend url")),
            Err(err) => {
                eprintln!("{err}");
                std::process::exit(1);
            }
        }
    } else {
        WebviewUrl::App("auth.html".into())
    };

    tauri::Builder::default()
        .manage(app_state)
        .setup(move |app| {
            let auth = AuthService::new(user_data.clone()).map_err(|e| e.to_string())?;
            auth.attach_app(app.handle().clone());
            app.manage(auth);

            let window_icon = app_icon();
            let window = WebviewWindowBuilder::new(app, "main", initial_url)
                .title("AINews")
                .inner_size(1280.0, 800.0)
                .maximized(true)
                .icon(window_icon.clone())?
                .build()?;
            window.show()?;
            let _ = window.maximize();

            let show_item = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let data_item =
                MenuItem::with_id(app, "data_dir", "打开数据目录", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let tray_menu = Menu::with_items(app, &[&show_item, &data_item, &quit_item])?;

            let data_path = user_data.clone();
            let _tray = TrayIconBuilder::new()
                .icon(window_icon)
                .menu(&tray_menu)
                .tooltip("AINews")
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                    "data_dir" => {
                        #[cfg(windows)]
                        {
                            let _ = std::process::Command::new("explorer").arg(&data_path).spawn();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.show();
                            let _ = win.set_focus();
                        }
                    }
                })
                .build(app)?;

            if skip_auth {
                if let Some(auth) = app.try_state::<AuthService>() {
                    let _ = auth.start_post_auth_services(app.handle());
                }
            } else {
                let app_handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let Some(auth) = app_handle.try_state::<AuthService>() else {
                        return;
                    };
                    let Some(state) = app_handle.try_state::<AppState>() else {
                        return;
                    };
                    match auth.bootstrap().await {
                        Ok(true) => finish_authorized_startup(&app_handle, &state, &auth),
                        Ok(false) => {
                            // Window already opened on auth.html; avoid re-navigating
                            // to tauri.localhost with the wrong scheme (https).
                        }
                        Err(err) => {
                            eprintln!("鉴权初始化失败: {err:#}");
                            let _ = show_auth_page(&app_handle);
                        }
                    }
                    auth.mark_bootstrap_completed();
                });
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::auth_get_status,
            commands::auth_login,
            commands::auth_register,
            commands::auth_logout,
            commands::auth_redeem_offline_code,
            commands::auth_clear_offline,
            commands::auth_refresh,
            commands::auth_change_password,
            commands::auth_request_password_reset,
            commands::auth_health_check,
            commands::auth_send_phone_code,
            commands::auth_get_captcha,
            commands::auth_save_remembered_password,
            commands::auth_load_remembered_password,
            commands::auth_clear_remembered_password,
            commands::auth_list_remembered_emails,
            commands::auth_phone_login,
            commands::auth_phone_register,
            commands::auth_bind_phone,
            commands::auth_bootstrap_completed,
            auth_start_app,
            ainews_show_login,
            commands::desktop_window_minimize,
            commands::desktop_window_toggle_maximize,
            commands::desktop_window_close,
            commands::desktop_window_is_maximized,
            commands::ainews_open_devtools,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    state.shutdown_backend();
                }
            }
        });
}
