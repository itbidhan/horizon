# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2013, Big Switch Networks, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import logging
import re

from django.utils.translation import ugettext as _

from horizon import exceptions
from horizon import forms
from horizon.utils import fields
from horizon.utils.validators import validate_port_range
from horizon import workflows

from openstack_dashboard import api


LOG = logging.getLogger(__name__)


class AddPoolAction(workflows.Action):
    name = forms.CharField(max_length=80, label=_("Name"))
    description = forms.CharField(
        initial="", required=False,
        max_length=80, label=_("Description"))
    subnet_id = forms.ChoiceField(label=_("Subnet"))
    protocol = forms.ChoiceField(label=_("Protocol"))
    lb_method = forms.ChoiceField(label=_("Load Balancing Method"))
    admin_state_up = forms.BooleanField(label=_("Admin State"),
                                     initial=True, required=False)

    def __init__(self, request, *args, **kwargs):
        super(AddPoolAction, self).__init__(request, *args, **kwargs)

        tenant_id = request.user.tenant_id

        subnet_id_choices = [('', _("Select a Subnet"))]
        try:
            networks = api.quantum.network_list_for_tenant(request, tenant_id)
        except:
            exceptions.handle(request,
                              _('Unable to retrieve networks list.'))
            networks = []
        for n in networks:
            for s in n['subnets']:
                subnet_id_choices.append((s.id, s.cidr))
        self.fields['subnet_id'].choices = subnet_id_choices

        protocol_choices = [('', _("Select a Protocol"))]
        protocol_choices.append(('HTTP', 'HTTP'))
        protocol_choices.append(('HTTPS', 'HTTPS'))
        self.fields['protocol'].choices = protocol_choices

        lb_method_choices = [('', _("Select a Method"))]
        lb_method_choices.append(('ROUND_ROBIN', 'ROUND_ROBIN'))
        lb_method_choices.append(('LEAST_CONNECTIONS', 'LEAST_CONNECTIONS'))
        lb_method_choices.append(('SOURCE_IP', 'SOURCE_IP'))
        self.fields['lb_method'].choices = lb_method_choices

    class Meta:
        name = _("PoolDetails")
        permissions = ('openstack.services.network',)
        help_text = _("Create Pool for current tenant.\n\n"
                      "Assign a name and description for the pool. "
                      "Choose one subnet where all members of this "
                      "pool must be on. "
                      "Select the protocol and load balancing method "
                      "for this pool. "
                      "Admin State is UP (checked) by default.")


class AddPoolStep(workflows.Step):
    action_class = AddPoolAction
    contributes = ("name", "description", "subnet_id",
                   "protocol", "lb_method", "admin_state_up")

    def contribute(self, data, context):
        context = super(AddPoolStep, self).contribute(data, context)
        if data:
            return context


class AddPool(workflows.Workflow):
    slug = "addpool"
    name = _("Add Pool")
    finalize_button_name = _("Add")
    success_message = _('Added pool "%s".')
    failure_message = _('Unable to add pool "%s".')
    success_url = "horizon:project:loadbalancers:index"
    default_steps = (AddPoolStep,)

    def format_status_message(self, message):
        name = self.context.get('name')
        return message % name

    def handle(self, request, context):
        try:
            pool = api.lbaas.pool_create(request, **context)
            return True
        except:
            return False


