/// Canonical endpoint catalog — every path here was extracted from
/// `grep -rnE "Blueprint\(" src/backend/` and `@<bp>.route(...)` source sites
/// (plan §4 RULE 1 audit). DO NOT invent paths. Any new endpoint MUST be
/// added here AFTER a grep against `src/backend/` proves it exists.
library;

abstract final class Endpoints {
  Endpoints._();

  // --- auth (manage_authentication.py, prefix /auth) ---
  static const authBootstrapInfo = '/auth/bootstrap-info';
  static const authAppConfig = '/auth/app-config';
  static const authLogin = '/auth/login';
  static const authLogout = '/auth/logout';
  static const authForgotPassword = '/auth/forgot-password';
  static const authMe = '/auth/me';
  static const authMeStats = '/auth/me/stats';
  static const authQrLoginLink = '/auth/qr-login-link';
  static String authQrLogin(String token) => '/auth/qr-login/$token';
  static const authQrImage = '/auth/qr-image';
  static const authDevicePairingStart = '/auth/device-pairing/start';
  static String authPairDevice(String token) => '/auth/pair-device/$token';
  static String authDevicePairingStatus(String token) =>
      '/auth/device-pairing/status/$token';
  static String authDevicePairingClaim(String token) =>
      '/auth/device-pairing/claim/$token';
  static const authDevicePairingApprove = '/auth/device-pairing/approve';
  static const authDevicePairingReject = '/auth/device-pairing/reject';
  static const authTrustedDevices = '/auth/trusted-devices';
  static String authTrustedDevice(int id) => '/auth/trusted-devices/$id';
  static String authTrustedDeviceRevoke(int id) =>
      '/auth/trusted-devices/$id/revoke';
  static const authHouseholdMembers = '/auth/household-members';
  static const authUsers = '/auth/users';
  static String authUser(int id) => '/auth/users/$id';
  static const authServiceAccounts = '/auth/service-accounts';
  static String authServiceAccount(int id) => '/auth/service-accounts/$id';
  static String authServiceAccountRotate(int id) =>
      '/auth/service-accounts/$id/rotate';
  static const authInvites = '/auth/invites';
  static String authInvite(int id) => '/auth/invites/$id';
  static String authInviteByToken(String token) => '/auth/invite/$token';
  static const authOauthGoogleStatus = '/auth/oauth/google/status';
  static const authOauthGoogle = '/auth/oauth/google';
  static const authOauthGoogleCallback = '/auth/oauth/google/callback';
  static const authOauthGoogleLink = '/auth/oauth/google/link';
  static const authOauthGoogleUnlink = '/auth/oauth/google/unlink';

  // --- receipts (handle_receipt_upload.py, prefix /receipts) ---
  static const receipts = '/receipts';
  static const receiptsUpload = '/receipts/upload';
  static String receipt(int id) => '/receipts/$id';
  static const receiptsManual = '/receipts/manual';
  static String receiptImage(int id) => '/receipts/$id/image';
  static String receiptApprove(int id) => '/receipts/$id/approve';
  static const receiptsBulkUpdate = '/receipts/bulk-update';
  static String receiptUpdate(int id) => '/receipts/$id/update';
  static String receiptReprocess(int id) => '/receipts/$id/reprocess';
  static const receiptsCleanupFailed = '/receipts/cleanup-failed';
  static const receiptsDedupScan = '/receipts/dedup-scan';
  static const receiptsAutoLinkPlaid = '/receipts/auto-link-plaid';
  static const receiptsMerge = '/receipts/merge';
  static const receiptsDedupDismiss = '/receipts/dedup-dismiss';
  static String receiptAttribution(int id) => '/receipts/$id/attribution';
  static const receiptsBulkAttribution = '/receipts/bulk-attribution';
  static const receiptsAttributionStats = '/receipts/attribution-stats';
  static String receiptItemAttribution(int receiptId, int itemId) =>
      '/receipts/$receiptId/items/$itemId/attribution';
  static String receiptBillStatus(int id) => '/receipts/$id/bill-status';
  static const receiptsBillsSyncAutopay = '/receipts/bills/sync-autopay';
  static String receiptRotate(int id) => '/receipts/$id/rotate';
  static const receiptsBillProviders = '/receipts/bill-providers';
  static String receiptsBillsProjection(String yyyymm) =>
      '/receipts/bills/projection/$yyyymm';

