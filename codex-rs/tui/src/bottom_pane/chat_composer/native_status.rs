//! Cache configured native status rows and their hyperlink ranges.
//! Measurement and paint share explicit row boundaries at every terminal width.

use super::ChatComposer;
use super::FooterContent;
use crate::terminal_hyperlinks::HyperlinkLine;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::text::Span;
use std::cell::Ref;

pub(super) struct NativeStatusRows {
    width: u16,
    suffix: Vec<Span<'static>>,
    rows: Vec<HyperlinkLine>,
}

impl NativeStatusRows {
    pub(super) fn height(&self) -> u16 {
        u16::try_from(self.rows.len()).unwrap_or(u16::MAX)
    }

    pub(super) fn render(&self, area: Rect, buf: &mut Buffer) {
        for (index, line) in self.rows.iter().take(usize::from(area.height)).enumerate() {
            let row = Rect::new(area.x, area.y + index as u16, area.width, 1);
            if line.width() > usize::from(area.width) {
                line.clone().render_with_ellipsis(row, buf);
            } else {
                line.render_fitted(row, buf);
            }
        }
    }
}

impl ChatComposer {
    pub(super) fn native_status_rows(
        &self,
        content: &FooterContent,
        width: u16,
    ) -> Option<Ref<'_, NativeStatusRows>> {
        let (line, _) = content.native_parts()?;
        if width == 0 {
            return None;
        }
        // The setter invalidates configured spans. The styled agent suffix can change independently.
        let configured = self
            .footer
            .status_line_value
            .as_ref()
            .and_then(FooterContent::native_parts)
            .map_or(0, |(line, _)| line.spans.len());
        let suffix = &line.spans[configured..];
        let cache = &self.footer.native_status_rows;
        if cache
            .borrow()
            .as_ref()
            .is_none_or(|entry| entry.width != width || entry.suffix != suffix)
        {
            cache.replace(Some(NativeStatusRows {
                width,
                suffix: suffix.to_vec(),
                rows: content
                    .clone()
                    .into_rows()
                    .into_iter()
                    .map(FooterContent::into_hyperlink_line)
                    .collect(),
            }));
        }
        Ref::filter_map(cache.borrow(), Option::as_ref).ok()
    }
}
