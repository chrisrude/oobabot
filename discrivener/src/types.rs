// we want to store 30 seconds of audio, 16-bit stereo PCM at 48kHz
// divided into 20ms chunks

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_with::serde_as;
use songbird::events::context_data;
use songbird::model::payload;

pub const AUDIO_CHANNELS: usize = 2;

pub const DISCORD_SAMPLES_PER_SECOND: usize = 48000;
pub const DISCORD_SAMPLES_PER_MILLISECOND: usize = DISCORD_SAMPLES_PER_SECOND / 1000;
pub const PERIOD_PER_PACKET_GROUP_MS: usize = 20;
pub const AUDIO_SAMPLES_PER_FRAME: usize =
    DISCORD_SAMPLES_PER_MILLISECOND * PERIOD_PER_PACKET_GROUP_MS;

pub const AUDIO_TO_RECORD_SECONDS: usize = 30;
pub const AUDIO_TO_RECORD_MILLISECONDS: usize = AUDIO_TO_RECORD_SECONDS * 1000;
pub const AUDIO_TO_RECORD_FRAMES: usize = AUDIO_TO_RECORD_MILLISECONDS / PERIOD_PER_PACKET_GROUP_MS;

pub const AUDIO_BUFFER_SIZE: usize =
    AUDIO_SAMPLES_PER_FRAME * AUDIO_TO_RECORD_FRAMES * AUDIO_CHANNELS;

pub type AudioSample = i16;
pub type AudioClip = Arc<Vec<AudioSample>>;
pub type UserId = u64;
pub type Ssrc = u32;

pub type AudioCallback = std::sync::Arc<dyn Fn(UserId, AudioClip) + Sync + Send>;

pub const WHISPER_SAMPLES_PER_SECOND: usize = 16000;
pub type WhisperAudioSample = f32;

/// These types shadow the ones in the songbird crate.
/// We need to do this because we want to serialize them,
/// for testing and debugging purposes.

#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
pub struct MySpeakingUpdateData {
    /// Whether this user is currently speaking.
    pub speaking: bool,
    /// ssrc ID of the user who has begun speaking.
    pub ssrc: u32,
}

impl MySpeakingUpdateData {
    pub fn from(other: &context_data::SpeakingUpdateData) -> Self {
        Self {
            speaking: other.speaking,
            ssrc: other.ssrc,
        }
    }
}

#[serde_as]
#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
pub struct MyVoiceData {
    /// Decoded audio from this packet.  The songbird version,
    /// VoiceData, uses an Option here.  We will just drop any
    /// updates that don't have audio, since we don't need them.
    /// This makes it easier to serialize.
    #[serde_as(as = "Vec<_>")]
    pub audio: Vec<i16>,
    pub ssrc: u32,
}

impl MyVoiceData {
    pub fn from(other: &context_data::VoiceData) -> Self {
        Self {
            audio: other.audio.clone().unwrap(),
            ssrc: other.packet.ssrc,
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
pub enum MyEventContext {
    /// Speaking state update, typically describing how another voice
    /// user is transmitting audio data. Clients must send at least one such
    /// packet to allow SSRC/UserID matching.
    SpeakingStateUpdate(payload::Speaking),
    /// Speaking state transition, describing whether a given source has started/stopped
    /// transmitting. This fires in response to a silent burst, or the first packet
    /// breaking such a burst.
    SpeakingUpdate(MySpeakingUpdateData),
    /// Opus audio packet, received from another stream.
    VoicePacket(MyVoiceData),
    /// Fired whenever a client disconnects.
    ClientDisconnect(payload::ClientDisconnect),
}

impl MyEventContext {
    pub fn from(other: &songbird::EventContext) -> Option<Self> {
        match other {
            songbird::EventContext::SpeakingStateUpdate(s) => {
                Some(Self::SpeakingStateUpdate(s.clone()))
            }
            songbird::EventContext::SpeakingUpdate(s) => {
                Some(Self::SpeakingUpdate(MySpeakingUpdateData::from(s)))
            }
            songbird::EventContext::VoicePacket(s) => {
                if s.audio.is_none() {
                    eprintln!(
                        "RTP packet, but audio is None. Driver may not be configured to decode."
                    );
                    return None;
                }
                if 0 == s.audio.as_ref().unwrap().len() {
                    eprintln!("RTP packet, but 0 bytes of audio. Packet received out-of-order.");
                    return None;
                }
                Some(Self::VoicePacket(MyVoiceData::from(s)))
            }
            songbird::EventContext::ClientDisconnect(s) => Some(Self::ClientDisconnect(s.clone())),
            _ => None,
        }
    }
}
