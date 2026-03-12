use docsearch_core::parser::*;
use std::path::Path;

#[test]
fn test_detect_pdf() {
    assert!(matches!(detect_format(Path::new("test.pdf")), Some(DocumentFormat::Pdf)));
}

#[test]
fn test_detect_markdown() {
    assert!(matches!(detect_format(Path::new("readme.md")), Some(DocumentFormat::Markdown)));
}

#[test]
fn test_unknown_format() {
    assert!(detect_format(Path::new("test.xyz")).is_none());
}
