//! Cache configured native status rows and their hyperlink ranges.
//! Measurement and paint share explicit row boundaries at every terminal width.

use super::ChatComposer;
use super::FooterContent;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::text::Span;
use std::cell::Ref;

pub(super) struct NativeStatusRows {
    width: u16,
    suffix: Vec<Span<'static>>,
    rows: Vec<FooterContent>,
}

impl NativeStatusRows {
    pub(super) fn height(&self) -> u16 {
        u16::try_from(self.rows.len()).unwrap_or(u16::MAX)
    }

    pub(super) fn render(&self, area: Rect, buf: &mut Buffer) {
        FooterContent::Rows(self.rows.clone()).render(area, buf);
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
                rows: content.clone().into_rows(),
            }));
        }
        Ref::filter_map(cache.borrow(), Option::as_ref).ok()
    }
}
