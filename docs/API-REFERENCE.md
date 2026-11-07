# 6529 API reference

Generated from `https://api.6529.io/openapi.json` on **2026-11-07** (`openapi 3.0.3`, `info.version 1.0.0`, **446 paths**).

Base URL: `https://api.6529.io/api`.

Routes this connector actually calls are marked **[used]** and are specified
precisely in [API-CONTRACT.md](API-CONTRACT.md), including the places where
this spec disagrees with the deployed service. Everything else is listed so an
agent can discover what exists without guessing a path.

> Anything not marked **[used]** is unimplemented here. Read the live spec
> before calling it, and check whether it is inside your permitted scope.

## Authentication

| | route | what it does |
|---|---|---|
| `POST` | `/auth/connection-share` | Create a one-time wallet connection share code |
| `POST` | `/auth/connection-share/legacy-desktop` | Create a legacy desktop connection share link |
| `POST` | `/auth/connection-share/redeem` | Redeem a one-time wallet connection share code |
| `POST` | `/auth/login` | Authenticate and get JWT token |
| `GET` | `/auth/nonce` | Get a message to sign with your web3 wallet |
| `POST` | `/auth/redeem-refresh-token` | Redeem refresh token |
| `POST` | `/auth/session-login` **[used]** | Authenticate and create a wallet auth session |
| `POST` | `/auth/session-logout` **[used]** | Revoke a wallet auth session |
| `GET` | `/auth/session-nonce` **[used]** | Get a wallet auth session message to sign |
| `POST` | `/auth/session-refresh` **[used]** | Rotate a wallet auth session and issue a fresh JWT |

## Identity and profile

| | route | what it does |
|---|---|---|
| `GET` | `/collected-stats/{identityKey}` **[used]** | Get consolidated collection stats for an identity |
| `GET` | `/identities` | Search or list identities |
| `GET` | `/identities/by-wallet/{wallet}` **[used]** | Get identity by wallet |
| `GET` | `/identities/{identity_key}` | Get identity by it"s key. Key can be id, wallet, handle, ENS name, etc... |
| `GET` | `/identities/{id}/activity` | Get daily public-wave drop activity for an identity. |
| `GET` | `/identities/{id}/artwork-alerts` | Read your independent artwork-alert preference for an artist. |
| `POST` | `/identities/{id}/artwork-alerts` | Enable future artwork alerts without following the artist. |
| `DELETE` | `/identities/{id}/artwork-alerts` | Disable artwork alerts without changing feed subscriptions. |
| `GET` | `/identities/{id}/mute` | Get authenticated user's mute state for an identity. |
| `POST` | `/identities/{id}/mute` | Mute identity notifications for authenticated user. |
| `DELETE` | `/identities/{id}/mute` | Unmute identity notifications for authenticated user. |
| `GET` | `/identities/{id}/subscriptions` | Get subscribed actions to identity for authenticated user. |
| `POST` | `/identities/{id}/subscriptions` | Subscribe authenticated user to identities actions. |
| `DELETE` | `/identities/{id}/subscriptions` | Unsubscribe authenticated user from identity actions. |
| `GET` | `/og-metadata/profiles/{identity}` | Get OG metadata for a profile |
| `GET` | `/profile-preferences` | Get the authenticated profile's privacy and notification preferences |
| `PUT` | `/profile-preferences` | Update the authenticated profile's privacy and notification preferences |
| `POST` | `/profiles` **[used]** | Create or update a profile |
| `GET` | `/profiles/{identity}/cic/contributors` | Get profile CIC contributors |
| `GET` | `/profiles/{identity}/cic/overview` | Get profile CIC overview |
| `POST` | `/profiles/{identity}/cic/rating` | Change profile CIC rating. If you are authenticated as proxy, you will be rating on beha |
| `GET` | `/profiles/{identity}/cic/ratings/by-rater` | Get profile CIC ratings by rater |
| `GET` | `/profiles/{identity}/cic/statements` **[used]** | Get profile identity statements |
| `POST` | `/profiles/{identity}/cic/statements` **[used]** | Add a profile identity statement |
| `GET` | `/profiles/{identity}/cic/statements/{statement_id}` | Get a profile identity statement |
| `DELETE` | `/profiles/{identity}/cic/statements/{statement_id}` | Delete a profile identity statement |
| `GET` | `/profiles/{identity}/proxies` | Get profile proxies |
| `GET` | `/profiles/{identity}/proxies/granted` | Get proxies granted by a profile |
| `GET` | `/profiles/{identity}/proxies/received` | Get proxies received by a profile |
| `GET` | `/profiles/{identity}/rep/categories` | Get profile REP categories |
| `GET` | `/profiles/{identity}/rep/categories/{category}/contributors` | Get profile REP contributors for category |
| `GET` | `/profiles/{identity}/rep/overview` | Get profile REP overview |
| `POST` | `/profiles/{identity}/rep/rating` | Change profile REP rating. If you are authenticated as proxy, you will be rating on beha |
| `GET` | `/profiles/{identity}/rep/rating` | Get profile REP rating |
| `GET` | `/profiles/{identity}/rep/ratings/by-rater` | Get profile REP ratings by rater |
| `GET` | `/profiles/{identity}/wave` | Get profile wave |
| `POST` | `/profiles/{identity}/wave` | Set explicit profile wave |
| `DELETE` | `/profiles/{identity}/wave` | Clear explicit profile wave |

## TDH and holdings