class AddVipAction(workflows.Action):
    name = forms.CharField(max_length=80, label=_("Name"))
    description = forms.CharField(
        initial="", required=False,
        max_length=80, label=_("Description"))
    floatip_address = forms.ChoiceField(
        label=_("VIP Address from Floating IPs"),
        widget=forms.Select(attrs={'disabled': 'disabled'}),
        required=False)
    other_address = fields.IPField(required=False,
                                   initial="",
                                   version=fields.IPv4,
                                   mask=False)
    protocol_port = forms.IntegerField(label=_("Protocol Port"), min_value=1,
                              help_text=_("Enter an integer value "
                                          "between 1 and 65535."),
                              validators=[validate_port_range])
    protocol = forms.ChoiceField(label=_("Protocol"))
    session_persistence = forms.ChoiceField(
        required=False, initial={}, label=_("Session Persistence"))
    cookie_name = forms.CharField(
        initial="", required=False,
        max_length=80, label=_("Cookie Name"),
        help_text=_("Required for APP_COOKIE persistence;"
                    " Ignored otherwise."))
    connection_limit = forms.IntegerField(
        min_value=-1, label=_("Connection Limit"),
        help_text=_("Maximum number of connections allowed "
                    "for the VIP or '-1' if the limit is not set"))
    admin_state_up = forms.BooleanField(
        label=_("Admin State"), initial=True, required=False)

    def __init__(self, request, *args, **kwargs):
        super(AddVipAction, self).__init__(request, *args, **kwargs)

        self.fields['other_address'].label = _("Specify a free IP address"
                                               " from %s" %
                                               args[0]['subnet'])

        protocol_choices = [('', _("Select a Protocol"))]
        protocol_choices.append(('HTTP', 'HTTP'))
        protocol_choices.append(('HTTPS', 'HTTPS'))
        self.fields['protocol'].choices = protocol_choices

        session_persistence_choices = [('', _("Set Session Persistence"))]
        for mode in ('SOURCE_IP', 'HTTP_COOKIE', 'APP_COOKIE'):
            session_persistence_choices.append((mode, mode))
        self.fields[
            'session_persistence'].choices = session_persistence_choices

        floatip_address_choices = [('', _("Currently Not Supported"))]
        self.fields['floatip_address'].choices = floatip_address_choices

    def clean(self):
        cleaned_data = super(AddVipAction, self).clean()
        if (cleaned_data.get('session_persistence') == 'APP_COOKIE' and
                not cleaned_data.get('cookie_name')):
            msg = _('Cookie name is required for APP_COOKIE persistence.')
            self._errors['cookie_name'] = self.error_class([msg])
        return cleaned_data

    class Meta:
        name = _("AddVip")
        permissions = ('openstack.services.network',)
        help_text = _("Create a VIP for this pool. "
                      "Assign a name and description for the VIP. "
                      "Specify an IP address and port for the VIP. "
                      "Choose the protocol and session persistence "
                      "method for the VIP."
                      "Specify the max connections allowed. "
                      "Admin State is UP (checked) by default.")


class AddVipStep(workflows.Step):
    action_class = AddVipAction
    depends_on = ("pool_id", "subnet")
    contributes = ("name", "description", "floatip_address",
                   "other_address", "protocol_port", "protocol",
                   "session_persistence", "cookie_name",
                   "connection_limit", "admin_state_up")

    def contribute(self, data, context):
        context = super(AddVipStep, self).contribute(data, context)
        return context


class AddVip(workflows.Workflow):
    slug = "addvip"
    name = _("Add VIP")
    finalize_button_name = _("Add")
    success_message = _('Added VIP "%s".')
    failure_message = _('Unable to add VIP "%s".')
    success_url = "horizon:project:loadbalancers:index"
    default_steps = (AddVipStep,)

    def format_status_message(self, message):
        name = self.context.get('name')
        return message % name

    def handle(self, request, context):
        if context['other_address'] == '':
            context['address'] = context['floatip_address']
        else:
            if not context['floatip_address'] == '':
                self.failure_message = _('Only one address can be specified. '
                                         'Unable to add VIP "%s".')
                return False
            else:
                context['address'] = context['other_address']
        try:
            pool = api.lbaas.pool_get(request, context['pool_id'])
            context['subnet_id'] = pool['subnet_id']
        except:
            context['subnet_id'] = None
            self.failure_message = _('Unable to retrieve the specified pool. '
                                     'Unable to add VIP "%s".')
            return False

        if context['session_persistence']:
            stype = context['session_persistence']
            if stype == 'APP_COOKIE':
                cookie = context['cookie_name']
                context['session_persistence'] = {'type': stype,
                                                  'cookie_name': cookie}
            else:
                context['session_persistence'] = {'type': stype}
        else:
            context['session_persistence'] = {}

        try:
            api.lbaas.vip_create(request, **context)
            return True
        except:
            return False


