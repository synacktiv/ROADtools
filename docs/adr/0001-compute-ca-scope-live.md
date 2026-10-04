# Compute Conditional Access scope live instead of reading lnk_policy_*

The GUI computes which users a policy targets (and which policies target an object) from the policy JSON and the membership tables at request time, rather than reading the `lnk_policy_user_*` tables that `policyanalysis` fills during `gather`. Those tables are missing on older dumps, ignore role membership through role-assignable groups and eligible roles, and only cover users; the live computation works on any dump and can explain each match ("via group X"). `policyanalysis` is left untouched for other consumers.