  // --- shopping_list (manage_shopping_list.py, prefix /shopping-list) ---
  static const shoppingList = '/shopping-list';
  static const shoppingListShareLink = '/shopping-list/share-link';
  static String shoppingListShared(String token) =>
      '/shopping-list/shared/$token';
  static const shoppingListIdentifyPhoto =
      '/shopping-list/identify-product-photo';
  static const shoppingListItems = '/shopping-list/items';
  static String shoppingListItem(int id) => '/shopping-list/items/$id';
  static String shoppingListSharedItem(String token, int itemId) =>
      '/shopping-list/shared/$token/items/$itemId';
  static const shoppingSessionReadyToBill =
      '/shopping-list/session/ready-to-bill';
  static const shoppingSessionFinalize = '/shopping-list/session/finalize';
  static const shoppingSessionReopen = '/shopping-list/session/reopen';
  static const shoppingSessions = '/shopping-list/sessions';
  static String shoppingSession(int id) => '/shopping-list/sessions/$id';
  static String shoppingProductConfirmRec(int productId) =>
      '/shopping-list/products/$productId/confirm-recommendation';

  // --- plaid (plaid_integration.py, prefix /plaid) ---
  static const plaidStatus = '/plaid/status';
  static const plaidLinkToken = '/plaid/link-token';
  static const plaidExchangePublicToken = '/plaid/exchange-public-token';
  static const plaidItems = '/plaid/items';
  static String plaidItemSync(int id) => '/plaid/items/$id/sync';
  static String plaidItem(int id) => '/plaid/items/$id';
  static const plaidStagedTx = '/plaid/staged-transactions';
  static String plaidStagedTxConfirm(int id) =>
      '/plaid/staged-transactions/$id/confirm';
  static const plaidStagedTxBulkConfirm =
      '/plaid/staged-transactions/bulk-confirm';
  static String plaidStagedTxDismiss(int id) =>
      '/plaid/staged-transactions/$id/dismiss';
  static String plaidStagedTxFlagDup(int id) =>
      '/plaid/staged-transactions/$id/flag-duplicate';
  static String plaidStagedTxMatch(int id) =>
      '/plaid/staged-transactions/$id/match-candidates';
  static String plaidStagedTxLink(int id) =>
      '/plaid/staged-transactions/$id/link-receipt';
  static String plaidStagedTxAttachUpload(int id) =>
      '/plaid/staged-transactions/$id/attach-upload';
  static const plaidAccounts = '/plaid/accounts';
  static const plaidAccountsRefreshBalances =
      '/plaid/accounts/refresh-balances';
  static const plaidCardsOverview = '/plaid/cards-overview';
  static String plaidAccountLoanMeta(int id) =>
      '/plaid/accounts/$id/loan-meta';
  static String plaidAccountIdentity(int id) =>
      '/plaid/accounts/$id/identity';
  static const plaidTransactionBreakdown = '/plaid/transaction-breakdown';
  static const plaidTransactions = '/plaid/transactions';
  static const plaidSpendingTrends = '/plaid/spending-trends';

  // --- analytics (calculate_spending_analytics.py, prefix /analytics) ---
  static const analyticsExpenseSummary = '/analytics/expense-summary';
  static const analyticsRestaurantSummary = '/analytics/restaurant-summary';
  static const analyticsSpending = '/analytics/spending';
  static const analyticsPriceHistory = '/analytics/price-history';
  static const analyticsDealsCaptured = '/analytics/deals-captured';
  static const analyticsStoreComparison = '/analytics/store-comparison';
  static const analyticsUtilitySummary = '/analytics/utility-summary';
  static const analyticsSpendByPerson = '/analytics/spend-by-person';
  static const analyticsRecurringObligations =
      '/analytics/recurring-obligations';
  static const analyticsBillProjections = '/analytics/bill-projections';
  static const analyticsSpendingByCategory =
      '/analytics/spending-by-category';
  static const analyticsSpendingByCategoryItems =
      '/analytics/spending-by-category/items';
  static const analyticsReceiptsActivity = '/analytics/receipts-activity';

  // --- inventory (manage_inventory.py, prefix /inventory) ---
  static const inventory = '/inventory';
  static const inventoryAddItem = '/inventory/add-item';
  static String inventoryConsume(int itemId) => '/inventory/$itemId/consume';
  static String inventoryUpdate(int itemId) => '/inventory/$itemId/update';
  static String inventoryProductLowStatus(int productId) =>
      '/inventory/products/$productId/low-status';
  static String inventoryProductRegularUse(int productId) =>
      '/inventory/products/$productId/regular-use';
  static String inventoryProductConfirmLow(int productId) =>
      '/inventory/products/$productId/confirm-low';
  static String inventoryItem(int itemId) => '/inventory/$itemId';
  static String inventoryProduct(int productId) =>
      '/inventory/products/$productId';
  static String inventoryProductExpiryOverride(int productId) =>
      '/inventory/products/$productId/expiry-override';
  static const inventoryRecentlyUsedUp = '/inventory/recently-used-up';
  static String inventoryProductRestore(int productId) =>
      '/inventory/products/$productId/restore';