class AddMemberAction(workflows.Action):
    pool_id = forms.ChoiceField(label=_("Pool"))
    members = forms.MultipleChoiceField(
        label=_("Member(s)"),
        required=True,
        initial=["default"],
        widget=forms.CheckboxSelectMultiple(),
        error_messages={'required':
                            _('At least one member must be specified')},
        help_text=_("Select members for this pool "))
    weight = forms.IntegerField(max_value=256, min_value=0, label=_("Weight"),
                                help_text=_("Relative part of requests this "
                                "pool member serves compared to others"))
    protocol_port = forms.IntegerField(label=_("Protocol Port"), min_value=1,
                              help_text=_("Enter an integer value "
                                          "between 1 and 65535."),
                              validators=[validate_port_range])
    admin_state_up = forms.BooleanField(label=_("Admin State"),
                                        initial=True, required=False)

    def __init__(self, request, *args, **kwargs):
        super(AddMemberAction, self).__init__(request, *args, **kwargs)

        pool_id_choices = [('', _("Select a Pool"))]
        try:
            pools = api.lbaas.pools_get(request)
        except:
            pools = []
            exceptions.handle(request,
                              _('Unable to retrieve pools list.'))
        pools = sorted(pools,
                       key=lambda pool: pool.name)
        for p in pools:
            pool_id_choices.append((p.id, p.name))
        self.fields['pool_id'].choices = pool_id_choices

        members_choices = []
        try:
            servers, has_more = api.nova.server_list(request)
        except:
            servers = []
            exceptions.handle(request,
                              _('Unable to retrieve instances list.'))

        if len(servers) == 0:
            self.fields['members'].label = _("No servers available. "
                                             "Click Add to cancel.")
            self.fields['members'].required = False
            self.fields['members'].help_text = _("Select members "
                                                 "for this pool ")
            self.fields['pool_id'].required = False
            self.fields['weight'].required = False
            self.fields['protocol_port'].required = False
            return

        for m in servers:
            members_choices.append((m.id, m.name))
        self.fields['members'].choices = sorted(
            members_choices,
            key=lambda member: member[1])

    class Meta:
        name = _("MemberDetails")
        permissions = ('openstack.services.network',)
        help_text = _("Add member to selected pool.\n\n"
                      "Choose one or more listed instances to be "
                      "added to the pool as member(s). "
                      "Assign a numeric weight for this member "
                      "Specify the port number the member(s) "
                      "operate on; e.g., 80.")


class AddMemberStep(workflows.Step):
    action_class = AddMemberAction
    contributes = ("pool_id", "members", "protocol_port", "weight",
                   "admin_state_up")

    def contribute(self, data, context):
        context = super(AddMemberStep, self).contribute(data, context)
        return context


class AddMember(workflows.Workflow):
    slug = "addmember"
    name = _("Add Member")
    finalize_button_name = _("Add")
    success_message = _('Added member(s).')
    failure_message = _('Unable to add member(s).')
    success_url = "horizon:project:loadbalancers:index"
    default_steps = (AddMemberStep,)

    def handle(self, request, context):
        for m in context['members']:
            params = {'device_id': m}
            try:
                plist = api.quantum.port_list(request, **params)
            except:
                return False
            if plist:
                context['address'] = plist[0].fixed_ips[0]['ip_address']
            try:
                context['member_id'] = api.lbaas.member_create(
                    request, **context).id
            except:
                return False
        return True


