use anyhow::{Context, Result};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;

const PREFIX_DPAPI: &str = "dpapi:";
const PREFIX_PLAIN: &str = "plain:";

/// How tokens are sealed on disk for this platform.
pub fn encryption_method() -> &'static str {
    #[cfg(windows)]
    {
        "dpapi"
    }
    #[cfg(not(windows))]
    {
        "plain"
    }
}

pub fn seal(plain: &str) -> Result<String> {
    if plain.is_empty() {
        return Ok(String::new());
    }
    #[cfg(windows)]
    {
        let protected = dpapi_protect(plain.as_bytes())?;
        Ok(format!(
            "{PREFIX_DPAPI}{}",
            URL_SAFE_NO_PAD.encode(protected)
        ))
    }
    #[cfg(not(windows))]
    {
        Ok(format!(
            "{PREFIX_PLAIN}{}",
            URL_SAFE_NO_PAD.encode(plain.as_bytes())
        ))
    }
}

pub fn open(sealed: &str) -> Result<String> {
    if sealed.is_empty() {
        return Ok(String::new());
    }
    if let Some(b64) = sealed.strip_prefix(PREFIX_DPAPI) {
        #[cfg(windows)]
        {
            let bytes = URL_SAFE_NO_PAD
                .decode(b64)
                .context("decode dpapi blob")?;
            let plain = dpapi_unprotect(&bytes)?;
            return String::from_utf8(plain).context("dpapi plaintext utf8");
        }
        #[cfg(not(windows))]
        {
            return Err(anyhow!("无法在非 Windows 环境解密 DPAPI 令牌"));
        }
    }
    if let Some(b64) = sealed.strip_prefix(PREFIX_PLAIN) {
        let bytes = URL_SAFE_NO_PAD
            .decode(b64)
            .context("decode plain blob")?;
        return String::from_utf8(bytes).context("plain token utf8");
    }
    // Legacy M1–M3: tokens stored as raw strings in session.json
    Ok(sealed.to_string())
}

#[cfg(windows)]
fn dpapi_protect(data: &[u8]) -> Result<Vec<u8>> {
    use windows::Win32::Foundation::{LocalFree, HLOCAL};
    use windows::Win32::Security::Cryptography::{
        CryptProtectData, CRYPT_INTEGER_BLOB, CRYPTPROTECT_UI_FORBIDDEN,
    };

    unsafe {
        let mut in_blob = CRYPT_INTEGER_BLOB {
            cbData: data.len() as u32,
            pbData: data.as_ptr() as *mut u8,
        };
        let mut out_blob = CRYPT_INTEGER_BLOB::default();
        CryptProtectData(
            &mut in_blob,
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut out_blob,
        )
        .ok()
        .context("CryptProtectData")?;
        let out =
            std::slice::from_raw_parts(out_blob.pbData, out_blob.cbData as usize).to_vec();
        let _ = LocalFree(HLOCAL(out_blob.pbData as _));
        Ok(out)
    }
}

#[cfg(windows)]
fn dpapi_unprotect(data: &[u8]) -> Result<Vec<u8>> {
    use windows::Win32::Foundation::{LocalFree, HLOCAL};
    use windows::Win32::Security::Cryptography::{
        CryptUnprotectData, CRYPT_INTEGER_BLOB, CRYPTPROTECT_UI_FORBIDDEN,
    };

    unsafe {
        let mut in_blob = CRYPT_INTEGER_BLOB {
            cbData: data.len() as u32,
            pbData: data.as_ptr() as *mut u8,
        };
        let mut out_blob = CRYPT_INTEGER_BLOB::default();
        CryptUnprotectData(
            &mut in_blob,
            None,
            None,
            None,
            None,
            CRYPTPROTECT_UI_FORBIDDEN,
            &mut out_blob,
        )
        .ok()
        .context("CryptUnprotectData")?;
        let out =
            std::slice::from_raw_parts(out_blob.pbData, out_blob.cbData as usize).to_vec();
        let _ = LocalFree(HLOCAL(out_blob.pbData as _));
        Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seal_roundtrip() {
        let sample = "test-access-token-value";
        let sealed = seal(sample).expect("seal");
        assert!(sealed.starts_with(PREFIX_DPAPI) || sealed.starts_with(PREFIX_PLAIN));
        let opened = open(&sealed).expect("open");
        assert_eq!(opened, sample);
    }
}
