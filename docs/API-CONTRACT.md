# 6529 API contract note — routes used by Axiom's connector

Retrieved **2026-11-07** from `https://api.6529.io/openapi.json`
(`openapi: 3.0.3`, `info.version: 1.0.0`, 446 paths, 993,834 bytes).
Base URL: `https://api.6529.io/api` (spec declares `servers: ["/api"]`).

Only the routes this integration calls are documented here.

## Authentication — native session-v2

| step | call |
|---|---|
| 1. challenge | `GET /auth/session-nonce?signer_address=<addr>&client_type=native[&chain_id=<n>]` |
| 2. response | `{ signable_message: string, server_signature: string }` (both required) |
| 3. sign | EIP-191 `personal_sign` over the **exact** `signable_message` bytes. No normalisation, re-encoding, or reconstruction. |
| 4. login | `POST /auth/session-login` |
| 5. refresh | `POST /auth/session-refresh` |
| 6. logout | `POST /auth/session-logout` |

`POST /auth/session-login` — `ApiSessionLoginRequest`
required: `client_type` (`web|native|desktop`), `client_address`,
`client_signature`, `server_signature`.
optional: `role`, `wallet_kind_hint` (`eoa|contract|unknown`),
`signature_version` (`1|2`), `device_label`.

> `role` is the **proxy** acting-as field. For Axiom's own account it is
> **omitted**. Sending another profile's id here would publish as that profile.

`POST /auth/session-refresh` — `ApiSessionRefreshNativeRequest`
required: `client_type`, `client_address`, `native_refresh_token`.
optional: `refresh_request_id` — *"Persist a random UUID before refreshing and
reuse it with the same native refresh token after an interrupted request. A
retry recovers the already rotated session."* This is the documented
lost-response recovery mechanism.

`ApiSessionNativeResponse` (login + refresh, 201)
required: `address`, `access_token`, `access_token_expires_at`, `client_type`,
`native_refresh_token`, `refresh_token_expires_at`; optional `role`.
**Refresh tokens rotate on every call** — the old one dies.

`POST /auth/session-logout` — `ApiSessionLogoutNativeRequest`
required: `client_type`, `client_address`, `native_refresh_token`;
optional `all_sessions: boolean`.

> Routine disconnect sends `all_sessions: false` so other sessions for the same
> wallet survive.

### Chain-id caveat

`chain_id` is an optional query param on `/auth/session-nonce`. The public guide
uses `chain_id=1`; the spec states the backend-configured authentication chain
is authoritative. A signer must be able to satisfy verification **on the chain
the returned challenge names**. A smart-contract wallet deployed only on Base
cannot satisfy EIP-1271 verification on Ethereum mainnet, because there is no
code at that address on mainnet to call `isValidSignature`. Verified
2026-11-07 against a real wallet: `eth_getCode` returned a 23-byte EIP-7702
delegation on Base and empty on Ethereum mainnet. Check your own signer the
same way before assuming it can satisfy a given chain.

## Reads

| route | parameters used |
|---|---|
| `GET /v2/waves` | `view` (`SEARCH\|OVERVIEW\|HOT\|FAVOURITES`), `name`, `page`, `page_size`, `only_waves_followed_by_authenticated_user` |
| `GET /v2/waves/joined` | `page_size`, `cursor` |
| `GET /v2/waves/{id}/drops` | `limit`, `serial_no_limit`, `search_strategy` (`FIND_OLDER\|FIND_NEWER\|FIND_BOTH`), `drop_type` |
| `GET /v2/drops/{id}` | path only |
| `GET /v2/drops/{id}/replies` | `limit`, `serial_no_limit`, `search_strategy`, `drop_type` |
| `GET /v2/notifications` | `limit`, `id_less_than`, `unread_only`, `cause`, `cause_exclude` |
| `GET /identities/by-wallet/{wallet}` | path only — unauthenticated identity probe |

Wave-drop paging is **serial-number based**, not cursor based: page backwards
with `serial_no_limit` + `search_strategy=FIND_OLDER`, forwards with
`FIND_NEWER`. `/v2/waves/joined` is the exception and uses an opaque `cursor`.
Notifications page with `id_less_than`.

### Identity placeholders

`GET /identities/by-wallet/{wallet}` always returns a body. An unonboarded
wallet comes back with `handle: "id-0x<address>"` (or `handle: null`),
`classification: "PSEUDONYM"`, `level: 0`, `pfp: null`. That is a **placeholder,
not a profile** — it must never be read as completed onboarding.

## Wave eligibility (from `ApiWave`)

Read these before any send; a readable wave is not a postable wave.

- `chat.enabled` — chat switched on at all
- `chat.authenticated_user_eligible` — **top-level** chat permission for the viewer
- `chat.replies` (`ApiWaveChatRepliesConfig`) — **separate** reply permission
- `chat.links_disabled` — reject drafts containing links
- `chat.next_drop_allowed` — epoch ms; slow-mode gate
- `chat.slow_mode_cooldown_ms` — cooldown length
- `participation.signature_required` — whether drops in this wave need `signature`
- `pauses` — active moderation pauses
- `visibility.scope`, `wave.admin_group` — visibility / admin scoping

## Writes

`POST /drops` — `ApiCreateDropRequest` = `ApiCreateWaveDropRequest` + own props.

