use std::path::Path;
use std::sync::Arc;

use tokio::sync::Mutex;
use tokio::task;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext};

use crate::api_types;
use crate::types;

/// If an audio clip is less than this length, we'll ignore it.
pub const MIN_AUDIO_THRESHOLD_MS: u32 = 500;

#[derive(Clone)]
pub struct LastTranscriptionData {
    tokens: Vec<i32>,
    timestamp: u64,
    user_id: types::UserId,
}

const MAX_TOKENS_PER_SEGMENT: usize = 100;

impl LastTranscriptionData {
    fn from_transcribed_message(
        whisper_context: &WhisperContext,
        message: api_types::TranscribedMessage,
        end_timestmap: u64,
    ) -> LastTranscriptionData {
        let tokens = message
            .text_segments
            .iter()
            .map(|segment| whisper_context.tokenize(segment.text.as_str(), MAX_TOKENS_PER_SEGMENT))
            .filter_map(|x| x.ok())
            .collect::<Vec<_>>()
            .concat();

        return LastTranscriptionData {
            tokens,
            timestamp: end_timestmap,
            user_id: message.user_id,
        };
    }
}

pub struct Whisper {
    event_callback: Arc<dyn Fn(api_types::VoiceChannelEvent) + Send + Sync>,
    last_transcription: Arc<Mutex<Option<LastTranscriptionData>>>,
    whisper_context: Arc<WhisperContext>,
}

fn make_params() -> FullParams<'static, 'static> {
    let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });

    params.set_print_special(false);
    params.set_print_progress(false);
    params.set_print_realtime(false);
    params.set_print_timestamps(false);

    return params;
}

impl Whisper {
    /// Load a model from the given path
    pub fn load(
        model_path: String,
        event_callback: Arc<dyn Fn(api_types::VoiceChannelEvent) + Send + Sync>,
    ) -> Self {
        let path = Path::new(model_path.as_str());
        if !path.exists() {
            panic!("Model file does not exist: {}", path.to_str().unwrap());
        }
        if !path.is_file() {
            panic!("Model is not a file: {}", path.to_str().unwrap());
        }

        let whisper_context =
            Arc::new(WhisperContext::new(model_path.as_str()).expect("failed to load model"));

        let last_transcription = Arc::new(Mutex::new(None));

        return Self {
            event_callback,
            last_transcription,
            whisper_context,
        };
    }

    /// Called once we have a full audio clip from a user.
    /// This is called on an event handling thread, so do not do anything
    /// major on it, and return asap.
    pub fn on_audio_complete(&self, user_id: types::UserId, audio: Arc<Vec<types::AudioSample>>) {
        let audio_duration_ms =
            ((audio.len() / types::AUDIO_CHANNELS) / types::DISCORD_SAMPLES_PER_MILLISECOND) as u32;
        if audio_duration_ms < MIN_AUDIO_THRESHOLD_MS {
            // very short messages are usually just noise, ignore them
            return;
        }
        // get our unixtime in ms
        let start_time = std::time::SystemTime::now();
        let unixsecs = start_time
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs();

        // make clones of everything so that the closure can own them, if
        let audio_copy = audio.clone();
        let callback_copy = self.event_callback.clone();
        let last_transcription_copy = self.last_transcription.clone();
        let whisper_context_copy = self.whisper_context.clone();

        // todo: if we're running too far behind, we should drop audio in order to catch up
        // todo: if we're always running too far behind, we should display some kind of warning
        // todo: try quantized model?

        task::spawn(async move {
            let whisper_audio = resample_audio_from_discord_to_whisper(audio_copy);

            // get the last transcription, and pass it in if:
            // - it's from the same user
            // - the last transcription ended less than 5 seconds ago
            let mut last_transcription_context: Option<LastTranscriptionData> = None;
            {
                let last_transcription = last_transcription_copy.lock().await;
                let lt = last_transcription.clone();
                if let Some(last_transcription) = lt {
                    if (unixsecs - last_transcription.timestamp) < 5 {
                        if last_transcription.user_id == user_id {
                            last_transcription_context = Some(last_transcription);
                        }
                    }
                }
            }
            let text_segments = audio_to_text(
                &whisper_context_copy,
                whisper_audio,
                last_transcription_context,
            );

            // if there's nothing in the last transcription, then just stop
            if text_segments.len() == 0 {
                return;
            }

            let end_time = std::time::SystemTime::now();
            let processing_time_ms =
                end_time.duration_since(start_time).unwrap().as_millis() as u32;
            let transcribed_message = api_types::TranscribedMessage {
                timestamp: unixsecs,
                user_id,
                text_segments,
                audio_duration_ms,
                processing_time_ms,
            };

            // this is now our last transcription
            let last_data = LastTranscriptionData::from_transcribed_message(
                &whisper_context_copy,
                transcribed_message.clone(),
                end_time
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_secs(),
            );
            {
                last_transcription_copy.lock().await.replace(last_data);
            }

            callback_copy(api_types::VoiceChannelEvent::TranscribedMessage(
                transcribed_message,
            ));
        });
    }
}

