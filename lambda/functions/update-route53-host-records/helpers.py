# Python imports
import logging
import os

# 3rd party imports

# local imports

# global variables
log = logging.getLogger()
defaults = {
    "dynamo_table_name": {
        "env_var": "DYNAMO_TABLE_NAME",
        "default": "update-route53-host-records",
    },
    "account_state_tag": {
        "env_var": "ACCOUNT_STATE_TAG",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/account/state",
    },
    "account_enabled_values": {
        "env_var": "ACCOUNT_ENABLED_VALUES",
        "default": "enabled",
    },
    "iam_role_tag": {
        "env_var": "IAM_ROLE_TAG",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/iam/role",
    },
    "default_iam_role": {
        "env_var": "DEFAULT_IAM_ROLE",
        "default": "STS-UpdateRoute53HostRecords",
    },
    "hostname_tag_name_account_tag": {
        "env_var": "HOSTNAME_TAG_NAME_ACCOUNT_TAG",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/tags/hostname",
    },
    "default_hostname_tag_name": {
        "env_var": "DEFAULT_HOSTNAME_TAG_NAME",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/hostname"
    },
    "dns_domain_tag_name_account_tag": {
        "env_var": "DNS_DOMAIN_TAG_NAME_ACCOUNT_TAG",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/tags/dns_domain",
    },
    "default_dns_domain_tag_name": {
        "env_var": "DEFAULT_DNS_DOMAIN_TAG_NAME",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/dns_domain"
    },
    "aliases_tag_name_account_tag": {
        "env_var": "ALIASES_TAG_NAME_ACCOUNT_TAG",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/tags/aliases",
    },
    "default_aliases_tag_name": {
        "env_var": "DEFAULT_ALIASES_TAG_NAME",
        "default": "fn.aws.joshhogle.com/update-route53-host-records/aliases"
    }
}


def get_event_value(event, key):
    """Gets a value from the event and raises an Exception if it is missing.

    Parameters:
      event (dict):   Dictionary containing event information.
      key (str):      The event key to retrieve the value for.

    Returns:
      value (object): The value of the key.

    Raises:
      Exception:  If the value missing from the event.
    """
    value = event.get(key, None)
    if value is None:
        msg = "'{}' is missing from the event".format(key)
        log.fatal(msg)
        raise Exception(msg)
    return value


def get_setting(setting):
    """Retrieves the value of a setting from the environment.

    Parameters:
      setting (str):  The name of the setting to retrieve.

    Returns:
      object: The value of the setting.
    """
    value = os.environ.get(defaults[setting]["env_var"], None)
    if value is None:
        return defaults[setting]["default"]
    return value


def tags_to_dict(tags):
    """Takes the list of tags and converts it to a regular Python dict object.

    If a tag has no "Key" or "Value" or "Values" key, it is ignored.

    Parameters:
      tags (list):    A list of tags to convert.

    Returns:
      dict: The converted dictionary representation of the tags.
    """
    result = {}
    for t in tags:
        key = t.get("Key", None)
        if key is None:
            continue
        values = t.get("Values", t.get("Value", None))
        if values is None:
            continue
        result[key] = values
    return result
