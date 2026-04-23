# Optimization Rules

Use this file for performance, cost, and reliability optimization tasks.

## Optimization Order
1. Define the bottleneck clearly.
2. Measure baseline.
3. Apply smallest meaningful change.
4. Re-measure and compare.
5. Keep or revert based on evidence.

## Metrics First
- Track latency (p50/p95), throughput, error rate, and resource usage.
- Separate cold-start metrics from steady-state metrics.
- For provider calls, track cost per request and per successful package.

## Code-Level Rules
- Do not optimize speculative code paths.
- Remove obvious duplicate work before complex optimizations.
- Prefer algorithmic improvements over micro-optimizations.
- Keep readability unless measured gains justify complexity.

## Database Rules
- Add indexes based on query evidence, not guesswork.
- Avoid N+1 query patterns.
- Limit result sets and paginate where needed.
- Measure query plans before and after index changes.

## Async and I/O Rules
- Use async boundaries only for true I/O wait.
- Set explicit timeouts and retries for external calls.
- Apply backoff and jitter for transient API failures.
- Add concurrency limits to avoid upstream throttling.

## Caching Rules
- Cache only expensive and repeatable operations.
- Define TTL explicitly.
- Design invalidation before shipping cache logic.
- Track cache hit/miss metrics.

## Cost Controls
- Log provider usage and per-call cost.
- Enforce configurable budget guards for expensive operations.
- Prefer cheaper fallback providers when quality is acceptable.

## Validation Checklist
- Baseline and after-change metrics captured.
- No behavior regression in tests.
- Error handling remains intact.
- Net impact documented in commit/task notes.
