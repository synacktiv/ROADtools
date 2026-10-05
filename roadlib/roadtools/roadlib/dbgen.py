from roadtools.roadlib.metadef.entitytypes import *
from roadtools.roadlib.metadef.entitytypes_pim import *
from roadtools.roadlib.metadef.entitytypes_ig import *
import enum
header = '''import os
import json
import datetime
import sqlalchemy.types
from sqlalchemy import Column, Text, Boolean, BigInteger as Integer, create_engine, Table, ForeignKey
from sqlalchemy.orm import relationship, sessionmaker, foreign, declarative_base
from sqlalchemy.types import TypeDecorator, TEXT
Base = declarative_base()


class JSON(TypeDecorator):
    impl = TEXT
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value

class DateTime(TypeDecorator):
    impl = sqlalchemy.types.DateTime
    def process_bind_param(self, value, dialect):
        if value is not None and isinstance(value, str):
            # Sometimes it ends on a Z, sometimes it doesn't
            if value[-1] == 'Z':
                if '.' in value:
                    try:
                        value = datetime.datetime.strptime(value[:-2], '%Y-%m-%dT%H:%M:%S.%f')
                    except ValueError:
                        value = datetime.datetime.strptime(value[:-2], '%Y-%m-%dT%H:%M:%S.')
                else:
                    value = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
            elif '.' in value:
                if '+' in value[-7:] or '-' in value[-7:]:
                    value = datetime.datetime.strptime(value[:-7], '%Y-%m-%dT%H:%M:%S.%f')
                else:
                    try:
                        value = datetime.datetime.strptime(value[:-1], '%Y-%m-%dT%H:%M:%S.%f')
                    except ValueError:
                        value = datetime.datetime.strptime(value[:-1], '%Y-%m-%dT%H:%M:%S.')
            elif '+' in value[-7:] or '-' in value[-7:]:
                value = datetime.datetime.strptime(value[:-6], '%Y-%m-%dT%H:%M:%S')
            else:
                value = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')

        return value

class SerializeMixin():
    def as_dict(self, delete_empty=False):
        """
            Converts the object to a dict
        """
        result = {}
        for c in self.__table__.columns:
            attr = getattr(self, c.name)
            if delete_empty:
                if attr:
                    result[c.name] = attr
            else:
                result[c.name] = attr
        return result


    def __repr__(self):
        return str(self.as_dict(True))
'''

dbdef = '''
class %s(Base, SerializeMixin):
    __tablename__ = "%ss"
%s
%s
'''

footer = '''
def parse_db_argument(dbarg):
    \'\'\'
    Parse DB string given as argument into full path required
    for SQLAlchemy
    \'\'\'
    if not ':/' in dbarg:
        if dbarg[0] != '/':
            return 'sqlite:///' + os.path.join(os.getcwd(), dbarg)
        else:
            return 'sqlite:///' + dbarg
    else:
        return dbarg

def init(create=False, dburl='sqlite:///roadrecon.db'):
    if 'postgresql' in dburl:
        engine = create_engine(dburl,
                               executemany_mode='values',
                               executemany_values_page_size=1001)
    else:
        engine = create_engine(dburl)

    if create:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
'''

# Custom joins for service principals since these are kinda weird
custom_splinks = '''
    oauth2PermissionGrants = relationship("OAuth2PermissionGrant",
        primaryjoin=objectId == foreign(OAuth2PermissionGrant.clientId))

    appRolesAssigned = relationship("AppRoleAssignment",
        primaryjoin=objectId == foreign(AppRoleAssignment.resourceId))

    appRolesAssignedTo = relationship("AppRoleAssignment",
        primaryjoin=objectId == foreign(AppRoleAssignment.principalId))
'''

coldef = '    %s = Column(%s)'
pcoldef = '    %s = Column(%s, primary_key=True)'
fcoldef = '    %s = Column(%s, ForeignKey("%s"))'

