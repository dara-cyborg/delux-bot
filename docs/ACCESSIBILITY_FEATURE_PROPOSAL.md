# Accessibility Feature Proposal

Status: Proposed only. No implementation changes yet.

## Summary
This proposal adds new accessibility and interaction improvements to the Telegram bot experience:

1. Users can add a short note to any customer, capped at 50 characters.
2. Users can delete an order from a customer’s order list through a two-step confirmation flow.
3. The old “View Orders” action is removed from the UI.
4. New live-order alerts no longer include a profile link.
5. New live-order alert timestamps are displayed as HH:MM AM/PM.
6. The Name and Comment fields in the new-order alert become interactive actions.

## Proposed UX Changes

### 1) Customer notes (max 50 chars)
- When a user taps a customer entry, the bot opens a customer action flow.
- The primary action is “Add Note”.
- The bot prompts the user to enter a note.
- The note is stored against the customer record.
- If the note exceeds 50 characters, the bot rejects it and asks the user to shorten it.

Suggested interaction:
- Customer button -> open customer action menu
- Action: Add Note
- Follow-up: ask for note input
- Save: store note and confirm success

### 2) Delete order with confirmation
- When a user taps an order entry, the bot shows a confirmation prompt.
- The confirmation UI contains exactly two buttons:
  - Cancel
  - Confirm
- If Cancel is pressed, the action is aborted.
- If Confirm is pressed, the order is deleted and the user receives confirmation.

Suggested callback flow:
- `btn_delete_order_request|order_id`
- `btn_delete_order_confirm|order_id`
- `btn_delete_order_cancel|order_id`

### 3) Remove “View Orders”
- Remove the “View Orders” button from session/customer navigation.
- Avoid exposing any standalone “View Orders” screen in the bot menu.
- Any customer-related action should flow through the new customer note and order actions instead.

### 4) Remove profile link from new order alerts
- The default order alert template should no longer include a Profile line.
- The related profile URL field can remain in storage for compatibility, but it should not be displayed in the alert message.

### 5) New order timestamp formatting
- Format the order alert time as HH:MM AM/PM.
- Example: `09:35 PM` instead of the current full timestamp.

### 6) Make Name and Comment interactive in new order alerts
- The Name line becomes a button-like action that opens the customer-focused flow.
- The Comment line becomes a button-like action that opens the delete-order confirmation flow.
- This can be implemented with Telegram inline keyboard buttons attached to the alert message.

## Proposed Message Structure

Current style:
- New Live Order
- Name: <customer>
- Comment: <comment>
- Profile: <url>
- Time: <full timestamp>

Proposed style:
- New Live Order
- Name: <customer>  [interactive action]
- Comment: <comment>  [interactive action]
- Time: HH:MM AM/PM

## Proposed Backend Changes

### Data model
- Add a customer note field or a dedicated notes table.
- Recommended minimal approach: add a `note` column to the customer storage layer if the database already stores customer data.
- If customer storage is normalized across tenants/sessions, a dedicated table keyed by tenant/session/customer is cleaner.

### Callback handling
- Add new callback handlers for:
  - customer note entry
  - note save
  - delete-order request
  - delete-order confirm
  - delete-order cancel

### Message rendering
- Update the alert template builder so it:
  - removes the Profile line
  - formats the time as HH:MM AM/PM
  - attaches inline keyboard actions to the Name and Comment lines

## Suggested Implementation Plan

### Phase 1 – UI and flow
- Remove the “View Orders” button from session/customer navigation.
- Add the customer note action flow.
- Add the order delete confirmation flow.

### Phase 2 – Alert message behavior
- Update the order alert template.
- Remove the Profile line.
- Apply HH:MM AM/PM formatting.
- Attach inline actions for Name and Comment.

### Phase 3 – Persistence and safety
- Store customer notes safely.
- Ensure delete actions only affect the intended order.
- Add validation for note length and confirmation flow.

## Acceptance Criteria
- A customer can be tapped to begin adding a note.
- Notes are saved and enforced to a maximum of 50 characters.
- An order can be deleted only after the user confirms via Cancel/Confirm.
- The old “View Orders” entry is no longer shown.
- New order alerts do not include the Profile line.
- New order alerts display time as HH:MM AM/PM.
- The Name and Comment fields in a new order alert are interactive.

## Open Questions
- Should the Name action open a customer note screen only, or a customer detail screen that also includes order history?
- Should notes be stored per customer globally or per tenant/session/customer combination?
- Should the same inline action pattern be used for other bot messages beyond new-order alerts?

## Notes for the Next Implementation Pass
- This proposal intentionally keeps the scope focused on the requested accessibility improvements.
- The implementation should be done in small steps so each interaction can be tested independently.
- The current code paths most likely to change are the alert formatter, the callback handler, and the customer/order storage layer.
