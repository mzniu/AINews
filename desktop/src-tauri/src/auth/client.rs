use anyhow::{anyhow, Context, Result};
use serde::Serialize;

use super::config::AuthConfig;
use super::types::{
    BindPhoneRequest, CaptchaResponse, MessageResponse, PhoneLoginRequest,
    PhoneRegisterRequest, RegisterResponse, SendCodeResponse, SendPhoneCodeRequest,
    TokenResponse, UserProfileResponse,
};

/// Typed error for HTTP API failures. Carries the HTTP status code so that
/// callers can distinguish non-recoverable auth failures (401) from
/// transient server errors (5xx, network) without relying on substring
/// matching against the error message.
#[derive(Debug, Clone)]
pub struct AuthApiError {
    pub status: u16,
    pub message: String,
}

impl std::fmt::Display for AuthApiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "HTTP {}: {}", self.status, self.message)
    }
}

impl std::error::Error for AuthApiError {}

#[derive(Serialize)]
struct LoginBody<'a> {
    email: &'a str,
    password: &'a str,
    app_id: &'a str,
}

#[derive(Serialize)]
struct RegisterBody<'a> {
    email: &'a str,
    password: &'a str,
    app_id: &'a str,
}

#[derive(Serialize)]
struct AppIdBody<'a> {
    app_id: &'a str,
}

#[derive(Serialize)]
struct ChangePasswordBody<'a> {
    old_password: &'a str,
    new_password: &'a str,
}

#[derive(Serialize)]
struct ForgotPasswordBody<'a> {
    email: &'a str,
    app_id: &'a str,
}

fn format_validation_array(items: &[serde_json::Value]) -> String {
    let mut parts = Vec::new();
    for item in items {
        let msg = item.get("msg").and_then(|v| v.as_str()).unwrap_or("");
        let loc = item
            .get("loc")
            .and_then(|v| v.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|x| x.as_str())
                    .collect::<Vec<_>>()
                    .join(".")
            })
            .unwrap_or_default();
        let field = if loc.contains("password") {
            "密码"
        } else if loc.contains("email") {
            "邮箱"
        } else {
            ""
        };
        if field.is_empty() {
            if !msg.is_empty() {
                parts.push(msg.to_string());
            }
        } else {
            parts.push(format!("{field}：{msg}"));
        }
    }
    if parts.is_empty() {
        "请求参数无效".to_string()
    } else {
        parts.join("；")
    }
}

fn format_api_detail(detail: &serde_json::Value) -> String {
    if detail.is_array() {
        detail
            .as_array()
            .map(|a| format_validation_array(a))
            .unwrap_or_else(|| detail.to_string())
    } else if let Some(s) = detail.as_str() {
        s.to_string()
    } else {
        detail.to_string()
    }
}

pub struct AuthClient {
    http: reqwest::Client,
    pub config: AuthConfig,
}

