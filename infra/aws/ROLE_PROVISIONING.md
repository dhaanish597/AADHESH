# Cognito role provisioning

The Aadesh user pool is administrator-provisioned. `AdminCreateUserConfig.AllowAdminCreateUserOnly`
is enabled, and the public app client can write `email` only. `custom:role`,
`custom:assigned_site`, and `custom:principal_id` are read into the API's verified Cognito claims
and must be assigned through an IAM-authorized operator process. Do not add these attributes to
the app client's `WriteAttributes` list.

Before inviting a user, an operator must assign exactly one supported role (`supervisor`,
`facilitator`, or `worker`) and a stable `custom:principal_id`. Supervisors must also receive the
exact `custom:assigned_site` identifier used by the site profile. Facilitators and workers should
receive a site only if their account workflow requires it. API requests, query parameters and
frontend state cannot assign or override these values. The API rejects a missing or unrecognized
role and rejects a supervisor with no assigned site.

Provision users with Cognito's administrative APIs (`AdminCreateUser` and
`AdminUpdateUserAttributes`) under a separately controlled operator IAM identity. For example,
the operator workflow may create a supervisor with these attributes:

```text
email=<verified work email>
custom:role=supervisor
custom:assigned_site=<site id>
custom:principal_id=<stable supervisor id>
```

Do not expose those administrative credentials to the browser, Amplify build, or Lambda API
caller. This repository does not provision an operator identity or grant a human admin role;
deployment owners must configure that restricted operator access before inviting users. The API
also checks site-scoped Cedar policy before returning a roster or its QR payloads.
