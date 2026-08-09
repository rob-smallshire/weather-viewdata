# Captured responses

Real responses, kept so that the parsing can be exercised against what the
service actually sends rather than against what we imagine it sends.

| | |
|---|---|
| `trondheim-compact.json` | `locationforecast/2.0/compact` for Trondheim (63.4305, 10.3951, 14m), captured 9 August 2026 |

Prefer re-using these to making fresh requests. met.no asks for traffic to be
spread out and for responses to be cached, and a test suite that calls a public
API on every run is exactly what those terms are about.

Forecast data from the Norwegian Meteorological Institute, CC BY 4.0.
