//! Document parser module
use std::path::Path;

pub enum DocumentFormat {
    Pdf,
    Txt,
    Markdown,
    Html,
}

pub struct ParsedDocument {
    pub title: Option<String>,
    pub content: String,
    pub format: DocumentFormat,
    pub metadata: std::collections::HashMap<String, String>,
}

pub fn detect_format(path: &Path) -> Option<DocumentFormat> {
    match path.extension()?.to_str()? {
        "pdf" => Some(DocumentFormat::Pdf),
        "txt" => Some(DocumentFormat::Txt),
        "md" | "markdown" => Some(DocumentFormat::Markdown),
        "html" | "htm" => Some(DocumentFormat::Html),
        _ => None,
    }
}

pub fn parse(path: &Path) -> Result<ParsedDocument, Box<dyn std::error::Error>> {
    let content = std::fs::read_to_string(path)?;
    let format = detect_format(path).unwrap_or(DocumentFormat::Txt);
    Ok(ParsedDocument {
        title: path.file_stem().map(|s| s.to_string_lossy().into_owned()),
        content,
        format,
        metadata: std::collections::HashMap::new(),
    })
}
