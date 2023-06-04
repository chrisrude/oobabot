/// Manages multiple buffers for each user who is speaking.
/// Tracks when users have stopped speaking, and fires a callback.
use std::collections::HashMap;
use std::io::Write;
use std::sync::Arc;
use std::sync::Mutex;

use crate::types;
use crate::voice_buffer;

pub const MAX_NUM_SPEAKING_PARTICIPANTS: usize = 10;

pub struct PacketHandler {
    // we want to store a VoiceBuffer for each participant who is
    // talking simultaneously. We can use the SSRC to identify each
    // participant.
    //
    // We can do things like eagerly allocate a number of buffers,
    // so that we don't have to run an allocation from the packet
    // handler thread.
    ssrc_to_user_voice_data: Arc<Mutex<HashMap<types::Ssrc, voice_buffer::VoiceBufferForUser>>>,

    audio_complete_callback: types::AudioCallback,

    maybe_log_file_mutex: Option<Arc<Mutex<std::fs::File>>>,
}

impl PacketHandler {
    pub fn new(
        audio_complete_callback: types::AudioCallback,
        dump_everything_to_a_file: Option<String>,
    ) -> Self {
        let mut maybe_log_file_mutex = None;
        if let Some(everything_file) = dump_everything_to_a_file {
            let log_file = std::fs::File::create(everything_file).unwrap();
            maybe_log_file_mutex = Some(Arc::new(Mutex::new(log_file)));
        }
        Self {
            ssrc_to_user_voice_data: Arc::new(Mutex::new(HashMap::with_capacity(
                MAX_NUM_SPEAKING_PARTICIPANTS,
            ))),
            audio_complete_callback,
            maybe_log_file_mutex,
        }
    }

    fn on_user_join(
        &self,
        ssrc: types::Ssrc,
        user_id: types::UserId,
        audio_callback: types::AudioCallback,
    ) {
        let buffer_mutex = self.ssrc_to_user_voice_data.clone();
        let mut ssrc_to_user_voice_data = buffer_mutex.lock().unwrap();
        if let Some(user_voice_data) = ssrc_to_user_voice_data.get_mut(&ssrc) {
            // println!("found existing buffer for ssrc {}", ssrc);
            assert!(user_voice_data.user_id == user_id);
            user_voice_data.on_start_talking();
        }
        ssrc_to_user_voice_data.insert(
            ssrc,
            voice_buffer::VoiceBufferForUser::new(user_id, audio_callback),
        );
    }

    fn on_start_talking(&self, ssrc: types::Ssrc) {
        self._with_ssrc(ssrc, |user_voice_data| {
            user_voice_data.on_start_talking();
        });
    }

    fn on_audio(&self, ssrc: types::Ssrc, audio: &Vec<types::AudioSample>) {
        self._with_ssrc(ssrc, |user_voice_data| {
            user_voice_data.push(audio);
        });
    }

    fn on_stop_talking(&self, ssrc: types::Ssrc) {
        // set timer to go off in 500ms, and if speaking is still
        // false then flush the buffer.
        self._with_ssrc(ssrc, |user_voice_data| {
            user_voice_data.on_stop_talking();
        });
    }

    fn on_user_leave(&self, user_id: types::UserId) {
        let buffer_mutex = self.ssrc_to_user_voice_data.clone();
        let mut ssrc_to_voice_buffer = buffer_mutex.lock().unwrap();
        ssrc_to_voice_buffer.retain(|_, user_voice_data| user_voice_data.user_id != user_id);
    }

    fn _with_ssrc(&self, ssrc: types::Ssrc, f: impl FnOnce(&mut voice_buffer::VoiceBufferForUser)) {
        let buffer_mutex = self.ssrc_to_user_voice_data.clone();
        let mut ssrc_to_voice_buffer = buffer_mutex.lock().unwrap();
        if let Some(mut user_voice_data) = ssrc_to_voice_buffer.get_mut(&ssrc) {
            f(&mut user_voice_data);
        } else {
            eprintln!("no buffer for ssrc {}", ssrc);
        }
    }

