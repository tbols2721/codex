//! Separate persistent transcript context from the composer's transient hint row.
//! Measurement, rendering, and cursor placement share the same reserved status rectangle.
//! Shortcut help grows above the input, preserving status and close rows below it even when clipped.
//! Persistent status retains the rows assigned by configured `line-break` items at every width.

use super::*;

impl ChatComposer {
    pub(super) fn status_surface_enabled(&self, options: ComposerRenderOptions<'_>) -> bool {
        options.separate_status_line && self.footer.status_line_enabled
    }

    pub(super) fn status_surface_height(
        &self,
        width: u16,
        options: ComposerRenderOptions<'_>,
    ) -> u16 {
        if !self.status_surface_enabled(options) {
            return 0;
        }
        self.status_surface_layout(width, options).height()
    }

    pub(super) fn hint_footer_props(&self, options: ComposerRenderOptions<'_>) -> FooterProps {
        let mut props = self.footer_props();
        if self.status_surface_enabled(options) {
            props.status_line_enabled = false;
            props.status_line_value = None;
            props.active_agent_label = None;
        }
        props
    }

    fn status_surface_layout(
        &self,
        width: u16,
        options: ComposerRenderOptions<'_>,
    ) -> ExplicitStatusLine {
        let area = Rect::new(0, 0, width, 1);
        let mut props = self.footer_props();
        let show_cycle_hint = !props.is_task_running
            && !self.blocks_direct_input
            && self.draft.input_enabled
            && !self.popup_active()
            && matches!(
                props.mode,
                FooterMode::ComposerEmpty | FooterMode::ComposerHasDraft
            )
            && options.footer.is_none_or(|footer| !footer.is_interactive);
        // Persistent context is independent of help, queue, search, and quit modes.
        props.mode = FooterMode::ComposerHasDraft;
        props.is_task_running = false;
        let line = passive_footer_status_line(&props);
        let full = self.mode_indicator_line(show_cycle_hint);
        let rows =
            crate::render::line_utils::split_line_at_newlines(line.clone().unwrap_or_default());
        let left_width = rows.first().map_or(0, |line| line.width() as u16);
        let full_width = full
            .as_ref()
            .map_or(/*default*/ 0, |line| line.width() as u16);
        let right = if full_width <= inset_footer_hint_area(area).width
            && can_show_left_with_context(area, left_width, full_width)
        {
            full
        } else {
            self.mode_indicator_line(/*show_cycle_hint*/ false)
        };
        let right_width = right
            .as_ref()
            .map_or(/*default*/ 0, |line| line.width() as u16);
        let width = max_left_width_for_right(area, right_width)
            .unwrap_or_else(|| inset_footer_hint_area(area).width);
        let transition = self
            .effort_status_line_transition
            .as_ref()
            .filter(|transition| !transition.is_finished() && rows.len() == 1);
        let line = if let Some(transition) = transition {
            transition.render_line(line.as_ref(), width)
        } else {
            line
        };
        ExplicitStatusLine::new(area.width, line.unwrap_or_default(), right)
    }

    pub(super) fn render_status_surface(
        &self,
        area: Rect,
        buf: &mut Buffer,
        options: ComposerRenderOptions<'_>,
    ) {
        if area.is_empty() {
            return;
        }
        self.status_surface_layout(area.width, options)
            .render(area, buf);
        if let Some(url) = self.footer.status_line_hyperlink_url.as_deref() {
            mark_underlined_hyperlink(buf, area, url);
        }
        if self
            .effort_status_line_transition
            .as_ref()
            .is_some_and(|transition| !transition.is_finished())
            && let Some(frame_requester) = &self.frame_requester
        {
            frame_requester.schedule_frame_in(EFFORT_STATUS_LINE_FRAME_TICK);
        }
    }
}

#[cfg(test)]
#[path = "status_surface_tests.rs"]
mod tests;