def gen_db_class(classdef, rels, rev_rels):
    classname = classdef.__name__
    props = {}
    for base in classdef.__bases__:
        try:
            props.update(base.props)
        except AttributeError:
            # No base, so no props
            pass
    props.update(classdef.props)
    cols = []
    for pname, pclass in props.items():
        try:
            dbtype = pclass.DBTYPE.__name__
        except AttributeError:
            if isinstance(pclass, enum.EnumType):
                dbtype = 'Text'
            else:
                # Complex type
                dbtype = 'JSON'
        if dbtype == 'Binary':
            dbtype = 'Text'
        if dbtype == 'LargeBinary':
            dbtype = 'Text'
        if pname == 'objectId' or (classname == 'Domain' and pname == 'name') or (classname in ['RoleAssignment', 'EligibleRoleAssignment', 'AuthorizationPolicy', 'DirectorySetting'] and pname == 'id') or (classname == 'ApplicationRef' and pname == 'appId') or ((classname.startswith('PIM') or classname.startswith('IG')) and pname == 'id'):
            cols.append(pcoldef % (pname, dbtype))
        elif pname == 'resourceId' and classname.startswith('PIM'):
            cols.append(fcoldef % (pname, dbtype, 'PIMgovernanceResources.id'))
        elif pname == 'accessPackageId' and classname.startswith('IG'):
            cols.append(fcoldef % (pname, dbtype, 'IGaccessPackages.id'))
        elif pname == 'assignmentPolicyId' and classname.startswith('IG'):
            cols.append(fcoldef % (pname, dbtype, 'IGaccessPackageAssignmentPolicys.id'))
        elif pname == 'roleDefinitionId':
            if classname.startswith('PIM'):
                cols.append(fcoldef % (pname, dbtype, 'PIMgovernanceRoleDefinitions.id'))
            else:
                cols.append(fcoldef % (pname, dbtype, 'RoleDefinitions.objectId'))
        else:
            cols.append(coldef % (pname, dbtype))
    outrels = []
    for rel in rels:
        try:
            reldata = relations[rel]
            if reldata[0] == reldata[1]:
                outrels.append(gen_link_fkey(rel, reldata[1], reldata[2], reldata[3], reldata[0], 'child'+reldata[0]))
            else:
                outrels.append(gen_link(rel, reldata[1], reldata[2], reldata[3]))
        except KeyError:
            # Probably one to many relationship
            reldata = relations_nolink[rel]
            outrels.append(gen_link_nolinktbl(reldata[1], reldata[2], reldata[3]))

    for rel in rev_rels:
        try:
            reldata = relations[rel]
            if reldata[0] == reldata[1]:
                outrels.append(gen_link_fkey(rel, reldata[0], reldata[3], reldata[2], 'child'+reldata[0], reldata[0]))
            else:
                outrels.append(gen_link(rel, reldata[0], reldata[3], reldata[2]))
        except KeyError:
            # Probably one to many relationship
            reldata = relations_nolink[rel]
            outrels.append(gen_link_nolinktbl(reldata[0], reldata[3], reldata[2]))

    if classname == 'ServicePrincipal':
        outrels.append(custom_splinks)
    return dbdef % (classname, classname, '\n'.join(cols), '\n'.join(outrels))

