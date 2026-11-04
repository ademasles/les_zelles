# Security policy

Please report vulnerabilities privately through [GitHub security advisories](https://github.com/ademasles/les_zelles/security/advisories/new), not in public issues. You should get an answer within a week.

## Deployment notes

- Set `ZELLES_API_KEY` whenever the API is reachable by anyone other than you. Without it the API is open.
- Tender documents can be confidential. With `ZELLES_LLM_MODEL=none` or a local provider, no document content leaves the machine. With a cloud provider, passages are sent to that provider under its data policy.
- Uploaded files are size-limited (`ZELLES_MAX_UPLOAD_MB`), type-checked from their bytes, and stored under a content hash; document ids are validated before any file path is built.
- Never commit `.env`. Secrets are read from the environment only.
