mod client;
mod config;
mod offline;
mod remembered;
mod secrets;
mod session;
mod types;

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Mutex;

use anyhow::{anyhow, Result};
use chrono::{Duration, Utc};
use tauri::{AppHandle, Emitter, Manager};

pub use types::{AuthHealthDto, AuthStatusDto, CaptchaResponse};

use client::{AuthApiError, AuthClient};
use config::AuthConfig;
use offline::{grant_has_feature, revalidate_stored_grant};
use session::{
    access_needs_refresh, clear_session, load_session, refresh_bearer_token, save_session,
    session_is_authorized,
};
use types::{
    AccountStatus, AuthMode, SessionFile, TokenResponse,
};

pub fn validate_phone_number(phone: &str) -> Result<()> {
    let cleaned = phone.trim().replace([' ', '-'], "");
    if cleaned.len() != 11 {
        return Err(anyhow!("请输入 11 位手机号"));
    }
    if !cleaned.chars().all(|c| c.is_ascii_digit()) {
        return Err(anyhow!("手机号只能包含数字"));
    }
    Ok(())
}

pub struct AuthService {
    config: AuthConfig,
    client: AuthClient,
    session: Mutex<Option<SessionFile>>,
    app_handle: Mutex<Option<AppHandle>>,
    background_started: AtomicBool,
    token_refresh_loop_started: AtomicBool,
    bootstrap_completed: AtomicBool,
    /// Consecutive non-recoverable refresh failures (HTTP 401). Cleared on
    /// any successful refresh. Session is only cleared after
    /// `REFRESH_FATAL_THRESHOLD` consecutive failures, with `/me`
    /// re-verification, to avoid mid-task logout on transient server errors
    /// whose bodies happen to contain "expired"/"unauthorized" keywords.
    consecutive_non_recoverable_failures: AtomicU32,
}

/// Number of consecutive 401 refresh failures (confirmed by `/me` also
/// returning 401) required before clearing the local session. 2 means a
/// single transient 401-shaped error won't kick the user out — the loop
/// must see the failure persist across consecutive ticks.
const REFRESH_FATAL_THRESHOLD: u32 = 2;

/// Refresh failures that won't succeed on retry. We require an explicit
/// HTTP 401 status code (carried by `AuthApiError`); transient server
/// errors (5xx, network, timeouts) are NOT non-recoverable even if their
/// bodies happen to contain "expired"/"unauthorized" keywords — the old
/// substring matching caused mid-task logouts when the auth server
/// returned 504 with such a body.
pub fn is_non_recoverable_refresh_error(err: &anyhow::Error) -> bool {
    match err.downcast_ref::<AuthApiError>() {
        Some(api_err) => api_err.status == 401,
        None => false,
    }
}

impl AuthService {
    pub fn new(data_dir: PathBuf) -> Result<Self> {
        let config = AuthConfig::from_data_dir(&data_dir);
        let client = AuthClient::new(config.clone())?;
        let session = load_session(&config.auth_dir).ok().flatten();
        Ok(Self {
            config,
            client,
            session: Mutex::new(session),
            app_handle: Mutex::new(None),
            background_started: AtomicBool::new(false),
            token_refresh_loop_started: AtomicBool::new(false),
            bootstrap_completed: AtomicBool::new(false),
            consecutive_non_recoverable_failures: AtomicU32::new(0),
        })
    }

    pub fn mark_bootstrap_completed(&self) {
        self.bootstrap_completed.store(true, Ordering::SeqCst);
    }

    pub fn bootstrap_completed(&self) -> bool {
        self.bootstrap_completed.load(Ordering::SeqCst)
    }

    pub fn attach_app(&self, app: AppHandle) {
        *self.app_handle.lock().unwrap() = Some(app);
    }

    fn notify_auth_changed(&self) {
        if let Some(app) = self.app_handle.lock().unwrap().as_ref() {
            let _ = app.emit("auth://status-changed", ());
        }
    }

