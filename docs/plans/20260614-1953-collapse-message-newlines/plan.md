# Collapse multiple newlines in rendered message text

## Problem

Some users post messages containing runs of newlines, e.g.
`"Watching the World Cup\n\n\n\n\n\nOf Darts"`. The messages view renders the
message body with `white-space: pre-wrap` (table cell, line 339) and
`whitespace-pre-wrap` (mobile card, line 306), so the embedded newlines are
preserved and blow up the row/card height, breaking the table layout.

We want the body to render as `"Watching the World Cup Of Darts"` — i.e.
collapse any run of one-or-more newlines (and surrounding whitespace) down to a
single space when displaying.

## Scope

Display-only normalization on the messages page. We do **not** alter stored
message data — the raw text in the DB/API is untouched; only the rendered
string changes.

## Affected code

- `src/meshcore_hub/web/static/js/spa/pages/messages.js`
  - `messageTextWithSender(msg, text)` (lines ~106-118) builds the final
    display string used by both the mobile card (`displayMessage`, line 274)
    and the desktop table row (`displayMessage`, line 319). This is the single
    chokepoint for the displayed body.

## Approach

Add a small whitespace-normalizing helper and apply it to the body inside
`messageTextWithSender` so both render paths benefit from one change.

1. Add a helper near the other text helpers in `messages.js`:

   ```js
   // Collapse any run of newlines (and the whitespace around them) into a
   // single space so multi-line messages don't blow up the table/card layout.
   function collapseNewlines(text) {
       if (!text || typeof text !== 'string') return text;
       return text.replace(/\s*\n\s*/g, ' ');
   }
   ```

   Notes on the regex:
   - `\s*\n\s*` matches each newline plus adjacent spaces/tabs/newlines, so a
     run like `\n\n\n\n` collapses to one space (the `\s*` on both sides
     absorbs the intermediate newlines), and a single `\n` also becomes one
     space. This satisfies the example exactly.
   - It deliberately leaves single spaces between words alone (no aggressive
     `\s+` collapse) to avoid changing intentional spacing.

2. Apply it in `messageTextWithSender` to the computed `body`:

   ```js
   const body = collapseNewlines((parsed.text || text || '-').trim()) || '-';
   ```

   The sender-prefix logic (`${sender}: ${body}`) stays as-is and now operates
   on the single-line body.

## Why here (and not in CSS or the API)

- CSS alone (`white-space: normal`) would collapse newlines visually but the
  `pre-wrap` is intentional for legitimate wrapping; switching it wholesale
  risks other formatting. Normalizing the string is more precise and matches
  the requested output exactly.
- Doing it in the API/DB would lose the original text and affect non-display
  consumers (e.g. packet detail). This is purely a presentation concern for the
  messages list.

## Build / artifacts

The SPA is bundled with esbuild (`npm run build` → `node build.js`), output to
`src/meshcore_hub/web/static/dist/`. After editing the source `messages.js`,
run the build so the hashed `dist/chunks/messages.*.js` is regenerated.

## Testing / verification

- Manual: load the messages view with a message containing multiple newlines
  (or temporarily inject one) and confirm it renders on a single line as
  `"Watching the World Cup Of Darts"` in both the desktop table and the mobile
  card.
- Confirm normal single-line messages and sender-prefixed messages
  (`@[name]: ...`) still render unchanged.
- Spot-check that channel-label parsing (`[label] body`) is unaffected, since
  `channelInfo` runs before `messageTextWithSender`.

## Out of scope

- Changing stored message text.
- Other views that display message text (packet detail, dashboards), unless a
  follow-up reports the same layout issue there.
