document.getElementById('searchBtn').addEventListener('click', async () => {
    const query = document.getElementById('query').value;
    if (!query.trim()) return;

    const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 10 })
    });
    const data = await res.json();

    const container = document.getElementById('results');
    container.innerHTML = data.results.map(r => `
        <div class="result-card">
            <div class="score">Score: ${r.score}</div>
            <div class="snippet">${r.snippet}</div>
        </div>
    `).join('');
});