    /// Emit `ainews:auth-token-deprecated` when the server flags the
    /// token grant as deprecated (e.g. email login being phased out).
    /// The frontend can surface the `warning` message as a banner so the
    /// user knows to re-login with the new method before the grant stops
    /// working. No-op when `deprecated == false` (the common path).
    fn notify_token_deprecated(&self, warning: Option<&str>) {
        if let Some(app) = self.app_handle.lock().unwrap().as_ref() {
            let payload = serde_json::json!({
                "deprecated": true,
                "warning": warning,
            });
            let _ = app.emit("ainews:auth-token-deprecated", payload);
        }
    }

    /// Called when a refresh attempt failed. If the failure is
    /// non-recoverable (HTTP 401) AND `/me` re-verification confirms the
    /// access token is also dead AND this has happened on
    /// `REFRESH_FATAL_THRESHOLD` consecutive ticks, clear the local
    /// session. Otherwise just bump the consecutive-failure counter and
    /// return without clearing — the user keeps working, the next tick
    /// will retry.
    async fn clear_online_session_after_fatal_refresh(&self, err: &anyhow::Error) {
        if !is_non_recoverable_refresh_error(err) {
            return;
        }
        // 1. Bump the consecutive-401 counter.
        let n = self
            .consecutive_non_recoverable_failures
            .fetch_add(1, Ordering::SeqCst)
            + 1;
        if n < REFRESH_FATAL_THRESHOLD {
            log::warn!(
                "登录刷新返回 401（第 {n}/{REFRESH_FATAL_THRESHOLD} 次），暂不清除会话，等待下轮重试"
            );
            return;
        }

        // 2. Re-verify with /me — if the access token is still valid, the
        // refresh-token 401 is treated as transient (e.g. server glitch on
        // the refresh endpoint) and we keep the session.
        let access_token = self
            .session
            .lock()
            .unwrap()
            .as_ref()
            .and_then(|s| s.access_token.clone());
        let me_still_ok = match access_token.as_deref() {
            Some(token) => self.client.get_me(token).await.is_ok(),
            None => false,
        };
        if me_still_ok {
            // /me confirms the access token is still valid — the refresh-401
            // was transient (e.g. server glitch on the refresh endpoint).
            // Reset the streak so a future blip doesn't accumulate toward
            // an unwanted session clear.
            self.reset_consecutive_refresh_failures();
            log::warn!(
                "刷新接口返回 401 但 /me 仍可成功，判定为瞬时故障，保留会话"
            );
            return;
        }

        // 3. Both refresh and /me confirm the session is dead — clear.
        log::info!("登录已失效（连续 {n} 次 401 且 /me 验证失败），已清除本地会话: {err:#}");
        self.consecutive_non_recoverable_failures
            .store(0, Ordering::SeqCst);
        if clear_session(&self.config.auth_dir).is_ok() {
            *self.session.lock().unwrap() = None;
            self.notify_auth_changed();
        }
    }

    fn reset_consecutive_refresh_failures(&self) {
        self.consecutive_non_recoverable_failures
            .store(0, Ordering::SeqCst);
    }

    pub fn is_authorized(&self) -> bool {
        let guard = self.session.lock().unwrap();
        guard
            .as_ref()
            .map(session_is_authorized)
            .unwrap_or(false)
    }

    /// Cloud Control Plane bearer token for the embedded Python API (industry sync).
    pub fn cloud_access_token_for_backend(&self) -> Option<String> {
        let guard = self.session.lock().unwrap();
        guard.as_ref().and_then(|session| {
            if session.mode != AuthMode::Online {
                return None;
            }
            session
                .access_token
                .clone()
                .filter(|token| !token.is_empty())
        })
    }

    /// Online sessions allow all product features; offline grants use payload `features`.
    pub fn allows_feature(&self, feature: &str) -> bool {
        let guard = self.session.lock().unwrap();
        let Some(session) = guard.as_ref() else {
            return false;
        };
        if !session_is_authorized(session) {
            return false;
        }
        match session.mode {
            AuthMode::Online => true,
            AuthMode::Offline => session
                .offline
                .as_ref()
                .map(|g| grant_has_feature(g, feature))
                .unwrap_or(false),
        }
    }

