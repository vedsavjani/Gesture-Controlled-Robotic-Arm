# Board benchmarks (UNO Q, 2026-10-30, Python 3.13.5)

CPU has no ARMv8.1 LSE ("atomics" missing in /proc/cpuinfo).

| Test | Result |
|---|---|
| MediaPipe 1.2.0 (py 3.13 and 3.12) | Crash: "compiled with lse enabled" |
| MediaPipe 0.10.18 (py 3.12) | Works, 6.0 FPS (167 ms/frame) |
| ai-edge-litert 2.3.0, palm detector | 190 / 101 / 62 ms (1 / 2 / 4 threads) |
| ai-edge-litert 2.3.0, landmark model | 136 / 76 / 45 ms (1 / 2 / 4 threads) |

Decision: ai-edge-litert, 4 threads, system Python 3.13.
