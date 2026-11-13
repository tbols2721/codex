//! Native and extension status content measured and painted inside the status rectangle.

use crate::line_truncation::line_width;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::text::Line;
use std::sync::Arc;

use crate::render::highlight::with_syntax_theme;
use crate::render::line_utils::split_line_at_newlines;
use crate::terminal_hyperlinks::HyperlinkLine;
use crate::terminal_hyperlinks::TerminalHyperlink;
use crate::ui_tree::PreparedUiTree;
use crate::ui_tree::UiTree;

/// Owned status content displayed below the composer.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum FooterContent {
    Line(Line<'static>),
    HyperlinkLine(HyperlinkLine),
    Extension { content: Arc<PreparedUiTree> },
    Rows(Vec<FooterContent>),
}

impl From<UiTree> for FooterContent {
    fn from(tree: UiTree) -> Self {
        Self::Extension {
            content: Arc::new(tree.prepare()),
        }
    }
}

impl FooterContent {
    pub(crate) fn native_parts(&self) -> Option<(&Line<'static>, &[TerminalHyperlink])> {
        match self {
            Self::Line(line) => Some((line, &[])),
            Self::HyperlinkLine(line) => Some((&line.line, &line.hyperlinks)),
            Self::Extension { .. } | Self::Rows(_) => None,
        }
    }

    /// Natural display width in terminal cells.
    pub(crate) fn width(&self) -> u16 {
        let width = match self {
            Self::Line(line) => line_width(line),
            Self::HyperlinkLine(line) => line.width(),
            Self::Extension { content } => return content.measure_natural().width,
            Self::Rows(rows) => return rows.first().map_or(0, Self::width),
        };
        u16::try_from(width).unwrap_or(u16::MAX)
    }

    /// Paint only inside the final area supplied by the parent.
    pub(crate) fn render(self, area: Rect, buf: &mut Buffer) {
        match self {
            Self::Rows(rows) => {
                for (index, row) in rows.into_iter().enumerate().take(usize::from(area.height)) {
                    row.render(Rect::new(area.x, area.y + index as u16, area.width, 1), buf);
                }
            }
            Self::Extension { content } => {
                with_syntax_theme(|theme| content.render(area, theme, buf));
            }
            native => {
                let line = native.into_hyperlink_line();
                let area = Rect {
                    height: area.height.min(1),
                    ..area
                };
                let width = usize::from(area.width);
                if line.width() > width {
                    line.render_with_ellipsis(area, buf);
                } else {
                    line.render_fitted(area, buf);
                }
            }
        }
    }

    pub(crate) fn into_hyperlink_line(self) -> HyperlinkLine {
        match self {
            Self::Line(line) => line.into(),
            Self::HyperlinkLine(line) => line,
            Self::Extension { content } => {
                with_syntax_theme(|theme| content.render_line(u16::MAX, theme))
            }
            Self::Rows(rows) => {
                let mut combined = HyperlinkLine::default();
                for (index, row) in rows.into_iter().enumerate() {
                    if index > 0 {
                        combined.line.push_span("\n");
                    }
                    let row = row.into_hyperlink_line();
                    let offset = combined.source_width();
                    combined
                        .hyperlinks
                        .extend(row.hyperlinks.into_iter().map(|link| {
                            link.with_columns(
                                link.columns.start + offset..link.columns.end + offset,
                            )
                        }));
                    combined.line.spans.extend(row.line.spans);
                }
                combined
            }
        }
    }

    /// The configured row count, independent of the terminal width.
    /// Extension trees without explicit row boundaries keep their own measurement.
    pub(crate) fn explicit_row_count(&self) -> Option<u16> {
        let count = match self {
            Self::Rows(rows) => rows
                .iter()
                .map(|row| usize::from(row.explicit_row_count().unwrap_or(1)))
                .sum(),
            Self::Extension { .. } => return None,
            native => {
                let (line, _) = native.native_parts()?;
                1 + line
                    .spans
                    .iter()
                    .map(|span| span.content.chars().filter(|&ch| ch == '\n').count())
                    .sum::<usize>()
            }
        };
        Some(u16::try_from(count).unwrap_or(u16::MAX))
    }

    /// Split explicit row markers and retain link columns relative to each row.
    pub(crate) fn into_rows(self) -> Vec<Self> {
        match self {
            Self::Rows(rows) => rows.into_iter().flat_map(Self::into_rows).collect(),
            Self::Extension { .. } => vec![self],
            content => {
                let line = content.into_hyperlink_line();
                let mut offset = 0;
                let newline_width = crate::width::display_width("\n");
                split_line_at_newlines(line.line)
                    .into_iter()
                    .map(|text| {
                        let mut row = HyperlinkLine::from(text);
                        let end = offset + row.source_width();
                        row.hyperlinks = line
                            .hyperlinks
                            .iter()
                            .filter_map(|link| {
                                let start = link.columns.start.max(offset);
                                let stop = link.columns.end.min(end);
                                (start < stop)
                                    .then(|| link.with_columns(start - offset..stop - offset))
                            })
                            .collect();
                        offset = end + newline_width;
                        Self::HyperlinkLine(row)
                    })
                    .collect()
            }
        }
    }
}

impl From<HyperlinkLine> for FooterContent {
    fn from(line: HyperlinkLine) -> Self {
        Self::HyperlinkLine(line)
    }
}

impl From<Line<'static>> for FooterContent {
    fn from(line: Line<'static>) -> Self {
        Self::Line(line)
    }
}

impl From<&'static str> for FooterContent {
    fn from(text: &'static str) -> Self {
        Self::Line(Line::from(text))
    }
}

#[cfg(test)]
#[path = "footer_content_tests.rs"]
mod tests;
