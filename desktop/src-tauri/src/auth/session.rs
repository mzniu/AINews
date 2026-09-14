use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use super::secrets::{open, seal};
use super::types::{AuthMode, SessionFile};

pub fn session_path(auth_dir: &Path) -> std::path::PathBuf {
    auth_dir.join("session.json")
}

/// On-disk layout: tokens are sealed; legacy plain `access_token` is migrated on load.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct SessionOnDisk {
    version: u32,
    mode: AuthMode,
    app_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    access_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    refresh_token: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    access_token_sealed: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    refresh_token_sealed: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    expires_at: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    user: Option<super::types::AuthUser>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    offline: Option<super::types::OfflineGrant>,
}

impl SessionOnDisk {
    fn into_session(self) -> Result<SessionFile> {
        let access_token = if let Some(sealed) = self.access_token_sealed {
            Some(open(&sealed)?)
        } else {
            self.access_token
        };
        let refresh_token = if let Some(sealed) = self.refresh_token_sealed {
            Some(open(&sealed)?)
        } else {
            self.refresh_token
        };
        Ok(SessionFile {
            version: self.version,
            mode: self.mode,
            app_id: self.app_id,
            access_token,
            refresh_token,
            expires_at: self.expires_at,
            user: self.user,
            offline: self.offline,
        })
    }

    fn from_session(session: &SessionFile) -> Result<Self> {
        let (access_token_sealed, refresh_token_sealed) = if session.mode == AuthMode::Online {
            (
                session
                    .access_token
                    .as_deref()
                    .filter(|s| !s.is_empty())
                    .map(seal)
                    .transpose()?,
                session
                    .refresh_token
                    .as_deref()
                    .filter(|s| !s.is_empty())
                    .map(seal)
                    .transpose()?,
            )
        } else {
            (None, None)
        };
        Ok(Self {
            version: session.version,
            mode: session.mode,
            app_id: session.app_id.clone(),
            access_token: None,
            refresh_token: None,
            access_token_sealed,
            refresh_token_sealed,
            expires_at: session.expires_at.clone(),
            user: session.user.clone(),
            offline: session.offline.clone(),
        })
    }
}

pub fn load_session(auth_dir: &Path) -> Result<Option<SessionFile>> {
    let path = session_path(auth_dir);
    if !path.is_file() {
        return Ok(None);
    }
    let raw = fs::read_to_string(&path).context("read auth session")?;
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    let on_disk: SessionOnDisk = serde_json::from_str(trimmed).context("parse auth session")?;
    let session = on_disk.into_session()?;
    Ok(Some(session))
}

pub fn save_session(auth_dir: &Path, session: &SessionFile) -> Result<()> {
    fs::create_dir_all(auth_dir).context("create auth dir")?;
    let path = session_path(auth_dir);
    let on_disk = SessionOnDisk::from_session(session)?;
    let json = serde_json::to_string_pretty(&on_disk).context("serialize session")?;
    fs::write(&path, format!("{json}\n")).context("write auth session")?;
    Ok(())
}

pub fn clear_session(auth_dir: &Path) -> Result<()> {
    let path = session_path(auth_dir);
    if path.is_file() {
        fs::remove_file(&path).context("remove auth session")?;
    }
    Ok(())
}

pub fn session_is_authorized(session: &SessionFile) -> bool {
    match session.mode {
        AuthMode::Online => {
            if let Some(user) = &session.user {
                if !user.account_status.allows_use() {
                    return false;
                }
            }
            if let Some(exp) = &session.expires_at {
                if let Ok(dt) = DateTime::parse_from_rfc3339(exp) {
                    return dt > Utc::now();
                }
            }
            session.access_token.as_ref().is_some_and(|t| !t.is_empty())
        }
        AuthMode::Offline => session.offline.as_ref().is_some_and(|o| {
            DateTime::parse_from_rfc3339(&o.expires_at)
                .map(|dt| dt > Utc::now())
                .unwrap_or(false)
        }),
    }
}

pub fn access_needs_refresh(session: &SessionFile, skew_secs: i64) -> bool {
    if session.mode != AuthMode::Online {
        return false;
    }
    let Some(exp) = &session.expires_at else {
        return true;
    };
    let Ok(dt) = DateTime::parse_from_rfc3339(exp) else {
        return true;
    };
    let refresh_at = dt - chrono::Duration::seconds(skew_secs);
    Utc::now() >= refresh_at
}

/// Bearer token for `POST /v1/auth/refresh` — use refresh_token once access is expired.
pub fn refresh_bearer_token(session: &SessionFile) -> Option<String> {
    if session.mode != AuthMode::Online {
        return None;
    }
    let access = session.access_token.clone().filter(|t| !t.is_empty())?;
    let refresh = session
        .refresh_token
        .clone()
        .filter(|t| !t.is_empty());
    if access_needs_refresh(session, 0) {
        return refresh.or(Some(access));
    }
    Some(access)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::types::{AuthMode, AuthUser, AccountStatus};

    fn online_session(expires_at: &str, refresh: Option<&str>) -> SessionFile {
        SessionFile {
            version: 1,
            mode: AuthMode::Online,
            app_id: "niuclaude".to_string(),
            access_token: Some("access-abc".to_string()),
            refresh_token: refresh.map(str::to_string),
            expires_at: Some(expires_at.to_string()),
            user: Some(AuthUser {
                user_id: "u1".to_string(),
                email: "u@example.com".to_string(),
                phone: None,
                nickname: None,
                account_status: AccountStatus::Active,
            }),
            offline: None,
        }
    }

    #[test]
    fn refresh_bearer_uses_access_while_valid() {
        let exp = (Utc::now() + chrono::Duration::hours(2)).to_rfc3339();
        let session = online_session(&exp, Some("refresh-xyz"));
        assert_eq!(
            refresh_bearer_token(&session).as_deref(),
            Some("access-abc")
        );
    }

    #[test]
    fn refresh_bearer_uses_refresh_token_when_expired() {
        let exp = (Utc::now() - chrono::Duration::hours(1)).to_rfc3339();
        let session = online_session(&exp, Some("refresh-xyz"));
        assert_eq!(
            refresh_bearer_token(&session).as_deref(),
            Some("refresh-xyz")
        );
    }
}
