use std::path::PathBuf;

pub const DEFAULT_AUTH_BASE_URL: &str = "https://auth.jiamenkou.online";
pub const DEFAULT_CLOUD_API_BASE: &str = "https://ainews-api.xiaoniuliaoai.com";
pub const DEFAULT_APP_ID: &str = "app_ai_news";
/// Default path for password-reset email requests (override via env if your UserCenter uses another route).
pub const DEFAULT_FORGOT_PASSWORD_PATH: &str = "/v1/auth/forgot-password";

#[derive(Clone)]
pub struct AuthConfig {
    pub base_url: String,
    pub app_id: String,
    pub forgot_password_path: String,
    pub auth_dir: PathBuf,
}

impl AuthConfig {
    pub fn from_data_dir(data_dir: &PathBuf) -> Self {
        let base_url = std::env::var("AINEWS_AUTH_BASE_URL")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| DEFAULT_AUTH_BASE_URL.to_string());
        let app_id = std::env::var("AINEWS_AUTH_APP_ID")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| DEFAULT_APP_ID.to_string());
        let forgot_password_path = std::env::var("AINEWS_AUTH_FORGOT_PASSWORD_PATH")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| DEFAULT_FORGOT_PASSWORD_PATH.to_string());
        let forgot_password_path = if forgot_password_path.starts_with('/') {
            forgot_password_path
        } else {
            format!("/{forgot_password_path}")
        };
        let auth_dir = data_dir.join("auth");
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            app_id,
            forgot_password_path,
            auth_dir,
        }
    }

    pub fn cloud_api_base_url() -> String {
        std::env::var("AINEWS_CLOUD_API_BASE")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| DEFAULT_CLOUD_API_BASE.to_string())
            .trim_end_matches('/')
            .to_string()
    }
}
