# Property Revenue Dashboard fixes

This was a focused debugging pass on the revenue dashboard. I kept the changes close to the existing structure rather than rebuilding the application.

## What I found

The two client reports pointed to separate issues, although they both came from the same revenue request path.

The first thing I checked was how a revenue summary moved from the API to Redis and back again. The cache key only used the property ID. Property IDs are not a safe cache boundary in a multi-tenant system, so a cached result could be returned to a different client when the IDs matched. That explained why a refresh could occasionally show revenue from another company.

I then followed the monthly calculation. The page called itself a monthly dashboard, but the API was summing every reservation for the property. The earlier monthly helper was also only a placeholder, so it never queried the database. On top of that, month boundaries were treated as plain UTC dates even though properties can be in Paris, New York, and other time zones. A booking near midnight could end up in the wrong month.

Finally, the total was converted from a database decimal to a Python float before it was returned to the browser. That is where the small rounding differences came from.

## Root causes and fixes

### Tenant data appearing after a refresh

**Root cause:** Redis cached a summary as `revenue:{property_id}`. The tenant and reporting period were missing from the key.

**Fix:** The cache key now includes tenant ID, property ID, year, and month. The dashboard also takes the tenant only from the authenticated request context. It no longer accepts or sends a client-side tenant simulation header.

### March totals not matching client records

**Root cause:** The dashboard total was not limited to a reporting month. The unfinished monthly helper did not query the database, and month boundaries did not account for the property's timezone.

**Fix:** The dashboard now sends a selected month and year. Revenue is filtered using the property's local timezone, including daylight-saving boundaries. For example, a reservation that starts at 23:30 UTC on 29 February is counted in March for a Paris property because it is already 1 March locally.

### Totals being a few cents off

**Root cause:** Currency values passed through a float before being sent to the frontend.

**Fix:** Database totals stay as `Decimal` values, are rounded once using normal financial half-up rounding, and are returned as fixed two-decimal strings. The API also rejects an attempt to combine multiple currencies rather than silently adding unlike amounts together.

### Database-backed data never being used

**Root cause:** The database pool was assembled from settings that do not exist in this project, and its session getter was declared in a way that prevented use as an async context manager. That caused the service to fall back to hard-coded mock figures.

**Fix:** The pool now uses the configured `DATABASE_URL`, initializes once, and returns a usable async session. The hard-coded fallback figures were removed so a database failure cannot look like real revenue.

### Local backend build timing out

**Root cause:** The backend image installed Python packages with pip's default network timeout. A slow response from PyPI could stop the Docker build even though nothing in the application was wrong.

**Fix:** The Docker build now gives pip a longer timeout and five retries. A temporary download problem should no longer mean starting the build from scratch.

### Dashboard failing after login

**Root cause:** The first database-pool version still passed SQLAlchemy's synchronous `QueuePool` to an async engine. SQLAlchemy rejects that combination, so the dashboard could authenticate successfully but then fail when it tried to load revenue.

**Fix:** The async engine now uses SQLAlchemy's own async-compatible pool. The monthly date condition was also made explicit in the query instead of relying on a nullable SQL parameter whose type PostgreSQL would have to guess.

### Profile page failing even though the request said 200

**Root cause:** The frontend container did not forward `/api` requests to the backend. Nginx served the single-page app HTML for the profile request instead, which explains the misleading 200 response and the profile page failing to read its data.

**Fix:** Nginx now proxies `/api` to FastAPI. The local session also records the expiry from the challenge JWT and validates the existing token when a refresh is requested, so a page reload keeps a valid local session instead of treating it as an incomplete Supabase session.

## Validation completed

I ran the backend syntax check, checked fixed-decimal rounding values, and built the frontend successfully with Vite. The repository-wide frontend lint command still reports a large number of existing issues outside this change, so it is not currently a useful pass/fail check for the dashboard work.
