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

1. Enable Places API (New) and create an API key.
2. Set `GOOGLE_PLACES_API_KEY`.
3. Set `PLACE_PROVIDER=google`.
4. Save both latitude and longitude in Preferences. Restaurant search does not run without them.

The field mask is the explicit place list in the V1 plan. It is never `*`.

## Google Calendar

1. In Google Cloud, create an OAuth client for a web application.
2. Set the authorized redirect URI to `http://localhost:8000/api/integrations/google/calendar/callback`.
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` to that same callback.
4. Set `CALENDAR_PROVIDER=google`.
5. Open Integrations and choose Connect.

The requested scope is only `https://www.googleapis.com/auth/calendar.events`. Nemi does not request `openid` or `email`. Connected is shown without an account email.

The refresh token is stored in local Postgres as plaintext and is read only through `OAuthConnectionRepository`. Responses and logs do not include it. This is acceptable for one local user. It is not production encryption.

The local calendar list remains a notebook. Those rows are not Google busy time while `CALENDAR_PROVIDER=google`.

## What stays local

`GET /api/integrations` reports connection state from settings and the last real call. It does not probe Ticketmaster, Places, or Google.

If a real provider misbehaves, set that one variable back to `mock` or `local` and restart.
