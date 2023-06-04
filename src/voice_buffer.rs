use crate::types;
use ringbuf::{Consumer, Producer};
use std::sync::Arc;
use std::sync::Mutex;

type AudioBuffer = ringbuf::HeapRb<types::AudioSample>;

struct VoiceBuffer {
    // store 30 seconds of audio, 16-bit stereo PCM at 48kHz
    // divided into 20ms chunks

    // whenever we fill up a buffer, we'll send it to decoding.
    // we have A & B buffers, so that one can be filled while the other is being
    // decoded.
    buffer_mutex: Arc<Mutex<AudioBuffer>>,

    // function to call when a buffer is full
    on_buffer_full_fn: types::AudioCallback,
}

impl<'a> VoiceBuffer {
    fn new(callback: types::AudioCallback) -> Self {
        let buffer = AudioBuffer::new(types::AUDIO_BUFFER_SIZE);

        Self {
            buffer_mutex: Arc::new(Mutex::new(buffer)),
            on_buffer_full_fn: callback,
        }
    }

    /// If the current buffer is full, flush it and return the other buffer.
    /// Flushing means calling the callback with the current buffer, which
    /// should consume everything in the buffer.
    /// In any case, returns the buffer that we should be writing to.
    fn push(&self, audio: &Vec<types::AudioSample>) {
        // if we have enough space in the current buffer, push it there.
        // if not, mark the buffer as full and put all the audio in the
        // other buffer.
        let m = self.buffer_mutex.clone();
        let mut buffer = m.lock().unwrap();
        let (mut producer, consumer) = buffer.split_ref();

        if producer.free_len() < audio.len() {
            println!("buffer is full, flushing");
            println!("producer free len: {}", producer.free_len());
            println!("consumer len: {}", consumer.len());
            println!("audio len: {}", audio.len());
            self._flush_buffer(&producer, consumer);
        }

        producer.push_slice(audio.as_slice());
    }

    /// Flush the buffer, calling the callback.
    /// This should consume everything in the buffer.
    fn flush_buffer(&self) {
        let mut buffer = self.buffer_mutex.lock().unwrap();
        let (producer, consumer) = buffer.split_ref();
        if consumer.is_empty() {
            return;
        }
        self._flush_buffer(&producer, consumer);
    }

    /// we've filled up a buffer, so we need to send it to decoding.
    /// we'll swap the buffers, so that we can continue to fill the
    /// other buffer while we're decoding this one.
    /// Must be called with the buffer lock held.
    fn _flush_buffer(
        &self,
        producer: &Producer<types::AudioSample, &'a AudioBuffer>,
        mut consumer: Consumer<types::AudioSample, &'a AudioBuffer>,
    ) {
        let buffer_contents = consumer.pop_iter().collect::<Vec<_>>();
        let audio = Arc::new(buffer_contents);

        // the user ID passed from voice_buffer is always 0, since
        // we don't know it.  The packet handler will get this
        // callback and inject it.
        (self.on_buffer_full_fn)(0, audio);

        // make sure that iter is empty.  If the callback didn't do it,
        // we'll do it here.
        if !producer.is_empty() {
            eprintln!("iter should be empty");
        }
    }
}

pub struct VoiceBufferForUser {
    pub user_id: types::UserId,
    buffer: VoiceBuffer,
    speaking: bool,
}

impl VoiceBufferForUser {
    pub fn new(user_id: types::UserId, callback: types::AudioCallback) -> Self {
        Self {
            user_id,
            buffer: VoiceBuffer::new(callback),
            speaking: true,
        }
    }

    pub fn push(&self, audio: &Vec<types::AudioSample>) {
        if !self.speaking {
            if audio.iter().all(|sample| *sample == 0) {
                return;
            }
            eprintln!("got audio for non-speaking user {}", self.user_id);
            return;
        }
        self.buffer.push(audio);
    }

    /// Called when a user has started talking after a period of silence.
    /// This is NOT called when a user starts talking for the first time.
    pub fn on_start_talking(&mut self) {
        self.speaking = true;
    }

    pub fn on_stop_talking(&mut self) {
        self.speaking = false;
        self.buffer.flush_buffer();
    }
}
