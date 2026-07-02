# Accessibility Feature Implementation Plan

Status: Implementation planning document for the next pass.

## Objective
Implement the requested accessibility improvements with a focused, maintainable approach that minimizes surface area and preserves existing behavior.

## Scope
This plan covers:
1. Customer note entry (max 50 characters)
2. Order deletion with Cancel/Confirm confirmation
3. Removal of the “View Orders” action from the main UI
4. Removal of the profile link from new-order alerts
5. New-order alert time formatting as HH:MM AM/PM
6. Interactive Name and Comment actions in new-order alerts

## Working Assumptions
- The current bot uses callback-driven Telegram interactions.
- The current storage layer already supports orders and tenant context.
- The current alert formatter can be updated without breaking existing integrations.
- The implementation should stay small and incremental.

## Implementation Order

### Phase 1 — Foundation and low-risk UI changes
1. Remove the “View Orders” button from session/customer navigation.
2. Update the default new-order alert template to remove the profile line.
3. Update the alert timestamp formatting to HH:MM AM/PM.
4. Ensure existing message formatting paths still work with the updated output.

Files likely to change:
- [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- [telegram_bot/config.py](telegram_bot/config.py)
- [telegram_bot/message_builder.py](telegram_bot/message_builder.py)
- [telegram_bot/utils.py](telegram_bot/utils.py)

### Phase 2 — Order deletion flow
1. Add a callback action to request order deletion confirmation.
2. Add a confirmation screen with exactly two buttons:
   - Cancel
   - Confirm
3. Add the actual delete action behind the confirm callback.
4. Ensure deletion is scoped to the right tenant and specific order ID.
5. Return a success or failure message after deletion.

Files likely to change:
- [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py)
- [telegram_bot/database.py](telegram_bot/database.py)

### Phase 3 — Customer note flow
1. Add a callback action for customer note entry.
2. Show a prompt for entering a note.
3. Enforce a max length of 50 characters.
4. Save the note in a customer-related storage field.
5. Confirm success to the user.

Files likely to change:
- [telegram_bot/callback_handler.py](telegram_bot/callback_handler.py)
- [telegram_bot/tenant_store.py](telegram_bot/tenant_store.py)
- [telegram_bot/database.py](telegram_bot/database.py)

### Phase 4 — Interactive order alert actions
1. Add a structured way to attach inline keyboard actions to outgoing alert messages.
2. Make the Name line trigger the customer note flow.
3. Make the Comment line trigger the delete-order confirmation flow.
4. Keep the implementation compatible with the existing alert sender path.

Files likely to change:
- [telegram_bot/message_builder.py](telegram_bot/message_builder.py)
- [telegram_bot/client.py](telegram_bot/client.py)
- [server.py](server.py)
- [telegram_bot/bot.py](telegram_bot/bot.py)

## Recommended Implementation Strategy

### Keep the first version simple
Use the existing callback flow and storage helpers rather than introducing a new subsystem.

Suggested approach:
- Reuse existing callback naming patterns with `btn_*` actions.
- Reuse existing order lookup by `order_id`.
- Reuse existing formatter helpers where possible.
- Add note capability through a lightweight customer metadata field rather than a full database redesign.

### Prefer small, focused changes
Avoid broad refactors at the start. Implement the features in the smallest practical steps:
- First: remove UI items and adjust alert formatting
- Second: add deletion confirmation and actual deletion
- Third: add note storage and prompt flow
- Fourth: attach interactive actions to alert messages

## Callback Design
Use callback payloads that are easy to parse and consistent with the existing code.

Suggested callback names:
- `btn_customer_note|customer_name`
- `btn_customer_note_save|customer_name|note`
- `btn_delete_order_request|order_id`
- `btn_delete_order_confirm|order_id`
- `btn_delete_order_cancel|order_id`

## Data and Storage Notes

### Customer note storage
Recommended minimal approach:
- Add a nullable note field to the customer-facing persistence model if a customer entity already exists.
- If not, store the note in a lightweight metadata field associated with the tenant/session/customer context.

### Order deletion
Recommended minimal approach:
- Delete by `order_id` only.
- Require the tenant context to match before deleting.
- Avoid relying on text-based matching for safety.

## Message Formatting Notes
The alert message should be updated to:
- remove the profile line
- show time in HH:MM AM/PM
- keep the text readable and consistent with Telegram HTML formatting

The interactive actions should be added as inline buttons attached to the message rather than embedded as plain text links.

## Validation Checklist
After implementation, verify the following:
- “View Orders” is no longer shown in the main UI.
- New order alerts no longer include the profile link.
- Alert time is formatted as HH:MM AM/PM.
- The Name field can trigger the customer note flow.
- The Comment field can trigger the confirmation delete flow.
- Notes are saved and capped at 50 characters.
- Cancel leaves the order intact.
- Confirm deletes the intended order.

## Implementation Notes for the Next AI Pass
- Start with the low-risk formatting changes first.
- Then implement delete confirmation.
- Then implement note storage and entry flow.
- Finally wire the inline alert actions.
- Keep each step isolated enough to be tested independently.
