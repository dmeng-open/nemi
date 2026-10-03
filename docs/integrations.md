# Integrations

Nemi runs without these keys. The defaults are `EVENT_PROVIDER=mock`, `PLACE_PROVIDER=mock`, and `CALENDAR_PROVIDER=local`.

Set a provider only when you want that one service. Restart the API after changing `.env`. Do not put secret values in the frontend.

`APP_BASE_URL` is the browser origin Nemi returns to after Google OAuth. The local value is `http://localhost:5173`. The API does not accept an open redirect. The only return paths are `/integrations` and `/plans/{uuid}` for a plan that belongs to the local user.

## Ticketmaster

1. Create a Discovery API key in the Ticketmaster developer portal.
2. Set `TICKETMASTER_API_KEY` to that key.
3. Set `EVENT_PROVIDER=ticketmaster`.
4. Save a home city in Preferences. Coordinates are optional. Nemi does not geocode the city.

A missing key or a failed search does not show demo events.

## Google Places

Places API (New) is billed by Google. A restaurant search is not free, and the monthly allowance is small. Leave this off if you do not want that bill:

```env
PLACE_PROVIDER=mock
GOOGLE_PLACES_API_KEY=
```

Restaurant plans then use the demo catalog. Events and Calendar do not use Places and do not incur a Places charge.

Turn it on only when you accept the cost:

1. Enable Places API (New) and create an API key.
2. Set `GOOGLE_PLACES_API_KEY`.
3. Set `PLACE_PROVIDER=google`.
4. Save both latitude and longitude in Preferences. Restaurant search does not run without them.

The field mask is the explicit place list in the V1 plan. It is never `*`.

## Google Calendar

Google Calendar is separate from Places. The Calendar API does not use a Places key, and connecting your calendar does not turn on restaurant search.

You will not see **Connect** while `CALENDAR_PROVIDER=local`. The Integrations page then says the calendar is Local. That is the current default.

### 1. Create the Google Cloud credentials

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, or pick one you already have.
2. Enable **Google Calendar API** for that project. Do not enable Places.
3. Open **APIs & Services → OAuth consent screen**. Choose External, name the app, and add your own Google account under **Test users**. While the app is in Testing, only those users can connect. You do not need to publish the app.
4. Open **APIs & Services → Credentials → Create credentials → OAuth client ID**.
5. Application type: **Web application**.
6. Authorized redirect URI, exactly:

   `http://localhost:8000/api/integrations/google/calendar/callback`

   That is the API port, not the React port `5173`.
7. Copy the client ID and client secret. They go in `.env` only.

### 2. Point Nemi at those credentials

In `.env`:

```env
CALENDAR_PROVIDER=google
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/google/calendar/callback
APP_BASE_URL=http://localhost:5173
```

Leave `PLACE_PROVIDER=mock` unless you intend to pay for Places. Restart the API after saving `.env`. A running server keeps the old settings until it restarts.

### 3. Connect your account

1. Open `http://localhost:5173/integrations`.
2. The calendar row should say **Not connected**, with a **Connect** button. If it still says **Local**, the API did not pick up `CALENDAR_PROVIDER=google`.
3. Choose **Connect** and sign in as the test user you added. Allow access to calendar events.
4. Google sends you back to Integrations. The row says **Connected**. Nemi does not show your email, because it does not request an email scope.

After that, approve a plan with **Add to schedule**. Nemi reads your primary calendar for conflicts and creates one event there. Approving the same plan again does not create a second event. If Google cannot save it, the plan stays unscheduled and offers **Download .ics**.

The local list on the Integrations page is a notebook. Those sample rows are not your Google events while `CALENDAR_PROVIDER=google`.

The requested scope is only `https://www.googleapis.com/auth/calendar.events`. Nemi does not request `openid` or `email`. Connected is shown without an account email.

The refresh token is stored in local Postgres as plaintext and is read only through `OAuthConnectionRepository`. Responses and logs do not include it. This is acceptable for one local user. It is not production encryption.

The local calendar list remains a notebook. Those rows are not Google busy time while `CALENDAR_PROVIDER=google`.

## What stays local

`GET /api/integrations` reports connection state from settings and the last real call. It does not probe Ticketmaster, Places, or Google.

If a real provider misbehaves, set that one variable back to `mock` or `local` and restart.