  // --- products (manage_product_catalog.py, prefix /products) ---
  static const products = '/products';
  static const productsSearch = '/products/search';
  static const productsCreate = '/products/create';
  static String productUpdate(int id) => '/products/$id/update';
  static const productsReviewQueue = '/products/review-queue';
  static const productsReviewQueueEnhance = '/products/review-queue/enhance';
  static String productEnhance(int id) => '/products/$id/enhance';
  static String productReviewStatus(int id) => '/products/$id/review-status';
  static String product(int id) => '/products/$id';
  static String productPriceHistory(int id) => '/products/$id/price-history';
  static const productsAutoDedupTokens = '/products/auto-dedup-tokens';

  // --- budget (manage_household_budget.py, prefix /budget) ---
  static const budgetSetMonthly = '/budget/set-monthly';
  static const budgetStatus = '/budget/status';
  static const budgetAllocationSummary = '/budget/allocation-summary';
  static const budgetCategorySummary = '/budget/category-summary';
  static const budgetTargetHistory = '/budget/target-history';

  // --- contributions (manage_contributions.py, prefix /contributions) ---
  static const contributionsSummary = '/contributions/summary';
  static String contributionsUser(int userId) =>
      '/contributions/users/$userId';

  // --- recommendations ---
  static const recommendations = '/recommendations';

  // --- chat ---
  static const chatMessages = '/chat/messages';
  static const chatAudit = '/chat/audit';

  // --- medications ---
  static const medications = '/medications';
  static const medicationsBarcodeLookup = '/medications/barcode-lookup';
  static String medication(int id) => '/medications/$id';
  static String medicationPhoto(int id) => '/medications/$id/photo';

  // --- floor_obligations (prefix /floor-obligations) ---
  static const floorObligations = '/floor-obligations/';
  static String floorObligation(int id) => '/floor-obligations/$id';
  static const floorObligationsAvailable = '/floor-obligations/available';
  static const floorObligationsSummary = '/floor-obligations/summary';

  // --- shared_dining ---
  static String sharedDiningFromPurchase(int purchaseId) =>
      '/shared-dining/purchases/$purchaseId';
  static String sharedDiningExpenseParticipant(int expenseId, int participantId) =>
      '/shared-dining/expenses/$expenseId/participants/$participantId';
  static String sharedDiningDebtSettle(int debtId) =>
      '/shared-dining/debts/$debtId/settle';
  static String sharedDiningContactSettleAll(int contactId) =>
      '/shared-dining/contacts/$contactId/settle-all';
  static const sharedDiningBalances = '/shared-dining/balances';
  static String sharedDiningBalance(int contactId) =>
      '/shared-dining/balances/$contactId';
  static const sharedDiningContacts = '/shared-dining/contacts';
  static const sharedDiningContactsMerge = '/shared-dining/contacts/merge';

  // --- product_snapshots ---
  static const productSnapshotsUpload = '/product-snapshots/upload';
  static const productSnapshots = '/product-snapshots';
  static String productSnapshot(int id) => '/product-snapshots/$id';
  static String productSnapshotImage(int id) =>
      '/product-snapshots/$id/image';
  static const productSnapshotsReviewQueue =
      '/product-snapshots/review-queue';
  static String productSnapshotReview(int id) =>
      '/product-snapshots/$id/review';
  static String productSnapshotPromote(int id) =>
      '/product-snapshots/$id/promote';

  // --- cash_transactions ---
  static const cashTransactions = '/cash-transactions';
  static String cashTransaction(int id) => '/cash-transactions/$id';

  // --- bill_edit (root-level, no prefix) ---
  static String billProvider(int id) => '/bill-providers/$id';
  static String billServiceLine(int id) => '/bill-service-lines/$id';

  // --- household_members (top-level, NOT the same as /auth/household-members) ---
  static const householdMembers = '/household-members';
  static String householdMember(int id) => '/household-members/$id';

  // --- stores ---
  static const apiStores = '/api/stores';
  static String apiStoreVisibility(int id) => '/api/stores/$id/visibility';

  // --- kitchen ---
  static const apiKitchenCatalog = '/api/kitchen/catalog';

  // --- global search ---
  static const search = '/api/search';

  // --- ai models ---
  static const apiModels = '/api/models';
  static const apiModelsSelect = '/api/models/select';
  static const apiModelsUnlock = '/api/models/unlock';
  static const apiAdminModels = '/api/admin/models';
  static const apiAdminModelsUsage = '/api/admin/models/usage';
  static String apiAdminModel(int id) => '/api/admin/models/$id';
}