# Relationships defined here
# these are many to many
relations = {
    # Relationship name: (LeftGroup, RightGroup, relation name, reverse relation name)
    'group_member_user': ('Group', 'User', 'memberUsers', 'memberOf'),
    'group_member_group': ('Group', 'Group', 'memberGroups', 'memberOf'),
    'group_member_contact': ('Group', 'Contact', 'memberContacts', 'memberOf'),
    'group_member_device': ('Group', 'Device', 'memberDevices', 'memberOf'),
    'group_member_serviceprincipal': ('Group', 'ServicePrincipal', 'memberServicePrincipals', 'memberOf'),
    'device_owner': ('Device', 'User', 'owner', 'ownedDevices'),
    'application_owner_user': ('Application', 'User', 'ownerUsers', 'ownedApplications'),
    'application_owner_serviceprincipal': ('Application', 'ServicePrincipal', 'ownerServicePrincipals', 'ownedApplications'),
    'serviceprincipal_owner_user': ('ServicePrincipal', 'User', 'ownerUsers', 'ownedServicePrincipals'),
    'serviceprincipal_owner_serviceprincipal': ('ServicePrincipal', 'ServicePrincipal', 'ownerServicePrincipals', 'ownedServicePrincipals'),
    'role_member_user': ('DirectoryRole', 'User', 'memberUsers', 'memberOfRole'),
    'role_member_serviceprincipal': ('DirectoryRole', 'ServicePrincipal', 'memberServicePrincipals', 'memberOfRole'),
    'role_member_group': ('DirectoryRole', 'Group', 'memberGroups', 'memberOfRole'),
    'group_owner_user': ('Group', 'User', 'ownerUsers', 'ownedGroups'),
    'group_owner_serviceprincipal': ('Group', 'ServicePrincipal', 'ownerServicePrincipals', 'ownedGroups'),
    'au_member_user': ('AdministrativeUnit', 'User', 'memberUsers', 'memberOfAu'),
    'au_member_group': ('AdministrativeUnit', 'Group', 'memberGroups', 'memberOfAu'),
    'au_member_device': ('AdministrativeUnit', 'Device', 'memberDevices', 'memberOfAu'),
    'policy_user_include': ('Policy', 'User', 'includedUsers', 'policiesIncluded'),
    'policy_user_exclude': ('Policy', 'User', 'excludedUsers', 'policiesExcluded'),

    # PIM
    'pim_resource': ('PIMprivilegedAccess', 'PIMgovernanceResource', 'resources', 'parent'),
    'pim_resource_rolealerts': ('PIMgovernanceResource', 'PIMgovernanceAlert', 'alerts', 'resource'),
    'pim_resource_aadgroup': ('PIMgovernanceResource', 'Group', 'group', 'pimResource'),
    'pim_roleassignment_subjectuser': ('PIMgovernanceRoleAssignment', 'User', 'subjectUser', 'pimRoleAssignments'),
    'pim_roleassignment_subjectgroup': ('PIMgovernanceRoleAssignment', 'Group', 'subjectGroup', 'pimRoleAssignments'),
    'pim_roleassignment_subjectserviceprincipal': ('PIMgovernanceRoleAssignment', 'ServicePrincipal', 'subjectServicePrincipal', 'pimRoleAssignments'),
    'pim_roleassignmentrequest_subjectuser': ('PIMgovernanceRoleAssignmentRequest', 'User', 'subjectUser', 'pimRoleAssignmentRequests'),
    'pim_roleassignmentrequest_subjectgroup': ('PIMgovernanceRoleAssignmentRequest', 'Group', 'subjectGroup', 'pimRoleAssignmentRequests'),
    'pim_roleassignmentrequest_subjectserviceprincipal': ('PIMgovernanceRoleAssignmentRequest', 'ServicePrincipal', 'subjectServicePrincipal', 'pimRoleAssignmentRequests'),

    # IG
    'ig_cg_resource': ('IGaccessPackageCatalog', 'IGaccessPackageResource', 'resources', 'catalog'),
    'ig_ap': ('IGaccessPackageCatalog', 'IGaccessPackage', 'accessPackages', 'catalog'),
    'ig_ap_resource_request': ('IGaccessPackageResource', 'IGaccessPackageResourceRequest', 'resourceRequests', 'resource'),
    'ig_ap_rrs_role': ('IGaccessPackageResourceRoleScope', 'IGaccessPackageResourceRole', 'role', 'resourceRoleScopes'),
    'ig_ap_rrs_scope': ('IGaccessPackageResourceRoleScope', 'IGaccessPackageResourceScope', 'scope', 'resourceRoleScopes'),
    'ig_ap_rr': ('IGaccessPackageResource', 'IGaccessPackageResourceRole', 'resourceRoles', 'resource'),
    'ig_ap_rr_scope': ('IGaccessPackage', 'IGaccessPackageResourceRoleScope', 'resourceRoleScopes', 'accessPackage'),
    'ig_ap_assignment_target': ('IGaccessPackageAssignment', 'IGaccessPackageSubject', 'subject', 'assignments'),
    'ig_ap_assignment_request': ('IGaccessPackage', 'IGaccessPackageAssignmentRequest', 'assignmentRequests', 'accessPackage'),
    'ig_ap_assignment_request_target': ('IGaccessPackageAssignmentRequest', 'IGaccessPackageSubject', 'subject', 'assignmentRequestsAsTarget'),
    'ig_ap_assignment_request_requestor': ('IGaccessPackageAssignmentRequest', 'IGaccessPackageSubject', 'requestor', 'assignmentRequests'),
    'ig_ap_assignment_policy_inscope_user': ('IGaccessPackageAssignmentPolicy', 'User', 'scopeUsers', 'accessPackagePolicies'),
    'ig_ap_assignment_policy_inscope_group': ('IGaccessPackageAssignmentPolicy', 'Group', 'scopeGroups', 'accessPackagePolicies'),
    'ig_ap_assignment_policy_inscope_serviceprincipal': ('IGaccessPackageAssignmentPolicy', 'ServicePrincipal', 'scopeServicePrincipals', 'accessPackagePolicies'),
    #'ig_ap_assignment_policy_inscope_agent': ('IGaccessPackageAssignmentPolicy', 'User', 'scopeAgents', 'accessPackagePolicies'),

    # Linked to assignment? check
    'ig_ap_assignment_resource_role': ('IGaccessPackageAssignment', 'IGaccessPackageAssignmentResourceRole', 'assignmentResourceRoles', 'assignment'),

    # AZ
    'az_roleassignment_user': ('AZroleAssignment', 'User', 'user', 'azRoleAssignments'),
    'az_roleassignment_group': ('AZroleAssignment', 'Group', 'group', 'azRoleAssignments'),
    'az_roleassignment_serviceprincipal': ('AZroleAssignment', 'ServicePrincipal', 'serviceprincipal', 'azRoleAssignments'),
    'az_roleassignment_eligible_user': ('AZroleEligibilityScheduleInstance', 'User', 'user', 'azEligibleRoleAssignments'),
    'az_roleassignment_eligible_group': ('AZroleEligibilityScheduleInstance', 'Group', 'group', 'azEligibleRoleAssignments'),
    'az_roleassignment_eligible_serviceprincipal': ('AZroleEligibilityScheduleInstance', 'ServicePrincipal', 'serviceprincipal', 'azEligibleRoleAssignments'),


}

