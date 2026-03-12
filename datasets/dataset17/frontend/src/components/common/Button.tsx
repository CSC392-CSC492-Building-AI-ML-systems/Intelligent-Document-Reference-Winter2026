import React, { ButtonHTMLAttributes } from 'react';
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> { variant?: 'primary' | 'secondary'; }
export const Button: React.FC<Props> = ({ variant = 'primary', children, ...props }) => (
    <button className={`btn btn-${variant}`} {...props}>{children}</button>
);
