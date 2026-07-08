import { Tag } from 'antd';
import { formatAuthStatus } from '../domain/labels';

const authStatusColors: Record<string, string> = {
  not_required: 'blue',
  configured: 'success',
  missing: 'warning',
  unknown: 'default',
};

export function resolveAuthStatus({
  authStatus,
  configAuthStatus,
  requiresToken,
}: {
  authStatus?: string;
  configAuthStatus?: string;
  requiresToken: boolean;
}) {
  return authStatus ?? configAuthStatus ?? (requiresToken ? 'unknown' : 'not_required');
}

export function AuthStatusTag({ status }: { status?: string }) {
  const normalizedStatus = status || 'unknown';
  return <Tag color={authStatusColors[normalizedStatus] ?? 'default'}>{formatAuthStatus(normalizedStatus)}</Tag>;
}