# One to many relationships
relations_nolink = {
    # Relationship name: (LeftGroup, RightGroup, relation name, reverse relation name)
    'role_assignment_active': ('RoleDefinition', 'RoleAssignment', 'assignments', 'roleDefinition'),
    'role_assignment_eligible': ('RoleDefinition', 'EligibleRoleAssignment', 'eligibleAssignments', 'roleDefinition'),

    # PIM
    'pim_resource_roledefinitions': ('PIMgovernanceResource', 'PIMgovernanceRoleDefinition', 'roleDefinitions', 'resource'),
    'pim_resource_roleassignmentrequests': ('PIMgovernanceResource', 'PIMgovernanceRoleAssignmentRequest', 'roleAssignmentrequests', 'resource'),
    'pim_roledefinition_assignment': ('PIMgovernanceRoleDefinition', 'PIMgovernanceRoleAssignment', 'roleAssignments', 'roleDefinition'),
    'pim_roledefinition_rolesettings': ('PIMgovernanceRoleDefinition', 'PIMgovernanceRoleSetting', 'roleSettings', 'roleDefinition'),
    'pim_roledefinition_rolesettingsv2': ('PIMgovernanceRoleDefinition', 'PIMgovernanceRoleSettingV2', 'roleSettingsv2', 'roleDefinition'),
    'pim_resource_roleassignments': ('PIMgovernanceResource', 'PIMgovernanceRoleAssignment', 'roleAssignments', 'resource'),
    'pim_resource_rolesettings': ('PIMgovernanceResource', 'PIMgovernanceRoleSetting', 'roleSettings', 'resource'),
    'pim_resource_rolesettingsv2': ('PIMgovernanceResource', 'PIMgovernanceRoleSettingV2', 'roleSettingsv2', 'resource'),

    # IG
    'ig_ap_assignment_policy': ('IGaccessPackage', 'IGaccessPackageAssignmentPolicy', 'assignmentPolicies', 'accessPackage'),
    'ig_ap_assignment': ('IGaccessPackage', 'IGaccessPackageAssignment', 'assignments', 'accessPackage'),

}

