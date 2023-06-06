use serde::{Deserialize, Serialize};
use serde_with::serde_as;

#[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Hash, Debug, Default, Serialize, Deserialize)]
pub struct UserJoinData {
    pub user_id: u64,
    pub joined: bool,
}

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

#[serde_as]
#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialOrd, PartialEq, Serialize)]
pub struct ConnectData {
    /// ID of the voice channel being joined, if it is known.
    ///
    /// If this is available, then this can be used to reconnect/renew
    /// a voice session via thew gateway.
    pub channel_id: Option<u64>,
    /// ID of the target voice channel's parent guild.
    pub guild_id: u64,
    /// Unique string describing this session for validation/authentication purposes.
    pub session_id: String,
    /// The domain name of Discord's voice/TURN server.
    ///
    /// With the introduction of Discord's automatic voice server selection,
    /// this is no longer guaranteed to match a server's settings. This field
    /// may be useful if you need/wish to move your voice connection to a node/shard
    /// closer to Discord.
    pub server: String,
    /// The [RTP SSRC] *("Synchronisation source")* assigned by the voice server
    /// for the duration of this call.
    ///
    /// All packets sent will use this SSRC, which is not related to the sender's User
    /// ID. These are usually allocated sequentially by Discord, following on from
    /// a random starting SSRC.
    ///
    /// [RTP SSRC]: https://tools.ietf.org/html/rfc3550#section-3
    pub ssrc: u32,
}

#[serde_as]
#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialOrd, PartialEq, Serialize)]
pub enum DisconnectKind {
    /// The voice driver failed to connect to the server.
    ///
    /// This requires explicit handling at the gateway level
    /// to either reconnect or fully disconnect.
    Connect,
    /// The voice driver failed to reconnect to the server.
    ///
    /// This requires explicit handling at the gateway level
    /// to either reconnect or fully disconnect.
    Reconnect,
    /// The voice connection was terminated mid-session by either
    /// the user or Discord.
    ///
    /// If `reason == None`, then this disconnection is either
    /// a full disconnect or a user-requested channel change.
    /// Otherwise, this is likely a session expiry (requiring user
    /// handling to fully disconnect/reconnect).
    Runtime,
}

/// The reason that a voice connection failed.
#[serde_as]
#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialOrd, PartialEq, Serialize)]
pub enum DisconnectReason {
    /// This (re)connection attempt was dropped due to another request.
    AttemptDiscarded,
    /// Songbird had an internal error.
    ///
    /// This should never happen; if this is ever seen, raise an issue with logs.
    Internal,
    /// A host-specific I/O error caused the fault; this is likely transient, and
    /// should be retried some time later.
    Io,
    /// Songbird and Discord disagreed on the protocol used to establish a
    /// voice connection.
    ///
    /// This should never happen; if this is ever seen, raise an issue with logs.
    ProtocolViolation,
    /// A voice connection was not established in the specified time.
    TimedOut,
    /// The Websocket connection was closed by Discord.
    ///
    /// This typically indicates that the voice session has expired,
    /// and a new one needs to be requested via the gateway.
    WsClosed(Option<u32>),
}

#[serde_as]
#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialOrd, PartialEq, Serialize)]
pub struct DisconnectData {
    /// The location that a voice connection was terminated.
    pub kind: DisconnectKind,
    /// The cause of any connection failure.
    ///
    /// If `None`, then this disconnect was requested by the user in some way
    /// (i.e., leaving or changing voice channels).
    pub reason: Option<DisconnectReason>,
    /// ID of the voice channel being joined, if it is known.
    ///
    /// If this is available, then this can be used to reconnect/renew
    /// a voice session via thew gateway.
    pub channel_id: Option<u64>,
    /// ID of the target voice channel's parent guild.
    pub guild_id: u64,
    /// Unique string describing this session for validation/authentication purposes.
    pub session_id: String,
}

#[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Hash, Debug, Serialize, Deserialize)]
pub enum VoiceChannelEvent {
    UserJoin(UserJoinData),
    TranscribedMessage(TranscribedMessage),
    Connect(ConnectData),
    Reconnect(ConnectData),
    Disconnect(DisconnectData),
}
