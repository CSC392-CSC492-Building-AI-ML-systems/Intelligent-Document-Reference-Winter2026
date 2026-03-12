package handler

import (
    "encoding/json"
    "net/http"
)

type SearchRequest struct {
    Query string `json:"query"`
    TopK  int    `json:"top_k"`
}

type SearchResult struct {
    ID    string  `json:"id"`
    Score float64 `json:"score"`
    Text  string  `json:"text"`
}

func Search(w http.ResponseWriter, r *http.Request) {
    if r.Method != http.MethodPost {
        http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
        return
    }

    var req SearchRequest
    if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
        http.Error(w, "Bad request", http.StatusBadRequest)
        return
    }

    results := []SearchResult{
        {ID: "doc1", Score: 0.95, Text: "Sample result"},
    }

    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(map[string]interface{}{
        "results": results,
        "count":   len(results),
    })
}
