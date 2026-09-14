use std::path::Path;

use anyhow::{anyhow, Context, Result};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::Deserialize;

use super::config::DEFAULT_APP_ID;
use super::types::{AuthMode, OfflineGrant, SessionFile};

const LICENSE_PREFIX: &str = "AINEWS1-";

#[derive(Debug, Deserialize)]
struct OfflinePayload {
    v: u32,
    license_id: String,
    app_id: String,
    exp: i64,
    #[serde(default)]
    features: Vec<String>,
    #[serde(default)]
    issued_to: Option<String>,
}

fn embedded_public_key_hex() -> Option<&'static str> {
    option_env!("AINEWS_OFFLINE_PUBLIC_KEY_HEX").filter(|s| !s.is_empty())
}

pub fn offline_pubkey_configured(auth_dir: &Path) -> bool {
    if std::env::var("AINEWS_OFFLINE_PUBLIC_KEY_HEX")
        .ok()
        .is_some_and(|v| !v.trim().is_empty())
    {
        return true;
    }
    if auth_dir.join("offline_public_key.hex").is_file() {
        return true;
    }
    embedded_public_key_hex().is_some()
}

pub fn load_verifying_key(auth_dir: &Path) -> Result<VerifyingKey> {
    if let Ok(hex) = std::env::var("AINEWS_OFFLINE_PUBLIC_KEY_HEX") {
        let trimmed = hex.trim();
        if !trimmed.is_empty() {
            return verifying_key_from_hex(trimmed);
        }
    }
    let key_path = auth_dir.join("offline_public_key.hex");
    if key_path.is_file() {
        let hex = std::fs::read_to_string(&key_path).context("read offline public key")?;
        return verifying_key_from_hex(hex.trim());
    }
    if let Some(hex) = embedded_public_key_hex() {
        return verifying_key_from_hex(hex);
    }
    Err(anyhow!(
        "未配置离线验签公钥：设置 AINEWS_OFFLINE_PUBLIC_KEY_HEX、写入 {}，或在编译时注入公钥",
        key_path.display()
    ))
}

/// Re-verify a stored offline grant (detect tampering / expiry).
pub fn revalidate_stored_grant(grant: &OfflineGrant, auth_dir: &Path) -> Result<OfflineGrant> {
    let code = format!(
        "{LICENSE_PREFIX}{}.{}",
        grant.payload_b64, grant.signature_b64
    );
    verify_offline_code(&code, auth_dir)
}

pub fn grant_has_feature(grant: &OfflineGrant, feature: &str) -> bool {
    grant
        .features
        .iter()
        .any(|f| f == feature || f == "*")
}

