//! Remembered email/password storage for the email login form.
//!
//! When the user ticks "记住密码" on the email login form, the credentials
//! are sealed with DPAPI (Windows) / base64 (other platforms) via
//! [`super::secrets`] and persisted to `auth_dir/remembered_credentials.json`
//! keyed by email. Multiple accounts can be remembered simultaneously; the
//! frontend auto-fills the password field when the user types a remembered
//! email.
//!
//! The file lives next to `session.json` under the user's `data_dir`, so it
//! inherits the same OS-level access isolation as the session file itself.
//! The passwords inside are sealed, not plaintext — even if the file is
//! exfiltrated, DPAPI's user-key binding prevents decryption on another
//! machine or by another user.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};

use super::secrets;

const FILENAME: &str = "remembered_credentials.json";
const CURRENT_VERSION: u32 = 1;

#[derive(Debug, Serialize, Deserialize, Default)]
pub struct RememberedCredentialsFile {
    pub version: u32,
    /// email → sealed password (prefix-tagged by [`secrets::seal`]).
    pub entries: BTreeMap<String, String>,
}

impl RememberedCredentialsFile {
    pub fn path_for(auth_dir: &Path) -> PathBuf {
        auth_dir.join(FILENAME)
    }

    /// Load the file from disk. Returns an empty struct on any read/parse
    /// error — the user simply loses the remembered entries rather than
    /// being locked out of the login form.
    pub fn load(auth_dir: &Path) -> Self {
        let path = Self::path_for(auth_dir);
        if !path.is_file() {
            return Self::default();
        }
        let data = match std::fs::read_to_string(&path) {
            Ok(s) => s,
            Err(_) => return Self::default(),
        };
        match serde_json::from_str::<Self>(&data) {
            Ok(mut file) => {
                if file.version == 0 {
                    file.version = CURRENT_VERSION;
                }
                file
            }
            Err(_) => Self::default(),
        }
    }

    pub fn save(&self, auth_dir: &Path) -> Result<()> {
        let path = Self::path_for(auth_dir);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("create auth dir for remembered credentials")?;
        }
        let json = serde_json::to_string_pretty(self)
            .context("serialize remembered credentials")?;
        std::fs::write(&path, json).context("write remembered credentials file")
    }

    /// Seal and store the password for `email`. Overwrites any existing
    /// entry for the same email.
    pub fn set_entry(&mut self, email: &str, password: &str) -> Result<()> {
        let sealed = secrets::seal(password)?;
        self.entries.insert(email.to_string(), sealed);
        Ok(())
    }

    pub fn remove_entry(&mut self, email: &str) -> bool {
        self.entries.remove(email).is_some()
    }

    pub fn clear(&mut self) {
        self.entries.clear();
    }

    /// Unseal and return the password for `email`, or `None` if there's no
    /// entry or unsealing failed (e.g. DPAPI key changed since the entry
    /// was written — the user just re-types the password).
    pub fn get_password(&self, email: &str) -> Option<String> {
        let sealed = self.entries.get(email)?;
        secrets::open(sealed).ok()
    }

    pub fn emails(&self) -> Vec<String> {
        self.entries.keys().cloned().collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir() -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "niuclaude-remembered-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn set_and_get_roundtrip() {
        let dir = temp_dir();
        let mut file = RememberedCredentialsFile::default();
        file.set_entry("user@example.com", "hunter2").unwrap();
        file.save(&dir).unwrap();

        let loaded = RememberedCredentialsFile::load(&dir);
        assert_eq!(
            loaded.get_password("user@example.com").as_deref(),
            Some("hunter2")
        );
        std::fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn remove_entry_clears() {
        let mut file = RememberedCredentialsFile::default();
        file.set_entry("a@x.com", "pw").unwrap();
        assert!(file.remove_entry("a@x.com"));
        assert_eq!(file.get_password("a@x.com"), None);
    }

    #[test]
    fn list_emails_returns_sorted_keys() {
        let mut file = RememberedCredentialsFile::default();
        file.set_entry("b@x.com", "1").unwrap();
        file.set_entry("a@x.com", "2").unwrap();
        assert_eq!(file.emails(), vec!["a@x.com".to_string(), "b@x.com".to_string()]);
    }
}