| | route | what it does |
|---|---|---|
| `GET` | `/aggregated-activity` | Get aggregated activity |
| `GET` | `/aggregated-activity/consolidation/{consolidation_key}` | Get aggregated activity by consolidation key. |
| `GET` | `/aggregated-activity/consolidation/{consolidation_key}/memes` | Get memes aggregated activity by consolidation key per season. |
| `POST` | `/collect/tdh-daily-plans` | Find a best available portfolio for a daily TDH objective or ETH budget |
| `GET` | `/collect/tdh-listings` | Browse listings by cost per base TDH accrual rate |
| `POST` | `/collect/tdh-ranking` | rank Collect Tdh Purchases |
| `POST` | `/collect/tdh-scenarios` | project Collect Purchases |
| `POST` | `/collect/tdh-target-plans` | Estimate a purchase budget for a profile TDH target |
| `GET` | `/nft-owners` | Get NFT owners |
| `GET` | `/nft-owners/consolidation/{consolidation_key}` | Get NFT owners by consolidation key |
| `GET` | `/owners-balances` | Get owner balances |
| `GET` | `/owners-balances/consolidation/{consolidation_key}` | Get owner balance by consolidation key. |
| `GET` | `/owners-balances/consolidation/{consolidation_key}/memes` | Get memes owner balance by consolidation key. |
| `GET` | `/tdh-editions/consolidation/{consolidation_key}` | Get TDH editions by consolidation key |
| `GET` | `/tdh-editions/identity/{identity}` **[used]** | Get TDH editions for an identity, wallet address, or ENS |
| `GET` | `/tdh-editions/wallet/{wallet}` | Get TDH editions for a wallet |
| `GET` | `/tdh/consolidated_metrics` | Get consolidated TDH metrics with pagination and sorting. |
| `GET` | `/tdh/consolidation/{identity}` **[used]** | Get consolidated TDH for an identity |
| `GET` | `/tdh/rules` | Get current TDH boost definitions evaluated for the latest completed snapshot |

## Waves (read)

| | route | what it does |
|---|---|---|
| `GET` | `/v2/waves` **[used]** | Get V2 waves |
| `GET` | `/v2/waves/active-votes` | Find waves with active TDH voting |
| `GET` | `/v2/waves/joined` **[used]** | List joined waves using a stable snapshot |
| `GET` | `/v2/waves/mention-search` | Search draft-wave-eligible profiles for user mentions |
| `GET` | `/v2/waves/profile-activity/{identity}` | Get profile wave activity |
| `GET` | `/v2/waves/{id}/decisions` | Get already decided V2 wave decision outcomes |
| `GET` | `/v2/waves/{id}/leaderboard` | Get V2 waves leaderboard |
| `GET` | `/v2/waves/{id}/metadata` | Get V2 wave metadata |
| `POST` | `/v2/waves/{id}/metadata` | Create V2 wave metadata |
| `DELETE` | `/v2/waves/{id}/metadata/{metadata_id}` | Delete V2 wave metadata |
| `GET` | `/v2/waves/{id}/polls` | Get V2 polls in a wave. |
| `GET` | `/v2/waves/{waveId}/all-mention-count` | Preview the current number of recipients for an all mention |
| `GET` | `/v2/waves/{waveId}/mention-search` | Search wave-eligible profiles for user mentions |
| `GET` | `/v2/waves/{waveId}/search` | Search for V2 drops in a wave |
| `GET` | `/v2/waves/{waveId}/search-authors` | Search profiles that authored a drop in a wave |
| `GET` | `/waves` | Get waves. |
| `POST` | `/waves` | Create new wave |
| `GET` | `/waves-overview` | Get overview of waves by different criteria. |
| `GET` | `/waves-overview/favourites-of-identity/{identityKey}` | Get waves where a profile has written the most messages. |
| `GET` | `/waves-overview/hot` | Get hot waves overview. |
| `POST` | `/waves/direct-message/new` | Create a direct message wave |
| `GET` | `/waves/{id}` **[used]** | Get wave by ID. |
| `DELETE` | `/waves/{id}` **[used]** | Delete wave by ID |
| `POST` | `/waves/{id}` **[used]** | Update wave by ID |
| `GET` | `/waves/{id}/curations` | List curations configured for wave |
| `POST` | `/waves/{id}/curations` | Create curation for wave |
| `POST` | `/waves/{id}/curations/{curationId}` | Update curation for wave |
| `DELETE` | `/waves/{id}/curations/{curationId}` | Delete curation from wave |
| `GET` | `/waves/{id}/decisions` | Get already decided wave decision outcomes |
| `GET` | `/waves/{id}/leaderboard` | Get waves leaderboard |
| `GET` | `/waves/{id}/logs` | Get drop logs |
| `POST` | `/waves/{id}/mute` | Mute a wave |
| `DELETE` | `/waves/{id}/mute` | Unmute a wave |
| `POST` | `/waves/{id}/my-chat-history` | Prepare a bounded deletion of the authenticated user's chat history |
| `DELETE` | `/waves/{id}/my-chat-history` | Delete the authenticated user's chat history from a wave |
| `POST` | `/waves/{id}/pauses` | Create or edit wave decision pause |
| `POST` | `/waves/{id}/pinned-drop` | Change pinned drop in a wave |
| `POST` | `/waves/{id}/pins` | Pin a wave |
| `DELETE` | `/waves/{id}/pins` | Unpin a wave |
| `GET` | `/waves/{id}/rep/categories` | Get wave REP categories |
| `GET` | `/waves/{id}/rep/categories/{category}/contributors` | Get wave REP contributors for category |
| `GET` | `/waves/{id}/rep/overview` | Get wave REP overview |
| `POST` | `/waves/{id}/rep/rating` | Change wave REP rating. If you are authenticated as proxy, you will be rating on behalf  |
| `GET` | `/waves/{id}/rep/rating` | Get wave REP rating |
| `GET` | `/waves/{id}/rep/ratings/by-rater` | Get wave REP ratings by rater |
| `POST` | `/waves/{id}/subscriptions` | Subscribe authenticated user to wave actions. |
| `DELETE` | `/waves/{id}/subscriptions` | Unsubscribe authenticated user from wave actions. |
| `GET` | `/waves/{id}/subwaves` | Get wave subwaves. |
| `GET` | `/waves/{id}/undiscovered-drop` | Get the next undiscovered participatory drop for quick vote |
| `GET` | `/waves/{id}/voters` | Get info about waves voters (top voters etc) |
| `GET` | `/waves/{waveId}/outcomes` | Get wave outcomes |
| `GET` | `/waves/{waveId}/outcomes/{outcomeIndex}/distribution` | Get wave outcome distribution |
| `DELETE` | `/waves/{waveId}/pauses/{id}` | Delete wave decision pause |
| `GET` | `/waves/{waveId}/search` | Search for drops in wave by content |

## Drops (read)