fn verifying_key_from_hex(hex: &str) -> Result<VerifyingKey> {
    let bytes = hex
        .chars()
        .filter(|c| !c.is_whitespace())
        .collect::<String>();
    if bytes.len() != 64 {
        return Err(anyhow!("offline public key must be 64 hex chars (32 bytes)"));
    }
    let raw = (0..32)
        .map(|i| {
            u8::from_str_radix(&bytes[i * 2..i * 2 + 2], 16)
                .map_err(|e| anyhow!("invalid hex: {e}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let arr: [u8; 32] = raw
        .try_into()
        .map_err(|_| anyhow!("invalid key length"))?;
    VerifyingKey::from_bytes(&arr).map_err(|e| anyhow!("invalid ed25519 public key: {e}"))
}

/// Parse `NCLOUD1-<payload_b64>.<sig_b64>` and verify signature.
pub fn verify_offline_code(code: &str, auth_dir: &Path) -> Result<OfflineGrant> {
    let trimmed = code.trim();
    let rest = trimmed
        .strip_prefix(LICENSE_PREFIX)
        .ok_or_else(|| anyhow!("授权码须以 {LICENSE_PREFIX} 开头"))?;
    let (payload_b64, sig_b64) = rest
        .split_once('.')
        .ok_or_else(|| anyhow!("授权码格式无效，应为 {LICENSE_PREFIX}<payload>.<signature>"))?;

    let payload_bytes = URL_SAFE_NO_PAD
        .decode(payload_b64)
        .context("decode license payload")?;
    let sig_bytes = URL_SAFE_NO_PAD
        .decode(sig_b64)
        .context("decode license signature")?;

    let key = load_verifying_key(auth_dir)?;
    let sig_arr: [u8; 64] = sig_bytes
        .as_slice()
        .try_into()
        .map_err(|_| anyhow!("signature must be 64 bytes"))?;
    let signature = Signature::from_bytes(&sig_arr);
    key.verify(&payload_bytes, &signature)
        .map_err(|_| anyhow!("授权码签名无效"))?;

    let payload: OfflinePayload =
        serde_json::from_slice(&payload_bytes).context("parse license payload")?;
    if payload.v != 1 {
        return Err(anyhow!("不支持的授权码版本"));
    }
    if payload.app_id != DEFAULT_APP_ID {
        return Err(anyhow!("授权码 app_id 不匹配"));
    }
    let exp = DateTime::from_timestamp(payload.exp, 0)
        .ok_or_else(|| anyhow!("授权码过期时间无效"))?;
    if exp <= Utc::now() {
        return Err(anyhow!("授权码已过期"));
    }

    Ok(OfflineGrant {
        license_id: payload.license_id,
        issued_to: payload.issued_to,
        expires_at: exp.to_rfc3339(),
        features: if payload.features.is_empty() {
            vec!["desktop".to_string()]
        } else {
            payload.features
        },
        payload_b64: payload_b64.to_string(),
        signature_b64: sig_b64.to_string(),
    })
}

pub fn session_from_offline_grant(grant: OfflineGrant, app_id: &str) -> SessionFile {
    SessionFile {
        version: 1,
        mode: AuthMode::Offline,
        app_id: app_id.to_string(),
        access_token: None,
        refresh_token: None,
        expires_at: None,
        user: None,
        offline: Some(grant),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::Signer;
    use ed25519_dalek::SigningKey;

    #[test]
    fn roundtrip_offline_code() {
        let signing = SigningKey::from_bytes(&[7u8; 32]);
        let dir = std::env::temp_dir().join("niuclaude-auth-roundtrip");
        install_test_pubkey(&dir, &signing);

        let payload = serde_json::json!({
            "v": 1,
            "license_id": "lic_test",
            "app_id": "niuclaude",
            "exp": (Utc::now() + chrono::Duration::days(30)).timestamp(),
            "features": ["desktop"]
        });
        let payload_bytes = serde_json::to_vec(&payload).unwrap();
        let sig = signing.sign(&payload_bytes);
        let code = format!(
            "{LICENSE_PREFIX}{}.{}",
            URL_SAFE_NO_PAD.encode(&payload_bytes),
            URL_SAFE_NO_PAD.encode(sig.to_bytes())
        );
        let grant = verify_offline_code(&code, &dir).expect("verify");
        assert_eq!(grant.license_id, "lic_test");
    }

    fn test_key_hex(signing: &SigningKey) -> String {
        signing
            .verifying_key()
            .to_bytes()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }

    fn install_test_pubkey(dir: &Path, signing: &SigningKey) {
        std::fs::create_dir_all(dir).ok();
        std::fs::write(
            dir.join("offline_public_key.hex"),
            test_key_hex(signing),
        )
        .unwrap();
    }

    fn make_code(signing: &SigningKey, payload: serde_json::Value) -> String {
        let payload_bytes = serde_json::to_vec(&payload).unwrap();
        let sig = signing.sign(&payload_bytes);
        format!(
            "{LICENSE_PREFIX}{}.{}",
            URL_SAFE_NO_PAD.encode(&payload_bytes),
            URL_SAFE_NO_PAD.encode(sig.to_bytes())
        )
    }

    #[test]
    fn rejects_expired_offline_code() {
        let signing = SigningKey::from_bytes(&[8u8; 32]);
        let dir = std::env::temp_dir().join("niuclaude-auth-expired");
        install_test_pubkey(&dir, &signing);
        let payload = serde_json::json!({
            "v": 1,
            "license_id": "lic_exp",
            "app_id": "niuclaude",
            "exp": (Utc::now() - chrono::Duration::days(1)).timestamp(),
            "features": ["desktop"]
        });
        let err = verify_offline_code(&make_code(&signing, payload), &dir).unwrap_err();
        assert!(err.to_string().contains("过期"));
    }

    #[test]
    fn rejects_wrong_app_id() {
        let signing = SigningKey::from_bytes(&[9u8; 32]);
        let dir = std::env::temp_dir().join("niuclaude-auth-appid");
        install_test_pubkey(&dir, &signing);
        let payload = serde_json::json!({
            "v": 1,
            "license_id": "lic_bad",
            "app_id": "other",
            "exp": (Utc::now() + chrono::Duration::days(1)).timestamp(),
            "features": ["desktop"]
        });
        let err = verify_offline_code(&make_code(&signing, payload), &dir).unwrap_err();
        assert!(err.to_string().contains("app_id"));
    }

    #[test]
    fn revalidate_detects_tampered_payload() {
        let signing = SigningKey::from_bytes(&[10u8; 32]);
        let dir = std::env::temp_dir().join("niuclaude-auth-tamper");
        install_test_pubkey(&dir, &signing);
        let payload = serde_json::json!({
            "v": 1,
            "license_id": "lic_tamper",
            "app_id": "niuclaude",
            "exp": (Utc::now() + chrono::Duration::days(7)).timestamp(),
            "features": ["desktop"]
        });
        let grant = verify_offline_code(&make_code(&signing, payload), &dir).expect("ok");
        let mut bad = grant.clone();
        bad.payload_b64.push('x');
        assert!(revalidate_stored_grant(&bad, &dir).is_err());
    }
}
