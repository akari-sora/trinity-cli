# Security policy

English | [繁體中文](SECURITY.zh-TW.md)

## Supported versions

Only the latest release gets security fixes.

## Reporting a vulnerability

Please do not report a security problem in a public issue or merge request.

1. Open a [confidential issue](https://gitlab.com/aa22396584/trinity-cli/-/issues/new?issue[confidential]=true) on GitLab.
2. Include the version (`trinity-cli --version`), your OS, what you expected, what happened, and how to reproduce it.
3. Before you paste logs, replace tokens, cookies, credential file contents, account, chat, or bot ids, and message text with placeholders.

You should get a first reply within 7 days. After a fix is released, the report is made public with credit unless you ask otherwise.

In scope: trinity-cli itself: how it starts the seat tools, the ledger and state files, the brief, and anything that could leak a token, an id, a message, or a local path. Report a bug in one seat tool to that tool's project.

Out of scope: problems in ChatGPT (OpenAI), Grok Bot (Cursor / xAI), or Meta Muse (Meta) services themselves. Report those to the service.
