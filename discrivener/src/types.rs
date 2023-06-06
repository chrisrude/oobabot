// we want to store 30 seconds of audio, 16-bit stereo PCM at 48kHz
// divided into 20ms chunks

use std::sync::Arc;

use serde::{Deserialize, Serialize};
use serde_with::serde_as;
use songbird::events::context_data;
use songbird::model::payload;

use crate::api_types;

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

impl api_types::ConnectData {
    pub fn from(other: &songbird::events::context_data::ConnectData) -> Self {
        Self {
            channel_id: if let Some(id) = other.channel_id {
                Some(id.0)
            } else {
                None
            },
            guild_id: other.guild_id.0,
            session_id: other.session_id.clone().to_string(),
            server: other.server.clone().to_string(),
            ssrc: other.ssrc,
        }
    }
}

impl api_types::DisconnectKind {
    pub fn from(other: &songbird::events::context_data::DisconnectKind) -> Self {
        match other {
            songbird::events::context_data::DisconnectKind::Connect => Self::Connect,
            songbird::events::context_data::DisconnectKind::Reconnect => Self::Reconnect,
            songbird::events::context_data::DisconnectKind::Runtime => Self::Runtime,
            _ => panic!("Unknown disconnect kind: {:?}", other),
        }
    }
}

impl api_types::DisconnectReason {
    pub fn from(other: &songbird::events::context_data::DisconnectReason) -> Self {
        match other {
            songbird::events::context_data::DisconnectReason::AttemptDiscarded => {
                Self::AttemptDiscarded
            }
            songbird::events::context_data::DisconnectReason::Internal => Self::Internal,
            songbird::events::context_data::DisconnectReason::Io => Self::Io,
            songbird::events::context_data::DisconnectReason::ProtocolViolation => {
                Self::ProtocolViolation
            }
            songbird::events::context_data::DisconnectReason::TimedOut => Self::TimedOut,
            songbird::events::context_data::DisconnectReason::WsClosed(code) => {
                if code.is_none() {
                    Self::WsClosed(None)
                } else {
                    Self::WsClosed(Some(code.unwrap() as u32))
                }
            }
            _ => panic!("Unknown disconnect reason: {:?}", other),
        }
    }
}

impl api_types::DisconnectData {
    pub fn from(other: &songbird::events::context_data::DisconnectData) -> Self {
        Self {
            kind: api_types::DisconnectKind::from(&other.kind),
            reason: if let Some(reason) = &other.reason {
                Some(api_types::DisconnectReason::from(reason))
            } else {
                None
            },
            channel_id: if let Some(id) = other.channel_id {
                Some(id.0)
            } else {
                None
            },
            guild_id: other.guild_id.0,
            session_id: other.session_id.clone().to_string(),
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
    /// Fires when this driver successfully connects to a voice channel.
    DriverConnect(api_types::ConnectData),
    /// Fires when this driver successfully reconnects after a network error.
    DriverReconnect(api_types::ConnectData),
    /// Fires when this driver fails to connect to, or drops from, a voice channel.
    DriverDisconnect(api_types::DisconnectData),
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
            songbird::EventContext::DriverConnect(connect_data) => Some(Self::DriverConnect(
                api_types::ConnectData::from(connect_data),
            )),
            songbird::EventContext::DriverReconnect(reconnect_data) => Some(Self::DriverConnect(
                api_types::ConnectData::from(reconnect_data),
            )),
            songbird::EventContext::DriverDisconnect(disconnect_data) => Some(
                Self::DriverDisconnect(api_types::DisconnectData::from(disconnect_data)),
            ),
            _ => None,
        }
    }
}