# Normal link table
link_tbl_tpl = '''
lnk_%s = Table('lnk_%s', Base.metadata,
    Column('%s', Text, ForeignKey('%ss.objectId')),
    Column('%s', Text, ForeignKey('%ss.objectId'))
)
'''

# PIM link table, uses ID
link_tbl_tpl_pim = '''
lnk_%s = Table('lnk_%s', Base.metadata,
    Column('%s', Text, ForeignKey('%ss.id')),
    Column('%s', Text, ForeignKey('%ss.id'))
)
'''

# Linking PIM to AAD data, use id on left objectId on right
link_tbl_tpl_pim_aad = '''
lnk_%s = Table('lnk_%s', Base.metadata,
    Column('%s', Text, ForeignKey('%ss.id')),
    Column('%s', Text, ForeignKey('%ss.objectId'))
)
'''

def gen_link_table(linkname, left_tbl, right_tbl):
    # For links between same properties, use different names
    if left_tbl == right_tbl:
        right_tbl_name = 'child' + right_tbl
    else:
        right_tbl_name = right_tbl
    return link_tbl_tpl % (linkname, linkname, left_tbl, left_tbl, right_tbl_name, right_tbl)

def gen_link_table_pim(linkname, left_tbl, right_tbl):
    # For links between same properties, use different names
    if left_tbl == right_tbl:
        right_tbl_name = 'child' + right_tbl
    else:
        right_tbl_name = right_tbl
    return link_tbl_tpl_pim % (linkname, linkname, left_tbl, left_tbl, right_tbl_name, right_tbl)

def gen_link_table_pim_aad(linkname, left_tbl, right_tbl):
    # For links between same properties, use different names
    if left_tbl == right_tbl:
        right_tbl_name = 'child' + right_tbl
    else:
        right_tbl_name = right_tbl
    return link_tbl_tpl_pim_aad % (linkname, linkname, left_tbl, left_tbl, right_tbl_name, right_tbl)


# Simple link template for many to many relationships with link table
link_tpl = '''    %s = relationship("%s",
        secondary=lnk_%s,
        back_populates="%s")
'''

def gen_link(link_name, ref_table, rel_name, rev_rel_name):
    return link_tpl % (rel_name, ref_table, link_name, rev_rel_name)

# Simple link template for one to many relationships
link_tpl_nolinktbl = '''    %s = relationship("%s",
        back_populates="%s")
'''

def gen_link_nolinktbl(ref_table, rel_name, rev_rel_name):
    return link_tpl_nolinktbl % (rel_name, ref_table, rev_rel_name)

# Link template with explicit foreign key
# this voodoo is inspired by https://docs.sqlalchemy.org/en/13/orm/join_conditions.html#self-referential-many-to-many-relationship
link_tpl_fkey = '''    {0} = relationship("{1}",
        secondary=lnk_{2},
        primaryjoin=objectId==lnk_{2}.c.{3},
        secondaryjoin=objectId==lnk_{2}.c.{4},
        back_populates="{5}")
'''

def gen_link_fkey(link_name, ref_table, rel_name, rev_rel_name, ref_column, sec_ref_column):
    return link_tpl_fkey.format(rel_name, ref_table, link_name, ref_column, sec_ref_column, rev_rel_name)

# Custom link table for indicating which policies include all users
link_policy_allusers = '''
lnk_policy_user_include_allusers = Table('lnk_policy_user_include_allusers', Base.metadata,
    Column('Policy', Text, ForeignKey('Policys.objectId'))
)
'''

