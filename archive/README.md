# Forge archive

The previous prediction workspace is preserved at Git tag `archive/forge-v1`
(commit `fb16e33`) and in the original branch `feat/forge-prediction-tools`.

Restore a separate checkout with:

```sh
git worktree add ../forge-archive archive/forge-v1
```

A local source archive is also available at `.archives/forge-v1.tar.gz`.
Credentials, internal discussions, uploaded datasets, and installed dependencies
are excluded from that archive. The original local `.forge` data is retained.
