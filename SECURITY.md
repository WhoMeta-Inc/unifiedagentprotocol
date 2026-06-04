# Security Policy

## Supported versions

| Version | Supported |
|---------|:---------:|
| 1.0.x   | ✅ |
| 0.x     | ❌ (deprecated, see CHANGELOG) |

## Reporting a vulnerability

Please **do not** open public GitHub issues for vulnerabilities.

Send a coordinated-disclosure report to:

    security@whometa.io

Include:
- Affected version and component (`core/`, `bridges/<name>/`, `runtime/`, `cli/`).
- Reproduction steps or PoC.
- Expected vs. actual impact.

You will receive an acknowledgement within **3 working days**. A fix
schedule is agreed within **10 working days**. Embargoed credit on
release notes by default; opt out by request.

## Secret handling

UAP `AuthConfig` rejects inline secrets at the schema layer. Producers
MUST reference secrets via supported URI schemes (`vault://`,
`aws-sm://`, `gcp-sm://`, `env://NAME`, `file://`). Any bridge that
encounters an inline secret is required to fail validation, not coerce.

## Threat model assumptions

- UAP payloads may cross trust boundaries (registry → runtime → caller).
- Bridges MUST treat foreign payloads as untrusted input — no dynamic
  imports, no code execution, no network calls during conversion.
- The `runtime/` adapter does not enforce auth by itself — wrap it in
  your reverse proxy / API gateway and apply scopes from `AuthConfig`.
