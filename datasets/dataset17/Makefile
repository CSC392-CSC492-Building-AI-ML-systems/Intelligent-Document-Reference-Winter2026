.PHONY: all build test clean

all: build

build:
	cd crates && cargo build --release
	cd services/search-api && go build -o ../../bin/search-api ./cmd/server
	cd frontend && npm run build

test:
	cd crates && cargo test
	cd services/search-api && go test ./...
	cd frontend && npm test

clean:
	rm -rf bin/ target/ frontend/dist/
