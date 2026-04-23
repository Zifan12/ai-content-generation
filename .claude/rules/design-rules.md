# Design Rules

Use this file only for UI/design tasks.

## Goals
- Prioritize clarity, hierarchy, and fast decision-making.
- Keep interfaces focused on the current workflow step.
- Optimize for desktop first, but keep layouts responsive.

## Visual System
- Define tokens first: colors, spacing, radius, shadows, typography scale.
- Reuse tokens consistently; avoid one-off styles.
- Use high-contrast text and controls.
- Limit the palette to neutrals plus one accent and one semantic error color.

## Layout
- Prefer simple page structure: header, primary content area, right rail or footer actions.
- Keep related actions near the data they modify.
- Keep dense tables scannable with consistent alignment and spacing.
- Avoid deep nesting of cards inside cards.

## Components
- Buttons must have clear intent labels (for example: "Approve Trend", not "Submit").
- Dangerous actions require clear styling and confirmation.
- Forms should show inline validation and sensible defaults.
- Empty/loading/error states must be explicitly designed.

## Content and Copy
- Use short, specific labels and helper text.
- Prefer actionable error messages that explain next steps.
- Avoid vague wording like "Something went wrong."

## Motion and Feedback
- Keep transitions quick and subtle.
- Show immediate feedback for long-running actions.
- Use progress states for generation and provider calls.

## Accessibility
- Meet keyboard navigation basics for all primary actions.
- Ensure visible focus state on interactive elements.
- Avoid color-only signals; include text or icons.

## Responsiveness
- Validate layouts at 360px, 768px, and 1280px widths.
- Collapse secondary panels on smaller screens.
- Keep primary actions reachable without horizontal scrolling.

## Review Checklist
- Is the primary action obvious in under 3 seconds?
- Can user recover from any error state?
- Is there unnecessary visual noise to remove?
- Are spacing and typography tokens applied consistently?
