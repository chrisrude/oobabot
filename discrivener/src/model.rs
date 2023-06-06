use async_trait::async_trait;
use std::sync::Arc;

use crate::api_types;
use crate::packet_handler;
use crate::types;
use crate::whisper;

/// Receives audio from Discord, and sends it to the Whisper model.
pub struct Model {
    driver: songbird::Driver,
}

impl Model {
    pub fn load(
        model_path: String,
        dump_everything_to_a_file: Option<String>,
        event_callback: Arc<dyn Fn(api_types::VoiceChannelEvent) + Send + Sync>,
    ) -> Self {
        let mut config = songbird::Config::default();
        config.decode_mode = songbird::driver::DecodeMode::Decode; // convert incoming audio from Opus to PCM

        let driver = songbird::Driver::new(config);

        let mut model = Self { driver };

        let whisper = whisper::Whisper::load(model_path, event_callback.clone());

        let handler_arc = Arc::new(packet_handler::PacketHandler::new(
            Arc::new(move |user_id, audio| whisper.on_audio_complete(user_id, audio)),
            dump_everything_to_a_file,
            event_callback.clone(),
        ));

        // event handlers for the songbird driver
        model.driver.add_global_event(
            songbird::CoreEvent::SpeakingStateUpdate.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::SpeakingUpdate.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::VoicePacket.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::ClientDisconnect.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::DriverConnect.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::DriverDisconnect.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );
        model.driver.add_global_event(
            songbird::CoreEvent::DriverReconnect.into(),
            VoicePacketHandlerWrapper::new(handler_arc.clone()),
        );

        return model;
    }

    pub async fn connect(
        &mut self,
        connection_info: songbird::ConnectionInfo,
    ) -> Result<(), songbird::error::ConnectionError> {
        return self.driver.connect(connection_info).await;
    }

    pub fn disconnect(&mut self) {
        self.driver.leave();
    }
}

struct VoicePacketHandlerWrapper {
    voice_packet_handler: Arc<packet_handler::PacketHandler>,
}

impl VoicePacketHandlerWrapper {
    fn new(voice_packet_handler: Arc<packet_handler::PacketHandler>) -> Self {
        Self {
            voice_packet_handler,
        }
    }
}

#[async_trait]
impl songbird::EventHandler for VoicePacketHandlerWrapper {
    async fn act(&self, ctx: &songbird::EventContext<'_>) -> Option<songbird::Event> {
        if let Some(my_ctx) = types::MyEventContext::from(ctx) {
            return self.voice_packet_handler.act(&my_ctx).await;
        }
        return None;
    }
}
