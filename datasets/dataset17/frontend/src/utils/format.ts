export function truncate(text: string, maxLength: number): string {
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength - 3) + '...';
}

export function formatScore(score: number): string {
    return (score * 100).toFixed(1) + '%';
}

export function formatDate(date: string): string {
    return new Date(date).toLocaleDateString();
}