| | route | what it does |
|---|---|---|
| `GET` | `/v2/drops` | Get V2 drops. |
| `GET` | `/v2/drops/search` | Search messages across all waves visible to the caller |
| `GET` | `/v2/drops/{id}` **[used]** | Get V2 drop by ID. |
| `GET` | `/v2/drops/{id}/boosts` | Get V2 drop boosts by drop ID. |
| `GET` | `/v2/drops/{id}/metadata` | Get V2 drop metadata by drop ID. |
| `GET` | `/v2/drops/{id}/parts/{part_no}` | Get a single V2 drop part by drop ID and part number. |
| `POST` | `/v2/drops/{id}/poll/vote` | Vote in a V2 drop poll. |
| `GET` | `/v2/drops/{id}/poll/{option_no}/voters` | Get V2 drop poll option voters by drop ID and option number. |
| `GET` | `/v2/drops/{id}/reactions` | Get V2 drop reactions by drop ID. |
| `GET` | `/v2/drops/{id}/replies` **[used]** | Get V2 replies to a drop. |
| `GET` | `/v2/drops/{id}/vote-summary` | Get the current vote allocation summary for a drop. |
| `GET` | `/v2/drops/{id}/votes` | Get V2 drop voters by drop ID. |
| `GET` | `/v2/drops/{id}/votes/download` | Download V2 drop voters by drop ID as CSV. |
| `GET` | `/v2/drops/{id}/votes/logs` | Get V2 drop vote edit logs by drop ID. |
| `GET` | `/v2/waves/{id}/competition-drops` | Get one author's competition drops in a wave |
| `GET` | `/v2/waves/{id}/curations/{curation_id}/drops` | List V2 drops in a curation for wave |
| `GET` | `/v2/waves/{id}/drops` **[used]** | Get V2 timeline drops for a wave |
| `GET` | `/waves/{id}/curations/{curation_id}/drops` | List drops in a curation for wave |
| `GET` | `/waves/{id}/drops` | Get drops related to wave or parent drop |
| `GET` | `/waves/{id}/undiscovered-drops` | Get an ordered quick vote preview window with shared counts |

## Drops (write)

| | route | what it does |
|---|---|---|
| `GET` | `/drops` **[used]** | Get latest drops. |
| `POST` | `/drops` **[used]** | Create a drop |
| `GET` | `/drops/{dropId}` | Get drop by ID. |
| `POST` | `/drops/{dropId}` | Update drop by ID |
| `DELETE` | `/drops/{dropId}` | Delete drop by ID |
| `POST` | `/drops/{dropId}/bookmark` | Bookmark a drop |
| `DELETE` | `/drops/{dropId}/bookmark` | Remove bookmark from drop |
| `GET` | `/drops/{dropId}/boosts` | Get drop boosts by Drop ID. |
| `POST` | `/drops/{dropId}/boosts` | Boost drop |
| `DELETE` | `/drops/{dropId}/boosts` | Delete drop boost |
| `GET` | `/drops/{dropId}/curations` | Get curations for a drop |
| `POST` | `/drops/{dropId}/curations` | Add a drop to a curation |
| `DELETE` | `/drops/{dropId}/curations` | Remove a drop from a curation |
| `POST` | `/drops/{dropId}/mark-unread` | Mark a drop and all subsequent drops in the wave as unread |
| `POST` | `/drops/{dropId}/ratings` | Rate a drop |
| `POST` | `/drops/{dropId}/reaction` | React to a drop |
| `DELETE` | `/drops/{dropId}/reaction` | Remove reaction from a drop |
| `GET` | `/drops/{dropId}/signed-events` | Get the device signed events of a drop |
| `POST` | `/drops/{dropId}/subscriptions` | Subscribe authenticated user to drop actions. |
| `DELETE` | `/drops/{dropId}/subscriptions` | Unsubscribe authenticated user from drop actions. |
| `POST` | `/drops/{dropId}/toggle-hide-link-preview` | Toggle hide link preview for a drop |
| `GET` | `/drops/{drop_id}/collaborations` | getMemeCollaborationState |
| `POST` | `/drops/{drop_id}/collaborations` | inviteMemeCollaborators |
| `POST` | `/drops/{drop_id}/collaborations/{invitation_id}/response` | respondToMemeCollaboration |

## Notifications

| | route | what it does |
|---|---|---|
| `GET` | `/notifications` | Get notifications for authenticated user. |
| `POST` | `/notifications/read` | Mark all notifications as read |
| `GET` | `/notifications/wave-subscription/{wave_id}` | Get wave subscription |
| `POST` | `/notifications/wave-subscription/{wave_id}` | Subscribe to wave notifications |
| `DELETE` | `/notifications/wave-subscription/{wave_id}` | Unsubscribe from wave notifications |
| `POST` | `/notifications/wave/{wave_id}/read` | Mark wave notifications as read |
| `POST` | `/notifications/{id}/read` | Mark notification as read |
| `GET` | `/v2/notifications` **[used]** | Get V2 notifications for authenticated user. |

## Media upload

| | route | what it does |
|---|---|---|
| `POST` | `/attachments/multipart-upload` | Initialize multipart upload for a document attachment |
| `POST` | `/attachments/multipart-upload/completion` | Complete an attachment multipart upload |
| `POST` | `/attachments/multipart-upload/part` | Upload a part of an attachment multipart upload |
| `GET` | `/attachments/{attachment_id}` | Get attachment status and final URL |
| `POST` | `/drop-media/multipart-upload` | Get upload ID and key for multipart upload |
| `POST` | `/drop-media/multipart-upload/completion` | Complete the multipart upload |
| `POST` | `/drop-media/multipart-upload/part` | Upload a part of multipart upload |
| `POST` | `/drop-media/prep` **[used]** | Create S3 URL for drop media upload |
| `POST` | `/drop-media/proposal-frame` | Publish an optional proposal frame around uploaded artwork |
| `GET` | `/drop-media/uploads/{media_upload_id}` | Get drop or wave media upload status |
| `POST` | `/wave-media/multipart-upload` | Get upload ID and key for multipart upload |
| `POST` | `/wave-media/multipart-upload/completion` | Complete the multipart upload |
| `POST` | `/wave-media/multipart-upload/part` | Upload a part of multipart upload |
| `POST` | `/wave-media/prep` | Create S3 URL for wave PFP |

## Moderation and safety

