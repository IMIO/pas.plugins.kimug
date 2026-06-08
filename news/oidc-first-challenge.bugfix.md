Make the `oidc` plugin handle the interactive login challenge instead of `oidc_sso_apps`. The `oidc_sso_apps` plugin is now removed from `IChallengePlugin` (it only validates Bearer tokens), and upgrade step 1004→1005 fixes already-installed sites.
[remdub]
