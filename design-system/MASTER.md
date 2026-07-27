# Remove Number Plate — Desktop Design System

## Product character

A precise, quiet workspace for automotive photographers. The interface should
feel closer to a professional photo utility than an AI demo: content-first,
low-noise, fast, and trustworthy.

## Visual direction

- Dark graphite surfaces reduce glare around photography.
- A cool blue primary color communicates active processing.
- Teal communicates verified completion; amber means human review; red is
  reserved for actionable failures.
- Corners are gently rounded, never pill-shaped except for compact status tags.
- Shadows are restrained. Hierarchy comes from surface tone, spacing, and type.
- No decorative gradients, glass effects, emoji, or novelty AI imagery.

## Semantic color tokens

| Token | Value | Use |
|---|---:|---|
| `canvas` | `#0C111B` | Window background |
| `surface` | `#121A27` | Primary panels |
| `surface-raised` | `#182334` | Cards and selected rows |
| `surface-hover` | `#1D2A3D` | Hover and pressed states |
| `border` | `#2A3850` | Dividers and outlines |
| `text-primary` | `#F4F7FB` | Headings and core values |
| `text-secondary` | `#A9B6C8` | Supporting copy |
| `text-muted` | `#74839A` | Low-priority metadata |
| `primary` | `#4C8DFF` | Primary action and focus |
| `primary-hover` | `#6BA2FF` | Primary action hover |
| `success` | `#35C69A` | Completed and offline |
| `warning` | `#F0B44C` | Needs review |
| `danger` | `#F16B74` | Failed and destructive |

All normal text must meet WCAG 4.5:1 contrast. State is always communicated by
text plus color, never color alone.

## Typography and spacing

- Use the Windows system UI font (`Segoe UI`, `Microsoft YaHei UI` fallback).
- Type scale: 12, 13, 14, 16, 20, 28 px.
- Numeric counters use tabular figures.
- Spacing follows a 4/8 px system: 4, 8, 12, 16, 24, 32, 40.
- Interactive controls are at least 40 px high on desktop, with 8 px separation.

## Layout

- Minimum supported window: 1040 × 680.
- Top navigation remains fixed and contains four peer workspaces:
  批处理、待复核、任务历史、设置.
- Only one workspace is visible at once.
- Main content uses a maximum comfortable width but allows the task table and
  review canvas to grow with the window.
- Dense lists keep 44 px rows and use alternating surface emphasis only when
  it improves scanning.

## Interaction

- Drag-and-drop always has a visible “选择照片” keyboard/mouse alternative.
- Primary feedback appears within 100 ms; long work shows determinate progress.
- Processing never blocks navigation, resize, or image scrolling.
- Focus rings use a 2 px primary outline and are never removed.
- Buttons expose visible hover, pressed, disabled, and keyboard-focus states.
- Destructive cancellation is visually separated from pause/resume.
- Motion is limited to 150–220 ms opacity/color transitions; no decorative
  movement and no layout-shifting animation.

## Page rules

### 批处理

- One dominant drop surface before work begins.
- Show totals as a compact five-card strip: 总计、已完成、待复核、处理中、失败.
- The current filename and total progress remain visible while processing.
- “完全离线” is a persistent trust signal, not marketing decoration.

### 待复核

- Queue and canvas are separate panes; they are not shown beside batch progress.
- Amber identifies pending review.
- Manual tools use one consistent outline-icon family when assets are added.

### 任务历史

- Focus on recoverability and output locations, not analytics.
- Never display or store OCR text.

### 设置

- Present only presets and device status by default.
- Put thresholds and mask geometry under an advanced disclosure.

## Anti-patterns

- No emoji used as structural icons.
- No low-contrast gray-on-gray body copy.
- No invisible drag-only actions.
- No multiple competing primary buttons.
- No modal for primary navigation.
- No model loading or image decoding on the interface thread.
- No unbounded full-resolution thumbnails in list views.
