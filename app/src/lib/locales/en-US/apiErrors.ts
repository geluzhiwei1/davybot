/**
 * apiErrors — error translation layer strings (en).
 * Used by apiErrorMessage() in lib/api/errors.ts; page-level fallbacks stay in their own namespaces.
 */
export default {
  cancel: "Cancel",
  network: "Network connection failed. Check your connection and retry",
  auth: "Session expired. Please sign in again",
  forbidden: "You do not have permission for this action. Contact an admin or partner",
  notFound: "The data does not exist or has been deleted",
  conflict: "The action conflicts with the current state. Refresh and retry",
  validation: "The submitted content is invalid. Check the fields and retry",
  server: "The service is temporarily unavailable. Please retry later",
  unknown: "Action failed. Please retry",
  invalidTransition: "Illegal status transition. Refresh and follow the workflow",
  insufficient: "Insufficient data or balance to complete the action",
};