| | route | what it does |
|---|---|---|
| `GET` | `/content-moderation/block-activity` | List profile block and unblock activity for authorized moderators. |
| `GET` | `/content-moderation/blocked-profiles` | List profiles blocked by the authenticated profile. |
| `GET` | `/content-moderation/checks` | getModerationChecks |
| `GET` | `/content-moderation/checks/access` | getModerationAccess |
| `GET` | `/content-moderation/checks/cases` | getModerationReviewCases |
| `GET` | `/content-moderation/checks/counts` | getModerationCounts |
| `GET` | `/content-moderation/checks/profile/{profile_id}` | getModerationProfileCheck |
| `GET` | `/content-moderation/checks/report/{report_id}` | getModerationReportCheck |
| `GET` | `/content-moderation/checks/{id}` | getModerationCheck |
| `POST` | `/content-moderation/checks/{id}/actions` | moderationCheckAction |
| `POST` | `/content-moderation/drops/{drop_id}/decision` | Apply an authorized moderation decision to a drop. |
| `PUT` | `/content-moderation/drops/{drop_id}/hide` | Hide one drop for the authenticated viewer. |
| `DELETE` | `/content-moderation/drops/{drop_id}/hide` | Unhide one drop for the authenticated viewer. |
| `POST` | `/content-moderation/drops/{drop_id}/reports` | Report a drop and optionally apply personal visibility actions. |
| `DELETE` | `/content-moderation/drops/{drop_id}/reports/mine` | Withdraw the authenticated profile's open report for a drop. |
| `GET` | `/content-moderation/moderator-access` | Get moderation access for the authenticated profile. |
| `GET` | `/content-moderation/profiles/suspended` | List currently suspended profiles for authorized moderators. |
| `PUT` | `/content-moderation/profiles/{profile_id}/block` | Block a profile for the authenticated viewer. |
| `DELETE` | `/content-moderation/profiles/{profile_id}/block` | Unblock a profile for the authenticated viewer. |
| `GET` | `/content-moderation/profiles/{profile_id}/status` | Get the public moderation status of a profile. |
| `POST` | `/content-moderation/profiles/{profile_id}/status` | Suspend or reinstate a profile as an authorized moderator. |
| `GET` | `/content-moderation/reports` | Get the authorized content moderation queue. |
| `GET` | `/content-moderation/reports/mine` | List reports submitted by the authenticated profile. |

## Everything else

304 further operations - competitions, subscriptions, minting, CMS,
delegation, groups, analytics. None are in this connector's scope.

<details><summary>Expand</summary>

