use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AuthMode {
    Online,
    Offline,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AccountStatus {
    Inactive,
    Active,
    Suspended,
}

impl AccountStatus {
    pub fn parse(s: &str) -> Self {
        match s {
            "active" => Self::Active,
            "suspended" => Self::Suspended,
            _ => Self::Inactive,
        }
    }

    pub fn allows_use(&self) -> bool {
        matches!(self, Self::Active)
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Active => "active",
            Self::Inactive => "inactive",
            Self::Suspended => "suspended",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthUser {
    pub user_id: String,
    pub email: String,
    pub phone: Option<String>,
    pub nickname: Option<String>,
    pub account_status: AccountStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OfflineGrant {
    pub license_id: String,
    pub issued_to: Option<String>,
    pub expires_at: String,
    pub features: Vec<String>,
    pub payload_b64: String,
    pub signature_b64: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionFile {
    pub version: u32,
    pub mode: AuthMode,
    pub app_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub access_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub refresh_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expires_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub user: Option<AuthUser>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub offline: Option<OfflineGrant>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenResponse {
    pub access_token: String,
    #[serde(default = "default_bearer")]
    pub token_type: String,
    pub expires_in: i64,
    pub refresh_token: String,
    /// Server-side flag indicating the token grant is deprecated
    /// (e.g. email login being phased out). When `true`, the server
    /// may also populate `warning` with a human-readable message.
    /// Defaults to `false` for older servers that don't send the field.
    #[serde(default)]
    pub deprecated: bool,
    /// Optional human-readable deprecation warning from the server.
    /// Present only when `deprecated == true` (typically). Defaults to
    /// `None` when the server omits the field.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub warning: Option<String>,
}

fn default_bearer() -> String {
    "bearer".to_string()
}

#[derive(Debug, Deserialize)]
pub struct UserProfileResponse {
    pub user_id: String,
    /// Phone-only accounts may have `email: null` per UserCenter OpenAPI.
    #[serde(default)]
    pub email: Option<String>,
    #[serde(default)]
    pub phone: Option<String>,
    #[serde(default)]
    pub nickname: Option<String>,
    #[serde(default)]
    pub avatar_url: Option<String>,
    pub account_status: AccountStatus,
    #[serde(default)]
    pub created_at: Option<String>,
}

impl UserProfileResponse {
    pub fn into_auth_user(self) -> AuthUser {
        AuthUser {
            user_id: self.user_id,
            email: self.email.unwrap_or_default(),
            phone: self.phone,
            nickname: self.nickname,
            account_status: self.account_status,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct RegisterResponse {
    pub user_id: String,
    pub account_status: String,
    #[serde(default)]
    pub message: Option<String>,
    pub access_token: Option<String>,
    pub refresh_token: Option<String>,
    pub expires_in: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct MessageResponse {
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct SendPhoneCodeRequest {
    pub phone: String,
    pub purpose: String,
    /// Optional captcha fields — required when the server has
    /// `CAPTCHA_ENABLED=true`. The client fetches these via
    /// `GET /v1/auth/captcha` and surfaces a modal so the user can solve
    /// the arithmetic challenge before send-code is dispatched.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub captcha_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub captcha_code: Option<String>,
}

/// SVG arithmetic captcha challenge issued by `GET /v1/auth/captcha`.
/// `svg_data` is rendered inline (it's a self-contained `<svg>` document);
/// `captcha_id` is echoed back on the send-code call so the server can
/// validate the answer against the challenge it issued.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CaptchaResponse {
    pub captcha_id: String,
    pub svg_data: String,
}

#[derive(Debug, Serialize)]
pub struct PhoneRegisterRequest {
    pub phone: String,
    pub code: String,
    pub app_id: String,
}

#[derive(Debug, Serialize)]
pub struct PhoneLoginRequest {
    pub phone: String,
    pub code: String,
    pub app_id: String,
}

#[derive(Debug, Serialize)]
pub struct BindPhoneRequest {
    pub phone: String,
    pub code: String,
}

#[derive(Debug, Deserialize)]
pub struct SendCodeResponse {
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthStatusDto {
    pub authorized: bool,
    pub mode: Option<String>,
    pub email: Option<String>,
    pub phone: Option<String>,
    pub account_status: Option<String>,
    pub offline_expires_at: Option<String>,
    pub auth_base_url: String,
    pub message: Option<String>,
    /// Offline license feature flags (e.g. `desktop`, `weixin`); online sessions omit this.
    pub features: Option<Vec<String>>,
    /// `dpapi` on Windows, `plain` on other platforms when tokens are stored.
    pub token_encryption: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthHealthDto {
    pub auth_base_url: String,
    pub auth_reachable: bool,
    pub auth_latency_ms: Option<u64>,
    pub auth_status_code: Option<u16>,
    pub auth_detail: Option<String>,
    pub offline_pubkey_configured: bool,
    pub token_encryption: String,
    pub session_authorized: bool,
    pub session_mode: Option<String>,
}

#[cfg(test)]
mod user_profile_response_tests {
    use super::*;

    #[test]
    fn parses_phone_only_profile_with_null_email() {
        let json = r#"{
            "user_id": "u-phone-1",
            "email": null,
            "phone": "18205922861",
            "nickname": null,
            "avatar_url": null,
            "account_status": "active",
            "created_at": "2026-07-05T06:00:00Z"
        }"#;
        let profile: UserProfileResponse = serde_json::from_str(json).unwrap();
        assert_eq!(profile.user_id, "u-phone-1");
        assert!(profile.email.is_none());
        assert_eq!(profile.phone.as_deref(), Some("18205922861"));
        assert_eq!(profile.account_status, AccountStatus::Active);
        let user = profile.into_auth_user();
        assert!(user.email.is_empty());
        assert_eq!(user.phone.as_deref(), Some("18205922861"));
    }
}

#[cfg(test)]
mod phone_type_tests {
    use super::*;

    #[test]
    fn auth_user_can_carry_phone() {
        let user = AuthUser {
            user_id: "u1".to_string(),
            email: "a@b.com".to_string(),
            phone: Some("13800138000".to_string()),
            nickname: None,
            account_status: AccountStatus::Active,
        };
        assert_eq!(user.phone.as_deref(), Some("13800138000"));
    }
}

#[cfg(test)]
mod token_response_deprecated_tests {
    use super::*;

    #[test]
    fn parses_deprecated_and_warning_from_server_json() {
        let json = r#"{
            "access_token": "at",
            "token_type": "bearer",
            "expires_in": 7200,
            "refresh_token": "rt",
            "deprecated": true,
            "warning": "Email login is being phased out; please re-login with phone."
        }"#;
        let resp: TokenResponse = serde_json::from_str(json).unwrap();
        assert!(resp.deprecated);
        assert_eq!(
            resp.warning.as_deref(),
            Some("Email login is being phased out; please re-login with phone.")
        );
    }

    #[test]
    fn defaults_deprecated_false_and_warning_none_when_omitted() {
        // Older servers don't send `deprecated` / `warning`. serde defaults
        // must keep deserialization working without surfacing a false
        // positive deprecation banner.
        let json = r#"{
            "access_token": "at",
            "token_type": "bearer",
            "expires_in": 7200,
            "refresh_token": "rt"
        }"#;
        let resp: TokenResponse = serde_json::from_str(json).unwrap();
        assert!(!resp.deprecated, "deprecated must default to false");
        assert!(resp.warning.is_none(), "warning must default to None");
    }

    #[test]
    fn ignores_unknown_extra_fields() {
        // Forward-compat: if the server adds more fields later, serde
        // (default lenient mode — no `deny_unknown_fields`) must not fail.
        let json = r#"{
            "access_token": "at",
            "token_type": "bearer",
            "expires_in": 7200,
            "refresh_token": "rt",
            "deprecated": false,
            "future_field": "ignored"
        }"#;
        let resp: TokenResponse = serde_json::from_str(json).unwrap();
        assert!(!resp.deprecated);
        assert!(resp.warning.is_none());
    }
}
