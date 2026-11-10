//! The composer measures the natural width before allocating the left column, then renders
//! the selected content in the allotted rectangle.

use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::text::Line;
use ratatui::widgets::Widget;

use crate::line_truncation::truncate_line_with_ellipsis_if_overflow;
use crate::render::line_utils::split_line_at_newlines;
use crate::terminal_hyperlinks::HyperlinkLine;
use crate::ui_tree::UiNode;

/// Owned content for the footer's negotiated left-hand area.
#[derive(Clone, Debug, PartialEq)]
pub(crate) enum FooterContent {
    Line(Line<'static>),
    HyperlinkLine(HyperlinkLine),
    Extension { content: UiNode },
    Rows(Vec<FooterContent>),
}

impl FooterContent {
    /// Natural display width, before the footer allocates space for the right indicator.
    pub(crate) fn width(&self) -> u16 {
        let width = match self {
            Self::Line(line) => line.width(),
            Self::HyperlinkLine(line) => line.width(),
            Self::Extension { content } => content.render_line(u16::MAX).width(),
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
            Self::Line(line) => Widget::render(line, area, buf),
            Self::Extension { content } => content.render_line(area.width).render_fitted(area, buf),
            Self::HyperlinkLine(mut line) => {
                let area = Rect {
                    height: area.height.min(1),
                    ..area
                };
                let width = usize::from(area.width);
                if line.width() > width {
                    line.line = truncate_line_with_ellipsis_if_overflow(line.line, width);
                    // The ellipsis is never part of the link.
                    line.clip_hyperlinks_to_width(line.width().saturating_sub(1));
                }
                line.render_fitted(area, buf);
            }
        }
    }

    /// Keep link destinations when handing the status line to the effort transition.
    pub(crate) fn into_hyperlink_line(self) -> HyperlinkLine {
        match self {
            Self::Line(line) => line.into(),
            Self::HyperlinkLine(line) => line,
            Self::Extension { content } => content.render_line(u16::MAX),
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

    /// Split only explicit row markers, retaining link ranges relative to each row.
    pub(crate) fn into_rows(self) -> Vec<Self> {
        match self {
            Self::Rows(rows) => rows.into_iter().flat_map(Self::into_rows).collect(),
            Self::Extension { .. } => vec![self],
            content => {
                let line = content.into_hyperlink_line();
                let mut offset = 0;
                let newline_width = HyperlinkLine::from("\n").source_width();
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
                        // Source columns include the marker removed between painted rows.
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