    fn revalidate_offline_session(&self) -> Result<()> {
        let mut guard = self.session.lock().unwrap();
        let Some(session) = guard.as_ref() else {
            return Ok(());
        };
        if session.mode != AuthMode::Offline {
            return Ok(());
        }
        let grant = session
            .offline
            .clone()
            .ok_or_else(|| anyhow!("离线会话缺少授权信息"))?;
        let refreshed = revalidate_stored_grant(&grant, &self.config.auth_dir)?;
        let mut updated = session.clone();
        updated.offline = Some(refreshed);
        save_session(&self.config.auth_dir, &updated)?;
        *guard = Some(updated);
        Ok(())
    }

    pub fn status_dto(&self) -> AuthStatusDto {
        let guard = self.session.lock().unwrap();
        let authorized = guard
            .as_ref()
            .map(session_is_authorized)
            .unwrap_or(false);
        let mut message = None;
        if let Some(session) = guard.as_ref() {
            if session.mode == AuthMode::Online
                && !authorized
                && session.access_token.as_ref().is_some_and(|t| !t.is_empty())
            {
                message = Some("登录已过期，请在「账号」中重新登录".to_string());
            }
        }
        let base = AuthStatusDto {
            authorized,
            mode: None,
            email: None,
            phone: None,
            account_status: None,
            offline_expires_at: None,
            auth_base_url: self.config.base_url.clone(),
            message,
            features: None,
            token_encryption: Some(secrets::encryption_method().to_string()),
        };
        let Some(session) = guard.as_ref() else {
            return base;
        };
        match session.mode {
            AuthMode::Online => AuthStatusDto {
                mode: Some("online".to_string()),
                email: session.user.as_ref().and_then(|u| {
                    if u.email.trim().is_empty() {
                        None
                    } else {
                        Some(u.email.clone())
                    }
                }),
                phone: session.user.as_ref().and_then(|u| u.phone.clone()),
                account_status: session
                    .user
                    .as_ref()
                    .map(|u| u.account_status.as_str().to_string()),
                ..base
            },
            AuthMode::Offline => AuthStatusDto {
                mode: Some("offline".to_string()),
                offline_expires_at: session.offline.as_ref().map(|o| o.expires_at.clone()),
                email: session.offline.as_ref().and_then(|o| o.issued_to.clone()),
                features: session.offline.as_ref().map(|o| o.features.clone()),
                ..base
            },
        }
    }

    /// Load session, refresh online token if needed; returns whether user may use the app.
    pub async fn bootstrap(&self) -> Result<bool> {
        if self.session.lock().unwrap().as_ref().is_some_and(|s| s.mode == AuthMode::Offline) {
            if let Err(err) = self.revalidate_offline_session() {
                log::warn!("离线授权校验失败，已清除会话: {err:#}");
                clear_session(&self.config.auth_dir)?;
                *self.session.lock().unwrap() = None;
            }
        }
        let needs_refresh = {
            let guard = self.session.lock().unwrap();
            guard
                .as_ref()
                .map(|s| s.mode == AuthMode::Online && access_needs_refresh(s, 300))
                .unwrap_or(false)
        };
        if needs_refresh {
            if let Err(err) = self.refresh_online().await {
                if !is_non_recoverable_refresh_error(&err) {
                    log::warn!("启动时刷新登录失败: {err:#}");
                }
            }
        }
        Ok(self.is_authorized())
    }

