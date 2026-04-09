# Multi-Household Plan

## Goal

Evolve Extended from a single-household web app into a multi-household platform where:

- each household has its own isolated data
- each household can have its own admin and members
- one person can belong to more than one household
- a platform-level admin can optionally oversee multiple households

This should preserve the current household experience while allowing clean expansion to additional families and homes.

## Product Direction

Move from:

- one shared household dataset

To:

- one deployment
- many households
- strict household isolation
- optional cross-house admin/support capabilities

## Recommended Model

### 1. Real Household Entity

Introduce a true `Household` model instead of treating the current app as implicitly single-household.

Each household should own its own:

- users and memberships
- products and catalog groupings
- receipts and purchases
- receipt items
- shopping list items
- inventory
- trusted devices
- budgets
- contributions
- recommendation state

### 2. Membership Model

A user should be able to belong to one or more households through membership records.

Recommended structure:

- `users`
- `households`
- `household_memberships`

Membership should include a role per household.

Recommended household roles:

- `admin`
- `member`
- later optionally `viewer`

### 3. Optional Platform-Level Role

Support a higher-level role for operating across homes.

Recommended platform roles:

- `platform_owner`
- `platform_admin`

These are separate from household roles.

That allows:

- a family admin to manage only their own home
- a platform owner/admin to help manage multiple homes when needed

## Core Rules

### Household Isolation

Every major data record should belong to exactly one `household_id`.

That includes:

- products
- purchases
- receipt items
- telegram receipts / uploaded receipt records
- shopping list rows
- inventory records
- trusted devices
- budgets
- contributions
- recommendations

No household should see another household's data unless a platform-level capability explicitly allows it.

### Trusted Devices

Trusted devices must be household-bound.

Examples:

- a fridge tablet belongs to one household
- a kitchen display belongs to one household
- revoking it should affect only that household

### Current Household Context

Once users can belong to multiple households, the app needs an active household context.

That context should drive:

- all page data queries
- writes and updates
- dashboard summaries
- recommendation generation
- shopping and inventory actions

## UX Recommendations

### Household Switcher

Add a household switcher in the authenticated UI.

Good first version:

- current household shown in the header or Settings
- switch between households you belong to

### Household Creation / Joining

Support:

- create a household
- invite members
- accept invite

### Household Admin Controls

Household admins should manage:

- members
- roles
- trusted devices
- household settings

### Platform Admin Controls

Platform admins can later get:

- household list
- impersonation/support tools
- health and backup visibility
- usage reporting

## Recommended Phases

### Phase 1: Multi-Household Foundation

Goal:

- introduce `household_id` everywhere and preserve current behavior for the existing household

Work:

- add `households` table
- add `household_memberships` table
- create a default household from current single-household data
- add `household_id` to all major tables
- backfill all existing records into the default household
- scope backend queries to current household

Outcome:

- no visible product change yet for most users
- architecture becomes multi-household ready

### Phase 2: Household Switching

Goal:

- allow one user to access more than one household

Work:

- household switcher in UI
- current household in session/auth context
- household-scoped dashboard and navigation

Outcome:

- one login can move between homes cleanly

### Phase 3: Invites and Household Admin

Goal:

- let households self-manage

Work:

- invite flow
- membership acceptance
- household admin controls
- role management

Outcome:

- each family can operate independently

### Phase 4: Platform Admin Layer

Goal:

- support cross-house management where desired

Work:

- platform admin role
- household directory
- admin/support tools
- backup/restore visibility by household or environment

Outcome:

- easier managed-service or support model

## Migration Strategy

Recommended migration path from the current single-household app:

1. Create one default household
2. Attach current primary user(s) to that household
3. Backfill `household_id` into all current records
4. Make all reads/writes require current household context
5. Only after that, introduce household creation and switching

This minimizes risk and avoids trying to ship data migration, switching, and invites all at once.

## Technical Notes

### Data Model Targets

Likely new or updated tables:

- `households`
- `household_memberships`
- `trusted_devices.household_id`
- `products.household_id`
- `purchases.household_id`
- `receipt_items.household_id`
- `shopping_list.household_id`
- `inventory.household_id`
- `budgets.household_id`
- `contributions.household_id`

### Auth / Session Context

Session should include:

- authenticated user
- active household id
- platform role if applicable

Trusted-device auth should also carry household context explicitly.

### Backups and Restore

The new backup/restore system should remain environment-wide at first, but the architecture should anticipate future support for:

- household-aware exports
- household-scoped admin tools

Do not attempt household-scoped restore until the multi-household data model is stable.

## Risks

Main risks:

- missing `household_id` on a table and accidentally leaking data
- recommendation, shopping, or trusted-device logic using unscoped queries
- backup/restore assumptions still treating the system as single-household
- invite and membership edge cases creating role confusion

## Recommended Next Step

Start a dedicated implementation phase called:

- `multi-household foundation`

That first phase should produce:

- schema design
- migration plan
- affected table inventory
- query scoping checklist
- auth/session household-context plan

## Success Criteria

Multi-household support is successful when:

- each family sees only its own data
- household admins can manage their own members and devices
- one user can switch between households cleanly
- trusted devices stay tied to the correct household
- current single-household users migrate without losing data
