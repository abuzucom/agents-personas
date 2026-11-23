# Button component spec

Primary action button.

## States
- default: background `color-action-primary`, label `text-on-action`
- hover: background `color-action-primary-hover`
- focus: 2px `color-focus-ring` outline, visible
- disabled: background `color-action-disabled`, `cursor: not-allowed`, not focusable
- error: 1px `color-border-error` border

## Tokens
```json
{
  "color-action-primary": "#1d4ed8",
  "color-action-primary-hover": "#1e40af",
  "color-on-action": "#ffffff",
  "color-focus-ring": "#f59e0b",
  "color-action-disabled": "#9ca3af",
  "color-border-error": "#dc2626"
}
```
