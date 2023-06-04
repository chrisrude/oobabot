use std::path::Path;
use std::sync::Arc;

use tokio::task;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext};

use crate::api_types;
use crate::types;

/// If an audio clip is less than this length, we'll ignore it.
pub const MIN_AUDIO_THRESHOLD_MS: u32 = 500;

pub struct Whisper {
    text_callback: Arc<dyn Fn(api_types::TranscribedMessage) + Send + Sync>,
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
        text_callback: Arc<dyn Fn(api_types::TranscribedMessage) + Send + Sync>,
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

        return Self {
            text_callback,
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

        // make clones of everything so that the closure can own them, if
        let audio_copy = audio.clone();
        let callback_copy = self.text_callback.clone();
        let whisper_context_copy = self.whisper_context.clone();
        task::spawn(async move {
            let start_time = std::time::Instant::now();

            let whisper_audio = resample_audio_from_discord_to_whisper(audio_copy);
            let text_segments = audio_to_text(whisper_context_copy, whisper_audio);

            let processing_time_ms = (start_time - std::time::Instant::now()).as_millis() as u32;

            let transcribed_message = api_types::TranscribedMessage {
                timestamp: 0, // TODO!!!
                user_id,
                text_segments,
                audio_duration_ms,
                processing_time_ms,
            };

            callback_copy(transcribed_message);
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
    whisper_context: Arc<WhisperContext>,
    audio_data: Vec<types::WhisperAudioSample>,
) -> Vec<api_types::TextSegment> {
    let mut state = whisper_context.create_state().unwrap();

    // actually convert audio to text.  Takes a while.
    state.full(make_params(), &audio_data[..]).unwrap();

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
