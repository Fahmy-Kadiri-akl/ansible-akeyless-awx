# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
    name: akeyless
    plugin_type: inventory
    short_description: Akeyless inventory source for AWX/AAP
    description:
      - Fetches secrets from Akeyless and injects them as Ansible host_vars or
        group_vars at inventory-sync time. Designed to be configured once at the
        AWX platform level so playbooks can consume Akeyless-sourced values as
        ordinary variables, with no per-playbook Akeyless code.
      - Supports two discovery modes which can be combined.
        I(secret_path_prefix) automatically discovers every secret under a
        given Akeyless path so that adding a new secret in Akeyless requires no
        AWX-side change. I(secrets) is an explicit name-to-var mapping for
        cases where a fixed naming contract is desired.
    requirements:
      - python >= 3.9
      - akeyless (Python SDK) >= 5.0
      - akeyless.secrets_management collection >= 1.0.0
    options:
      plugin:
        description: Token identifying this plugin.
        required: true
        choices: ['akeyless.awx_integration.akeyless']
      akeyless_api_url:
        description: Akeyless API URL. For api_key and cert auth, this is the
          Akeyless control plane (https://api.akeyless.io). For k8s auth, this
          is also the SaaS API; use I(akeyless_gateway_url) to point at the
          customer gateway that performs TokenReview.
        type: str
        default: 'https://api.akeyless.io'
        env:
          - name: AKEYLESS_API_URL
      akeyless_gateway_url:
        description: Akeyless customer gateway URL. Required for k8s auth; the
          gateway is what calls Kubernetes TokenReview to validate the
          ServiceAccount token. Ignored for api_key and cert auth.
        type: str
        env:
          - name: AKEYLESS_GATEWAY_URL
      access_type:
        description: Akeyless authentication method.
        type: str
        default: cert
        choices: [api_key, cert, k8s, jwt, aws_iam, azure_ad, gcp, ldap, oidc, saml, oci, universal_identity, password]
        env:
          - name: AKEYLESS_ACCESS_TYPE
      access_id:
        description: Akeyless access ID.
        type: str
        env:
          - name: AKEYLESS_ACCESS_ID
      access_key:
        description: Access key (used when access_type=api_key).
        type: str
        env:
          - name: AKEYLESS_ACCESS_KEY
      cert_file:
        description: Path to client certificate PEM file (cert auth).
        type: path
        env:
          - name: AKEYLESS_CERT_FILE
      key_file:
        description: Path to client private key PEM file (cert auth).
        type: path
        env:
          - name: AKEYLESS_KEY_FILE
      cert_data:
        description: Base64-encoded certificate (alternative to cert_file).
        type: str
        env:
          - name: AKEYLESS_CERT_DATA
      key_data:
        description: Base64-encoded private key (alternative to key_file).
        type: str
        env:
          - name: AKEYLESS_KEY_DATA
      k8s_auth_config_name:
        description: Name of the Kubernetes auth config in the Akeyless cert
          auth method (used when access_type=k8s). Identifies which K8s cluster
          this auth flow targets when the auth method spans multiple clusters.
        type: str
        env:
          - name: AKEYLESS_K8S_AUTH_CONFIG_NAME
      k8s_service_account_token:
        description: Kubernetes ServiceAccount JWT (used when access_type=k8s).
          If unset and I(k8s_token_path) is readable, the plugin reads the
          token from there. Inside an AWX EE pod, the default path resolves
          to the pod's own ServiceAccount token.
        type: str
        env:
          - name: AKEYLESS_K8S_SA_TOKEN
      k8s_token_path:
        description: Filesystem path to read the Kubernetes ServiceAccount
          JWT from when I(k8s_service_account_token) is not set. Defaults to
          the in-pod auto-mount path.
        type: path
        default: /var/run/secrets/kubernetes.io/serviceaccount/token
        env:
          - name: AKEYLESS_K8S_TOKEN_PATH
      ca_bundle:
        description: Path to a CA bundle to verify the gateway TLS cert.
        type: path
        env:
          - name: AKEYLESS_CA_BUNDLE
      validate_certs:
        description: Validate the gateway TLS certificate.
        type: bool
        default: true
        env:
          - name: AKEYLESS_VALIDATE_CERTS
      secret_path_prefix:
        description:
          - Akeyless path prefix under which to discover secrets automatically.
            Every static secret found under this prefix becomes an Ansible
            variable. New secrets added to Akeyless under this prefix are
            picked up on the next inventory sync without any AWX-side change.
        type: str
      secret_types:
        description: Akeyless item types to include during discovery.
        type: list
        elements: str
        default: ["static-secret"]
      var_name_template:
        description:
          - Format string for deriving Ansible variable names from discovered
            secret paths. Placeholders are C({basename}) (last path segment),
            C({relpath}) (path under prefix), and C({fullname}) (full path).
            Non-identifier characters are replaced with C(_).
        type: str
        default: '{relpath}'
      secrets:
        description:
          - Explicit list of Akeyless secret-to-variable mappings. Combined
            with anything discovered by I(secret_path_prefix).
        type: list
        elements: dict
        default: []
      hosts:
        description:
          - List of host names to attach the fetched secrets to.
          - If neither hosts nor groups is provided, defaults to ['localhost'].
        type: list
        elements: str
        default: []
      groups:
        description: Mapping of group_name to list of host names.
        type: dict
        default: {}
      default_group:
        description: Umbrella group containing every host/group created.
        type: str
        default: akeyless_managed
'''

EXAMPLES = r'''
# inventory.akeyless.yml: discover all secrets under a path prefix
plugin: akeyless.awx_integration.akeyless
secret_path_prefix: /apps/prod
hosts:
  - app01.example.com
  - app02.example.com
default_group: prod_apps

---
# inventory.akeyless.yml: explicit name-to-var mapping
plugin: akeyless.awx_integration.akeyless
secrets:
  - name: /apps/prod/db_password
    var: db_password
  - name: /apps/prod/api_token
    var: api_token
hosts:
  - app01.example.com
'''

import base64
import os
import re

from ansible.errors import AnsibleError, AnsibleParserError
from ansible.plugins.inventory import BaseInventoryPlugin, Cacheable, Constructable

try:
    import akeyless
    from akeyless import ApiException
    from ansible_collections.akeyless.secrets_management.plugins.module_utils._akeyless_helper import AkeylessHelper
    from ansible_collections.akeyless.secrets_management.plugins.module_utils._authenticator import AkeylessAuthenticator
    HAS_AKEYLESS = True
    _IMPORT_ERR = None
except ImportError as e:
    HAS_AKEYLESS = False
    _IMPORT_ERR = e


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = 'akeyless.awx_integration.akeyless'

    def verify_file(self, path):
        if super().verify_file(path):
            if path.endswith(('akeyless.yml', 'akeyless.yaml')):
                return True
        return False

    def parse(self, inventory, loader, path, cache=True):
        super().parse(inventory, loader, path, cache)
        if not HAS_AKEYLESS:
            raise AnsibleError(
                'akeyless Python SDK and akeyless.secrets_management collection '
                'are required: %s' % _IMPORT_ERR
            )
        self._read_config_data(path)

        opts = self._build_auth_options()
        self._resolve_cert_material(opts)
        self._resolve_k8s_token(opts)

        api_client = self._build_api_client(opts)
        authenticator = AkeylessAuthenticator(opts)
        try:
            authenticator.validate()
            auth_response = authenticator.authenticate(api_client)
        except ApiException as e:
            raise AnsibleError('Akeyless authentication failed: ' + AkeylessHelper.build_api_err_msg(e, 'auth'))
        except Exception as e:
            raise AnsibleError('Akeyless authentication failed: %s' % str(e))
        token = auth_response.token

        secrets_cfg = list(self.get_option('secrets') or [])
        for entry in secrets_cfg:
            if 'name' not in entry or 'var' not in entry:
                raise AnsibleParserError("each 'secrets' entry must have 'name' and 'var' keys")
        discovered = self._discover_via_prefix(api_client, token)
        secrets_cfg.extend(discovered)

        if not secrets_cfg:
            raise AnsibleParserError(
                "no secrets configured: provide 'secret_path_prefix' (recommended) "
                "and/or an explicit 'secrets' list"
            )

        names = [s['name'] for s in secrets_cfg]
        try:
            body = AkeylessHelper.build_get_secret_val_body(names, {'token': token})
            secrets_by_name = api_client.get_secret_value(body)
        except ApiException as e:
            raise AnsibleError('Akeyless get_secret_value failed: ' + AkeylessHelper.build_api_err_msg(e, 'get_secret_value'))

        self._populate_inventory(secrets_cfg, secrets_by_name)

    def _discover_via_prefix(self, api_client, token):
        prefix = self.get_option('secret_path_prefix')
        if not prefix:
            return []
        types = self.get_option("secret_types") or ["static-secret"]
        template = self.get_option('var_name_template') or '{relpath}'

        body = AkeylessHelper.build_list_items_body({
            'path': prefix,
            'types': types,
            'token': token,
        })
        try:
            resp = api_client.list_items(body)
        except ApiException as e:
            raise AnsibleError('Akeyless list_items failed: ' + AkeylessHelper.build_api_err_msg(e, 'list_items'))

        items = getattr(resp, 'items', None) or []
        norm_prefix = prefix.rstrip('/') + '/'
        out = []
        seen = set()
        for it in items:
            name = getattr(it, 'item_name', None)
            if not name:
                continue
            relpath = name[len(norm_prefix):] if name.startswith(norm_prefix) else name.lstrip('/')
            basename = relpath.split('/')[-1] if relpath else name.rstrip('/').split('/')[-1]
            try:
                raw_var = template.format(basename=basename, relpath=relpath, fullname=name.lstrip('/'))
            except KeyError as ke:
                raise AnsibleParserError('var_name_template uses unknown placeholder: %s' % ke)
            var = re.sub(r'[^A-Za-z0-9_]', '_', raw_var)
            if var and var[0].isdigit():
                var = '_' + var
            if not var:
                self.display.warning('Akeyless: cannot derive variable name from %s' % name)
                continue
            if var in seen:
                self.display.warning(
                    'Akeyless: duplicate variable name %s (from %s) skipped' % (var, name))
                continue
            seen.add(var)
            out.append({'name': name, 'var': var})
        return out

    def _build_api_client(self, opts):
        api_url = opts.get('akeyless_api_url') or 'https://api.akeyless.io'
        config = akeyless.Configuration(host=api_url)
        ca_bundle = self.get_option('ca_bundle')
        validate = self.get_option('validate_certs')
        if not validate:
            config.verify_ssl = False
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        elif ca_bundle:
            config.ssl_ca_cert = ca_bundle
        return akeyless.V2Api(akeyless.ApiClient(config))

    def _build_auth_options(self):
        result = {}
        for key in ['akeyless_api_url', 'akeyless_gateway_url',
                    'access_type', 'access_id', 'access_key',
                    'cert_file', 'key_file', 'cert_data', 'key_data',
                    'k8s_auth_config_name', 'k8s_service_account_token',
                    'k8s_token_path']:
            try:
                result[key] = self.get_option(key)
            except KeyError:
                result[key] = None
        return result

    def _resolve_cert_material(self, opts):
        if opts.get('access_type') != 'cert':
            return
        if not opts.get('cert_data') and opts.get('cert_file'):
            opts['cert_data'] = self._read_file_b64(opts['cert_file'])
        if not opts.get('key_data') and opts.get('key_file'):
            opts['key_data'] = self._read_file_b64(opts['key_file'])

    def _resolve_k8s_token(self, opts):
        if opts.get('access_type') != 'k8s':
            return
        if opts.get('k8s_service_account_token'):
            return
        path = opts.get('k8s_token_path')
        if not path:
            return
        try:
            with open(path, 'r') as f:
                opts['k8s_service_account_token'] = f.read().strip()
        except OSError as e:
            raise AnsibleError(
                'Cannot read Kubernetes ServiceAccount token from %s: %s. '
                'Either set k8s_service_account_token directly or ensure the '
                'inventory-update pod has the SA token mounted at this path.'
                % (path, e)
            )

    def _read_file_b64(self, path):
        try:
            with open(path, 'rb') as f:
                return base64.b64encode(f.read()).decode('ascii')
        except OSError as e:
            raise AnsibleError('Cannot read PEM file %s: %s' % (path, e))

    def _populate_inventory(self, secrets_cfg, secrets_by_name):
        hosts = self.get_option('hosts') or []
        groups = self.get_option('groups') or {}
        default_group = self.get_option('default_group')

        if not hosts and not groups:
            hosts = ['localhost']

        if default_group:
            self.inventory.add_group(default_group)

        for host in hosts:
            self.inventory.add_host(host)
            if default_group:
                self.inventory.add_child(default_group, host)
            self._set_vars_for(host, secrets_cfg, secrets_by_name)

        for group_name, group_hosts in groups.items():
            self.inventory.add_group(group_name)
            if default_group and group_name != default_group:
                self.inventory.add_child(default_group, group_name)
            for host in group_hosts or []:
                self.inventory.add_host(host)
                self.inventory.add_child(group_name, host)
            self._set_vars_for(group_name, secrets_cfg, secrets_by_name)

    def _set_vars_for(self, target, secrets_cfg, secrets_by_name):
        for s in secrets_cfg:
            value = secrets_by_name.get(s['name']) if isinstance(secrets_by_name, dict) else None
            if value is None:
                self.display.warning('Akeyless: secret %s not returned' % s['name'])
                continue
            self.inventory.set_variable(target, s['var'], value)
