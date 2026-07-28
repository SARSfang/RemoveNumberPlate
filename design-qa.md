# RC5 Design QA

source truth: `docs/design/desktop-preview-workspace-option-2.png`

implementation:

- `docs/audits/v0.2.0-rc.5/implementation-pass-1.png`
- `docs/audits/v0.2.0-rc.5/implementation-pass-2.png`
- `docs/audits/v0.2.0-rc.5/comparison-pass-1.png`
- `docs/audits/v0.2.0-rc.5/comparison-pass-2.png`
- `docs/audits/v0.2.0-rc.5/minimum-window-1040x680.png`
- `docs/audits/v0.2.0-rc.5/zoom-200-equivalent.png`

viewport: 1487 × 1058 CSS px for the full-view comparison; 1040 × 680 for the
minimum supported window; 744 × 530 for the 200% zoom-equivalent resilience pass.
Raster density: 1×. State: active ten-photo batch, result tab, automatic following,
third photo processing.

## Pass 1

The reference and implementation were placed side by side in
`comparison-pass-1.png`. The implementation matched the selected direction:
restrained dark surfaces, one dominant photograph, separate original/result tabs,
right inspector, compact command bar, and bottom filmstrip. Real Lucide assets,
real car imagery, three token layers, and the approved typography hierarchy were
present.

Finding: the minimum-width rule preserved the 1040 layout during a 200% zoom
equivalent, pushing “添加照片” and “进入待复核” outside the visible viewport. This
was an accessibility and responsive-layout defect. The minimum 1040 layout also
needed the disabled add-photo control to remain visible.

Fix: added a compact sub-800 layout in `styles/base.css` and `styles/batch.css`.
It removes the zoom-only minimum dimensions, compacts navigation and the command
bar, keeps add/review actions as icon controls, reduces filmstrip density, and
preserves the single-photo hierarchy.

## Pass 2

`comparison-pass-2.png` repeats the same 1487 × 1058 full-view comparison after
the fix. The wide target fidelity is unchanged. At 1040 × 680 the body width is
exactly 1040 px, the inspector becomes a details drawer, seven thumbnails remain
visible, and add-photo remains a 40 px visible disabled control. At 744 × 530,
representing the effective CSS viewport of 200% zoom, pause, cancel, add photo,
original/result switching, details, and review remain visible with no body
overflow.

Typography and spacing retain the intended restrained hierarchy. Key text
contrast samples range from 5.38:1 to 16.54:1. All visible icons use the bundled
Lucide family. There are no gradients, emoji, inline SVG, decorative CSS art, or
network-loaded assets. The browser console reported no warning or error.

Validated interactions: four primary navigation areas; original/result tabs;
filmstrip selection and pinned mode; automatic-follow restore; zoom controls;
cancel confirmation dialog with initial focus, Escape close, and trigger focus
restore; history filtering and detail selection; settings sections; minimum-width
details drawer and Escape close.

Performance evidence: 100 photos produced 14 filmstrip DOM items with a 13,600 px
virtual track; 500 photos still produced 14 DOM items with a 68,000 px virtual
track. Thumbnail and main-preview LRU limits are covered by state tests.

final result: passed
