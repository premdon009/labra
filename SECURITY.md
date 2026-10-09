# Security policy

Labra handles medical records, so security reports get priority.

## Reporting a vulnerability
Use GitHub's **private vulnerability reporting**: the repository's *Security* tab, then *Report a vulnerability*. Don't open a public issue for a security problem.

| Step | Target |
|---|---|
| Acknowledge the report | 3 working days |
| First assessment and severity | 10 working days |
| Fix released for high or critical issues | 30 days, sooner when actively exploited |

## Never send real patient data
Not in a report, an issue, a log excerpt or a screenshot. Reproduce the problem with `labra seed` data. If a real lab's data was exposed, say so in the private report, without including the data.

## Supported versions
While Labra is at 0.x, only the latest release gets fixes. Install from a tagged release, never from `master`.

## Scope
In scope: the Labra application, its container images, the Compose files and the install scripts in this repository. Out of scope: a lab's own server, network, Cloudflare, backup or identity-provider setup, unless Labra's documentation told them to set it up that way.