    /// Fires on receipt of a voice packet from another stream in the voice call.
    ///
    /// As RTP packets do not map to Discord's notion of users, SSRCs must be mapped
    /// back using the user IDs seen through client connection, disconnection,
    /// or speaking state update.
    /// Handles these events:
    ///
    /// [`SpeakingUpdate`]: crate::events::CoreEvent::SpeakingUpdate
    /// Fires when a source starts speaking, or stops speaking
    /// (*i.e.*, 5 consecutive silent frames).
    ///
    /// [`SpeakingStateUpdate`]: crate::events::CoreEvent::SpeakingStateUpdate
    /// Speaking state update, typically describing how another voice
    /// user is transmitting audio data. Clients must send at least one such
    /// packet to allow SSRC/UserID matching.
    ///
    /// Fired on receipt of a speaking state update from another host.
    ///
    /// Note: this will fire when a user starts speaking for the first time,
    /// or changes their capabilities.
    ///
    /// [`VoicePacket`]: crate::events::CoreEvent::VoicePacket
    /// Opus audio packet, received from another stream (detailed in `packet`).
    /// `payload_offset` contains the true payload location within the raw packet's `payload()`,
    /// if extensions or raw packet data are required.
    ///
    /// Valid audio data (`Some(audio)` where `audio.len >= 0`) contains up to 20ms of 16-bit stereo PCM audio
    /// at 48kHz, using native endianness. Songbird will not send audio for silent regions, these should
    /// be inferred using [`SpeakingUpdate`]s (and filled in by the user if required using arrays of zeroes).
    ///
    /// If `audio.len() == 0`, then this packet arrived out-of-order. If `None`, songbird was not configured
    /// to decode received packets.
    ///
    /// [`ClientDisconnect`]: crate::events::CoreEvent::ClientDisconnect
    ///
    /// Fired whenever a client disconnects.
    pub async fn act(&self, ctx: &types::MyEventContext) -> Option<songbird::Event> {
        if self.maybe_log_file_mutex.is_some() {
            let log_file_mutex = self.maybe_log_file_mutex.as_ref().unwrap().clone();
            let mut log_file = log_file_mutex.lock().unwrap();
            let j = serde_json::to_string(&ctx).unwrap();
            log_file.write_all(j.as_bytes()).unwrap();
        }

        use types::MyEventContext as Ctx;
        match ctx {
            Ctx::SpeakingStateUpdate(songbird::model::payload::Speaking {
                speaking,
                ssrc,
                user_id,
                ..
            }) => {
                // Discord voice calls use RTP, where every sender uses a randomly allocated
                // *Synchronisation Source* (SSRC) to allow receivers to tell which audio
                // stream a received packet belongs to. As this number is not derived from
                // the sender's user_id, only Discord Voice Gateway messages like this one
                // inform us about which random SSRC a user has been allocated. Future voice
                // packets will contain *only* the SSRC.
                //
                // You can implement logic here so that you can differentiate users'
                // SSRCs and map the SSRC to the User ID and maintain this state.
                // Using this map, you can map the `ssrc` in `voice_packet`
                // to the user ID and handle their audio packets separately.
                // println!(
                //     "Speaking state update: user {:?} has SSRC {:?}, using {:?}",
                //     user_id, ssrc, speaking,
                // );
                // only look at users who are speaking using the microphone
                // (the alternative is sharing their screen, which we ignore)
                if speaking.microphone() {
                    // make sure we have a buffer for this user
                    if let Some(user_id) = user_id {
                        let callback = self.audio_complete_callback.clone();
                        // we need to copy this so it has an independent lifetime
                        let user_id_copy = user_id.0.clone();
                        self.on_user_join(
                            *ssrc,
                            user_id.0,
                            // the user ID passed from voice_buffer is always 0, since
                            // it doesn't know it.  Inject it here.
                            Arc::new(move |_, audio| (callback)(user_id_copy, audio)),
                        );
                    } else {
                        eprintln!("No user_id for speaking state update");
                    }
                }
            }
            Ctx::SpeakingUpdate(data) => {
                // You can implement logic here which reacts to a user starting
                // or stopping speaking, and to map their SSRC to User ID.
                // println!(
                //     "Source {} has {} speaking.",
                //     data.ssrc,
                //     if data.speaking { "started" } else { "stopped" },
                // );
                if data.speaking {
                    self.on_start_talking(data.ssrc);
                } else {
                    // user stopped speaking, so fire off handler
                    // to flush the buffer.
                    self.on_stop_talking(data.ssrc);
                }
            }
            Ctx::VoicePacket(data) => {
                // An event which fires for every received audio packet,
                // containing the decoded data.
                self.on_audio(data.ssrc, &data.audio);
            }
            Ctx::ClientDisconnect(songbird::model::payload::ClientDisconnect {
                user_id, ..
            }) => {
                // You can implement your own logic here to handle a user who has left the
                // voice channel e.g., finalise processing of statistics etc.
                // You will typically need to map the User ID to their SSRC; observed when
                // first speaking.
                self.on_user_leave(user_id.0);

                println!("Client disconnected: user {:?}", user_id);
            }
        }

        None
    }
}