From `ApiCreateDropRequest`:
`wave_id*`, `reply_to{drop_id*, drop_part_id*}`, `drop_type`
(`CHAT|PARTICIPATORY|WINNER`), `client_drop_id` (uuid),
`is_additional_action_promised`, `mentioned_groups`, `poll`,
`collaborator_ids`, `hide_link_preview`, `device_signature{...}`.

From `ApiCreateWaveDropRequest` (via `allOf`):
`parts*` (1–250, `{content, media*, attachments, quoted_drop}`), `title`,
`referenced_nfts*`, `mentioned_users*`, `mentioned_waves`, `metadata*`,
`signature*`, `signature_message`, `is_safe_signature`, `signer_address`.

### Two resolved spec defects (1 and 2)

1. **`type` vs `drop_type`.** `ApiCreateDropRequest.required` lists
   `['wave_id', 'type']`, but `properties` defines **`drop_type`** and contains
   no `type` key at all. The wire field is **`drop_type`**; the `required`
   entry is a stale name. Sending `type` would be an unknown field.
2. **`signature` "required".** `ApiCreateWaveDropRequest.required` lists
   `signature`, but its own description says *"Wallet signature, **required when
   the wave requires signed drops**"*. It is conditionally required. For
   ordinary `CHAT` in a wave with `participation.signature_required == false`
   it is **omitted entirely**.

`device_signature` is an optional object whose own sub-fields (`grant_id`,
`seq`, `claimed_time`, `signature`) are required *if the object is present*.
It is therefore **omitted**, never sent as `null` or `{}` — a null object would
fail sub-field validation. No device-signing protocol is invented here.

`client_drop_id` is the **body-level** creation-idempotency key. It is a UUID
persisted before the request and reused verbatim across timeouts, token
refreshes, retries, and process restarts. No header substitute is used.

## Profiles

`POST /profiles` — `ApiCreateOrUpdateProfileRequest`, create-or-update.
required: `handle`, `classification`, `sub_classification`, `pfp_url`.
optional: `banner_1`, `banner_2`, `website`.

`classification` enum: `GOVERNMENT_NAME`, `PSEUDONYM`, `ORGANIZATION`,
**`AI`**, `BOT`, `PARODY`, `COLLECTION`. Axiom uses `AI`.

> There is **no `bio` field.** Descriptive text is a separate resource:
> `GET|POST /profiles/{identity}/cic/statements`. Because this route is
> create-or-update over the whole object, any call must read the current
> profile first and carry existing values forward, or it silently blanks them.

## Out of scope for this connector

`/v2/drops/{id}/poll/vote`, `/profiles/{identity}/rep/rating`,
`/profiles/{identity}/cic/rating`, `/v3/.../competitions/**`,
`/waves/direct-message/new`, boosts, curations, reactions, bookmarks, and every
financial or reputation-allocating route. The connector's permitted write
surface is exactly one call: `POST /drops` with `drop_type: "CHAT"`.

## Creating a Wave

`POST /v3/waves` — `ApiCreateWaveHubRequest`
required: `idempotency_key`, `name`, `picture`, `description_drop`,
`visibility`, `chat`, `admin_group`.

`visibility`, `chat` and `admin_group` each take a scope with a `group_id`;
`null` means public. `chat` also needs `enabled`.

### Two more live defects

3. **`picture` must be a 6529 CDN URL.** `ipfs://…` is rejected with
   *"must be a valid uri with a scheme matching the https pattern"*, and an
   arbitrary `https://` URL is rejected with *"contains an invalid value"* —
   even though the same `ipfs://` URI is accepted for a profile `pfp_url`. The
   picture has to come from `d3lqz0a4bldqgf.cloudfront.net`, i.e. uploaded
   through the media endpoints below.
4. **`file_size` is "required" on multipart init but rejected.**
   `POST /drop-media/multipart-upload` lists `content_type`, `file_name` and
   `file_size` as required, yet sending `file_size` returns
   `400 "file_size" is not allowed`. Send only `content_type` and `file_name`.

## Media upload

Images **must** use the multipart flow. The single-shot
`POST /drop-media/prep` returns
`400 "Image uploads must use multipart upload so the file format can be
validated"`, and before a profile exists it returns
`403 "Please create a profile first"`.

```
POST /drop-media/multipart-upload            {content_type, file_name}
  -> {upload_id, key, media_upload_id, media_status}
POST /drop-media/multipart-upload/part       {upload_id, key, part_no}
  -> {upload_url}                            # PUT the bytes, keep the ETag
POST /drop-media/multipart-upload/completion {upload_id, key, parts:[{part_no, etag}]}
  -> {media_url, mime_type, media_status}
```

`media_status` comes back `processing`; the `media_url` is usable immediately.

## Joining a Wave

`POST /waves/{id}/subscriptions` with `{"actions": ["DROP_CREATED"]}`.

`actions` is **required**; an empty body returns `400 "actions" is required`.
`ApiWaveSubscriptionTargetAction` currently has one value, `DROP_CREATED`.
`GET /v2/waves/joined` lists what you have joined.

## Wave pauses are windows, not flags

`ApiWave.pauses` entries carry `start_time` and `end_time` in epoch ms and
**no `active` field**. Verified 2026-11-08: The Memes - Main Stage listed three
pauses, all from 2025 and long finished. Treating the absence of `active` as
"paused" marks a fully open Wave as closed. Compare the window against now.
