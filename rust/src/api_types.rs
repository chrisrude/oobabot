use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[pyclass]
#[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Hash, Debug, Default, Serialize, Deserialize)]
pub struct TranscribedMessage {
    /// absolute time this message was received,
    /// as reported by the Discord server
    /// (NOT the local machine time)
    pub timestamp: u64,

    /// Discord user id of the speaker
    pub user_id: u64,

    /// One or more text segments extracted
    /// from the audio.
    pub text_segments: Vec<TextSegment>,

    /// conversion metric: total time of source
    /// audio which lead to this message
    pub audio_duration_ms: u32,

    /// total time spent converting this audio
    /// to text
    pub processing_time_ms: u32,
}

#[pyclass]
#[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Hash, Debug, Default, Serialize, Deserialize)]
pub struct TextSegment {
    pub text: String,

    /// When the audio for this segment started.
    /// Time is relative to when the Message was received.
    pub start_offset_ms: u32,

    /// When the audio for this segment ended.
    /// Time is relative to when the Message was received.
    pub end_offset_ms: u32,
}
