use pyo3::prelude::*;

pub mod api;
pub mod api_types;
mod model;
mod packet_handler;
mod types;
mod voice_buffer;
mod whisper;

/// A Python module implemented in Rust.
#[pymodule]
fn discrivener(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<api::Discrivener>()?;
    m.add_class::<api_types::TranscribedMessage>()?;
    m.add_class::<api_types::TextSegment>()?;
    Ok(())
}
