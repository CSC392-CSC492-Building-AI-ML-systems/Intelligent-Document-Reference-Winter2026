package handler

import (
    "encoding/json"
    "net/http"
)

type HealthResponse struct {
    Status  string `json:"status"`
    Service string `json:"service"`
}

func HealthCheck(w http.ResponseWriter, r *http.Request) {
    resp := HealthResponse{Status: "ok", Service: "search-api"}
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(resp)
}