fn resample_audio_from_discord_to_whisper(
    audio: types::AudioClip,
) -> Vec<types::WhisperAudioSample> {
    // this takes advantage of the ratio between the two sample rates
    // being a whole number. If this is not the case, we'll need to
    // do some more complicated resampling.
    assert!(types::DISCORD_SAMPLES_PER_SECOND % types::WHISPER_SAMPLES_PER_SECOND == 0);
    const BITRATE_CONVERSION_RATIO: usize =
        types::DISCORD_SAMPLES_PER_SECOND / types::WHISPER_SAMPLES_PER_SECOND;

    // do the conversion, we'll take the first sample, and then
    // simply skip over the next (BITRATE_CONVERSION_RATIO-1)
    // samples
    //
    // while converting the bitrate we'll also convert the audio
    // from stereo to mono, so we'll do everything in pairs.
    const GROUP_SIZE: usize = BITRATE_CONVERSION_RATIO * types::AUDIO_CHANNELS;

    let out_len = audio.len() / GROUP_SIZE;
    let mut audio_out = vec![0.0 as types::WhisperAudioSample; out_len];

    let mut audio_max: types::WhisperAudioSample = 0.0;

    // todo: drop audio which is very low signal?  It has had issues transcribing well.

    // iterate through the audio vector, taking pairs of samples and averaging them
    // while doing so, look for max and min values so that we can normalize later
    for (i, samples) in audio.chunks_exact(GROUP_SIZE).enumerate() {
        // take the first two values of samples, and add them into audio_out .
        // also, find the largest absolute value, and store it in audio_max
        let mut val = 0.0;
        for j in 0..types::AUDIO_CHANNELS {
            val += samples[j] as types::WhisperAudioSample;
        }
        let abs = val.abs();
        if abs > audio_max {
            audio_max = abs;
        }
        audio_out[i] = val;
        // don't worry about dividing by AUDIO_CHANNELS, as normalizing
        // will take care of it, saving us divisions
    }
    // normalize floats to be between -1 and 1
    for sample in audio_out.iter_mut() {
        *sample /= audio_max;
    }
    return audio_out;
}

/// ctx came from load_model
/// audio data should be is f32, 16KHz, mono
fn audio_to_text(
    whisper_context: &Arc<WhisperContext>,
    audio_data: Vec<types::WhisperAudioSample>,
    last_transcription: Option<LastTranscriptionData>,
) -> Vec<api_types::TextSegment> {
    let mut state = whisper_context.create_state().unwrap();

    let mut params = make_params();

    // if we have a last_transcription, add it to the state
    let last_tokens;
    if last_transcription.is_some() {
        last_tokens = last_transcription.unwrap().tokens;
        params.set_tokens(&last_tokens[..]);
    }

    // actually convert audio to text.  Takes a while.
    state.full(params, &audio_data[..]).unwrap();

    // todo: use a different context / token history for each user
    // see https://github.com/ggerganov/whisper.cpp/blob/57543c169e27312e7546d07ed0d8c6eb806ebc36/examples/stream/stream.cpp

    let num_segments = state.full_n_segments().unwrap();
    let mut result = Vec::<api_types::TextSegment>::with_capacity(num_segments as usize);
    for i in 0..num_segments {
        result.push(api_types::TextSegment {
            text: state.full_get_segment_text(i).unwrap().to_string(),
            start_offset_ms: state.full_get_segment_t0(i).unwrap() as u32,
            end_offset_ms: state.full_get_segment_t1(i).unwrap() as u32,
        });
    }
    return result;
}
