//! Footer replacement keeps the existing layout and the focused editor's cursor together.

use super::*;
use crate::app_event::AppEvent;
use crate::app_event_sender::AppEventSender;
use crate::bottom_pane::ChatComposer;
use crate::bottom_pane::footer::inset_footer_hint_area;
use pretty_assertions::assert_eq;
use tokio::sync::mpsc::unbounded_channel;

fn composer() -> ChatComposer {
    let (tx, _rx) = unbounded_channel::<AppEvent>();
    let mut composer = ChatComposer::new(
        /*has_input_focus*/ true,
        AppEventSender::new(tx),
        /*enhanced_keys_supported*/ false,
        "Ask Codex".to_string(),
        /*disable_paste_burst*/ true,
    );
    composer.set_status_line_enabled(/*enabled*/ true);
    composer.set_status_line(Some(Line::from("MODEL STATUS").into()));
    composer
}

fn render(
    composer: &ChatComposer,
    footer: Option<&TranscriptFooter>,
) -> (Buffer, Option<(u16, u16)>) {
    let options = composer.resolve_render_options(ComposerRenderOptions {
        footer,
        ..ComposerRenderOptions::default()
    });
    let width = 60;
    let area = Rect::new(
        /*x*/ 0,
        /*y*/ 0,
        width,
        composer.desired_height_with_options(width, options),
    );
    let mut buffer = Buffer::empty(area);
    composer.render_with_options(area, &mut buffer, /*mask_char*/ None, options);
    (buffer, composer.cursor_pos_with_options(area, options))
}

