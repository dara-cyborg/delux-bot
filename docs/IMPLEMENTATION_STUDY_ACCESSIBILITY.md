# Accessibility Feature Implementation Study

Status: Study and implementation guidance only. No code changes yet.

## Goal
This document maps the proposed accessibility improvements onto the current Telegram bot codebase and identifies the lowest-risk, most maintainable implementation strategy.

## Current Architecture Snapshot
The bot currently has three main areas that matter for these features:

1. Message rendering
   - [telegram_bot/message_builder.py](telegram_bot/message_builder.py)
   - Responsible for formatting alert text.

2. Callback handling
   - [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
   - Responsible for menu navigation and button-driven flows.

3. Persistence and storage
   - [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py)
   - [telegram_bot/storage.py](telegram_bot/storage.py)
   - [telegram_bot/database.py](telegram_bot/database.py)
   - Responsible for orders, sessions, tenants, and future note persistence.

4. Webhook and alert delivery
   - [server.py](server.py)
   - Sends alerts to Telegram using the current message template.

## Impact Analysis

### 1) Customer note feature
Impact areas:
- Customer navigation flow in [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- Customer listing and order detail screens in the same module
- Storage layer in [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py) and [telegram_bot/database.py](telegram_bot/database.py)

Why it impacts multiple layers:
- The current UI is callback-driven, so a note feature needs a new callback path.
- The current storage model has order records but no dedicated customer note field.

Recommended implementation approach:
- Add a lightweight note field to the customer-facing storage model instead of creating a large new subsystem.
- Keep the feature scoped to a single callback flow: customer -> add note -> save -> confirm.
- Avoid introducing a fully separate domain layer unless the app already needs richer customer profiles.

### 2) Delete order with confirmation
Impact areas:
- [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py)
- [telegram_bot/database.py](telegram_bot/database.py)

Why this is feasible:
- The app already has a callback-driven interaction pattern.
- The persistence layer already supports fetching and updating orders.
- The missing piece is a safe delete operation and a confirmation state.

Recommended implementation approach:
- Use a simple two-step callback pattern:
  - request confirmation
  - confirm or cancel
- Keep the delete operation scoped to the specific `order_id` to avoid accidental deletion.
- Reuse the existing callback data builder in [telegram_bot/utils.py](telegram_bot/utils.py) so callback payloads stay compact and safe.

### 3) Remove “View Orders”
Impact areas:
- [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- Possibly [telegram_bot/commands.py](telegram_bot/commands.py)

Why this is low-risk:
- The current menu contains an explicit “View Orders” button in the session detail view.
- Removing it does not require data model changes.

Recommended implementation approach:
- Remove the button from the relevant callback response payloads.
- Leave the underlying order listing logic in place in case it is still useful for future admin flows, but stop exposing it in the main UI.

### 4) Remove profile link from new order alerts
Impact areas:
- [telegram_bot/config.py](telegram_bot/config.py)
- [telegram_bot/message_builder.py](telegram_bot/message_builder.py)
- [server.py](server.py)

Why this is straightforward:
- The alert text is already assembled in one formatter.
- The profile URL remains available in storage and can be ignored by the alert formatter.

Recommended implementation approach:
- Change the default template and the formatter logic so the “Profile” line is not emitted.
- Keep the current argument signature stable to avoid breaking existing callers.

### 5) New order timestamp formatting
Impact areas:
- [telegram_bot/utils.py](telegram_bot/utils.py)
- [telegram_bot/message_builder.py](telegram_bot/message_builder.py)

Why this is simple:
- The repository already has a formatter for local time in [telegram_bot/utils.py](telegram_bot/utils.py).
- The current implementation already formats timestamps to a compact local time style.

Recommended implementation approach:
- Extend the existing formatter to support a dedicated “alert time” format for this use case.
- Prefer a shared helper rather than duplicating formatting logic inside the alert builder.

### 6) Interactive Name and Comment actions in new order alerts
Impact areas:
- [telegram_bot/message_builder.py](telegram_bot/message_builder.py)
- [telegram_bot/client.py](telegram_bot/client.py)
- [server.py](server.py)
- [telegram_bot/bot.py](telegram_bot/bot.py)

Why this is more involved:
- Telegram inline actions require the message sender to attach a keyboard payload to the outgoing message.
- The current send path supports button-based messages, but the alert builder currently only returns plain text.

Recommended implementation approach:
- Keep the alert text rendering simple and add an optional inline keyboard payload alongside it.
- Avoid hardcoding button behavior inside message formatting alone; instead, pass structured action metadata to the sender layer.
- A small action envelope object would be more maintainable than embedding raw Telegram button JSON directly into the template text.

## Recommended Design Direction
The most maintainable path is to introduce a light “action-aware message” layer rather than mixing UI, formatting, and callback logic in a single function.

Recommended structure:
- Keep the text builder focused on plain message formatting.
- Add a small helper that returns:
  - text
  - inline keyboard buttons
  - action metadata
- Let the server or bot layer send the final Telegram payload.

This approach is scalable because it keeps future interactive alert features easy to add without rewriting the existing formatter.

## Suggested Minimal Architecture

### Option A: Minimal change, good maintainability
Use the current formatter and add optional callback metadata for the Name and Comment fields.

Pros:
- Smallest code footprint
- Reuses existing flow and message sending structure
- Easy to test

Cons:
- Slightly more coupling between message building and Telegram-specific UI details

### Option B: Slightly more structured, better long-term extensibility
Introduce a small message payload object that contains:
- text
- inline keyboard buttons
- optional alert action metadata

Pros:
- Cleaner separation of concerns
- Easier to add future actions such as “open customer summary”, “add note”, “mark order”, etc.
- Better scaling for multi-feature UI growth

Cons:
- Slightly more code upfront

Recommendation:
- Choose Option B if the team expects more interactive alert features in the future.
- Choose Option A if the priority is rapid delivery with limited change surface.

## Storage Recommendations

### Notes storage
The most maintainable approach is to add a light note field to the customer-related storage model rather than introducing a new top-level subsystem immediately.

Suggested direction:
- Add a nullable `note` column to customer-oriented records if the app already stores a customer entity.
- If the current model only persists orders, the simplest path is to store a note in a lightweight metadata field associated with the customer name and tenant/session context.

This keeps the implementation efficient while avoiding premature schema complexity.

### Order deletion
The delete operation should be implemented as a targeted delete using the unique `order_id` field.

Recommended guardrails:
- Delete only when the callback payload and current tenant match the intended order.
- Return a clear success or error message after deletion.
- Avoid deleting by comment text alone because that is not unique and can be unsafe.

## Callback Design Recommendations
The current callback handler already uses action-based payloads, so the new features can fit naturally into that model.

Suggested callback naming pattern:
- `btn_customer_note|tenant_id|customer_name`
- `btn_note_save|order_id|note`
- `btn_delete_order_request|order_id`
- `btn_delete_order_confirm|order_id`
- `btn_delete_order_cancel|order_id`

This keeps the pattern consistent with the existing `btn_*` style and avoids introducing a second callback convention.

## Testing Implications
The implementation should be tested in three layers:

1. Message formatting
   - Ensure the new alert text no longer contains the Profile line.
   - Ensure the time is formatted correctly.

2. Callback handling
   - Ensure confirmation flow works as intended.
   - Ensure cancel exits safely.

3. Persistence
   - Ensure notes save correctly.
   - Ensure delete operations remove the intended order only.

## Implementation Risk Assessment

### Low risk
- Removing “View Orders”
- Removing the profile line from alerts
- Formatting the timestamp

### Medium risk
- Adding note storage
- Adding delete confirmation callbacks

### Higher risk
- Making the alert fields interactive with Telegram inline buttons

This risk ordering suggests a phased implementation:
1. Remove UI elements and adjust template formatting
2. Add note persistence and delete confirmation
3. Add interactive button actions to alert messages

## Suggested Next Step
The next implementation pass should focus on a single coherent slice:
- add order deletion confirmation first
- add note storage second
- wire interactive alert actions third

That order keeps the work manageable and allows validation after each feature.
