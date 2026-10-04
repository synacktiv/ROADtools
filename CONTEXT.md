# ROADrecon GUI

The browser interface for exploring an Entra ID tenant dump (`roadrecon.db`): directory objects, the links between them, and the Conditional Access policies that apply to them.

## Language

### Directory objects

**Object**:
Any directory entry with an `objectId`: user, group, device, service principal, application, administrative unit, directory role.
_Avoid_: entity, item, resource (resource means the target of a permission)

**Object reference**:
A pointer to an object as it appears anywhere in the UI: its id, its type and a display name, always rendered as a link to the object page.
_Avoid_: backlink, ref, pointer

**Unresolved reference**:
An id found in the dump (in a policy, an assignment, a grant) that matches no object in the database, usually a deleted or out-of-tenant principal.

**Principal**:
The object a role, app role, grant or policy is assigned to: a user, group or service principal.

**Resource**:
The service principal whose permissions are granted (target of an app role assignment or OAuth2 grant).
_Avoid_: target app, API

### Membership

**Direct member**:
An object linked to a group, role or administrative unit without any intermediate group.

**Transitive member**:
An object that is a member through one or more nested groups. Always includes direct members.
_Avoid_: nested member, indirect member, recursive member

**Owner**:
A user or service principal allowed to manage an object. Ownership is never transitive.

### Roles

**Active assignment**:
A directory role currently held by a principal.

**Eligible assignment**:
A directory role a principal can activate through PIM but does not currently hold.

**Scope**:
Where an assignment applies: the whole directory, an administrative unit, or a single application.

### Conditional Access

**Policy**:
A Conditional Access policy (policyType 18 in the dump).
_Avoid_: CAP, CA rule

**Named location**:
A set of IP ranges or countries that policies reference in their location condition (policyType 6).

**Include / Exclude**:
The two sides of every policy condition. An object excluded on any path is out of scope, even if it is also included.

**Policy scope**:
The set of users a policy targets after removing exclusions, ignoring the non-user conditions (apps, platforms, locations, client apps, risk).
_Avoid_: affected users (use "in scope"), applies to

**Match**:
One reason a policy concerns an object: which side (include or exclude), which condition, and the chain of groups or roles it came through ("via").

**Approximate match**:
A match computed from data that does not fully describe the condition, e.g. guest types inferred from `userType`, or role scope through an eligible assignment.

**Policy state**:
Enabled, report-only, or disabled. Report-only policies are evaluated but never enforced.
