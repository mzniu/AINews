use tauri::{AppHandle, Emitter, State, WebviewWindow};

use crate::auth::{AuthHealthDto, AuthService, AuthStatusDto};
use crate::remotion_setup;
use crate::remotion_setup::RemotionSetupStatusDto;
use crate::runtime_setup;
use crate::runtime_setup::RuntimeSetupStatusDto;
use crate::{AppState, StartupDiagnosticsDto};

fn emit_auth_status_changed(app: &AppHandle) {
    let _ = app.emit("auth://status-changed", ());
}

#[tauri::command]
pub async fn auth_get_status(auth: State<'_, AuthService>) -> Result<AuthStatusDto, String> {
    Ok(auth.status_dto())
}

#[tauri::command]
pub async fn auth_login(
    auth: State<'_, AuthService>,
    app: AppHandle,
    email: String,
    password: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth.login(&email, &password).await.map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_register(
    auth: State<'_, AuthService>,
    app: AppHandle,
    email: String,
    password: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth
        .register(&email, &password)
        .await
        .map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_logout(
    auth: State<'_, AuthService>,
    app: AppHandle,
) -> Result<AuthStatusDto, String> {
    let dto = auth.logout().await.map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_redeem_offline_code(
    auth: State<'_, AuthService>,
    app: AppHandle,
    code: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth.redeem_offline_code(&code).await.map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub fn auth_clear_offline(
    auth: State<'_, AuthService>,
    app: AppHandle,
) -> Result<AuthStatusDto, String> {
    let dto = auth.clear_offline().map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_refresh(auth: State<'_, AuthService>) -> Result<AuthStatusDto, String> {
    auth.refresh_online_manual()
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_change_password(
    auth: State<'_, AuthService>,
    old_password: String,
    new_password: String,
) -> Result<String, String> {
    auth.change_password(&old_password, &new_password)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_request_password_reset(
    auth: State<'_, AuthService>,
    email: String,
) -> Result<String, String> {
    auth.request_password_reset(&email)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_health_check(auth: State<'_, AuthService>) -> Result<AuthHealthDto, String> {
    Ok(auth.health_check().await)
}

#[tauri::command]
pub async fn auth_send_phone_code(
    auth: State<'_, AuthService>,
    phone: String,
    purpose: String,
    captcha_id: Option<String>,
    captcha_code: Option<String>,
) -> Result<String, String> {
    auth.send_phone_code(
        &phone,
        &purpose,
        captcha_id.as_deref(),
        captcha_code.as_deref(),
    )
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn auth_get_captcha(
    auth: State<'_, AuthService>,
) -> Result<crate::auth::CaptchaResponse, String> {
    auth.get_captcha().await.map_err(|e| e.to_string())
}

#[tauri::command]
pub fn auth_save_remembered_password(
    auth: State<'_, AuthService>,
    email: String,
    password: String,
) -> Result<(), String> {
    auth.save_remembered_password(&email, &password)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn auth_load_remembered_password(
    auth: State<'_, AuthService>,
    email: String,
) -> Result<Option<String>, String> {
    Ok(auth.load_remembered_password(&email))
}

#[tauri::command]
pub fn auth_clear_remembered_password(
    auth: State<'_, AuthService>,
    email: Option<String>,
) -> Result<bool, String> {
    Ok(auth.clear_remembered_password(email.as_deref()))
}

#[tauri::command]
pub fn auth_list_remembered_emails(auth: State<'_, AuthService>) -> Result<Vec<String>, String> {
    Ok(auth.list_remembered_emails())
}

#[tauri::command]
pub async fn auth_phone_login(
    auth: State<'_, AuthService>,
    app: AppHandle,
    phone: String,
    code: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth.phone_login(&phone, &code).await.map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_phone_register(
    auth: State<'_, AuthService>,
    app: AppHandle,
    phone: String,
    code: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth
        .phone_register(&phone, &code)
        .await
        .map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub async fn auth_bind_phone(
    auth: State<'_, AuthService>,
    app: AppHandle,
    phone: String,
    code: String,
) -> Result<AuthStatusDto, String> {
    let dto = auth.bind_phone(&phone, &code).await.map_err(|e| e.to_string())?;
    emit_auth_status_changed(&app);
    Ok(dto)
}

#[tauri::command]
pub fn auth_bootstrap_completed(auth: State<'_, AuthService>) -> bool {
    auth.bootstrap_completed()
}

#[tauri::command]
pub fn auth_get_startup_diagnostics(state: State<'_, AppState>) -> StartupDiagnosticsDto {
    state.startup_diagnostics()
}

#[tauri::command]
pub fn runtime_setup_status(state: State<'_, AppState>) -> RuntimeSetupStatusDto {
    runtime_setup::status(
        &state.python,
        &state.install_dir,
        &state.user_data,
        &state.app_dir,
    )
}

#[tauri::command]
pub async fn runtime_setup_run(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let app = app.clone();
    let python = state.python.clone();
    let install_dir = state.install_dir.clone();
    let user_data = state.user_data.clone();
    let app_dir = state.app_dir.clone();
    tokio::task::spawn_blocking(move || {
        runtime_setup::run(&app, &python, &install_dir, &user_data, &app_dir)
    })
    .await
    .map_err(|e| format!("运行环境安装任务异常: {e}"))??;
    Ok(())
}

#[tauri::command]
pub fn remotion_setup_status(state: State<'_, AppState>) -> RemotionSetupStatusDto {
    remotion_setup::status(&state.user_data, &state.app_dir, &state.app_version)
}

#[tauri::command]
pub async fn remotion_setup_run(
    app: AppHandle,
    state: State<'_, AppState>,
    auth: State<'_, AuthService>,
) -> Result<(), String> {
    let app_install = app.clone();
    let install_dir = state.install_dir.clone();
    let user_data = state.user_data.clone();
    let app_dir = state.app_dir.clone();
    let app_version = state.app_version.clone();

    tokio::task::spawn_blocking(move || {
        remotion_setup::run(
            &app_install,
            &install_dir,
            &user_data,
            &app_dir,
            &app_version,
        )
    })
    .await
    .map_err(|e| format!("Remotion 安装任务异常: {e}"))??;

    state
        .restart_backend(Some(&auth))
        .map_err(|e| format!("Remotion 已安装，但重启后端失败: {e}"))?;

    let _ = app.emit("ainews:backend-restarted", ());
    Ok(())
}

#[tauri::command]
pub fn desktop_window_minimize(window: WebviewWindow) -> Result<(), String> {
    window.minimize().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn desktop_window_toggle_maximize(window: WebviewWindow) -> Result<(), String> {
    if window.is_maximized().map_err(|e| e.to_string())? {
        window.unmaximize().map_err(|e| e.to_string())?;
    } else {
        window.maximize().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn desktop_window_close(window: WebviewWindow) -> Result<(), String> {
    window.close().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn desktop_window_is_maximized(window: WebviewWindow) -> Result<bool, String> {
    window.is_maximized().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn ainews_open_devtools(window: WebviewWindow) {
    window.open_devtools();
}
