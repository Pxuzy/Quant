import { Alert, Button, Space } from 'antd';
import { ApiError } from '../api/client';

type ErrorStateProps = {
  error: unknown;
  onRetry?: () => void;
};

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const description =
    error instanceof ApiError
      ? error.message
      : error instanceof Error
        ? error.message
        : '服务暂时不可用，请稍后重试。';

  return (
    <Alert
      type="error"
      showIcon
      message="数据加载失败"
      description={
        <Space direction="vertical" size={12}>
          <span>{description}</span>
          {onRetry ? (
            <Button size="small" onClick={onRetry}>
              重新加载
            </Button>
          ) : null}
        </Space>
      }
    />
  );
}