    fn start_token_refresh_loop(&self, app: AppHandle) {
        if self
            .token_refresh_loop_started
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return;
        }
        tauri::async_runtime::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(90)).await;
                let Some(auth) = app.try_state::<AuthService>() else {
                    continue;
                };
                let was_authorized = auth.is_authorized();
                if auth
                    .session
                    .lock()
                    .unwrap()
                    .as_ref()
                    .is_some_and(|s| s.mode == AuthMode::Online)
                {
                    if let Err(err) = auth.maybe_refresh_online().await {
                        if !is_non_recoverable_refresh_error(&err) {
                            log::debug!("后台刷新登录 token 失败: {err:#}");
                        }
                    }
                }
                let now_authorized = auth.is_authorized();
                if was_authorized != now_authorized {
                    let _ = app.emit("auth://status-changed", ());
                }
            }
        });
    }

    pub async fn login(&self, email: &str, password: &str) -> Result<AuthStatusDto> {
        let tokens = self.client.login(email, password).await?;
        self.apply_online_tokens(tokens).await?;
        Ok(self.status_dto())
    }

    pub async fn register(&self, email: &str, password: &str) -> Result<AuthStatusDto> {
        let reg = self.client.register(email, password).await?;
        if let (Some(access), Some(refresh), Some(expires_in)) = (
            reg.access_token.as_deref(),
            reg.refresh_token.as_deref(),
            reg.expires_in,
        ) {
            let tokens = TokenResponse {
                access_token: access.to_string(),
                token_type: "bearer".to_string(),
                expires_in,
                refresh_token: refresh.to_string(),
                deprecated: false,
                warning: None,
            };
            self.apply_online_tokens(tokens).await?;
            return Ok(self.status_dto());
        }
        // Server may not return tokens on register — follow with login.
        self.login(email, password).await
    }

    pub async fn send_phone_code(
        &self,
        phone: &str,
        purpose: &str,
        captcha_id: Option<&str>,
        captcha_code: Option<&str>,
    ) -> Result<String> {
        validate_phone_number(phone)?;
        let res = self
            .client
            .send_phone_code(phone, purpose, captcha_id, captcha_code)
            .await?;
        Ok(res.message)
    }

    /// Fetch an SVG arithmetic captcha challenge. Returns the parsed
    /// `{captcha_id, svg_data}` on success; the caller decides how to
    /// render the SVG and collect the user's answer.
    pub async fn get_captcha(&self) -> Result<crate::auth::types::CaptchaResponse> {
        self.client.get_captcha().await
    }

    // ---- Remembered email/password storage (email login "记住密码") ----

    /// Seal and persist `password` for `email`. Existing entry for the same
    /// email is overwritten. Errors are surfaced but the caller typically
    /// just logs them — failure to remember the password shouldn't block
    /// the login flow.
    pub fn save_remembered_password(&self, email: &str, password: &str) -> Result<()> {
        let mut file = remembered::RememberedCredentialsFile::load(&self.config.auth_dir);
        file.set_entry(email, password)?;
        file.save(&self.config.auth_dir)
    }

    /// Unseal and return the password for `email`, or `None` if there is no
    /// entry or the sealed blob could not be unsealed (e.g. DPAPI key
    /// changed). The caller should treat `None` as "no remembered password,
    /// leave the field blank".
    pub fn load_remembered_password(&self, email: &str) -> Option<String> {
        let file = remembered::RememberedCredentialsFile::load(&self.config.auth_dir);
        file.get_password(email)
    }

    /// Remove the entry for `email`, or clear all entries when `email` is
    /// `None`. Returns true if anything was removed.
    pub fn clear_remembered_password(&self, email: Option<&str>) -> bool {
        let path = remembered::RememberedCredentialsFile::path_for(&self.config.auth_dir);
        if !path.is_file() {
            return false;
        }
        let mut file = remembered::RememberedCredentialsFile::load(&self.config.auth_dir);
        let removed = match email {
            Some(e) => file.remove_entry(e),
            None => {
                if file.entries.is_empty() {
                    false
                } else {
                    file.clear();
                    true
                }
            }
        };
        if removed {
            let _ = file.save(&self.config.auth_dir);
        }
        removed
    }

    /// List all remembered email addresses, sorted alphabetically. The
    /// frontend uses this to pre-fill the email field and to populate a
    /// `<datalist>` of saved accounts.
    pub fn list_remembered_emails(&self) -> Vec<String> {
        let file = remembered::RememberedCredentialsFile::load(&self.config.auth_dir);
        file.emails()
    }

    pub async fn phone_login(&self, phone: &str, code: &str) -> Result<AuthStatusDto> {
        validate_phone_number(phone)?;
        if code.trim().len() != 6 {
            return Err(anyhow!("验证码应为 6 位"));
        }
        let tokens = self.client.phone_login(phone, code).await?;
        self.apply_online_tokens(tokens).await?;
        Ok(self.status_dto())
    }

    pub async fn phone_register(&self, phone: &str, code: &str) -> Result<AuthStatusDto> {
        validate_phone_number(phone)?;
        if code.trim().len() != 6 {
            return Err(anyhow!("验证码应为 6 位"));
        }
        let reg = self.client.phone_register(phone, code).await?;
        if let (Some(access), Some(refresh), Some(expires_in)) = (
            reg.access_token.as_deref(),
            reg.refresh_token.as_deref(),
            reg.expires_in,
        ) {
            let tokens = TokenResponse {
                access_token: access.to_string(),
                token_type: "bearer".to_string(),
                expires_in,
                refresh_token: refresh.to_string(),
                deprecated: false,
                warning: None,
            };
            self.apply_online_tokens(tokens).await?;
            return Ok(self.status_dto());
        }
        self.phone_login(phone, code).await
    }

    pub async fn bind_phone(&self, phone: &str, code: &str) -> Result<AuthStatusDto> {
        validate_phone_number(phone)?;
        if code.trim().len() != 6 {
            return Err(anyhow!("验证码应为 6 位"));
        }
        let access = {
            let guard = self.session.lock().unwrap();
            let session = guard.as_ref().ok_or_else(|| anyhow!("未登录"))?;
            if session.mode != AuthMode::Online {
                return Err(anyhow!("离线授权无法绑定手机号"));
            }
            session
                .access_token
                .clone()
                .ok_or_else(|| anyhow!("无 access_token"))?
        };
        let profile = self.client.bind_phone(&access, phone, code).await?;
        {
            let mut guard = self.session.lock().unwrap();
            if let Some(session) = guard.as_mut() {
                session.user = Some(profile.into_auth_user());
                save_session(&self.config.auth_dir, session)?;
            }
        }
        Ok(self.status_dto())
    }

    /// Refresh online access token when within 5 minutes of expiry.
    pub async fn maybe_refresh_online(&self) -> Result<()> {
        let needs_refresh = {
            let guard = self.session.lock().unwrap();
            guard
                .as_ref()
                .map(|s| s.mode == AuthMode::Online && access_needs_refresh(s, 300))
                .unwrap_or(false)
        };
        if needs_refresh {
            self.refresh_online().await?;
        }
        Ok(())
    }

    pub async fn refresh_online_manual(&self) -> Result<AuthStatusDto> {
        self.refresh_online().await?;
        Ok(self.status_dto())
    }

    pub async fn change_password(
        &self,
        old_password: &str,
        new_password: &str,
    ) -> Result<String> {
        if old_password.is_empty() {
            return Err(anyhow!("请输入当前密码"));
        }
        if new_password.len() < 8 {
            return Err(anyhow!("新密码至少需要 8 个字符"));
        }
        let access = {
            let guard = self.session.lock().unwrap();
            let session = guard
                .as_ref()
                .ok_or_else(|| anyhow!("未登录"))?;
            if session.mode != AuthMode::Online {
                return Err(anyhow!("离线授权无法在线改密"));
            }
            session
                .access_token
                .clone()
                .ok_or_else(|| anyhow!("无 access_token"))?
        };
        let resp = self
            .client
            .change_password(&access, old_password, new_password)
            .await?;
        Ok(resp.message)
    }

    pub async fn request_password_reset(&self, email: &str) -> Result<String> {
        let email = email.trim();
        if email.is_empty() {
            return Err(anyhow!("请输入邮箱"));
        }
        if !email.contains('@') {
            return Err(anyhow!("请输入有效的邮箱地址"));
        }
        let resp = self.client.request_password_reset(email).await?;
        Ok(if resp.message.trim().is_empty() {
            "若该邮箱已注册，您将收到重置密码的邮件，请查收（含垃圾箱）。".to_string()
        } else {
            resp.message
        })
    }

    pub async fn health_check(&self) -> AuthHealthDto {
        let (session_authorized, session_mode) = {
            let guard = self.session.lock().unwrap();
            (
                guard
                    .as_ref()
                    .map(session_is_authorized)
                    .unwrap_or(false),
                guard.as_ref().map(|s| match s.mode {
                    AuthMode::Online => "online".to_string(),
                    AuthMode::Offline => "offline".to_string(),
                }),
            )
        };

        let offline_pubkey =
            offline::offline_pubkey_configured(&self.config.auth_dir);
        let mut dto = AuthHealthDto {
            auth_base_url: self.config.base_url.clone(),
            auth_reachable: false,
            auth_latency_ms: None,
            auth_status_code: None,
            auth_detail: None,
            offline_pubkey_configured: offline_pubkey,
            token_encryption: secrets::encryption_method().to_string(),
            session_authorized,
            session_mode,
        };

        match self.client.health().await {
            Ok((status, body, latency)) => {
                dto.auth_latency_ms = Some(latency);
                dto.auth_status_code = Some(status);
                dto.auth_reachable = (200..300).contains(&status);
                dto.auth_detail = Some(if body.len() > 200 {
                    format!("{}…", &body[..200])
                } else {
                    body
                });
            }
            Err(err) => {
                dto.auth_detail = Some(format!("{err:#}"));
            }
        }
        dto
    }

    pub async fn refresh_online(&self) -> Result<()> {
        let (primary, fallback) = {
            let guard = self.session.lock().unwrap();
            let session = guard
                .as_ref()
                .ok_or_else(|| anyhow!("未登录"))?;
            if session.mode != AuthMode::Online {
                return Err(anyhow!("当前为离线授权，无法刷新"));
            }
            let primary = refresh_bearer_token(session)
                .ok_or_else(|| anyhow!("无可用 token（缺少 access_token / refresh_token）"))?;
            let fallback = session
                .refresh_token
                .clone()
                .filter(|t| !t.is_empty() && *t != primary);
            (primary, fallback)
        };
        let result = match self.client.refresh(&primary).await {
            Ok(tokens) => self.apply_online_tokens(tokens).await,
            Err(primary_err) => {
                if let Some(rt) = fallback {
                    log::debug!(
                        "access 刷新失败，改用 refresh_token 重试: {primary_err:#}"
                    );
                    match self.client.refresh(&rt).await {
                        Ok(tokens) => self.apply_online_tokens(tokens).await,
                        Err(fallback_err) => Err(fallback_err),
                    }
                } else {
                    Err(primary_err)
                }
            }
        };
        match &result {
            Ok(()) => self.reset_consecutive_refresh_failures(),
            Err(err) => self.clear_online_session_after_fatal_refresh(err).await,
        }
        result
    }

    pub async fn logout(&self) -> Result<AuthStatusDto> {
        let access = {
            let guard = self.session.lock().unwrap();
            guard.as_ref().and_then(|s| s.access_token.clone())
        };
        if let Some(token) = access {
            let _ = self.client.logout(&token).await;
        }
        clear_session(&self.config.auth_dir)?;
        *self.session.lock().unwrap() = None;
        Ok(self.status_dto())
    }

    pub async fn redeem_offline_code(&self, code: &str) -> Result<AuthStatusDto> {
        let grant = offline::verify_offline_code(code, &self.config.auth_dir)?;
        let session = offline::session_from_offline_grant(grant, &self.config.app_id);
        save_session(&self.config.auth_dir, &session)?;
        *self.session.lock().unwrap() = Some(session);
        Ok(self.status_dto())
    }

    pub fn clear_offline(&self) -> Result<AuthStatusDto> {
        let mut guard = self.session.lock().unwrap();
        if let Some(session) = guard.as_ref() {
            if session.mode == AuthMode::Offline {
                clear_session(&self.config.auth_dir)?;
                *guard = None;
            }
        }
        Ok(self.status_dto())
    }

    /// Start background token refresh loop once after authorization.
    pub fn start_post_auth_services(&self, app: &AppHandle) -> Result<()> {
        if !self.is_authorized() {
            return Err(anyhow!("未授权"));
        }
        if self
            .background_started
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return Ok(());
        }
        self.start_token_refresh_loop(app.clone());
        Ok(())
    }

    pub fn show_login_shell(&self, app: &AppHandle) -> Result<()> {
        let _ = app.emit("auth://required", ());
        Ok(())
    }

    async fn apply_online_tokens(&self, tokens: TokenResponse) -> Result<()> {
        // Server-side deprecation signal — emit before any async work so
        // the UI can surface the warning even if /me below fails. The
        // event is idempotent: the frontend re-renders the banner on each
        // emit, and `deprecated == false` is the common path (no emit).
        if tokens.deprecated {
            self.notify_token_deprecated(tokens.warning.as_deref());
        }
        let profile = self.client.get_me(&tokens.access_token).await?;
        let user = profile.into_auth_user();
        if !user.account_status.allows_use() {
            return Err(anyhow!(account_status_message(&user.account_status)));
        }
        let expires_at = (Utc::now() + Duration::seconds(tokens.expires_in.max(0)))
            .to_rfc3339();
        let session = SessionFile {
            version: 1,
            mode: AuthMode::Online,
            app_id: self.config.app_id.clone(),
            access_token: Some(tokens.access_token),
            refresh_token: Some(tokens.refresh_token),
            expires_at: Some(expires_at),
            user: Some(user),
            offline: None,
        };
        save_session(&self.config.auth_dir, &session)?;
        *self.session.lock().unwrap() = Some(session);
        Ok(())
    }
}