class AddMonitorAction(workflows.Action):
    pool_id = forms.ChoiceField(label=_("Pool"))
    type = forms.ChoiceField(
        label=_("Type"),
        choices=[('ping', _('PING')),
                 ('tcp', _('TCP')),
                 ('http', _('HTTP')),
                 ('https', _('HTTPS'))],
        widget=forms.Select(attrs={
            'class': 'switchable',
            'data-slug': 'type'
        }))
    delay = forms.IntegerField(
        min_value=1,
        label=_("Delay"),
        help_text=_("The minimum time in seconds between regular checks "
                    "of a member"))
    timeout = forms.IntegerField(
        min_value=1,
        label=_("Timeout"),
        help_text=_("The maximum time in seconds for a monitor to wait "
                    "for a reply"))
    max_retries = forms.IntegerField(
        max_value=10, min_value=1,
        label=_("Max Retries (1~10)"),
        help_text=_("Number of permissible failures before changing "
                    "the status of member to inactive"))
    http_method = forms.ChoiceField(
        initial="GET",
        required=False,
        choices=[('GET', _('GET'))],
        label=_("HTTP Method"),
        help_text=_("HTTP method used to check health status of a member"),
        widget=forms.Select(attrs={
            'class': 'switched',
            'data-switch-on': 'type',
            'data-type-http': _('HTTP Method'),
            'data-type-https': _('HTTP Method')
        }))
    url_path = forms.CharField(
        initial="/",
        required=False,
        max_length=80,
        label=_("URL"),
        widget=forms.TextInput(attrs={
            'class': 'switched',
            'data-switch-on': 'type',
            'data-type-http': _('URL'),
            'data-type-https': _('URL')
        }))
    expected_codes = forms.RegexField(
        initial="200",
        required=False,
        max_length=80,
        regex=r'^(\d{3}(\s*,\s*\d{3})*)$|^(\d{3}-\d{3})$',
        label=_("Expected HTTP Status Codes"),
        help_text=_("Expected code may be a single value (e.g. 200), "
                    "a list of values (e.g. 200, 202), "
                    "or range of values (e.g. 200-204)"),
        widget=forms.TextInput(attrs={
            'class': 'switched',
            'data-switch-on': 'type',
            'data-type-http': _('Expected HTTP Status Codes'),
            'data-type-https': _('Expected HTTP Status Codes')
        }))
    admin_state_up = forms.BooleanField(label=_("Admin State"),
                                        initial=True, required=False)

    def __init__(self, request, *args, **kwargs):
        super(AddMonitorAction, self).__init__(request, *args, **kwargs)

        pool_id_choices = [('', _("Select a Pool"))]
        try:
            pools = api.lbaas.pools_get(request)
            for p in pools:
                pool_id_choices.append((p.id, p.name))
        except:
            exceptions.handle(request,
                              _('Unable to retrieve pools list.'))
        self.fields['pool_id'].choices = pool_id_choices

    def clean(self):
        cleaned_data = super(AddMonitorAction, self).clean()
        type_opt = cleaned_data.get('type')

        if type_opt in ['http', 'https']:
            http_method_opt = cleaned_data.get('http_method')
            url_path = cleaned_data.get('url_path')
            expected_codes = cleaned_data.get('expected_codes')

            if not http_method_opt:
                msg = _('Please choose a HTTP method')
                self._errors['http_method'] = self.error_class([msg])
            if not url_path:
                msg = _('Please specify an URL')
                self._errors['url_path'] = self.error_class([msg])
            if not expected_codes:
                msg = _('Please enter a single value (e.g. 200), '
                        'a list of values (e.g. 200, 202), '
                        'or range of values (e.g. 200-204)')
                self._errors['expected_codes'] = self.error_class([msg])
        return cleaned_data

    class Meta:
        name = _("MonitorDetails")
        permissions = ('openstack.services.network',)
        help_text = _("Create a monitor for a pool.\n\n"
                      "Select target pool and type of monitoring. "
                      "Specify delay, timeout, and retry limits "
                      "required by the monitor. "
                      "Specify method, URL path, and expected "
                      "HTTP codes upon success.")


class AddMonitorStep(workflows.Step):
    action_class = AddMonitorAction
    contributes = ("pool_id", "type", "delay", "timeout", "max_retries",
                   "http_method", "url_path", "expected_codes",
                   "admin_state_up")

    def contribute(self, data, context):
        context = super(AddMonitorStep, self).contribute(data, context)
        if data:
            return context


class AddMonitor(workflows.Workflow):
    slug = "addmonitor"
    name = _("Add Monitor")
    finalize_button_name = _("Add")
    success_message = _('Added monitor')
    failure_message = _('Unable to add monitor')
    success_url = "horizon:project:loadbalancers:index"
    default_steps = (AddMonitorStep,)

    def handle(self, request, context):
        try:
            context['monitor_id'] = api.lbaas.pool_health_monitor_create(
                request, **context).get('id')
            return True
        except:
            return False
