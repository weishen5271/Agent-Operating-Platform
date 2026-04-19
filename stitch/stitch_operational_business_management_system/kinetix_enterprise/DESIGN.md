# Design System Specification: The Precision Architect

## 1. Overview & Creative North Star
The "Precision Architect" is the creative North Star for this design system. Traditional enterprise systems often fall into the trap of "grid-lock"—a rigid, flat, and uninspired collection of boxes. This system breaks that template by treating the interface as high-end digital architecture. 

We move beyond the "standard" blue-and-white dashboard by introducing **Tonal Depth** and **Editorial Hierarchy**. By utilizing intentional asymmetry, overlapping surfaces, and a sophisticated layering of whites and blues, we create an environment that feels authoritative yet breathable. We are not just building a tool; we are designing a professional workspace that commands respect and minimizes cognitive load through structural clarity.

---

## 2. Colors
Our palette is rooted in a professional blue (#005daa) but finds its soul in the nuances of the neutral scales.

*   **Primary Roles:** Use `primary` (#005daa) for high-impact actions and `primary_container` (#0075d5) for supporting interactive elements.
*   **The "No-Line" Rule:** To achieve a premium, custom look, **1px solid borders are prohibited for sectioning.** Boundaries must be defined through background shifts. For example, a sidebar navigation should use `surface_container_low`, while the main content area sits on `surface`. This creates a natural, soft-edge transition that feels modern and integrated.
*   **Surface Hierarchy & Nesting:** Treat the UI as physical layers. 
    *   The base canvas: `surface` (#f7f9fc).
    *   Main content cards: `surface_container_lowest` (#ffffff).
    *   Deep nested elements (like inner table headers): `surface_container_high` (#e6e8eb).
*   **The "Glass & Gradient" Rule:** Floating elements, such as top headers or dropdown menus, should utilize Glassmorphism. Use `surface_container_lowest` with a 70% opacity and a `20px` backdrop-blur. 
*   **Signature Textures:** For primary Action Buttons or Hero Data Cards, use a subtle linear gradient (45deg) from `primary` to `primary_container`. This adds a "lithographic" quality that flat colors cannot replicate.

---

## 3. Typography
For a Chinese-language enterprise system, typography must balance the density of Hanzi characters with the clarity of technical data.

*   **Typeface Pairing:** Use `Inter` for all numerical data and Latin characters to ensure high readability in tables. For Chinese text, prioritize `PingFang SC` or `Noto Sans SC`.
*   **Display & Headline:** Use `display-sm` (2.25rem) for main page titles. This "Editorial" scale creates an immediate sense of hierarchy, making the page feel like a professional report rather than a generic app.
*   **Data Density:** For tables and forms, `body-md` (0.875rem) is the standard. Use `label-md` (0.75rem) in `on_surface_variant` (#404753) for secondary metadata to keep the interface from feeling "noisy."
*   **Line Height:** For Chinese body text, always increase the line height to 1.6x to prevent the "dense block" effect common in enterprise software.

---

## 4. Elevation & Depth
We abandon the "drop shadow" of the 2010s in favor of **Tonal Layering**.

*   **The Layering Principle:** Depth is achieved by stacking tiers. A `surface_container_lowest` card placed on a `surface_container_low` background provides sufficient visual separation without the need for high-contrast lines.
*   **Ambient Shadows:** When a floating state is required (e.g., a Modal or a Popover), use a multi-layered ambient shadow:
    *   `box-shadow: 0 4px 20px 0 rgba(25, 28, 30, 0.04), 0 12px 40px 0 rgba(25, 28, 30, 0.08);`
    *   The shadow color is derived from `on_surface` to keep it natural.
*   **The "Ghost Border" Fallback:** If a border is required for accessibility in dense forms, use the `outline_variant` (#c0c7d6) at 20% opacity. This creates a "Ghost Border" that guides the eye without cluttering the layout.
*   **Glassmorphism:** Use for the Sidebar or Top Header to allow the "architectural" layers to bleed through, softening the interface's edges.

---

## 5. Components

### Buttons
*   **Primary:** Gradient of `primary` to `primary_container`. `md` roundedness (0.375rem). No border.
*   **Secondary:** `surface_container_highest` background with `on_surface` text.
*   **Tertiary:** No background. `primary` text. Use for low-emphasis actions like "Cancel."

### Input Fields & Forms
*   **Structure:** Forbid 100% opaque borders. Use `surface_container_high` as the background for input fields to create a "recessed" look.
*   **Active State:** Transition the background to `surface_container_lowest` and apply a `Ghost Border` using the `primary` color at 40% opacity.

### Data Tables (The "Ledger")
*   **Header:** `surface_container_high` with `label-md` uppercase text.
*   **Rows:** No horizontal dividers. Use a subtle `surface_container_low` background change on `:hover`.
*   **Spacing:** Use `lg` (0.5rem) vertical padding to give Hanzi characters room to breathe.

### Chips & Tags
*   **Style:** Use `secondary_container` with `on_secondary_container` text. Apply `full` roundedness (9999px) for a soft, pill-shaped aesthetic that contrasts against the structured grid.

### Tooltips
*   **Style:** `inverse_surface` background with `inverse_on_surface` text. Apply `sm` roundedness (0.125rem) to keep them feeling precise and technical.

---

## 6. Do's and Don'ts

### Do
*   **DO** use whitespace as a separator. If you feel the need for a line, try adding 16px of padding instead.
*   **DO** use `primary_fixed` for background highlights in selected states (e.g., a selected row in a table).
*   **DO** ensure all numerical data is monospaced or uses `Inter` to keep columns aligned in tables.
*   **DO** use the `xl` roundedness (0.75rem) for large container cards to soften the enterprise feel.

### Don't
*   **DON'T** use pure black (#000000) for text. Always use `on_surface` (#191c1e) to maintain a premium, ink-on-paper feel.
*   **DON'T** use 1px solid #DDD or #EEE borders. This is the hallmark of a "generic" system. Refer to the "No-Line" Rule.
*   **DON'T** crowd the sidebar. Use `title-sm` for category headers with generous top-margin to create clear, scannable sections.
*   **DON'T** use high-saturation red for error states. Use the sophisticated `error` (#ba1a1a) and `error_container` (#ffdad6) tokens to keep the UI professional even during alerts.