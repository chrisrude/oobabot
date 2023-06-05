use clap::Parser;
use colored::Colorize;
use discrivener::api;
use discrivener::api_types;
use std::sync::Arc;
use tokio::signal;

fn on_text(message: api_types::TranscribedMessage, log_performance: bool) {
    if message.text_segments.len() == 0 {
        println!("");
        return;
    }
    if log_performance {
        println!("Processing time: +{}ms", message.processing_time_ms);
        println!("Audio duration: {}ms", message.audio_duration_ms);
        println!(
            "total time / Audio duration: {}",
            message.processing_time_ms as f32 / message.audio_duration_ms as f32
        );
    }

    let mut first: bool = true;
    for text_segment in message.text_segments {
        if first {
            println!(
                "{}{} {}",
                message.user_id.to_string().bright_green(),
                " says:",
                text_segment.text.bold(),
            );
            first = false;
        } else {
            println!("\t\t\t\t {}", text_segment.text.bold());
        }
    }
}

#[tokio::main]
async fn tokio_main(cli: Cli) {
    let log_performance = cli.log_performance;
    let mut discrivener = api::Discrivener::load(
        cli.model_path,
        Arc::new(move |message| on_text(message, log_performance)),
        cli.save_everything_to_file,
    );

    let connection_result = discrivener
        .connect(
            cli.channel_id,
            cli.endpoint.as_str(),
            cli.guild_id,
            cli.session_id.as_str(),
            cli.user_id,
            cli.voice_token.as_str(),
        )
        .await;
    if let Ok(_) = connection_result {
        println!("Joined voice channel");
    } else {
        println!("Error joining voice channel");
    }

    signal::ctrl_c().await.unwrap();
    discrivener.disconnect();
}

/// Connect to a discord voice channel
#[derive(clap::Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Cli {
    model_path: String,

    /// Channel ID to connect to
    #[arg(short, long)]
    channel_id: u64,
    /// Discord voice endpoint, hostname
    #[arg(short, long)]
    endpoint: String,
    /// Guild ID to connect to
    #[arg(short, long)]
    guild_id: u64,
    /// Discord voice session ID
    #[arg(short, long)]
    session_id: String,
    /// Discord user ID
    #[arg(short, long)]
    user_id: u64,
    /// Discord voice token (NOT bot token)
    #[arg(short, long)]
    voice_token: String,

    #[arg(short, long, default_value = "false")]
    log_performance: bool,

    #[arg(long, default_value = None)]
    save_everything_to_file: Option<String>,
}

fn main() {
    let args = Cli::parse();
    tokio_main(args);
}
