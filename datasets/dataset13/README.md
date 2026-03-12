# Platform Monorepo

Deep package hierarchy (6+ nesting levels) simulating a Java enterprise project.
Tests the indexer's ability to handle deeply nested directory structures with
many small files at various depth levels.

## Structure
```
src/main/java/com/acme/platform/
├── core/
│   ├── domain/{entities,valueobjects,events}/
│   └── application/{services,commands,queries}/
├── infrastructure/
│   ├── persistence/{repositories,mappers,migrations}/
│   ├── messaging/{producers,consumers}/
│   └── external/{embedding,storage}/
└── api/
    ├── rest/{controllers,dto/{request,response},middleware}/
    └── graphql/{resolvers,types}/
```