impl AuthClient {
    pub fn new(config: AuthConfig) -> Result<Self> {
        let http = reqwest::Client::builder()
            .user_agent("AINews/1.0.1")
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .context("build auth http client")?;
        Ok(Self { http, config })
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}", self.config.base_url, path)
    }

    async fn api_error(res: reqwest::Response) -> anyhow::Error {
        let status = res.status().as_u16();
        let body = res.text().await.unwrap_or_default();
        let message = if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&body) {
            if let Some(detail) = parsed.get("detail") {
                format_api_detail(detail).to_string()
            } else if body.trim().starts_with('[') {
                match serde_json::from_str::<Vec<serde_json::Value>>(&body) {
                    Ok(arr) => format_validation_array(&arr).to_string(),
                    Err(_) => format!("HTTP {status}: {body}"),
                }
            } else {
                format!("HTTP {status}: {body}")
            }
        } else if body.trim().starts_with('[') {
            match serde_json::from_str::<Vec<serde_json::Value>>(&body) {
                Ok(arr) => format_validation_array(&arr).to_string(),
                Err(_) => format!("HTTP {status}: {body}"),
            }
        } else {
            format!("HTTP {status}: {body}")
        };
        AuthApiError { status, message }.into()
    }

    pub async fn register(&self, email: &str, password: &str) -> Result<RegisterResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/register"))
            .json(&RegisterBody {
                email,
                password,
                app_id: &self.config.app_id,
            })
            .send()
            .await
            .context("register request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse register response")
    }

    pub async fn login(&self, email: &str, password: &str) -> Result<TokenResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/login"))
            .json(&LoginBody {
                email,
                password,
                app_id: &self.config.app_id,
            })
            .send()
            .await
            .context("login request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse login response")
    }

    pub async fn refresh(&self, access_token: &str) -> Result<TokenResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/refresh"))
            .header("Authorization", format!("Bearer {access_token}"))
            .json(&AppIdBody {
                app_id: &self.config.app_id,
            })
            .send()
            .await
            .context("refresh request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse refresh response")
    }

    pub async fn logout(&self, access_token: &str) -> Result<()> {
        let res = self
            .http
            .post(self.url("/v1/auth/logout"))
            .header("Authorization", format!("Bearer {access_token}"))
            .json(&AppIdBody {
                app_id: &self.config.app_id,
            })
            .send()
            .await
            .context("logout request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        let _: MessageResponse = res.json().await.context("parse logout response")?;
        Ok(())
    }

    pub async fn health(&self) -> Result<(u16, String, u64)> {
        let started = std::time::Instant::now();
        let res = self
            .http
            .get(self.url("/health"))
            .send()
            .await
            .context("health request")?;
        let status = res.status().as_u16();
        let body = res.text().await.unwrap_or_default();
        let latency = started.elapsed().as_millis() as u64;
        log::debug!("auth health {status} in {latency}ms");
        Ok((status, body, latency))
    }

    pub async fn change_password(
        &self,
        access_token: &str,
        old_password: &str,
        new_password: &str,
    ) -> Result<MessageResponse> {
        let res = self
            .http
            .post(self.url("/v1/users/me/password"))
            .header("Authorization", format!("Bearer {access_token}"))
            .json(&ChangePasswordBody {
                old_password,
                new_password,
            })
            .send()
            .await
            .context("change_password request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json()
            .await
            .context("parse change_password response")
    }

    pub async fn request_password_reset(&self, email: &str) -> Result<MessageResponse> {
        let path = &self.config.forgot_password_path;
        let res = self
            .http
            .post(self.url(path))
            .json(&ForgotPasswordBody {
                email,
                app_id: &self.config.app_id,
            })
            .send()
            .await
            .context("forgot_password request")?;
        if res.status() == reqwest::StatusCode::NOT_FOUND {
            return Err(anyhow!(
                "账号服务暂未开通自助找回密码，请联系管理员重置密码。"
            ));
        }
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json()
            .await
            .context("parse forgot_password response")
    }

    pub async fn get_me(&self, access_token: &str) -> Result<UserProfileResponse> {
        let res = self
            .http
            .get(self.url("/v1/users/me"))
            .header("Authorization", format!("Bearer {access_token}"))
            .send()
            .await
            .context("get_me request")?;
        let status = res.status();
        let body = res.text().await.context("read user profile body")?;
        if !status.is_success() {
            return Err(anyhow!("HTTP {}: {}", status.as_u16(), body));
        }
        serde_json::from_str(&body).with_context(|| {
            format!(
                "parse user profile (HTTP {}): {}",
                status.as_u16(),
                body.chars().take(500).collect::<String>()
            )
        })
    }

    /// Fetch an SVG arithmetic captcha challenge from `GET /v1/auth/captcha`.
    /// Returns `Ok` with `{captcha_id, svg_data}` when the server has
    /// `CAPTCHA_ENABLED=true`. If the server has captcha disabled, this
    /// endpoint typically returns 404 — the caller should treat that as
    /// "captcha not required" and skip the modal.
    pub async fn get_captcha(&self) -> Result<CaptchaResponse> {
        let res = self
            .http
            .get(self.url("/v1/auth/captcha"))
            .send()
            .await
            .context("captcha request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse captcha response")
    }

    pub async fn send_phone_code(
        &self,
        phone: &str,
        purpose: &str,
        captcha_id: Option<&str>,
        captcha_code: Option<&str>,
    ) -> Result<SendCodeResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/send-code"))
            .json(&SendPhoneCodeRequest {
                phone: phone.to_string(),
                purpose: purpose.to_string(),
                captcha_id: captcha_id.map(str::to_string),
                captcha_code: captcha_code.map(str::to_string),
            })
            .send()
            .await
            .context("send phone code request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse send phone code response")
    }

    pub async fn phone_login(&self, phone: &str, code: &str) -> Result<TokenResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/phone/login"))
            .json(&PhoneLoginRequest {
                phone: phone.to_string(),
                code: code.to_string(),
                app_id: self.config.app_id.clone(),
            })
            .send()
            .await
            .context("phone login request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse phone login response")
    }

    pub async fn phone_register(&self, phone: &str, code: &str) -> Result<RegisterResponse> {
        let res = self
            .http
            .post(self.url("/v1/auth/phone/register"))
            .json(&PhoneRegisterRequest {
                phone: phone.to_string(),
                code: code.to_string(),
                app_id: self.config.app_id.clone(),
            })
            .send()
            .await
            .context("phone register request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        res.json().await.context("parse phone register response")
    }

    pub async fn bind_phone(
        &self,
        access_token: &str,
        phone: &str,
        code: &str,
    ) -> Result<UserProfileResponse> {
        let res = self
            .http
            .post(self.url("/v1/users/me/bind-phone"))
            .header("Authorization", format!("Bearer {access_token}"))
            .json(&BindPhoneRequest {
                phone: phone.to_string(),
                code: code.to_string(),
            })
            .send()
            .await
            .context("bind phone request")?;
        if !res.status().is_success() {
            return Err(Self::api_error(res).await);
        }
        let body = res.text().await.context("read bind phone response")?;
        serde_json::from_str(&body).with_context(|| {
            format!(
                "parse bind phone response: {}",
                body.chars().take(500).collect::<String>()
            )
        })
    }
}

#[cfg(test)]
mod phone_client_tests {
    use super::*;

    #[test]
    fn phone_login_body_serializes() {
        let body = PhoneLoginRequest {
            phone: "13800138000".to_string(),
            code: "123456".to_string(),
            app_id: "niuclaude".to_string(),
        };
        let json = serde_json::to_string(&body).unwrap();
        assert!(json.contains("13800138000"));
        assert!(json.contains("123456"));
        assert!(json.contains("niuclaude"));
    }
}