# Tables to generate and relationships with other tables are defined here
tables = [
    # Table, relation, back_relation
    # These come first since they are referenced from service principals
    (AppRoleAssignment, [], []),
    (OAuth2PermissionGrant, [], []),
    (User, [], ['group_member_user', 'application_owner_user', 'serviceprincipal_owner_user', 'role_member_user', 'device_owner', 'group_owner_user', 'au_member_user', 'policy_user_include', 'policy_user_exclude', 'pim_roleassignment_subjectuser', 'pim_roleassignmentrequest_subjectuser', 'ig_ap_assignment_policy_inscope_user', 'az_roleassignment_user', 'az_roleassignment_eligible_user']),
    (ServicePrincipal, ['serviceprincipal_owner_user', 'serviceprincipal_owner_serviceprincipal'], ['role_member_serviceprincipal', 'serviceprincipal_owner_serviceprincipal', 'application_owner_serviceprincipal', 'group_member_serviceprincipal', 'group_owner_serviceprincipal', 'pim_roleassignment_subjectserviceprincipal', 'pim_roleassignmentrequest_subjectserviceprincipal', 'ig_ap_assignment_policy_inscope_serviceprincipal', 'az_roleassignment_serviceprincipal', 'az_roleassignment_eligible_serviceprincipal']),
    (Group, ['group_member_group', 'group_member_user', 'group_member_contact', 'group_member_device', 'group_member_serviceprincipal', 'group_owner_user', 'group_owner_serviceprincipal'], ['group_member_group', 'role_member_group', 'au_member_group', 'pim_roleassignment_subjectgroup', 'pim_roleassignmentrequest_subjectgroup', 'ig_ap_assignment_policy_inscope_group', 'az_roleassignment_group', 'az_roleassignment_eligible_group', 'pim_resource_aadgroup']),
    (Application, ['application_owner_user', 'application_owner_serviceprincipal'], []),
    (Device, ['device_owner'], ['group_member_device', 'au_member_device']),
    # (Domain, [], []),
    (DirectoryRole, ['role_member_user', 'role_member_serviceprincipal', 'role_member_group'], []),
    (TenantDetail, [], []),
    (ApplicationRef, [], []),
    (ExtensionProperty, [], []),
    (Contact, [], ['group_member_contact']),
    (Policy, ['policy_user_include', 'policy_user_exclude'], []),
    (RoleDefinition, ['role_assignment_eligible', 'role_assignment_active'], []),
    (RoleAssignment, [], ['role_assignment_active']),
    (EligibleRoleAssignment, [], ['role_assignment_eligible']),
    (AuthorizationPolicy, [], []),
    (DirectorySetting, [], []),
    (AdministrativeUnit, ['au_member_group', 'au_member_user', 'au_member_device'], []),

    # PIM
    (PIMprivilegedAccess, ['pim_resource'], []),
    (PIMgovernanceResource, ['pim_resource_roledefinitions', 'pim_resource_roleassignments', 'pim_resource_roleassignmentrequests', 'pim_resource_rolealerts', 'pim_resource_rolesettings', 'pim_resource_rolesettingsv2', 'pim_resource_aadgroup'], ['pim_resource']),
    (PIMgovernanceRoleDefinition, ['pim_roledefinition_assignment', 'pim_roledefinition_rolesettings', 'pim_roledefinition_rolesettingsv2'], ['pim_resource_roledefinitions']),
    (PIMgovernanceRoleAssignment, ['pim_roleassignment_subjectuser', 'pim_roleassignment_subjectgroup', 'pim_roleassignment_subjectserviceprincipal'], ['pim_resource_roleassignments', 'pim_roledefinition_assignment']),
    (PIMgovernanceRoleAssignmentRequest, ['pim_roleassignmentrequest_subjectuser', 'pim_roleassignmentrequest_subjectgroup', 'pim_roleassignmentrequest_subjectserviceprincipal'], ['pim_resource_roleassignmentrequests']),
    (PIMgovernanceRoleSetting, [], ['pim_resource_rolesettings', 'pim_roledefinition_rolesettings']),
    (PIMgovernanceRoleSettingV2, [], ['pim_resource_rolesettingsv2', 'pim_roledefinition_rolesettingsv2']),
    (PIMgovernanceAlert, [], ['pim_resource_rolealerts']),

    # IG / ELM
    (IGaccessPackageCatalog, ['ig_cg_resource', 'ig_ap'], []),
    (IGaccessPackageResource, ['ig_ap_resource_request', 'ig_ap_rr'], ['ig_cg_resource']),
    (IGaccessPackageResourceRequest, [], ['ig_ap_resource_request']),
    # An access package has a resource role scope, which combines a resource and a scope together on that access package
    (IGaccessPackage, ['ig_ap_assignment_policy', 'ig_ap_assignment', 'ig_ap_assignment_request', 'ig_ap_rr_scope'], ['ig_ap']),
    (IGaccessPackageResourceRoleScope, ['ig_ap_rrs_role', 'ig_ap_rrs_scope'], ['ig_ap_rr_scope']),
    (IGaccessPackageResourceScope, [], ['ig_ap_rrs_scope']),
    (IGaccessPackageResourceRole, [], ['ig_ap_rrs_role', 'ig_ap_rr']),
    (IGaccessPackageAssignmentPolicy, ['ig_ap_assignment_policy_inscope_user', 'ig_ap_assignment_policy_inscope_group', 'ig_ap_assignment_policy_inscope_serviceprincipal'], ['ig_ap_assignment_policy']),
    (IGaccessPackageAssignment, ['ig_ap_assignment_resource_role', 'ig_ap_assignment_target'], ['ig_ap_assignment']),
    (IGaccessPackageAssignmentRequest, ['ig_ap_assignment_request_target', 'ig_ap_assignment_request_requestor'], ['ig_ap_assignment_request']),
    (IGaccessPackageAssignmentResourceRole, [], ['ig_ap_assignment_resource_role']),
    (IGaccessPackageSubject, [], ['ig_ap_assignment_request_target', 'ig_ap_assignment_request_requestor', 'ig_ap_assignment_target'])
]
custom_az = '''
class AZroleDefinition(Base, SerializeMixin):
    __tablename__ = 'AZroleDefinitions'

    id = Column(Text, primary_key=True)
    name = Column(Text)
    type = Column(Text)
    role_name = Column(Text)
    description = Column(Text)
    role_type = Column(Text)
    created_on = Column(DateTime)
    permissions = Column(JSON)

    roleAssignments = relationship("AZroleAssignment",
        back_populates="role")

    eligibleRoleAssignments = relationship("AZroleEligibilityScheduleInstance",
        back_populates="role")

class AZroleAssignment(Base, SerializeMixin):
    __tablename__ = 'AZroleAssignments'

    id = Column(Text, primary_key=True)
    name = Column(Text)
    type = Column(Text)
    scope = Column(Text)
    role_definition_id = Column(Text, ForeignKey("AZroleDefinitions.id"))
    principal_id = Column(Text)
    principal_type = Column(Text)
    description = Column(Text)
    condition = Column(Text)
    condition_version = Column(Text)
    created_on = Column(DateTime)
    delegated_managed_identity_resource_id = Column(Text)

    group = relationship("Group",
        secondary=lnk_az_roleassignment_group,
        back_populates="azRoleAssignments")

    user = relationship("User",
        secondary=lnk_az_roleassignment_user,
        back_populates="azRoleAssignments")

    serviceprincipal = relationship("ServicePrincipal",
        secondary=lnk_az_roleassignment_serviceprincipal,
        back_populates="azRoleAssignments")

    role = relationship("AZroleDefinition",
        back_populates="roleAssignments")

class AZsubscription(Base, SerializeMixin):
    __tablename__ = 'AZsubscriptions'

    id = Column(Text, primary_key=True)
    subscription_id = Column(Text)
    display_name = Column(Text)
    state = Column(Text)
    subscription_policies = Column(JSON)
    authorization_source = Column(Text)

class AZmanagementGroup(Base, SerializeMixin):
    __tablename__ = 'AZmanagementGroups'

    id = Column(Text, primary_key=True)
    name = Column(Text)
    type = Column(Text)
    display_name = Column(Text)
    tenant_id = Column(Text)
    details = Column(JSON)

class AZroleEligibilityScheduleInstance(Base, SerializeMixin):
    __tablename__ = 'AZroleEligibilityScheduleInstances'

    id = Column(Text, primary_key=True)
    name = Column(Text)
    type = Column(Text)
    role_definition_id = Column(Text, ForeignKey("AZroleDefinitions.id"))
    principal_id = Column(Text)
    principal_type = Column(Text)
    scope = Column(Text)
    role_eligibility_schedule_id = Column(Text)
    status = Column(Text)
    start_date_time = Column(DateTime)
    end_date_time = Column(DateTime)
    member_type = Column(Text)
    condition = Column(Text)
    condition_version = Column(Text)
    created_on = Column(DateTime)
    expanded_properties = Column(JSON)

    group = relationship("Group",
        secondary=lnk_az_roleassignment_eligible_group,
        back_populates="azEligibleRoleAssignments")

    user = relationship("User",
        secondary=lnk_az_roleassignment_eligible_user,
        back_populates="azEligibleRoleAssignments")

    serviceprincipal = relationship("ServicePrincipal",
        secondary=lnk_az_roleassignment_eligible_serviceprincipal,
        back_populates="azEligibleRoleAssignments")

    role = relationship("AZroleDefinition",
        back_populates="eligibleRoleAssignments")

class AZresource(Base, SerializeMixin):
    __tablename__ = 'AZresources'

    id = Column(Text, primary_key=True)
    name = Column(Text)
    type = Column(Text)
    type_display_name = Column(Text)
    resource_group = Column(Text)
    location_display_name = Column(Text)
    subscription_display_name = Column(Text)
    kind = Column(Text)
    location = Column(Text)
    subscription_id = Column(Text, ForeignKey("AZsubscriptions.id"))
    tags = Column(JSON)
    extended_location = Column(JSON)

'''

