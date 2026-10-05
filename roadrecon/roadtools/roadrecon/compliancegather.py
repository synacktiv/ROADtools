'''
Gather Intune device compliance settings and policies via MS Graph.

Needs an MS Graph access token with DeviceManagementConfiguration.Read.All
(DeviceManagementConfiguration.ReadWrite.All works too).
'''
import argparse
import json
import sys
import time

import requests
import roadtools.roadlib.metadef.database as database
from roadtools.roadlib.metadef.database import Base, DeviceManagementSetting, DeviceCompliancePolicy, \
DeviceCompliancePolicyAssignment
from roadtools.roadlib.auth import Authentication
from roadtools.roadrecon.gather import getargs
from sqlalchemy.orm import sessionmaker

GATHER_RESOURCE = 'https://graph.microsoft.com'
GRAPH_URL = 'https://graph.microsoft.com/beta'
SETTINGS_URL = GRAPH_URL + '/deviceManagement?$select=settings'
POLICIES_URL = GRAPH_URL + '/deviceManagement/deviceCompliancePolicies?$expand=assignments,scheduledActionsForRule($expand=scheduledActionConfigurations)'

DESCRIPTION = '''Gather Intune device compliance settings and policies via MS Graph.

The token must be for MS Graph and carry DeviceManagementConfiguration.Read.All.
Tokens from the default client (Azure AD PowerShell) or Azure CLI do not have it;
the collector then logs a 403 and stores nothing. Example with the
Microsoft Intune PowerShell client (it must still be present in the tenant):
  roadrecon auth -c d1ddf0e4-d672-4dae-b554-9d5bdfd93547 -r https://graph.microsoft.com --device-code
  roadrecon compliancegather
A tenant without Intune answers 400 or 403: this is logged and skipped.
'''

urlcounter = 0

def strip_type(odatatype, suffix):
    '''#microsoft.graph.windows10CompliancePolicy -> windows10'''
    value = (odatatype or '').replace('#microsoft.graph.', '')
    return value[:-len(suffix)] if value.endswith(suffix) else value

def fetch(url, headers, paged=False):
    '''GET url (following @odata.nextLink if paged). Returns None on error, so the caller skips.'''
    global urlcounter
    items = []
    while url:
        urlcounter += 1
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            print('Error %d for URL %s, skipping (no Intune licence or missing DeviceManagementConfiguration.Read.All?)' % (res.status_code, url))
            print(res.text[:500])
            return None
        data = res.json()
        if not paged:
            return data
        items.extend(data.get('value', []))
        url = data.get('@odata.nextLink')
    return items

def store(dbsession, tenantid, settings, policies):
    '''Replace the compliance rows with the given Graph data. None means "not collected": keep nothing.'''
    dbsession.query(DeviceCompliancePolicyAssignment).delete()
    dbsession.query(DeviceCompliancePolicy).delete()
    dbsession.query(DeviceManagementSetting).delete()
    if settings is not None:
        dbsession.add(DeviceManagementSetting(
            id=tenantid,
            secureByDefault=settings.get('secureByDefault'),
            deviceComplianceCheckinThresholdDays=settings.get('deviceComplianceCheckinThresholdDays'),
            enhancedJailBreak=settings.get('enhancedJailBreak'),
            isScheduledActionEnabled=settings.get('isScheduledActionEnabled'),
            settings=settings,
        ))
    for policy in policies or []:
        raw = {k: v for k, v in policy.items() if k not in ('assignments', 'assignments@odata.context', 'scheduledActionsForRule', 'scheduledActionsForRule@odata.context')}
        odatatype = policy.get('@odata.type')
        dbsession.add(DeviceCompliancePolicy(
            id=policy['id'],
            odataType=odatatype,
            platform=strip_type(odatatype, 'CompliancePolicy'),
            displayName=policy.get('displayName'),
            description=policy.get('description'),
            createdDateTime=policy.get('createdDateTime'),
            lastModifiedDateTime=policy.get('lastModifiedDateTime'),
            version=policy.get('version'),
            settings=raw,
            scheduledActionsForRule=policy.get('scheduledActionsForRule'),
        ))
        for assignment in policy.get('assignments') or []:
            target = assignment.get('target') or {}
            dbsession.add(DeviceCompliancePolicyAssignment(
                id=assignment['id'],
                policyId=policy['id'],
                targetType=strip_type(target.get('@odata.type'), 'AssignmentTarget'),
                groupId=target.get('groupId'),
                filterId=target.get('deviceAndAppManagementAssignmentFilterId'),
                filterType=target.get('deviceAndAppManagementAssignmentFilterType'),
                target=target,
            ))
    dbsession.commit()

def run(token, tenantid, dburl, user_agent=None):
    headers = {'Authorization': f"Bearer {token['accessToken']}"}
    if user_agent:
        headers['User-Agent'] = user_agent
    data = fetch(SETTINGS_URL, headers)
    settings = data.get('settings') if data is not None else None
    policies = fetch(POLICIES_URL, headers, paged=True)
    if settings is None and policies is None:
        print('No compliance data gathered, database left untouched')
        return
    engine = database.init(dburl=dburl)
    # Only creates the compliance tables if this DB predates them, never drops anything
    Base.metadata.create_all(engine)
    dbsession = sessionmaker(bind=engine)()
    store(dbsession, tenantid, settings, policies)
    print('Stored %d compliance policies' % len(policies or []))
    dbsession.close()

def main(args=None):
    global urlcounter
    if args is None:
        parser = argparse.ArgumentParser(add_help=True, description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)
        getargs(parser)
        args = parser.parse_args()
        if len(sys.argv) < 2:
            parser.print_help()
            sys.exit(1)
    if args.tokens_stdin:
        token = json.loads(sys.stdin.read())
    else:
        with open(args.tokenfile, 'r') as infile:
            token = json.load(infile)
    dburl = database.parse_db_argument(args.database)
    try:
        _, tokendata = Authentication.parse_accesstoken(token['accessToken'])
    except KeyError:
        print('No access token found in tokenfile')
        return
    if tokendata['aud'] not in ('https://graph.microsoft.com/', 'https://graph.microsoft.com', '00000003-0000-0000-c000-000000000000'):
        if args.autotoken:
            try:
                token = Authentication().handle_autotoken(token, args=args, resource=GATHER_RESOURCE)
            except Exception as exc:
                token = None
                print(f'Could not get an MS Graph token: {exc}')
            if not token:
                print('Skipping compliance gathering')
                return
        else:
            print(f"Wrong token audience, got {tokendata['aud']} but expected https://graph.microsoft.com")
            print("Make sure to request a token with -r https://graph.microsoft.com")
            return
    user_agent = None
    if args.user_agent:
        auth = Authentication()
        auth.set_user_agent(args.user_agent)
        user_agent = auth.user_agent
    tenantid = args.tenant or token.get('tenantId') or tokendata.get('tid')

    seconds = time.perf_counter()
    try:
        run(token, tenantid, dburl, user_agent)
    except requests.exceptions.RequestException as exc:
        print(f'Compliance gathering failed: {exc}')
    elapsed = time.perf_counter() - seconds
    print("ROADrecon compliancegather executed in {0:0.2f} seconds and issued {1} HTTP requests.".format(elapsed, urlcounter))

if __name__ == "__main__":
    main()