| | route | what it does |
|---|---|---|
| `POST` | `/alchemy-proxy/contracts` | Get contract metadata for a batch of Ethereum collections |
| `GET` | `/artwork-documentation/contexts/{id}` | GetDocumentationContext |
| `PATCH` | `/artwork-documentation/contexts/{id}` | PatchDocumentationContext |
| `POST` | `/artwork-documentation/contexts/{id}/artist-record-pin` | PinDocumentationArtist |
| `GET` | `/artwork-documentation/contexts/{id}/artist-records/{revisionId}` | Read the artist identity revision for comparison |
| `POST` | `/artwork-documentation/contexts/{id}/asset-links` | LinkDocumentationAsset |
| `PATCH` | `/artwork-documentation/contexts/{id}/asset-links/{linkId}` | PatchDocumentationAssetLink |
| `DELETE` | `/artwork-documentation/contexts/{id}/asset-links/{linkId}` | UnlinkDocumentationAsset |
| `POST` | `/artwork-documentation/contexts/{id}/assets/uploads` | StartDocumentationUpload |
| `GET` | `/artwork-documentation/contexts/{id}/assets/uploads/{uploadId}` | GetDocumentationUpload |
| `DELETE` | `/artwork-documentation/contexts/{id}/assets/uploads/{uploadId}` | CancelDocumentationUpload |
| `POST` | `/artwork-documentation/contexts/{id}/assets/uploads/{uploadId}/complete` | CompleteDocumentationUpload |
| `POST` | `/artwork-documentation/contexts/{id}/assets/uploads/{uploadId}/parts` | SignDocumentationParts |
| `POST` | `/artwork-documentation/contexts/{id}/assets/{assetId}/download` | DownloadDocumentationAsset |
| `POST` | `/artwork-documentation/contexts/{id}/confirmations` | ConfirmDocumentation |
| `GET` | `/artwork-documentation/contexts/{id}/dossier` | Inspect the portable artwork dossier and mapping report |
| `POST` | `/artwork-documentation/contexts/{id}/dossier/exports` | Prepare a portable dossier with verified original files |
| `GET` | `/artwork-documentation/contexts/{id}/dossier/exports/{exportId}` | Read export progress and obtain an authorized download |
| `GET` | `/artwork-documentation/contexts/{id}/grants` | ListDocumentationGrants |
| `POST` | `/artwork-documentation/contexts/{id}/grants` | GrantDocumentationAccess |
| `DELETE` | `/artwork-documentation/contexts/{id}/grants/{grantId}` | RevokeDocumentationAccess |
| `PATCH` | `/artwork-documentation/contexts/{id}/modules/{moduleId}` | PatchDocumentationModule |
| `GET` | `/artwork-documentation/contexts/{id}/museum-records` | Read attributed museum records |
| `POST` | `/artwork-documentation/contexts/{id}/museum-records` | Append an attributed museum record without changing artist confirmation |
| `POST` | `/artwork-documentation/contexts/{id}/profile-upgrades` | UpgradeDocumentationProfile |
| `POST` | `/artwork-documentation/contexts/{id}/profile-upgrades/preview` | PreviewDocumentationUpgrade |
| `GET` | `/artwork-documentation/contexts/{id}/public-preview` | Preview only the artist-selected public-record fields, still privately |
| `GET` | `/artwork-documentation/contexts/{id}/revisions` | ListDocumentationRevisions |
| `GET` | `/artwork-documentation/contexts/{id}/revisions/{revisionId}` | GetDocumentationRevision |
| `PUT` | `/artwork-documentation/contexts/{id}/revisions/{revisionId}/reviews/{lane}` | ReviewDocumentation |
| `POST` | `/artwork-documentation/contexts/{id}/source-imports` | ImportDocumentationSource |
| `GET` | `/artwork-documentation/contexts/{id}/source-imports/{receiptId}/preview` | PreviewDocumentationSource |
| `POST` | `/artwork-documentation/contexts/{id}/source-links` | LinkDocumentationSource |
| `GET` | `/artwork-documentation/contexts/{id}/threads` | ListDocumentationThreads |
| `POST` | `/artwork-documentation/contexts/{id}/threads` | CreateDocumentationThread |
| `PATCH` | `/artwork-documentation/contexts/{id}/threads/{threadId}` | PatchDocumentationThread |
| `POST` | `/artwork-documentation/contexts/{id}/threads/{threadId}/comments` | CommentDocumentationThread |
| `GET` | `/artwork-documentation/profiles` | GetDocumentationProfiles |
| `GET` | `/artwork-documentation/programs/{programId}/contexts` | ListDocumentationProgram |
| `GET` | `/artwork-documentation/works` | ListDocumentationWorks |
| `POST` | `/artwork-documentation/works` | CreateDocumentationWork |
| `GET` | `/artwork-documentation/works/{workId}` | GetDocumentationWork |
| `POST` | `/artwork-documentation/works/{workId}/contexts` | Create an explicitly empty documentation context for an artist-owned work |
| `GET` | `/blocks` | Get blocks and related timestamps |
| `GET` | `/boosted-drops/` | Get boosted drops. |
| `POST` | `/bulk-rep` | Change REP rating of multiple targets and categories in one go. Targets final REP value  |
| `GET` | `/cms/my/sites` | List CMS sites owned by the authenticated profile. |
| `GET` | `/cms/packages/{package_hash}` | Get a published CMS package by content hash. |
| `GET` | `/cms/profile/{identity}/primary` | Get the primary published CMS site for a profile identity. |
| `POST` | `/cms/sites` | Create a CMS site owned by the authenticated profile. |
| `POST` | `/cms/sites/{site_id}/published-packages` | Publish an immutable CMS package for a site. |
| `POST` | `/collect/analyses` | analyze Collect Goal |
| `GET` | `/collect/assets` | get Collect Assets |
| `GET` | `/collect/capabilities` | get Collect Capabilities |
| `GET` | `/collect/catalog` | get Collect Catalog |
| `POST` | `/collect/offer-analyses` | analyze Per NFT Offers |
| `POST` | `/collect/plans` | create Collect Plan |
| `GET` | `/collect/plans/{id}` | get Collect Plan |
| `POST` | `/collect/plans/{id}/advance` | advance Collect Plan |
| `POST` | `/collect/rules` | create Collect Rule |
| `GET` | `/collect/rules` | get Collect Rules |
| `GET` | `/collect/rules/{id}` | get Collect Rule |
| `POST` | `/collect/rules/{id}/pause` | pause Collect Rule |
| `POST` | `/collect/rules/{id}/prepare` | prepare Collect Rule |
| `POST` | `/collect/rules/{id}/reconcile` | reconcile Collect Rule |
| `GET` | `/community-members` | Get community members. |
| `GET` | `/community-members/top` | Get top community members with pagination and sorting. |
| `GET` | `/community-metrics` | Get community metrics. |
| `GET` | `/community-metrics/mints` | Get community mint metrics. |
| `GET` | `/community-metrics/series` | Get community metrics series. |
| `GET` | `/consolidated_uploads` | Get consolidated TDH snapshots links |
| `GET` | `/curated-profile-wave-drops` | Get curated profile wave drops |
| `GET` | `/device-grants` | List the device signing grants of the authenticated profile |
| `POST` | `/device-grants` | Register an app device grant |
| `POST` | `/device-grants/{grantId}/label` | Rename a device signing grant owned by the caller |
| `POST` | `/device-grants/{grantId}/revoke` | Revoke a device signing grant |
| `GET` | `/distribution_phases/{contract}/{nft_id}` | Get distribution phases for a specific contract and NFT |
| `GET` | `/distribution_photos/{contract}/{nft_id}` | Get distribution photos for a specific contract and NFT |
| `POST` | `/distribution_photos/{contract}/{nft_id}/complete` | Save uploaded distribution photos to database |
| `POST` | `/distribution_photos/{contract}/{nft_id}/multipart-upload` | Start multipart upload for distribution photo |
| `POST` | `/distribution_photos/{contract}/{nft_id}/multipart-upload/completion` | Complete multipart upload for distribution photo |
| `POST` | `/distribution_photos/{contract}/{nft_id}/multipart-upload/part` | Get presigned URL for multipart upload part |
| `POST` | `/distribution_photos/{contract}/{nft_id}/prep` | Get presigned S3 URL for distribution photo upload |
| `GET` | `/distributions` | Get distributions |
| `GET` | `/distributions/{contract}/{card_id}/wallet-allocations` | Get a wallet's phase allocations for a card |
| `GET` | `/distributions/{contract}/{id}/artist-airdrops` | Get artist airdrops for a specific contract and card |
| `POST` | `/distributions/{contract}/{id}/artist-airdrops` | Upload artist airdrops for a specific contract and card |
| `GET` | `/distributions/{contract}/{id}/overview` | Get distribution overview for a specific contract and card |
| `GET` | `/distributions/{contract}/{id}/team-airdrops` | Get team airdrops for a specific contract and card |
| `POST` | `/distributions/{contract}/{id}/team-airdrops` | Upload team airdrops for a specific contract and card |
| `GET` | `/dm-drops/unread` | Get authenticated user's direct-message unread count. |
| `GET` | `/dm-drops/unread/snapshot` | Get authenticated user's direct-message unread snapshot. |
| `GET` | `/drop-ids` | Get drop IDs in wave by serial range. |
| `GET` | `/drops-bookmarked/` | Get bookmarked drops for authenticated user |
| `GET` | `/drops-bookmarked/status` | Get the signed-in owner's accessible bookmark count |
| `GET` | `/e2ee/backup` | Get the caller's encrypted message-history backup |
| `DELETE` | `/e2ee/backup` | Delete all of the caller's encrypted backups |
| `POST` | `/e2ee/backups` | Start a new encrypted backup generation |
| `GET` | `/e2ee/backups/{backup_id}` | Get one of the caller's backup generations |
| `POST` | `/e2ee/backups/{backup_id}/activate` | Make a backup generation the active one |
| `GET` | `/e2ee/backups/{backup_id}/chunks` | List the chunks of a backup generation |
| `POST` | `/e2ee/backups/{backup_id}/chunks` | Append one ciphertext chunk to a backup generation |
| `GET` | `/e2ee/backups/{backup_id}/chunks/{seq}` | Download one ciphertext chunk of a backup generation |
| `POST` | `/e2ee/backups/{backup_id}/compact` | Delete the older chunks of a backup generation |
| `POST` | `/e2ee/blobs` | Start an encrypted attachment upload |
| `PUT` | `/e2ee/blobs/{blob_id}/chunks/{index}` | Upload one ciphertext chunk of an attachment |
| `GET` | `/e2ee/blobs/{blob_id}/chunks/{index}` | Download one ciphertext chunk of an attachment |
| `POST` | `/e2ee/blobs/{blob_id}/complete` | Complete an encrypted attachment upload |
| `POST` | `/e2ee/devices` | Register or renew an encrypted-messaging device |
| `POST` | `/e2ee/devices/login-grant` | Register or renew an encrypted-messaging device from a sign-in grant |
| `POST` | `/e2ee/devices/lookup` | Look up encrypted-messaging devices in bulk |
| `GET` | `/e2ee/devices/{device_key}` | Get an encrypted-messaging device record |
| `GET` | `/e2ee/devices/{device_key}/groups` | List groups whose current delivery roster contains an own device |
| `POST` | `/e2ee/devices/{device_key}/key-packages` | Upload MLS KeyPackages for an own device |
| `POST` | `/e2ee/devices/{device_key}/label` | Rename an encrypted-messaging device owned by the caller |
| `POST` | `/e2ee/devices/{device_key}/revoke` | Revoke an encrypted-messaging device |
| `GET` | `/e2ee/devices/{device_key}/welcomes` | List pending MLS Welcomes for an own device |
| `POST` | `/e2ee/devices/{device_key}/welcomes/{welcome_id}/ack` | Acknowledge a pending MLS Welcome |
| `POST` | `/e2ee/eligibility` | Check whether profiles can be added to an encrypted chat |
| `POST` | `/e2ee/groups` | Create an encrypted group's delivery record |
| `GET` | `/e2ee/groups/{group}` | Get an encrypted group's delivery record |
| `POST` | `/e2ee/groups/{group}/entries` | Submit an MLS commit or proposal for sequencing |
| `GET` | `/e2ee/groups/{group}/log` | Read an encrypted group's ordered log |
| `POST` | `/e2ee/groups/{group}/messages` | Send an encrypted application message |
| `POST` | `/e2ee/groups/{group}/roster` | Replace a group's delivery roster with the members' MLS view |
| `POST` | `/e2ee/key-packages/claim` | Claim KeyPackages to add profiles' devices to a group |
| `GET` | `/e2ee/me` | Get the caller's encrypted-messaging devices and KeyPackage status |
| `GET` | `/e2ee/profiles/{profile_id}/devices` | List a profile's encrypted-messaging devices |
| `POST` | `/e2ee/reports` | Report a decrypted encrypted message |
| `GET` | `/e2ee/trust-and-safety/reports` | List reported encrypted messages (trust and safety) |
| `GET` | `/e2ee/trust-and-safety/reports/{report_id}` | Read one reported encrypted message (trust and safety) |
| `POST` | `/e2ee/trust-and-safety/reports/{report_id}/hold` | Place a reported encrypted message on hold or release it |
| `GET` | `/feed` | Get feed |
| `GET` | `/groups` | Search for user groups |
| `POST` | `/groups` | Create a group |
| `POST` | `/groups/preview-members` | Preview current members for an unsaved group description |
| `GET` | `/groups/{id}/identity_groups/{identity_group_id}` | Get identity groups identities. Identities are represented as primary wallet addresses |
| `POST` | `/groups/{id}/visible` | Change group visibility |
| `GET` | `/identity-subscriptions/incoming/{target_type}/{target_id}` | Get identities subscribed to target. |
| `GET` | `/identity-subscriptions/outgoing/{target_type}` | Get outgoing subscriptions for authenticated user. |
| `GET` | `/light-drops` | Get light drops |
| `GET` | `/market-depth/{contract}/{token_id}` | Read timestamped OpenSea order depth for a token |
| `GET` | `/market/batch-capabilities` | Get atomic batch purchase capabilities |
| `GET` | `/market/listings` | get Market Listings |
| `GET` | `/market/me/operations` | get My Market Operations |
| `POST` | `/market/operations` | prepare Market Operation |
| `GET` | `/market/operations/{id}` | get Market Operation |
| `POST` | `/market/operations/{id}/continue` | continue Market Operation |
| `POST` | `/market/operations/{id}/preflight` | Simulate an exact reviewed batch without reserving or sending it |
| `POST` | `/market/operations/{id}/send-attempts` | Reserve an exact transaction before opening the wallet |
| `POST` | `/market/operations/{id}/send-attempts/rejection` | Acknowledge a positively identified pre-broadcast rejection |
| `POST` | `/market/operations/{id}/signature` | publish Market Operation |
| `POST` | `/market/operations/{id}/submissions` | submit Market Operation |
| `GET` | `/market/orders` | get Market Orders |
| `GET` | `/market/orders/{order_hash}` | Resolve an exact market order |
| `POST` | `/media/resolve` | Resolve decentralized media references |
| `GET` | `/meme-cards/{meme_card_id}/drop` | Get the Main Stage drop mapped to a Meme card |
| `GET` | `/memelab/artists_names` | memelab artists names |
| `GET` | `/memes-mint-stats` | Get paginated memes mint stats |
| `GET` | `/memes-mint-stats/total` | Get total memes mint stats |
| `GET` | `/memes-mint-stats/yearly` | Get yearly aggregated memes mint stats |
| `GET` | `/memes-mint-stats/{id}` | Get memes mint stats for one meme id |
| `GET` | `/memes/artists_names` | meme artists names |
| `GET` | `/memes_extended_data` | Get paginated Memes extended data |
| `GET` | `/mention-aliases` | List the authenticated profile's personal mention shortcuts |
| `POST` | `/mention-aliases` | Create a personal mention shortcut |
| `PUT` | `/mention-aliases/{aliasId}` | Update a personal mention shortcut |
| `DELETE` | `/mention-aliases/{aliasId}` | Delete a personal mention shortcut |
| `GET` | `/minting-claims/actions/{contract}/types` | Get supported minting claim action types for an authorized launch wallet |
| `GET` | `/minting-claims/actions/{contract}/{claim_id}` | Get minting claim actions for an authorized launch wallet |
| `POST` | `/minting-claims/actions/{contract}/{claim_id}` | Upsert minting claim action state for an authorized launch wallet |
| `GET` | `/minting-claims/{contract}/claims` | Get minting claims (paginated, admin only) |
| `GET` | `/minting-claims/{contract}/claims/{claim_id}` | Get minting claim by claim_id (admin only) |
| `PATCH` | `/minting-claims/{contract}/claims/{claim_id}` | Update minting claim (admin only) |
| `POST` | `/minting-claims/{contract}/claims/{claim_id}/arweave-upload` | Upload minting claim metadata and media to Arweave (admin only) |
| `GET` | `/minting-claims/{contract}/{card_id}/airdrops` | Get per-phase airdrop totals for a token |
| `GET` | `/minting-claims/{contract}/{card_id}/allowlists` | Get per-phase allowlist totals for a token |
| `GET` | `/minting-claims/{contract}/{card_id}/roots` | Get merkle roots for a token |
| `GET` | `/minting-claims/{contract}/{card_id}/{merkle_root}/proofs/{address}` | Get merkle proofs for an address in a card root |
| `GET` | `/nft-activity` | Read on-chain transactions and recorded marketplace actions |
| `GET` | `/nft-link` | Get marketplace data about NFT link |
| `GET` | `/nfts` | Get NFTs |
| `GET` | `/nfts/{contract}/media` | Get NFT Media by Contract |
| `GET` | `/og-metadata/drops/{drop}` | Get OG metadata for a drop by id or serial number |
| `GET` | `/og-metadata/waves/{id}` | Get OG metadata for a wave |
| `POST` | `/policies/eula-consent` | Save the current EULA acceptance for a device |
| `DELETE` | `/policies/eula-consent` | Delete the EULA acceptance for a device |
| `GET` | `/policies/eula-consent/{deviceId}` | Get the current EULA acceptance for a device |
| `DELETE` | `/profile-cms/agent-grants/{id}` | Revoke a draft agent grant |
| `GET` | `/profile-cms/agent-proposals/{id}` | Read a complete proposal for owner review |
| `POST` | `/profile-cms/agent-proposals/{id}` | Record owner review after rejection or an exact candidate save |
| `GET` | `/profile-cms/agent-session/draft` | Read the draft selected by the grant |
| `POST` | `/profile-cms/agent-session/proposals` | Submit a complete multipage candidate for owner review |
| `POST` | `/profile-cms/agent-session/proposals/validate` | Validate a complete multipage candidate without saving |
| `GET` | `/profile-cms/agent-session/proposals/{id}` | Read a proposal made by this grant |
| `GET` | `/profile-cms/agent/schema-bundle` | Get the BYO-agent CMS schema bundle |
| `POST` | `/profile-cms/packages` | Save a draft CMS package |
| `GET` | `/profile-cms/packages/by-hash/{package_hash}` | Fetch a CMS package by package hash |
| `POST` | `/profile-cms/packages/validate` | Validate a CMS package against V1 protocol |
| `GET` | `/profile-cms/packages/{id}` | Fetch a CMS package by database id |
| `POST` | `/profile-cms/packages/{id}/agent-grants` | Create a proposal-only grant for one saved draft |
| `GET` | `/profile-cms/packages/{id}/agent-grants` | List draft agent grants |
| `GET` | `/profile-cms/packages/{id}/agent-proposals` | List proposals for owner review |
| `POST` | `/profile-cms/packages/{id}/agent/patch/validate` | Validate an external agent patch against a draft CMS package |
| `GET` | `/profile-cms/packages/{id}/agent/source-packet` | Fetch a read-only CMS source packet for external agents |
| `POST` | `/profile-cms/packages/{id}/archive` | Archive a non-primary CMS package |
| `GET` | `/profile-cms/packages/{id}/export` | Export CMS package inspection data |
| `POST` | `/profile-cms/packages/{id}/publish` | Publish a draft CMS package |
| `POST` | `/profile-cms/packages/{id}/rollback` | Roll back primary CMS package pointer |
| `POST` | `/profile-cms/packages/{id}/storage/upload` | Upload a draft CMS package to decentralized storage |
| `POST` | `/profile-cms/packages/{id}/unpublish` | Remove the profile's current published CMS site |
| `GET` | `/profile-cms/profiles/{profile_id}/packages` | List CMS packages for a profile |
| `GET` | `/profile-cms/profiles/{profile_id}/packages/{package_id}/versions/{version}` | Fetch a CMS package by profile, package id, and version |
| `POST` | `/profile-cms/wallet-gallery/snapshot` | Create a wallet NFT holdings snapshot for CMS gallery generation |
| `GET` | `/profile-cms/{handle}/primary` | Get a profile's primary published CMS package |
| `GET` | `/profile-logs` | Get profile activity logs |
| `POST` | `/proxies` | Create a new proxy |
| `GET` | `/proxies/{proxyId}` | Get proxy by ID |
| `POST` | `/proxies/{proxyId}/actions` | Add action to proxy |
| `PUT` | `/proxies/{proxyId}/actions/{actionId}` | Update action |
| `POST` | `/proxies/{proxyId}/actions/{actionId}/acceptance` | Accept action |
| `GET` | `/push-notifications/devices` | Get all registered devices for the authenticated user |
| `DELETE` | `/push-notifications/devices/{device_id}` | Delete a registered device |
| `POST` | `/push-notifications/installations/badge-refresh` | Request the current aggregate iOS badge for this installation |
| `POST` | `/push-notifications/installations/revoke` | Revoke this installation's profile registrations and native sessions |
| `POST` | `/push-notifications/register` | Register a push notification token |
| `GET` | `/push-notifications/settings/{device_id}` | Get push notification settings for a device |
| `PUT` | `/push-notifications/settings/{device_id}` | Update push notification settings for a device |
| `POST` | `/ratings` | This is deprecated. Use bulk-rep instead. Bulk rate. Supplied amount will be added to al |
| `GET` | `/ratings/credit` | Get available credit for rating |
| `GET` | `/rep/categories/{category}/givers` | Get global REP category givers |
| `GET` | `/rep/categories/{category}/overview` | Get global REP category overview |
| `GET` | `/rep/categories/{category}/ratings` | Get global REP category giver-recipient pairings |
| `GET` | `/rep/categories/{category}/recipients` | Get global REP category recipients |
| `GET` | `/rep/categories/{category}/wave-contributors` | Get visible Wave REP contributors for a category |
| `GET` | `/rep/categories/{category}/wave-overview` | Get Wave REP category overview across visible waves |
| `GET` | `/rep/categories/{category}/waves` | Get visible waves using a REP category |
| `GET` | `/settings` | Seize settings |
| `GET` | `/subscriptions/consolidation/coverage/{consolidation_key}` | Get projected subscription coverage for a consolidation |
| `GET` | `/subscriptions/consolidation/details/{consolidation_key}` | Get subscription details for a consolidation |
| `GET` | `/subscriptions/consolidation/final/{consolidation_key}/{contract}/{token_id}` | Get final subscription for a consolidation |
| `GET` | `/subscriptions/consolidation/logs/{consolidation_key}` | Get subscription logs for a consolidation |
| `GET` | `/subscriptions/consolidation/redeemed/{consolidation_key}` | Get redeemed subscriptions for a consolidation |
| `GET` | `/subscriptions/consolidation/top-up/{consolidation_key}` | Get top-ups for a consolidation |
| `GET` | `/subscriptions/consolidation/upcoming-memes/{consolidation_key}` | Get upcoming meme subscriptions for a consolidation |
| `GET` | `/subscriptions/consolidation/upcoming-memes/{meme_id}/{consolidation_key}` | Get upcoming meme subscription status for a consolidation |
| `GET` | `/subscriptions/consolidation/{consolidation_key}/airdrop-address` | Get airdrop address for a consolidation |
| `GET` | `/subscriptions/final/{contract}/{token_id}/phases/{phase_name}` | Get final subscription airdrops for a token phase |
| `GET` | `/subscriptions/memes/{token_id}/count` | Get meme subscription count |
| `GET` | `/subscriptions/redeemed-memes-counts` | Get redeemed meme subscription counts |
| `GET` | `/subscriptions/redeemed-memes-counts/download` | Download redeemed meme subscription counts as CSV |
| `GET` | `/subscriptions/upcoming-memes-counts` | Get upcoming meme subscription counts |
| `GET` | `/subscriptions/uploads` | Get subscription uploads |
| `POST` | `/subscriptions/{consolidation_key}/subscribe-all-editions` | Toggle subscribe all editions preference |
| `POST` | `/subscriptions/{consolidation_key}/subscription` | Update subscription for a specific NFT |
| `POST` | `/subscriptions/{consolidation_key}/subscription-count` | Update subscription count for a specific NFT |
| `POST` | `/subscriptions/{consolidation_key}/subscription-mode` | Update subscription mode |
| `GET` | `/transactions` | Get transactions |
| `GET` | `/uploads` | Get TDH snapshots links |
| `GET` | `/v2/boosted-drops` | Get V2 boosted drops. |
| `GET` | `/v2/curated-profile-wave-drops` | Get V2 curated profile wave drops |
| `GET` | `/v2/official-waves` | Get official waves |
| `POST` | `/v3/waves` | create Wave Hub V3 |
| `PATCH` | `/v3/waves/{wave_id}` | Update shared wave settings without changing any competition |
| `GET` | `/v3/waves/{wave_id}` | Read a wave as a competition hub without selecting a competition |
| `POST` | `/v3/waves/{wave_id}/competitions` | create Competition V3 |
| `GET` | `/v3/waves/{wave_id}/competitions` | List zero, one, or many competitions owned by a visible wave |
| `PATCH` | `/v3/waves/{wave_id}/competitions/{competition_id}` | update Competition V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}` | Read one competition after checking both parent identifiers |
| `POST` | `/v3/waves/{wave_id}/competitions/{competition_id}/actions/{action}` | execute Competition Action V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/activity` | List vote activity for the selected competition |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/awards` | list Competition Awards V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/configuration` | getCompetitionConfigurationV3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/credits/me` | get Competition Credit Budget V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/decisions` | List competition decisions and ordered winners |
| `POST` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries` | create Competition Entry V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries` | List competition entries with stable competition context |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries/{entry_id}` | Read one entry after checking every parent identifier |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries/{entry_id}/content` | getCompetitionEntryContentV3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries/{entry_id}/votes` | List the normalized vote history for one competition entry |
| `PUT` | `/v3/waves/{wave_id}/competitions/{competition_id}/entries/{entry_id}/votes/me` | set Competition Vote V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/entry-contexts` | Read up to 50 visible entry contexts and their awards in one batch |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/leaderboard` | List the authoritative competition leaderboard |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/outcomes` | List competition outcomes with stable IDs and legacy positions |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/outcomes/{outcome_id}/distribution` | List ordered distribution items for one competition outcome |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/pauses` | List immutable pause history for a competition |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/versions` | List immutable competition configuration versions newest first |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/voters` | List voter totals and credit spend for a competition or entry |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/votes/me` | list Competition My Votes V3 |
| `GET` | `/v3/waves/{wave_id}/competitions/{competition_id}/winners` | List winner entries by win time, newest first by default |
| `GET` | `/v3/waves/{wave_id}/default-competition` | Resolve the viewer's default competition |
| `GET` | `/v3/waves/{wave_id}/drops/{drop_id}/competition-context` | Resolve the native competition and entry for a visible drop |
| `POST` | `/wave-group-validation` | Validate Wave privilege groups against its View group |
| `GET` | `/xtdh/collections` | Get info about xTDH collections |
| `GET` | `/xtdh/grantees` | Get info about xTDH grantees |
| `GET` | `/xtdh/grants` | Get xTDH grants |
| `POST` | `/xtdh/grants` | Create xTDH grant |
| `GET` | `/xtdh/grants/{id}` | Get xTDH grant |
| `POST` | `/xtdh/grants/{id}` | Update xTDH grant |
| `GET` | `/xtdh/grants/{id}/tokens` | Get xTDH grant tokens |
| `GET` | `/xtdh/stats` | Get global xTDH stats |
| `GET` | `/xtdh/stats/{identity}` | Get identities xTDH stats |
| `GET` | `/xtdh/tokens` | Get info about xTDH tokens |
| `GET` | `/xtdh/tokens/{contract}/{token}/contributors` | Get info about xTDH contributors |

</details>

## Enums worth knowing

```
ApiProfileClassification: GOVERNMENT_NAME, PSEUDONYM, ORGANIZATION, AI, BOT, PARODY, COLLECTION
ApiDropType:              CHAT, PARTICIPATORY, WINNER
ApiCicStatementGroup:     GENERAL, CONTACT, SOCIAL_MEDIA_ACCOUNT, NFT_ACCOUNTS, SOCIAL_MEDIA_VERIFICATION_POST
```
