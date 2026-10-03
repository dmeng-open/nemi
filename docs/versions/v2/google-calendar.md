# Google Calendar

Google Calendar is optional. The default is `CALENDAR_PROVIDER=local`, which never calls Google. The client secret stays in the API process. The React app only receives an authorization URL.

Connection state is on Integrations: **Connected** when `oauth_connections` has a Google row for the local user, otherwise **Not connected** and **Connect Google Calendar**. You will not see Connect while the provider is `local`.

## Google Cloud setup

1. Create or select a project in [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Google Calendar API**. Places API is unrelated. Enabling it is not required for calendar reads or writes.
3. Configure the OAuth consent screen. For an app in Testing, add your Google account as a test user.
4. Create an OAuth client ID of type **Web application**.
5. Add this authorized redirect URI exactly:

   `http://localhost:8000/api/integrations/google/calendar/callback`

   That is the API port, not the Vite port.

6. Put the client id and secret in `.env` only. Do not commit them and do not put them in frontend code.

## Environment

```env
CALENDAR_PROVIDER=google
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/google/calendar/callback
APP_BASE_URL=http://localhost:5173
```

Restart the API after changing `.env`. `APP_BASE_URL` is the browser origin used after OAuth. Return paths are limited to `/integrations` and `/plans/{uuid}` for a plan that belongs to the local user.

The requested scope is `https://www.googleapis.com/auth/calendar.events`. Nemi does not request `openid` or `email`.

## Local flow

1. Open `http://localhost:5173/integrations`.
2. Choose **Connect** and sign in as a test user.
3. Google redirects to the API callback. The API exchanges the code, stores the refresh token, and redirects the browser back to Integrations.
4. The calendar row reads **Connected**.

The refresh token is plaintext in `oauth_connections`, read only through `OAuthConnectionRepository`. Responses and logs do not include it. That is a single-user local choice, not production encryption.

`GET /api/integrations` does not call Google. It reports the stored connection.

## Reads

`GoogleCalendarProvider.get_events` lists primary-calendar events for a timezone-aware window. Timed events, all-day events, and cancelled events are handled in `_map_event`. Cancelled events and transparent events are dropped. All-day events become midnight-to-midnight blocks in the plan timezone. Google’s payload does not leave the provider. Callers see `CalendarEvent`.

Empty calendars return an empty list. HTTP 401 refreshes the access token once. `invalid_grant` does not create events. Timeouts and 429 or 5xx responses use the provider retry helper. 400, 401 after refresh, and 403 do not retry.

V2 calendar analysis calls this read, then `free_windows_for_range`, which is ordinary interval code.

## Writes

Only the execution agent creates events, and only after approval. Inserts are idempotent: the idempotency key is the Google event id. A second insert of the same key resolves to the existing event.

V2 writes one event for the meal and one for the activity. See [execution-safety.md](execution-safety.md).

A confirmed cancel deletes those events by id. Unconfirmed cancels do not.

## Common errors

| What you see | Likely cause |
| --- | --- |
| Integrations still says Local | `CALENDAR_PROVIDER` is not `google`, or the API was not restarted |
| Not connected, no Connect button | OAuth client id or secret is empty |
| Redirect mismatch | Redirect URI in Google Cloud is not the API callback above |
| Access blocked | The Google account is not a test user while the app is in Testing |
| Connect failed | The code was reused, the state expired, or the return path was not allowlisted |
| Could not add this to your schedule | Calendar read failed, the token was revoked, or the insert was not confirmed |

More provider context is in [integrations.md](../v1/integrations.md).