custom_intune = '''
class DeviceManagementSetting(Base, SerializeMixin):
    __tablename__ = 'DeviceManagementSettings'

    id = Column(Text, primary_key=True)
    secureByDefault = Column(Boolean)
    deviceComplianceCheckinThresholdDays = Column(Integer)
    enhancedJailBreak = Column(Boolean)
    isScheduledActionEnabled = Column(Boolean)
    settings = Column(JSON)

class DeviceCompliancePolicy(Base, SerializeMixin):
    __tablename__ = 'DeviceCompliancePolicys'

    id = Column(Text, primary_key=True)
    odataType = Column(Text)
    platform = Column(Text)
    displayName = Column(Text)
    description = Column(Text)
    createdDateTime = Column(DateTime)
    lastModifiedDateTime = Column(DateTime)
    version = Column(Integer)
    settings = Column(JSON)
    scheduledActionsForRule = Column(JSON)

class DeviceCompliancePolicyAssignment(Base, SerializeMixin):
    __tablename__ = 'DeviceCompliancePolicyAssignments'

    id = Column(Text, primary_key=True)
    policyId = Column(Text, ForeignKey("DeviceCompliancePolicys.id"))
    targetType = Column(Text)
    groupId = Column(Text)
    filterId = Column(Text)
    filterType = Column(Text)
    target = Column(JSON)

'''

with open('metadef/database.py', 'w') as outf:
    outf.write(header)
    for relname, reldata in relations.items():
        if not relname.startswith('pim_') and not relname.startswith('ig_') and not relname.startswith('az_'):
            outf.write(gen_link_table(relname, reldata[0], reldata[1]))
        elif relname.startswith('pim_roleassignment') or relname.startswith('ig_ap_assignment_policy_inscope') or relname.startswith('az_roleassignment') or relname == 'pim_resource_aadgroup':
            outf.write(gen_link_table_pim_aad(relname, reldata[0], reldata[1]))
        else:
            outf.write(gen_link_table_pim(relname, reldata[0], reldata[1]))
    outf.write(link_policy_allusers)
    for table, links, revlinks in tables:
        outf.write(gen_db_class(table, links, revlinks))
    outf.write(custom_az)
    outf.write(custom_intune)
    outf.write(footer)
