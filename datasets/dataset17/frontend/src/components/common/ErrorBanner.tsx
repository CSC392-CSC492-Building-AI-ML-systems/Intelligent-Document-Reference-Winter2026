import React from 'react';
interface Props { message: string; onDismiss?: () => void; }
export const ErrorBanner: React.FC<Props> = ({ message, onDismiss }) => (
    <div className="error-banner">
        <span>{message}</span>
        {onDismiss && <button onClick={onDismiss}>Dismiss</button>}
    </div>
);