fn account_status_message(status: &AccountStatus) -> String {
    match status {
        AccountStatus::Inactive => "账号待开通，请联系管理员".to_string(),
        AccountStatus::Suspended => "账号已停用".to_string(),
        AccountStatus::Active => String::new(),
    }
}

#[cfg(test)]
mod refresh_error_tests {
    use super::{is_non_recoverable_refresh_error, AuthApiError};
    use anyhow::anyhow;

    #[test]
    fn detects_http_401_from_refresh_endpoint() {
        let err: anyhow::Error = AuthApiError {
            status: 401,
            message: "Token expired".to_string(),
        }
        .into();
        assert!(is_non_recoverable_refresh_error(&err));
    }

    #[test]
    fn ignores_5xx_server_errors() {
        let err: anyhow::Error = AuthApiError {
            status: 504,
            message: "Gateway Timeout (body happened to mention: expired)".to_string(),
        }
        .into();
        assert!(!is_non_recoverable_refresh_error(&err));
    }

    #[test]
    fn ignores_transient_network_errors() {
        assert!(!is_non_recoverable_refresh_error(&anyhow!(
            "refresh request: connection timed out"
        )));
    }

    #[test]
    fn ignores_plain_string_errors_without_status() {
        // Old code matched on substrings like "Invalid or expired refresh
        // token". The new code requires a typed AuthApiError with status==401,
        // so a plain anyhow string never matches.
        assert!(!is_non_recoverable_refresh_error(&anyhow!(
            "Invalid or expired refresh token"
        )));
    }

    #[test]
    fn preserves_status_through_context_chain() {
        // anyhow::Error::downcast_ref walks the source chain, so a context-
        // wrapped AuthApiError is still detected.
        let api_err: anyhow::Error = AuthApiError {
            status: 401,
            message: "Unauthorized".to_string(),
        }
        .into();
        let chained = api_err.context("refresh request");
        assert!(is_non_recoverable_refresh_error(&chained));
    }
}

#[cfg(test)]
mod phone_validation_tests {
    use super::validate_phone_number;

    #[test]
    fn accepts_valid_cn_mobile() {
        assert!(validate_phone_number("13800138000").is_ok());
    }

    #[test]
    fn rejects_short_phone() {
        assert!(validate_phone_number("138001").is_err());
    }

    #[test]
    fn rejects_non_digit_phone() {
        assert!(validate_phone_number("1380013800a").is_err());
    }
}
