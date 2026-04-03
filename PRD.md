# Product Requirements Document (PRD)
## LocalOCR Extended

**Document Version:** 1.0  
**Created:** 2026-04-02  
**Status:** Approved for Extended implementation  

## 1. Executive Summary

`LocalOCR Extended` exists so the stable grocery app can remain clean while a broader household platform is explored in parallel.

The product direction is:

- preserve the current grocery system as the stable baseline
- run Extended beside it on a different port with separate data
- use Extended for restaurant receipts and future module architecture

## 2. Product Model

Extended is a modular household receipt platform with:

- a shared core
- a Grocery module
- a Restaurant module

Deployers should eventually be able to choose:

- Grocery only
- Restaurant only
- All modules

When multiple modules are enabled, users should eventually be able to choose separate vs combined presentation.

## 3. Shared Core Requirements

The shared core includes:

- household auth
- receipts upload and OCR
- receipt review
- local file storage
- contribution ledger
- optional Telegram ingestion
- optional MQTT/Home Assistant integration
- optional QR helper/login flows

## 4. Grocery Module

Inherited working capability:

- active inventory
- product cleanup and category tagging
- shopping list and helper QR
- grocery analytics and budget
- recommendation workflow

This module already works and should remain stable while Extended evolves.

## 5. Restaurant Module

Initial Extended capability now started:

- upload-time receipt intent selection:
  - Auto
  - Grocery
  - Restaurant
- restaurant receipt classification and storage
- exact restaurant line items preserved for repeat-order planning
- subtotal, tax, tip, and total tracking
- structured post-OCR correction flow in receipt detail
- ability to fix store/date/time/totals/items after upload
- restaurant workspace with:
  - dining budget card
  - selected receipt detail
  - repeat-order estimate
  - recent receipt inspection
- dining-out analytics
- separate dining budget
- no inventory side effects from restaurant receipts

Restaurant workflow requirement:

- users must be able to bias upload toward restaurant before OCR when they already know the receipt type
- if OCR is inaccurate, users must be able to correct the restaurant receipt without editing raw JSON
- corrected restaurant receipts must rebuild the saved purchase cleanly
- corrected restaurant receipts must remain isolated from grocery inventory behavior

## 6. Deployment Requirements

Extended must support safe side-by-side testing with the grocery app:

- grocery app remains on `8080`
- Extended runs on `8090`
- Extended uses separate DB, receipt storage, and backups
- Extended may share MQTT and Ollama with the grocery stack
- Extended must use different MQTT identifiers and namespaces so Home Assistant entities do not collide

## 7. Success Criteria

- Extended can run on `8090` while grocery keeps running on `8080`
- Extended can be abandoned later without damaging grocery data or deployment
- Extended preserves enough structural similarity that useful features can be cherry-picked back if desired
- Restaurant/module work can happen here without destabilizing the grocery repo
