use clap::Parser;
use discrivener::api;
use serde_json;
use std::sync::Arc;
use tokio::signal;

#[tokio::main]
async fn tokio_main(cli: Cli) {
    let mut discrivener = api::Discrivener::load(
        cli.model_path,
        Arc::new(|event| println!("{}", serde_json::to_string(&event).unwrap())),
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
        eprintln!("Joined voice channel");
    } else {
        eprintln!("Error joining voice channel");
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

    #[arg(long, default_value = None)]
    save_everything_to_file: Option<String>,
}

fn main() {
    let args = Cli::parse();
    tokio_main(args);
}
