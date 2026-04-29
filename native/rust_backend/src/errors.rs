//! Error types for the native backend.

use std::fmt;

#[derive(Debug)]
pub enum NativeError {
    Config(String),
    Serialization(String),
    Transport(String),
    FrameBuild(String),
}

impl fmt::Display for NativeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            NativeError::Config(msg) => write!(f, "Config error: {msg}"),
            NativeError::Serialization(msg) => write!(f, "Serialization error: {msg}"),
            NativeError::Transport(msg) => write!(f, "Transport error: {msg}"),
            NativeError::FrameBuild(msg) => write!(f, "Frame build error: {msg}"),
        }
    }
}

impl std::error::Error for NativeError {}