fn text(buffer: &Buffer) -> String {
    buffer
        .content
        .chunks(usize::from(buffer.area.width))
        .map(|row| {
            row.iter()
                .map(ratatui::buffer::Cell::symbol)
                .collect::<String>()
                .trim_end()
                .to_string()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn retained_command_suggestions_yield_paint_and_cursor_to_find() {
    let mut composer = composer();
    composer.draft.textarea.insert_str("/");
    composer.sync_popups();
    let original = render(&composer, /*footer*/ None);
    let footer = TranscriptFooter {
        text: vec![
            Line::from("Find: needle"),
            Line::from("Enter next · Esc close"),
        ]
        .into(),
        cursor_column: Some(8),
        is_interactive: true,
    };
    let options = composer.resolve_render_options(ComposerRenderOptions {
        footer: Some(&footer),
        command_popup_placement: CommandPopupPlacement::Hidden,
        ..ComposerRenderOptions::default()
    });
    let mut frames = Vec::new();
    for (width, height) in [(60, 8), (24, 8), (12, 3)] {
        let area = Rect::new(/*x*/ 0, /*y*/ 0, width, height);
        let mut buffer = Buffer::empty(area);
        composer.render_with_options(area, &mut buffer, /*mask_char*/ None, options);
        let cursor = composer.cursor_pos_with_options(area, options);
        let footer_area =
            inset_footer_hint_area(composer.layout_with_options(area, options).footer);
        assert_eq!(
            cursor,
            (footer_area.width > 8 && footer_area.height > 0)
                .then_some((footer_area.x + 8, footer_area.y))
        );
        assert!(matches!(composer.popups.active, ActivePopup::Command(_)));
        assert_eq!(composer.draft.textarea.text(), "/");
        frames.push(format!(
            "{width}x{height}, cursor {cursor:?}\n{}",
            text(&buffer)
        ));
    }
    insta::assert_snapshot!(
        "find_hides_retained_command_suggestions",
        frames.join("\n\n")
    );
    assert_eq!(render(&composer, /*footer*/ None), original);
}

#[test]
fn copying_from_find_preserves_the_query_above_selection_feedback() {
    let mut composer = composer();
    let footer = TranscriptFooter {
        text: vec![
            Line::from("Find: needle"),
            Line::from("Ctrl+C copy · Esc clear selection"),
        ]
        .into(),
        cursor_column: None,
        is_interactive: true,
    };
    composer.show_footer_flash(
        "Copied selection to clipboard".into(),
        Duration::from_secs(/*secs*/ 3),
    );
    let (buffer, cursor) = render(&composer, Some(&footer));
    assert_eq!(cursor, None);
    insta::assert_snapshot!("transcript_find_copy_footer", text(&buffer));
}

#[test]
fn interactive_query_keeps_focus_over_underlying_hints_but_empty_override_wins() {
    let mut composer = composer();
    let footer = TranscriptFooter {
        text: vec![
            Line::from("Find: needle"),
            Line::from("Enter next · Esc close"),
        ]
        .into(),
        cursor_column: Some(12),
        is_interactive: true,
    };
    let expected = render(&composer, Some(&footer));
    composer.set_footer_hint_override(Some(vec![("ctrl+c".to_string(), "quit".to_string())]));
    assert_eq!(render(&composer, Some(&footer)), expected);
    composer.set_footer_hint_override(Some(Vec::new()));
    assert_eq!(
        render(&composer, Some(&footer)),
        render(&composer, /*footer*/ None)
    );
}

#[test]
fn status_line_fields_stay_on_assigned_rows_at_every_width() {
    let mut composer = composer();
    composer.set_status_line(Some(Line::from(vec![
        ratatui::text::Span::raw("MODEL-A · PROJECT-B"),
        ratatui::text::Span::raw("\n"),
        ratatui::text::Span::raw("TOKENS-C · COST-D"),
    ])));
    for separate_status_line in [false, true] {
        let options = ComposerRenderOptions {
            separate_status_line,
            ..ComposerRenderOptions::default()
        };
        let mut heights = Vec::new();
        for width in [12, 32, 100] {
            let height = composer.desired_height_with_options(width, options);
            heights.push(height);
            let area = Rect::new(0, 0, width, height);
            let layout = composer.layout_with_options(area, options);
            let status = if separate_status_line {
                layout.status
            } else {
                layout.footer
            };
            assert_eq!(status.height, 2);
            let mut buffer = Buffer::empty(area);
            composer.render_with_options(area, &mut buffer, /*mask_char*/ None, options);
            let row = |y| {
                (0..width)
                    .map(|x| buffer[(x, y)].symbol())
                    .collect::<String>()
            };
            let first = row(status.y);
            let second = row(status.y + 1);
            assert!(first.contains("MODEL-A"), "{first:?}");
            assert!(!first.contains("TOKENS-C"), "{first:?}");
            assert!(second.contains("TOKENS-C"), "{second:?}");
            assert!(!second.contains("MODEL-A"), "{second:?}");
            if width == 12 {
                assert!(first.contains('…'));
                assert!(second.contains('…'));
            } else {
                assert!(first.contains("PROJECT-B"));
                assert!(second.contains("COST-D"));
            }
            assert!(composer.cursor_pos_with_options(area, options).is_some());
        }
        assert!(heights.windows(2).all(|pair| pair[0] == pair[1]));
    }
}

#[test]
fn warning_notice_only_limits_the_last_visible_status_row() {
    let mut composer = composer();
    composer.set_collaboration_modes_enabled(/*enabled*/ true);
    composer.set_collaboration_mode_indicator(Some(CollaborationModeIndicator::Plan));
    composer.footer.show_warnings_key = Some(crate::key_hint::plain(KeyCode::F(2)).into());
    composer.set_status_line(Some(Line::from(vec![
        ratatui::text::Span::raw("MODEL-A · PROJECT-B · BRANCH-C · CONTEXT-D · REASONING-E"),
        ratatui::text::Span::raw("\n"),
        ratatui::text::Span::raw("MIDDLE-A · FIELD-B · FIELD-C · FIELD-D · FIELD-E · FIELD-F"),
        ratatui::text::Span::raw("\n"),
        ratatui::text::Span::raw("TOKENS-A · COST-B · INPUT-C · OUTPUT-D · LIMIT-E · SESSION-F"),
    ])));
    let width = 80;
    for height_limit in [None, Some(5), Some(4)] {
        let options = ComposerRenderOptions::default();
        let warning_options = ComposerRenderOptions {
            warning_count: 1,
            ..options
        };
        let desired_height = composer.desired_height_with_options(width, options);
        assert_eq!(
            composer.desired_height_with_options(width, warning_options),
            desired_height
        );
        let area = Rect::new(3, 7, width, height_limit.unwrap_or(desired_height));
        let layout = composer.layout_with_options(area, options);
        let warning_layout = composer.layout_with_options(area, warning_options);
        assert_eq!(warning_layout.footer, layout.footer);
        assert_eq!(layout.footer.height, area.height - 3);
        assert_eq!(
            composer.cursor_pos_with_options(area, warning_options),
            composer.cursor_pos_with_options(area, options)
        );
        assert!(composer.cursor_pos_with_options(area, options).is_some());
        let mut baseline = Buffer::empty(area);
        composer.render_with_options(area, &mut baseline, /*mask_char*/ None, options);
        let mut warned = Buffer::empty(area);
        composer.render_with_options(area, &mut warned, /*mask_char*/ None, warning_options);
        let (warning_area, _) = composer
            .warning_notice_layout(inset_footer_hint_area(layout.footer), warning_options)
            .expect("the warning must fit");
        assert_eq!(warning_area.y, layout.footer.bottom() - 1);
        let row = |buffer: &Buffer, y| {
            (area.x..area.right())
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        };
        for y in layout.footer.y..warning_area.y {
            assert_eq!(row(&warned, y), row(&baseline, y));
        }
        if layout.footer.height > 1 {
            let first = row(&warned, layout.footer.y);
            assert!(first.contains("REASONING-E"), "{first:?}");
            assert!(first.contains("Plan mode"), "{first:?}");
            assert_eq!(
                first.find("Plan mode"),
                row(&baseline, layout.footer.y).find("Plan mode")
            );
        }
        let last = row(&warned, warning_area.y);
        assert!(last.contains('⚠'), "{last:?}");
        assert!(last.contains('…'), "{last:?}");
        assert!(!row(&baseline, warning_area.y).contains('⚠'));
        let status_end = warning_area.x.saturating_sub(2);
        let visible_status = (layout.footer.x..status_end)
            .map(|x| warned[(x, warning_area.y)].symbol())
            .collect::<String>();
        assert!(visible_status.contains('…'), "{visible_status:?}");
    }
}

#[test]
fn status_line_keeps_empty_rows_and_right_indicator_on_first_row() {
    let mut composer = composer();
    composer.set_collaboration_modes_enabled(/*enabled*/ true);
    composer.set_collaboration_mode_indicator(Some(CollaborationModeIndicator::Plan));
    composer.set_status_line(Some(Line::from(vec![
        ratatui::text::Span::raw("MODEL"),
        ratatui::text::Span::raw("\n\n"),
        ratatui::text::Span::raw("TOKENS"),
    ])));
    for separate_status_line in [false, true] {
        let options = ComposerRenderOptions {
            separate_status_line,
            ..ComposerRenderOptions::default()
        };
        let width = 80;
        let area = Rect::new(
            0,
            0,
            width,
            composer.desired_height_with_options(width, options),
        );
        let layout = composer.layout_with_options(area, options);
        let status = if separate_status_line {
            layout.status
        } else {
            layout.footer
        };
        assert_eq!(status.height, 3);
        let mut buffer = Buffer::empty(area);
        composer.render_with_options(area, &mut buffer, /*mask_char*/ None, options);
        let row = |y| {
            (0..width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        };
        assert!(row(status.y).contains("Plan mode"));
        assert!(row(status.y + 1).trim().is_empty());
        assert!(row(status.y + 2).contains("TOKENS"));
        assert!(!row(status.y + 2).contains("Plan mode"));
    }
}
