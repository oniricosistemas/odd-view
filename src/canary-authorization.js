export function canReadArtifact(requestedOwnerId, authenticatedUserId) {
  if (!requestedOwnerId || !authenticatedUserId) return false;
  return requestedOwnerId === authenticatedUserId;
}
