# Management Studio software releases

The local Management Studio can request a release of a GitHub branch or tag to the production Align app. The Studio only dispatches the workflow; it does not hold the Render API key or deploy code itself.

## Configure GitHub and Render

1. In the repository's GitHub Settings, create a `production` environment. Add required reviewers if a second approval should be required after the owner starts a release.
2. Add the Render API key as the environment secret `RENDER_API_KEY`.
3. Add the Render service ID as the environment variable `ALIGN_RENDER_SERVICE_ID`. The workflow checks that the service is named `align-v3` and is connected to `wjb006/Align-V3.0` before deploying.
4. Install GitHub CLI on the Windows PC and sign in with access to `wjb006/Align-V3.0`. Open the local Management Studio and use **Host overview → Send a software release**.

The release workflow is dispatched from the repository's trusted `codex/align-v3-rebuild` branch. It pins the selected source branch or tag to a commit, runs Python release-control tests, the desktop/mobile browser regressions, and Windows launcher tests/build without Render credentials, and then deploys that exact tested commit. The deployment job checks the Render service identity, waits for Render to report the deployment live, and checks `https://getalign.co.uk/api/health`.

Production is the only configured software target. Staging is not created or inferred by this workflow. Local Studio's separate **Publish on the website** design action defaults to `https://getalign.co.uk`; `ALIGN_PUBLISH_URL` can override it, and the publish key must also be configured before it can send. Configure GitHub environment protection before relying on an additional production reviewer gate. Do not put Render keys in the local installer, repository files, or Studio browser code.
