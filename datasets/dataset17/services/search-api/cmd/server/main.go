package main

import (
    "fmt"
    "log"
    "net/http"
    "os"

    "github.com/example/docsearch/services/search-api/internal/handler"
    "github.com/example/docsearch/services/search-api/internal/middleware"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    mux := http.NewServeMux()
    mux.HandleFunc("/health", handler.HealthCheck)
    mux.HandleFunc("/api/search", handler.Search)

    wrapped := middleware.Logging(middleware.CORS(mux))

    log.Printf("Starting search API on :%s", port)
    if err := http.ListenAndServe(fmt.Sprintf(":%s", port), wrapped); err != nil {
        log.Fatal(err)
    }
}
